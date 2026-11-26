# Backups, restore and migration

## VM backup

1. Ask the owner before shutdown if it interrupts work. Gracefully shut down the guest and verify `virsh domstate NAME` says `shut off`.
2. Run `sudo python3 scripts/vm.py backup NAME /safe/new-backup-directory`.
3. This creates standalone qcow2 disks, domain XML and a SHA-256 manifest. It refuses an existing backup directory and supports file-backed disks only. NVRAM/TPM state, snapshots, external devices, secrets and pool/network definitions are not included. Use a full host backup for those guests.
4. Copy the result to a separate owned disk/machine and encrypt it at rest. A backup on the same disk does not cover disk loss. Verify checksums after copying.

An offline VM snapshot is available with `vm.py snapshot NAME SNAPSHOT`. It can consume significant disk and is not a backup. Snapshot removal/rollback is deliberately not automated here.

## Restore without overwriting

`sudo python3 scripts/vm.py restore-clone /backup /new/empty/disk-directory NEWNAME`

This checks backup hashes, rejects an existing domain name/destination, generates a new UUID/MAC and defines a stopped clone. The source VM is untouched. Review storage owner/permissions, networking and firewall before starting it. The new disk directory must be traversable/readable by libvirt's QEMU account; do not use world-writable permissions. The clone receives new NIC MAC addresses and no installer/CD-ROM source. Cloud-init disks and secrets must be provisioned separately. A clone can still conflict at the application or IP-address level. Keep it isolated until configuration is reviewed. No live migration or automatic in-place restore is implemented.

Restore into the original VM would overwrite data and needs separate explicit approval. Keep the original stopped and intact until the clone is verified. Never delete the original to make space without asking.

## Desktop data

The persistent Compose volume is named by the Compose project and holds `/config`. Stop the desktop for a consistent archive. Record the exact project/volume name with `docker volume inspect`. Back up the volume's data, Compose configuration, deployed image digest and separately encrypted credentials. Do not archive a running container's writable layer as a substitute. User-installed system packages outside `/config` need a reproducible custom image or boot script.

Restore first to a new volume/new Compose project with loopback-only ports. Verify files, permissions, browser profile and settings. Change the production mapping only after approval. Never run `docker compose down -v` as routine maintenance.

## Host migration

1. Inventory: CPU architecture/virtualization flags, kernel, libvirt/QEMU versions, network definitions, disks, certificates, accounts, UID/GID and WireGuard public peers. Keep private keys/secrets in encrypted storage, not Git.
2. Install the same or compatible versions on the new owned host. Probe KVM. Do not assume nested virtualization exists on a rented VPS.
3. Copy offline backups and verify hashes. Restore stopped VM clones and the desktop to new storage. Set permissions without broad chmod.
4. Test isolated boot, root/sudo access, application data and restart persistence. For hardware-tied licenses or devices, follow vendor migration rules.
5. With approval, stop original services, take final consistent backups, move private VPN/DNS routing, then test from the owner's phone.
6. Retain the old machine and backups until the owner confirms the new host. Rollback routing to the old host only while avoiding two simultaneous writers to the same data.

Backups and migration must be rehearsed on the actual target before calling the deployment production-ready. The checklist is not evidence that migration already passed.
