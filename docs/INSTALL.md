# Installing INFINITY OS

## Host requirements

- Linux (x86_64 recommended) with hardware virtualization: `/dev/kvm` must exist
- QEMU/KVM and libvirt installed
- Python 3.10 or newer
- Android SDK command-line tools with an emulator image (for Android Cloud)

## Quick check

    ls /dev/kvm && egrep -c '(vmx|svm)' /proc/cpuinfo

If `/dev/kvm` is missing, enable VT-x/AMD-V in BIOS/UEFI. On cloud hosts, pick a KVM-capable instance.

## Setup

1. Clone this repository.
2. Create a Python virtual environment and install the panel requirements from `infinity-os/scripts/`.
3. Run the panel:

    python3 infinity-os/scripts/panel.py --root <vms-dir> --image <base-image.qcow2> --password-file <file> --adb <path-to-adb> --port 8080

4. Open `http://localhost:8080/login` and sign in with the owner credentials.

## Notes

- Never expose libvirt management interfaces directly to the internet.
- Put HTTPS in front of the panel for real deployments.
- All VM state lives under the `--root` directory; back it up to keep VMs across restarts.
