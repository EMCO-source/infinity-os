#!/usr/bin/env python3
"""Small safe libvirt helper. Cockpit Machines is the browser control panel."""
import argparse
import json
import os
import hashlib
import shutil
import uuid
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET


def name(value):
    if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]{0,47}', value):
        raise argparse.ArgumentTypeError('Use a letter, then letters, digits, _ or -, max 48')
    return value


def run(*args):
    return subprocess.check_output(list(args), text=True, env={**os.environ, 'LC_ALL': 'C'}).strip()


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def restore_clone(source, destination, new_name, virsh):
    # Restore only to a new name/new disk directory. No in-place overwrite path.
    if (source / 'INCOMPLETE').exists():
        raise ValueError('Backup is marked incomplete')
    manifest = json.loads((source / 'manifest.json').read_text())
    if not manifest:
        raise ValueError('Backup contains no disks')
    root = ET.fromstring((source / 'domain.xml').read_text())
    if root.find('./os/nvram') is not None:
        raise ValueError('NVRAM guests require a reviewed full-system restore, not this helper')
    existing = run(*virsh, 'list', '--all', '--name').splitlines()
    if new_name in existing:
        raise ValueError('Domain already exists; no changes made')
    for item in manifest:
        file = source / item['backup']
        if file.parent.resolve() != source.resolve() or not file.is_file():
            raise ValueError('Invalid backup path')
        if digest(file) != item['sha256']:
            raise ValueError('Backup checksum mismatch')
    destination = destination.resolve()
    destination.mkdir(mode=0o750, parents=True, exist_ok=False)
    root.find('name').text = new_name
    uid = root.find('uuid')
    if uid is not None:
        uid.text = str(uuid.uuid4())
    for iface in root.findall('./devices/interface'):
        mac = iface.find('mac')
        if mac is not None:
            iface.remove(mac)
    mapping = {x['original']: x['backup'] for x in manifest}
    for disk in root.findall('./devices/disk'):
        src = disk.find('source')
        if disk.get('device') == 'disk':
            old = src.get('file') if src is not None else None
            if old not in mapping:
                raise ValueError('Disk missing from manifest')
            output = destination / mapping[old]
            shutil.copy2(source / mapping[old], output)
            src.set('file', str(output.resolve()))
            driver = disk.find('driver')
            if driver is not None:
                driver.set('type', 'qcow2')
            for backing in disk.findall('backingStore'):
                disk.remove(backing)
        elif src is not None:
            disk.remove(src)  # Do not attach a stale installer or cloud-init secret.
    xml = destination / 'restored-domain.xml'
    ET.ElementTree(root).write(xml, encoding='unicode')
    print(run(*virsh, 'define', str(xml)))
    print('Defined stopped clone. Review disk permissions and network before starting.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--uri', default='qemu:///system')
    s = p.add_subparsers(dest='action', required=True)
    s.add_parser('list')
    q = s.add_parser('create')
    q.add_argument('name', type=name)
    q.add_argument('--root', required=True, type=Path)
    q.add_argument('--image', required=True, type=Path)
    q.add_argument('--public-key-file', required=True, type=Path)
    q.add_argument('--memory', type=int, default=1024)
    q.add_argument('--cpus', type=int, default=1)
    for action in ['start', 'shutdown', 'reboot', 'stats', 'snapshot', 'backup']:
        q = s.add_parser(action)
        q.add_argument('name', type=name)
        if action == 'snapshot':
            q.add_argument('snapshot', type=name)
        if action == 'backup':
            q.add_argument('destination', type=Path)
    q = s.add_parser('restore-clone')
    q.add_argument('source', type=Path)
    q.add_argument('destination', type=Path)
    q.add_argument('name', type=name)
    a = p.parse_args()
    v = ['virsh', '--connect', a.uri]
    if a.action == 'create':
        from engine import Engine
        print(json.dumps(Engine(a.root,a.image).create(a.name,a.public_key_file.read_text().strip(),a.memory,a.cpus)))
    elif a.action == 'restore-clone':
        restore_clone(a.source, a.destination, a.name, v)
    elif a.action == 'list':
        print(run(*v, 'list', '--all'))
    elif a.action in ['start', 'shutdown', 'reboot']:
        print(run(*v, a.action, a.name))
    elif a.action == 'stats':
        print(run(*v, 'domstats', a.name, '--state', '--cpu-total', '--balloon', '--block', '--interface'))
    elif a.action == 'snapshot':
        state = run(*v, 'domstate', a.name)
        if state != 'shut off':
            sys.exit('Stop the VM first for a consistent offline snapshot.')
        print(run(*v, 'snapshot-create-as', a.name, a.snapshot, '--atomic'))
    elif a.action == 'backup':
        if run(*v, 'domstate', a.name) != 'shut off':
            sys.exit('Stop the VM before backing up.')
        # Never overwrite an existing destination or touch an existing guest disk.
        a.destination = a.destination.resolve()
        a.destination.mkdir(mode=0o700, parents=True, exist_ok=False)
        (a.destination / 'INCOMPLETE').touch(mode=0o600)
        xml = run(*v, 'dumpxml', a.name)
        if ET.fromstring(xml).find('./os/nvram') is not None:
            sys.exit('NVRAM backup not supported; use a full-system backup.')
        (a.destination / 'domain.xml').write_text(xml)
        disks = []
        for i, disk in enumerate(ET.fromstring(xml).findall('./devices/disk')):
            if disk.get('device') != 'disk':
                continue
            src = disk.find('source')
            if src is None or 'file' not in src.attrib:
                sys.exit('Only file-backed disks supported; backup not complete.')
            target = a.destination / f'disk-{i}.qcow2'
            run('qemu-img', 'convert', '-O', 'qcow2', src.get('file'), str(target))
            disks.append({'original': src.get('file'), 'backup': target.name, 'sha256': digest(target)})
        (a.destination / 'manifest.json').write_text(json.dumps(disks, indent=2))
        (a.destination / 'INCOMPLETE').unlink()
        print(a.destination)

if __name__ == '__main__':
    main()
