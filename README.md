# INFINITY OS

Self-hosted Linux web desktop and KVM/QEMU VPS management from the browser. Mobile-first.

Open source (MIT), self-hostable, no forced paid services.

## Features (built and tested)

- Browser control panel with secure owner/client login
- Real KVM/QEMU virtual machines: create, start, stop, restart, persistent disks
- Android Cloud: run a real KVM-accelerated Android emulator and control it live from the browser with touch input
- Mobile-first web UI, tested on iOS Safari and Android Chrome
- Adaptive screen streaming tuned for slow mobile connections

## Stack

- QEMU/KVM and libvirt for virtualization
- Python panel server plus HTML/JS web UI
- Docker Compose for deployable components

## Requirements

- Linux host with `/dev/kvm` (hardware virtualization enabled)
- See [docs/INSTALL.md](docs/INSTALL.md)

## License

MIT - see [LICENSE](LICENSE)
