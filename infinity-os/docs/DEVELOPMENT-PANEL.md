# Direct QEMU development panel

This fallback does not depend on the currently failing Cockpit bridge. It is not libvirt-backed yet and is not a production release. No live create/boot proof or visual review has been completed for this new panel.

Use only on a trusted single-owner host. It binds 127.0.0.1 and requires a unique Basic Auth password from a mode-0600 file. Put it behind an authenticated private HTTPS tunnel. Never expose plain HTTP to a network. Root serial autologin is intentional for this single-owner guest console; anyone with panel access has full guest root.

```
python3 scripts/panel.py --root /absolute/private/new-vms --image /absolute/verified/debian.qcow2 --password-file /absolute/private/password --port 8080
```

Create VPS makes a new disk overlay, cloud-init seed and metadata. It never starts or overwrites an existing guest. Start launches actual QEMU with mandatory KVM acceleration and virtio networking. Graceful stop sends ACPI powerdown, never force-kills. Open Console sends actual text over QEMU's serial socket. This minimal console is request-driven rather than a terminal emulator and still needs a live usability test.

Snapshots require a stopped guest and use normal qemu-img locking, no force-share. Restore first saves the current state to a new snapshot, then applies the chosen snapshot. Per-guest operation locks serialize panel start/snapshot/restore. Do not manage these guest disks through another tool while the panel is active. No delete endpoint exists.

`vm.py create` exposes the same direct engine for CLI use. Other vm.py commands still address libvirt, so they do not list/control these direct-engine guests. This separation is explicit pending tested libvirt integration.

Unit tests mock subprocesses. Ten tests pass, but this does not prove live QEMU operations, browser usability, iPhone Safari, or security under hostile multi-user access. Do not treat this code as a finished cloud service.
