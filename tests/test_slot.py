import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "slot.py"
spec = importlib.util.spec_from_file_location("sam_slot", MODULE_PATH)
slot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(slot)


def executable(path, code):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!{sys.executable}\n" + code)
    path.chmod(0o700)


class InventoryTests(unittest.TestCase):
    def test_ranges_and_serials(self):
        ports = []
        for number in range(1, 11):
            info = slot.slot_info(number)
            self.assertEqual(info["serial"], f"emulator-{5554 + (number - 1) * 2}")
            ports.extend([info["console"], info["console"] + 1, info["vnc"], info["web"]])
        self.assertEqual(len(set(ports)), 40)
        for n in (0, 11):
            with self.assertRaises(ValueError):
                slot.slot_info(n)


class OrchestrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        sdk = root / "sdk"
        image = sdk / "system-images/android-35/google_apis_playstore/x86_64"
        image.mkdir(parents=True)
        (image / "package.xml").touch()
        self.env = {**os.environ, "ANDROID_HOME": str(sdk), "SAM_AVD_ROOT": str(root / "avds"),
                    "LOG": str(root / "calls"), "READY": str(root / "ready"), "PATH": f"{root / 'bin'}:{os.environ['PATH']}",
                    "SAM_WEB_ROOT": str(root / "www")}
        Path(self.env["SAM_WEB_ROOT"]).mkdir()
        (Path(self.env["SAM_WEB_ROOT"]) / "vnc.html").touch()
        record = ('import sys,os,pathlib,json,time,socket\n'
                  'with open(os.environ["LOG"],"a") as f: print(json.dumps(sys.argv),file=f)\n')
        executable(sdk / "cmdline-tools/latest/bin/avdmanager", record + '''
name=sys.argv[sys.argv.index("-n")+1]
folder=pathlib.Path(os.environ["ANDROID_AVD_HOME"])
(folder/(name+".ini")).write_text("created")
data=folder/(name+".avd")
data.mkdir()
(data/"config.ini").write_text("config")
''')
        sleeper = record + 'time.sleep(60)\n'
        executable(sdk / "emulator/emulator", sleeper)
        executable(sdk / "platform-tools/adb", record)
        for name in ("Xvfb", "x11vnc"):
            executable(root / "bin" / name, sleeper)
        for name in ("xauth", "xdpyinfo"):
            executable(root / "bin" / name, record)
        executable(root / "bin/websockify", record + '''
with socket.socket() as sock:
    sock.bind(("127.0.0.1",0))
    sock.listen()
    pathlib.Path(os.environ["READY"]).write_text(str(sock.getsockname()[1]))
    while True:
        c,_=sock.accept()
        c.sendall(b"fixture")
        c.close()
''')

    def test_persistent_provisioning(self):
        for number in [1, 2, 1]:
            subprocess.run([sys.executable, MODULE_PATH, "prepare", str(number)], env=self.env, check=True)
        calls = Path(self.env["LOG"]).read_text().splitlines()
        self.assertEqual(len(calls), 2)
        self.assertIn("SamDevice01", calls[0])
        self.assertIn("SamDevice02", calls[1])
        self.assertTrue((Path(self.env["SAM_AVD_ROOT"]) / "SamDevice01/SamDevice01.avd/config.ini").is_file())

    def test_partial_provision_preserved(self):
        folder = Path(self.env["SAM_AVD_ROOT"]) / "SamDevice03"
        folder.mkdir(parents=True)
        descriptor = folder / "SamDevice03.ini"
        descriptor.write_text("keep")
        p = subprocess.run([sys.executable, MODULE_PATH, "prepare", "3"], env=self.env, capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("Incomplete AVD", p.stderr)
        self.assertEqual(descriptor.read_text(), "keep")

    def test_supervise_fixture_and_release(self):
        # Leave real KVM untouched. Fake tools still spawn and terminate as real processes.
        injected = '''
import os,pathlib,signal,sys
src=pathlib.Path(sys.argv.pop(1))
sys.path.insert(0,str(src.parent))
import slot
access=os.access
os.access=lambda path,mode: True if path=="/dev/kvm" else access(path,mode)
# A concurrent fixture or live deployment may own these ports. Our viewer fixture
# binds its own ephemeral socket and records where the test client should connect.
slot.free_ports=lambda info: None
original_info=slot.slot_info
slot.slot_info=lambda n: dict(original_info(n),display=f":{os.getpid()+1024}")
signal.signal(signal.SIGTERM,slot.stop_handler)
try:
    slot.main()
except slot.StopRequested:
    pass
'''
        number = 10
        ready = Path(self.env["READY"])
        port = None
        p = subprocess.Popen([sys.executable, "-c", injected, MODULE_PATH, "run", str(number)],
                             env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            for _ in range(100):
                if p.poll() is not None:
                    self.fail(p.stderr.read().decode())
                if not ready.exists() or not ready.read_text():
                    time.sleep(.05)
                    continue
                port = int(ready.read_text())
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.25) as con:
                        self.assertEqual(con.recv(16), b"fixture")
                    break
                except OSError:
                    time.sleep(.05)
            else:
                self.fail("Fixture did not become ready")
            duplicate = subprocess.run([sys.executable, MODULE_PATH, "prepare", str(number)], env=self.env, capture_output=True)
            self.assertIn(b"already running", duplicate.stderr)
        finally:
            p.terminate()
            _, stderr = p.communicate(timeout=20)
        self.assertEqual(p.returncode, 0, stderr)
        argv = [json.loads(line) for line in Path(self.env["LOG"]).read_text().splitlines()]
        emu = next(cmd for cmd in argv if cmd[0].endswith("/emulator"))
        self.assertEqual(emu[emu.index("-avd")+1], "SamDevice10")
        self.assertEqual(emu[emu.index("-port")+1], "5572")
        self.assertNotIn("-wipe-data", emu)
        viewer = next(cmd for cmd in argv if cmd[0].endswith("/websockify"))
        self.assertEqual(viewer[-2:], ["127.0.0.1:6110", "127.0.0.1:5910"])
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", port), timeout=.2)


if __name__ == "__main__":
    unittest.main()
