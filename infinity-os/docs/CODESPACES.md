# Temporary development only

Codespaces is not the INFINITY OS server. It has quotas, lifecycle limits and costs outside included usage. Stop the Codespace after each bounded test. Do not put production data in it.

On the tested US East 2-core and 4-core machines, /dev/kvm exists and KVM API version 12 / create-VM ioctl succeeded. Container users initially lack permission; changing device permissions for a test is not a production access policy. Use the kvm group on the final host.

The development container lacks a normal booted systemd environment and host kernel module tree. Installing libvirt/Cockpit packages does not by itself prove host service integration. Direct QEMU KVM tests and final host Cockpit lifecycle tests must be recorded separately.

Binder kernel support for Redroid was absent in the tested environment. An official Android emulator was successfully tested separately; that is not the Linux guest acceptance test.
