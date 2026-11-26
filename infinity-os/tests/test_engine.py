import importlib.util, sys, tempfile, unittest, json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from engine import Engine

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.base=Path(self.temp.name); self.image=self.base/'base.qcow2'; self.image.write_bytes(b'fixture')
        self.e=Engine(self.base/'vms',self.image)
    def tearDown(self): self.temp.cleanup()
    def create(self):
        with patch.object(self.e,'run',return_value=''):
            return self.e.create('guest1','ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFixture')
    def test_create_and_no_overwrite(self):
        m=self.create(); self.assertEqual(m['port'],22300)
        with self.assertRaises(FileExistsError): self.create()
        self.assertIn('ssh_authorized_keys',(self.e.directory('guest1')/'user-data').read_text())
    def test_invalid_name_and_key(self):
        for name in ['../bad',';bad','bad space']:
            with self.assertRaises(ValueError): self.e.directory(name)
        with self.assertRaises(ValueError): self.e.create('valid','private key')
    def test_snapshot_refuses_running(self):
        self.create()
        with patch.object(self.e,'active',return_value=True),patch.object(self.e,'run') as run:
            with self.assertRaises(ValueError): self.e.snapshot('guest1','before')
            run.assert_not_called()
    def test_restore_preserves_current(self):
        self.create()
        with patch.object(self.e,'active',return_value=False),patch.object(self.e,'run',return_value='') as run:
            self.e.snapshot('guest1','before',True)
            self.assertEqual(run.call_args_list[0].args[2],'-c')
            self.assertEqual(run.call_args_list[1].args[2],'-a')
    def test_live_pid_blocks_disk(self):
        import os
        self.create(); (self.e.directory('guest1')/'qemu.pid').write_text(str(os.getpid()))
        self.assertTrue(self.e.active('guest1'))

if __name__=='__main__': unittest.main()
