# INFINITY OS, phase 1

Self-hosted Linux desktop and real KVM virtualization. This is an integration of open-source tools, not a new Linux distribution. No subscription or cloud API is required. Codespaces is used only for temporary tests, never the final server.

## Components

- Debian/Ubuntu host: QEMU/KVM, libvirt and Cockpit Machines.
- Cockpit: real host terminal, users, monitoring, networking and VM management using system login/PAM. Cockpit Files where packaged.
- LinuxServer Webtop Debian XFCE: real desktop, browser, file manager and terminal, with a persistent Docker volume.
- WireGuard: private access. Administrative services bind to loopback until private ingress is configured.
- Our scripts and configuration: MIT. Each dependency keeps its own license, see THIRD_PARTY.md.

## Host requirements

Owned x86_64 Linux machine, virtualization enabled in firmware, writable /dev/kvm; recommended 4+ cores, 8+ GB RAM, SSD with 40+ GB free. Each VM needs its own RAM/disk allocation. Host must remain powered and online. Electricity, internet, hardware, backups and any chosen domain/server are not free just because the software is.

A physical Android device, owned permanent server and public ingress have not been supplied. Do not treat a temporary test URL as permanent hosting.

## Install

Review scripts before running. Start on a clean Debian 12+/Ubuntu 24.04 host. Existing systems need a backup first. No script deletes guest disks.

```sh
sudo bash scripts/probe.sh
sudo bash scripts/setup-host.sh
```

Create a non-root administrator using `sudo adduser infinity` on the host, choosing a unique password locally. Give it sudo/libvirt membership only if it is intended to administer the entire host, using `sudo usermod -aG sudo,libvirt infinity` after that decision. Membership in libvirt is powerful and must not be given to untrusted tenants. Log out and back in for group membership to apply. No default passwords are shipped. Cockpit uses the host's existing accounts and PAM sessions; root login is not required.

Access the panel over an SSH tunnel first:

```sh
ssh -L 9090:127.0.0.1:9090 -L 3001:127.0.0.1:3001 your-host
```

Open https://localhost:9090. Cockpit initially uses its own certificate; deploy a trusted certificate before routine remote use. Do not disable certificate checks in production.

## Desktop

Install Docker Engine and Compose from your distribution or Docker's official repository. Set a unique desktop password through a protected file, not command-line arguments, Git or chat. The shipped Compose requires the file and username, and will not start with a default password.

```sh
export INFINITY_USER=infinity
export INFINITY_PASSWORD_FILE=/absolute/private/path/desktop-password
# The file must exist, mode 600, and contain the unique password.
docker compose config --quiet
docker compose up -d
```

Open https://localhost:3001 through the tunnel. Desktop auth is a second, separate login. The container is not privileged, has no Docker socket and no host root mount. Its /config volume keeps user files/settings. A browser desktop is still a powerful remote session; use only over a VPN/private tunnel. Multi-user isolated desktops are not implemented by this single-user Compose.

## Virtual machines

Open Cockpit > Virtual machines > Create VM. Choose an official Linux cloud image or installation ISO. Set vCPU/RAM/disk, use NAT on libvirt's default network, and a new persistent qcow2 disk. Add a per-VM SSH public key, not a shared password. Cloud images may lock direct root SSH by default; use the guest's sudo account for root, or explicitly provision key-only root access for a trusted guest.

Cockpit Machines exposes real VM lifecycle and console controls, not mock data. Availability of particular features depends on the installed version. Offline backups and snapshots are also available through `scripts/vm.py`. Restore overwrites data and is deliberately not automatic; see docs/BACKUP.md. Never approve restore/deletion without the owner's explicit choice.

## Private remote access

See config/wg0.conf.example. Generate keys on their respective devices with WireGuard's native tools, keep private keys off Git, and add only public peer keys to the server. A reachable UDP endpoint or router forwarding may be needed. Carrier NAT can prevent direct inbound access. No third-party relay is bundled or promised.

Keep libvirt's management socket local. Do not enable unauthenticated TCP libvirt, Docker TCP, public ADB, or public Webtop. Bind Cockpit to the VPN address only after WireGuard works, or retain SSH tunneling. HTTPS still applies inside the VPN.

## Verification

See docs/ACCEPTANCE.md for observed versus untested results. Run `python3 -m unittest discover -s tests -v` for the local static/unit checks. They are not a substitute for a real VM boot or browser test.
