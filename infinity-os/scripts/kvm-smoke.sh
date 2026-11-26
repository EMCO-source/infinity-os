#!/usr/bin/env bash
# Real, bounded KVM smoke test. Creates NEW disposable test data, never deletes it.
# Run only on an owned/authorized x86_64 host. Uses ~1GB RAM, 2 vCPU and disk space.
# Official image URL is supplied explicitly so the operator can choose a pinned release.
set -euo pipefail
[[ $# == 3 ]] || { echo 'Usage: kvm-smoke.sh NEW_ABSOLUTE_DIR IMAGE_URL SHA512SUMS_URL'; exit 2; }
root=$1
[[ $root == /* && ! -e $root ]] || { echo 'Destination must be a new absolute directory'; exit 1; }
for tool in qemu-system-x86_64 qemu-img cloud-localds ssh ssh-keygen curl python3 sha512sum; do command -v "$tool" >/dev/null; done
[[ -r /dev/kvm && -w /dev/kvm ]] || { echo 'Need KVM group access, no permissions changed'; exit 1; }
mkdir -m 700 "$root"
cd "$root"
# Caller must pass a direct official .qcow2 URL and matching checksum list.
file=${2##*/}
[[ $file =~ ^[a-zA-Z0-9._-]+\.qcow2$ ]] || { echo 'Invalid image filename'; exit 1; }
curl --fail --location --proto '=https' --tlsv1.2 "$2" -o "$file"
curl --fail --location --proto '=https' --tlsv1.2 "$3" -o SHA512SUMS
awk -v f="$file" '$2 == f || $2 == "*"f' SHA512SUMS > selected.sha512
[[ $(wc -l < selected.sha512) == 1 ]] || { echo 'Need exactly one matching checksum'; exit 1; }
sha512sum -c selected.sha512
ssh-keygen -q -t ed25519 -N '' -f guest-key
chmod 600 guest-key
python3 - <<'PY'
from pathlib import Path
import json
key=Path('guest-key.pub').read_text().strip()
Path('user-data').write_text('#cloud-config\n'+json.dumps({
    'disable_root':False, 'ssh_pwauth':False,
    'users':[{'name':'root','lock_passwd':True,'ssh_authorized_keys':[key]}],
    'runcmd':[['sh','-c','echo infinity-persistent-proof > /root/infinity-proof']]
}))
Path('meta-data').write_text('instance-id: infinity-kvm-smoke\nlocal-hostname: infinity-smoke\n')
PY
cloud-localds seed.iso user-data meta-data
qemu-img create -f qcow2 -F qcow2 -b "$root/$file" guest.qcow2 6G
# Fail rather than selecting a different port silently.
python3 - <<'PY'
import socket
s=socket.socket();s.bind(('127.0.0.1',22222));s.close()
PY
qmp() {
  python3 - "$root/qmp.sock" "$1" <<'PY'
import json,socket,sys
s=socket.socket(socket.AF_UNIX);s.settimeout(10);s.connect(sys.argv[1]);f=s.makefile('rwb')
def command(x):
    f.write((json.dumps({'execute':x})+'\n').encode());f.flush()
    while True:
        r=json.loads(f.readline())
        if 'return' in r: return r['return']
        if 'error' in r: raise RuntimeError(r['error'])
json.loads(f.readline());command('qmp_capabilities');print(json.dumps(command(sys.argv[2])))
PY
}
boot() {
  qemu-system-x86_64 -enable-kvm -cpu host -m 1024 -smp 2 \
    -drive file="$root/guest.qcow2",if=virtio -drive file="$root/seed.iso",media=cdrom \
    -nic user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:22222-:22 -display none \
    -serial file:"$root/serial-$1.log" -qmp unix:"$root/qmp.sock",server,nowait \
    -daemonize -pidfile "$root/qemu.pid"
  qmp query-kvm | tee "kvm-$1.json"
  grep -q '"enabled": true' "kvm-$1.json"
}
guest() {
  ssh -i "$root/guest-key" -p 22222 -o BatchMode=yes -o ConnectTimeout=3 \
    -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$root/known_hosts" root@127.0.0.1 "$@"
}
await_guest() {
  for ((n=0;n<90;n++)); do
    if guest 'id; test -f /root/infinity-proof && cat /root/infinity-proof'; then return; fi
    sleep 3
  done
  echo 'Guest SSH timed out, inspect serial log. VM remains intact.'; exit 1
}
shutdown() {
  pid=$(cat "$root/qemu.pid")
  qmp system_powerdown
  for ((n=0;n<60;n++)); do [[ -z $pid || ! -e /proc/$pid || $(ps -p "$pid" -o stat=) == Z* ]] && return; sleep 1; done
  echo 'Graceful shutdown timeout. No force stop or deletion performed.'; exit 1
}
boot 1
await_guest | tee root-first-boot.txt
shutdown
boot 2
await_guest | tee root-after-restart.txt
shutdown
qemu-img check guest.qcow2 | tee disk-check.txt
printf 'PASS: real KVM, key-only root SSH, graceful shutdown, restart and file read-back. Evidence: %s\n' "$root"
printf 'Test disk and SSH key are retained privately. No data deleted.\n'
