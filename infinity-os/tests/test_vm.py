import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import argparse

spec = importlib.util.spec_from_file_location('vm', Path(__file__).parents[1] / 'scripts/vm.py')
vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vm)

class SafetyTests(unittest.TestCase):
    def test_names(self):
        for value in [';reboot', '../disk', '-flag', 'a b', 'a'*49]:
            with self.assertRaises(argparse.ArgumentTypeError): vm.name(value)
        self.assertEqual(vm.name('guest-1'), 'guest-1')

    def backup(self, base):
        source = base / 'backup'; source.mkdir()
        (source / 'disk-0.qcow2').write_bytes(b'test disk')
        (source / 'domain.xml').write_text('<domain><name>old</name><uuid>old</uuid><os/><devices><disk device="disk"><driver type="raw"/><source file="/old/disk"/></disk><interface><mac address="old"/></interface></devices></domain>')
        manifest = [{'original':'/old/disk','backup':'disk-0.qcow2','sha256':vm.digest(source/'disk-0.qcow2')}]
        (source/'manifest.json').write_text(json.dumps(manifest))
        return source

    def test_restore_new_clone(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d); source=self.backup(base); dest=base/'restored'
            with patch.object(vm, 'run', side_effect=['old','defined']) as run:
                vm.restore_clone(source,dest,'new',['virsh'])
                self.assertEqual(run.call_args_list[-1].args[:2], ('virsh','define'))
            xml=(dest/'restored-domain.xml').read_text()
            self.assertIn('<name>new</name>',xml)
            self.assertNotIn('address="old"',xml)
            self.assertIn('type="qcow2"',xml)
            self.assertTrue((source/'disk-0.qcow2').exists())

    def test_checksum_fails_before_write(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d); source=self.backup(base)
            (source/'disk-0.qcow2').write_bytes(b'corrupt')
            with patch.object(vm,'run',return_value=''), self.assertRaises(ValueError):
                vm.restore_clone(source,base/'dest','new',['virsh'])
            self.assertFalse((base/'dest').exists())

    def test_incomplete_backup_refused(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d); source=self.backup(base)
            (source/'INCOMPLETE').touch()
            with self.assertRaises(ValueError):
                vm.restore_clone(source,base/'dest','new',['virsh'])
            self.assertFalse((base/'dest').exists())

    def test_existing_domain_refused(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d); source=self.backup(base)
            with patch.object(vm,'run',return_value='new'), self.assertRaises(ValueError):
                vm.restore_clone(source,base/'dest','new',['virsh'])

if __name__ == '__main__': unittest.main()
