#!/usr/bin/env bash
# Ubuntu 24.04 / Debian 12+ host. Does not modify SSH or firewall policy.
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run with sudo'; exit 1; }
. /etc/os-release
case "$ID" in ubuntu|debian) ;; *) echo 'Supported: Debian/Ubuntu only'; exit 1;; esac
for path in /etc/cockpit/cockpit.conf /etc/systemd/system/cockpit.socket.d/listen.conf; do
  [[ ! -e "$path" ]] || { echo "Existing configuration: $path. Review and merge manually; nothing changed."; exit 1; }
done
apt-get update
apt-get install -y qemu-system-x86 qemu-utils libvirt-daemon-system libvirt-clients virtinst \
  wireguard-tools cloud-image-utils openssh-client cockpit cockpit-machines cockpit-networkmanager curl ca-certificates
if apt-cache show cockpit-files >/dev/null 2>&1; then apt-get install -y cockpit-files; fi
install -d -m 0755 /etc/cockpit /etc/systemd/system/cockpit.socket.d
cat >/etc/cockpit/cockpit.conf <<'CONF'
[WebService]
LoginTitle = INFINITY OS
AllowUnencrypted = false
[Session]
IdleTimeout = 15
CONF
cat >/etc/systemd/system/cockpit.socket.d/listen.conf <<'CONF'
[Socket]
ListenStream=
ListenStream=127.0.0.1:9090
CONF
if [[ -d /run/systemd/system ]]; then
  systemctl daemon-reload
  systemctl enable --now libvirtd cockpit.socket
  virsh -c qemu:///system net-info default >/dev/null 2>&1 && \
    { virsh -c qemu:///system net-start default || true; virsh -c qemu:///system net-autostart default; }
else
  echo 'No systemd detected. Packages installed only; see docs/CODESPACES.md.'
fi
printf '\nNo login created and no ports exposed. Follow README for account and HTTPS setup.\n'
