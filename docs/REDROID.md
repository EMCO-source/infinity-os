# Redroid adaptation plan for AndroidServer

Goal: run the AndroidServer slots as Redroid containers (Android-in-Docker) on an
Oracle Cloud Ampere A1 free-tier host, instead of KVM-based AVD emulators. No nested
virtualization is required, which is why this works on hosts where the current
AVD-based stack cannot run.

Target host: Oracle Cloud `VM.Standard.A1.Flex` (ARM64), Always Free allotment of
2 OCPU / 12 GB RAM, Ubuntu 24.04 ARM64 image.

---

## 1. Host setup (Ubuntu 24.04 ARM64 on Oracle A1)

Run these checks and steps in order.

### 1.1 Page size gate (do this first)

```bash
getconf PAGESIZE   # must print 4096
```

Redroid requires 4 KB memory pages. **Ubuntu ARM64 uses 4 KB pages; Oracle Linux
ARM64 uses 64 KB pages and Redroid fails there** with `mprotect` errors that look
like a Redroid bug but are not. Always pick the Ubuntu 24.04 ARM64 image in the
OCI console, never Oracle Linux.

### 1.2 Kernel modules: binder (required), ashmem (skip)

```bash
sudo apt update
sudo apt install -y linux-modules-extra-$(uname -r)
sudo modprobe binder_linux devices="binder,hwbinder,vndbinder"

# Kernel 6.x: binder lives in binderfs and must be mounted explicitly.
# Most old guides miss this step and end up with no /dev/binder* nodes.
sudo mkdir -p /dev/binderfs
sudo mount -t binder binder /dev/binderfs
ls /dev/binderfs    # expect: binder  binder-control  hwbinder  vndbinder
```

`ashmem_linux` is obsolete on kernel 5.18+ with Android 12+ images (they use
`memfd` instead). Do not chase it.

Persist across reboots:

```bash
echo binder_linux | sudo tee /etc/modules-load.d/redroid.conf
echo 'options binder_linux devices=binder,hwbinder,vndbinder' | sudo tee /etc/modprobe.d/redroid.conf
echo 'binder /dev/binderfs binder defaults 0 0' | sudo tee -a /etc/fstab
```

### 1.3 Docker

```bash
curl -fsSL https://get.docker.com | sh
```

### 1.4 Security (important)

ADB on port 5555 has **no authentication**. Never publish it on the public IP.
Bind container ADB ports to localhost only, and reach the host over SSH (or
Tailscale/WireGuard). This matches how gateway.py already talks to devices
(`adb -s <serial>`), so local binding is sufficient.

In the OCI security list, open only the Caddy/HTTPS port publicly.

---

## 2. Image choice

| Need | Image | Notes |
| --- | --- | --- |
| Default (no Play Store) | `redroid/redroid:13.0.0_64only-latest` | `_64only` tag is **mandatory on Ampere**; standard images ship 32-bit components that kernel-panic on A1. Android 12 and 14 `_64only` tags also exist. |
| Play Store needed | `hrtrex/redroid:12.0.0_arm64-latest` | Community Redroid 12 build with GApps, explicitly verified on Oracle Cloud free-tier ARM64. Uncertified: Play Integrity and some apps will still refuse to run. Build-your-own with `remote-android/redroid-doc` is the cleaner long-term option. |

Architecture note: everything on the A1 is arm64. Apps that only ship x86 builds
will not run. Check the APKs the server is expected to launch before committing.

---

## 3. Code changes

### 3.1 slot.py: replace AVD provisioning and launch with Docker

Today `prepare()` creates an AVD with `avdmanager` and the `run` path boots the
`emulator` binary. Replace with one container per slot:

```bash
docker run -d --privileged --name sam-redroid-<N> \
  -v "$HOME/sam-redroid/slot<N>:/data" \
  -p 127.0.0.1:<ADB_PORT>:5555 \
  redroid/redroid:13.0.0_64only-latest \
  androidboot.sam_slot=<N>
adb connect 127.0.0.1:<ADB_PORT>
```

- Serial becomes `127.0.0.1:<ADB_PORT>` instead of `emulator-<5554+2(N-1)>`.
  Suggested mapping: `ADB_PORT = 6000 + N`. adb works identically over TCP, so
  every `adb -s <serial> ...` call in gateway.py keeps working once `slot_info`
  returns the TCP serial.
- Data persists in the host volume, matching the current "incomplete AVD data is
  preserved" philosophy. `docker stop -t 20 sam-redroid-<N>` gives the guest time
  to flush, equivalent to the current graceful shutdown.
- The `console`, `vnc`, and `display` fields of `slot_info` go away; keep `web`
  (6100+N) for the new viewer (see 3.3).
- Boot readiness is the same poll already in use:
  `adb -s <serial> shell getprop sys.boot_completed` until it returns `1`.

### 3.2 gateway.py: replace the `adb emu avd name` identity check

`open_guest()` currently verifies the device with:

```python
identity_ok, emulator_name = adb(slot, "emu", "avd", "name")
```

`adb emu` talks to the emulator console, which **does not exist on Redroid**; this
check will always fail there. Replace it with a boot property check against the
prop passed at container start:

```python
identity_ok, slot_prop = adb(slot, "shell", "getprop", "ro.boot.sam_slot")
# expect slot_prop.strip() == str(slot)
```

(`androidboot.sam_slot=N` on the docker command line surfaces inside Android as
`ro.boot.sam_slot`.)

### 3.3 Viewer: swap Xvfb + VNC for ws-scrcpy

Redroid is headless; there is no X display to capture. Use
[ws-scrcpy](https://github.com/NetrisTV/ws-scrcpy) (or a maintained fork) per
slot, pointed at the slot's ADB serial, and keep the existing `web` port
(6100+N) and Caddy routing so the gateway's `viewer()` URL shape is preserved.
`redroid.gpu.mode=guest` (SwiftShader) is the GPU mode on the A1; there is no
hardware GL.

### 3.4 Play Store deep links

The `store` action in gateway.py opens `market://details?id=...` against
`com.android.vending`. Stock Redroid has no Play Store, so this path only works
with the GApps build (section 2). Add a graceful fallback: if
`com.android.vending` is absent, return the same "alternatives" response the
missing-app branch already produces.

---

## 4. Capacity and pool sizing

Measured cost of one idle Android 13 Redroid container: ~600 MB RAM, near-zero
CPU. On the free allotment:

- RAM (12 GB total, minus host): fits 10+ containers on paper.
- CPU (2 OCPU Ampere): the real ceiling. Plan for **3-5 light interactive
  instances**; heavy concurrent use of more slots will stall.

Recommended default pool: 4 slots. Keep the 1..10 slot numbering so the same
code scales up unchanged on a future paid host.

---

## 5. Oracle account prerequisites (owner steps, not automated)

- Signup at oracle.com/cloud/free requires a **non-prepaid** credit/debit card
  whose billing address matches (verification only, no charge). Egyptian prepaid
  and virtual cards are routinely rejected.
- Always Free compute lives in the **home region, chosen permanently at signup**.
  A1 capacity in popular regions is frequently "out of host capacity"; pick the
  home region carefully and retry instance creation across availability domains.
- Idle reclamation: instances under 20% CPU/network/memory for 7 days can be
  reclaimed. Running containers keeps usage above the threshold.

---

## 6. CI note

The GitHub Actions workflow (`android-emulator-test`) runs on x86_64 hosted
runners and should stay AVD-based. Binder kernel modules cannot be assumed on
hosted runners, so do not try to run Redroid in CI; test the Redroid path on the
Oracle host itself.

---

## 7. References

- Oracle Cloud official guide: "Android as a Service with ARM on OCI"
  (https://blogs.oracle.com/cloud-infrastructure/post/android-as-a-service-with-arm-on-oci).
  Oracle's own walkthrough of running Android containers on Ampere A1; matches the
  host setup in section 1 (Ubuntu ARM64 image, binder modules).
- Kasm's Redroid integration: `kasmweb/redroid` on Docker Hub
  (https://hub.docker.com/r/kasmweb/redroid, verified publisher; source:
  kasmtech/workspaces-images, branch `dockerfile-kasm-redroid`). A Redroid image
  pre-wired with KasmVNC browser streaming. Considered as an alternative viewer to
  ws-scrcpy (section 3.3): it would replace both the X-less scrcpy stream and part
  of the viewer plumbing with Kasm's web-native VNC, at the cost of pulling the
  Kasm base image and adopting its session model instead of the gateway's
  per-slot `viewer()` routing. ws-scrcpy stays the default because it maps
  directly onto ADB serials and keeps the current gateway contract, but Kasm is a
  viable fallback if scrcpy streaming proves unreliable on the A1.
