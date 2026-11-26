#!/usr/bin/env bash
set -euo pipefail
printf 'INFINITY OS host probe\n'
uname -a
printf '\nCPU count: '; nproc
free -h
df -h .
printf '\nVirtualization flags: '; grep -m1 -oE 'vmx|svm' /proc/cpuinfo || true
ls -l /dev/kvm
python3 - <<'PY'
import os, fcntl
f = os.open('/dev/kvm', os.O_RDWR)
print('KVM API:', fcntl.ioctl(f, 0xAE00, 0))
v = fcntl.ioctl(f, 0xAE01, 0)
print('KVM_CREATE_VM: success')
os.close(v)
os.close(f)
PY
command -v qemu-system-x86_64 || true
command -v virsh || true
command -v docker || true
