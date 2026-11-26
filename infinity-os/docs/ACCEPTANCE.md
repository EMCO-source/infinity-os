# Acceptance ledger, 23 November 2026

This is a work-in-progress release, NOT an accepted complete system.

| Requirement | Result | Evidence / remaining check |
| --- | --- | --- |
| Execution host probe | PASS in temporary dev environment | 2/4 cores expose KVM; API=12, create-VM ioctl succeeded; 4-core has 16 GB RAM, 32 GB nominal disk. Final host not supplied. |
| QEMU/libvirt installation | PASS in dev | apt exit 0; libvirt system list responds. Container has no active polkit/systemd integration. |
| Real Linux VM via KVM | PASS in dev | Official Debian 12 genericcloud qcow2 passes publisher SHA-512 checksum; QEMU -enable-kvm; monitor info kvm says enabled. 2 vCPU, 1024 MiB RAM, 6 GiB virtual disk. |
| Linux guest boot | PASS in dev | Debian 12 serial login and cloud-init completion, uptime ~130s. |
| Root command inside guest | PASS in dev | cloud-init executed id: uid=0(root), gid=0(root), then INFINITY_ROOT_OK. No root password was used. |
| Graceful shutdown/restart | PARTIAL | ACPI powerdown completed, second boot reached Debian login from same qcow2 without seed ISO. Not driven through Cockpit yet. |
| Guest file persistence | UNTESTED | First boot wrote /root/infinity-proof. Second boot succeeded, but contents were not read back yet. |
| Web desktop process | PARTIAL | Webtop Debian XFCE image pulled; Selkies/X11 and websocket service started. Container then stopped. |
| Browser desktop access | NOT PASSED | Private Codespaces forwarded port sent HTTP to HTTPS backend, returning nginx 400. Must configure HTTPS forwarding or private TLS proxy. Not a desktop success. |
| Secure application login | UNTESTED | Compose requires unique secret-file password, loopback-only. No production credentials provisioned. Test container was loopback + GitHub-private, without app credentials, and was stopped. |
| Cockpit browser panel | UNTESTED | Packages installed; manual cockpit-tls startup failed due to missing runtime wsinstance socket directory in dev container. Final systemd socket route untested. |
| Panel create/start/stop/console/stats | UNTESTED | Reuse genuine Cockpit Machines, no mock controls. Must test with real libvirt managed guest on host. |
| SSH into guest | UNTESTED | Root command was via cloud-init, not SSH. Key-only provisioning still needs test. |
| File upload/download/move/delete | UNTESTED | Desktop file manager/Cockpit Files require browser tests. Deletion must remain explicitly authorized. |
| Snapshot and real backup/restore | UNTESTED integration | Helper implements offline snapshot, qcow2 backup and non-overwriting clone restore with checksums. Five unit safety tests pass, real restore rehearsal still required. |
| Desktop restart persistence | UNTESTED | Persistent /config volume configured; must read/write/restart/re-read. |
| Android device access/input | UNTESTED | No actual phone session performed. Responsive upstream UI is not Android-device evidence. |
| WireGuard private access | UNTESTED | Template and install package included; needs reachable owned host and client public key. |
| Final owned host deployment | BLOCKED on host | No permanent host connection provided. Codespaces is stopped after testing, not final hosting. |

## Local automated checks

`python3 -m unittest discover -s tests -v`: 5 pass.

- Unsafe VM names rejected.
- Restore only defines a new stopped clone, new UUID/MAC, standalone qcow2.
- Corrupt backup refused before destination creation.
- Existing VM name refused.
- Incomplete backup refused.

Also passed: Python compilation, shell syntax and YAML/isolation assertions. Docker Compose runtime validation is not run locally because the local build environment has no Docker executable.

## Upstream image tested

`lscr.io/linuxserver/webtop:debian-xfce`, pulled digest:
`sha256:064f2836e82e3cd3478011b087846561a65299f1a3b3d021d70b93afa1c18525`

This digest only proves which image the dev pull returned. Full browser test is pending. Pin only after acceptance and retain an update process.

## Required next sequence

1. Resolve private HTTPS backend forwarding; verify desktop pixels and real terminal command.
2. Provision unique app credentials securely, verify login/logout and idle/session behavior.
3. Start libvirt/D-Bus/polkit/Cockpit correctly; define a KVM guest, operate it from the panel, inspect real CPU/RAM/disk values.
4. Read guest persistence marker after reboot; test SSH key-only access, snapshot and restore to new isolated clone.
5. Rehearse installation and backup/restore on the permanent Debian host, then connect Android through WireGuard and test touch/file transfer/external input.

Do not mark the project complete until all required acceptance tests are evidenced.

## Reproducible next test

`scripts/kvm-smoke.sh` automates a fresh official-image checksum, KVM query through QMP, key-only root SSH, marker creation/read-back, graceful powerdown, second boot and disk consistency check. It refuses existing destinations, retains test disks/keys and never force-stops or deletes. It is syntax-checked but NOT yet executed end-to-end. Supply a new absolute private directory and verified official image/checksum URLs. It consumes compute and downloads a cloud image, so use only on an authorized host with capacity. Port 22222 binds loopback only.
