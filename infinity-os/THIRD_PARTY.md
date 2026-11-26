# Third-party software

MIT applies only to original files in this directory. No upstream program is relicensed. The deployment installs distribution packages and pulls an upstream image; this repository does not bundle those binaries. Keep source offers/notices when redistributing images. Read exact installed package copyright files under /usr/share/doc/PACKAGE/copyright and image source before redistribution.

Upstream source/licensing references:

- Cockpit: https://github.com/cockpit-project/cockpit (LGPL-2.1-or-later)
- Cockpit Machines: https://github.com/cockpit-project/cockpit-machines (LGPL-2.1-or-later)
- Cockpit Files: https://github.com/cockpit-project/cockpit-files
- QEMU: https://www.qemu.org/docs/master/about/license.html (GPLv2 and component-specific licenses)
- libvirt: https://libvirt.org/ (LGPL)
- LinuxServer Webtop: https://github.com/linuxserver/docker-webtop (GPL-3.0 repository; image contains separately licensed packages)
- WireGuard: https://www.wireguard.com/repositories/ (component-specific GPL/MIT licenses)
- Debian cloud images: https://cloud.debian.org/images/cloud/ (Debian packages retain their own licenses)

A mutable image tag is not a reproducible release. Before production, record the tested image digest and pin `image:` to it. Keep the distribution security-update plan separate from feature upgrades. The initial release does not supply a verified SBOM for the complete pulled image.
