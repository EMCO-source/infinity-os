#!/usr/bin/env python3
"""Create and serve a dedicated Android Emulator on a private, single-user host."""
import argparse
from contextlib import contextmanager, suppress
import fcntl
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

IMAGE = "system-images;android-35;google_apis_playstore;x86_64"


def slot_info(number):
    if not 1 <= number <= 10:
        raise ValueError("Device number must be in 1..10")
    console = 5554 + 2 * (number - 1)
    return {"slot": number, "name": f"SamDevice{number:02}", "console": console,
            "serial": f"emulator-{console}", "vnc": 5900 + number,
            "web": 6100 + number, "display": f":{110 + number}"}


def executable(path):
    if path and os.access(path, os.X_OK) and Path(path).is_file():
        return str(path)
    raise ValueError(f"Missing executable: {path}")


def helper(name):
    return executable(shutil.which(name) or name)


def sdk_paths(env):
    path = env.get("ANDROID_HOME") or env.get("ANDROID_SDK_ROOT")
    if not path:
        raise ValueError("Set ANDROID_HOME to the Android SDK directory")
    sdk = Path(path).resolve()
    if not (sdk / "system-images/android-35/google_apis_playstore/x86_64/package.xml").is_file():
        raise ValueError(f"Install {IMAGE} with sdkmanager first")
    return (executable(sdk / "cmdline-tools/latest/bin/avdmanager"),
            executable(sdk / "emulator/emulator"), executable(sdk / "platform-tools/adb"))


@contextmanager
def slot_lock(folder):
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (folder / ".session.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError(f"Device already running or provisioning: {folder.name}") from exc
        yield


def prepare(info, folder, env, avdmanager):
    name = info["name"]
    descriptor = folder / f"{name}.ini"
    data = folder / f"{name}.avd"
    if descriptor.is_file() and (data / "config.ini").is_file():
        return
    if descriptor.exists() or data.exists():
        raise ValueError(f"Incomplete AVD. Stop the device and inspect {folder}; its data was preserved.")
    subprocess.run([avdmanager, "create", "avd", "-n", name, "-k", IMAGE, "-d", "pixel_2"],
                   input="no\n", text=True, env=env, check=True, timeout=120)
    if not descriptor.is_file() or not (data / "config.ini").is_file():
        raise ValueError(f"avdmanager did not create a complete AVD in {folder}")


def free_ports(info):
    for port in [info["console"], info["console"] + 1, info["vnc"], info["web"]]:
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("127.0.0.1", port))


class StopRequested(Exception):
    pass


STOP_REQUESTED = False


def stop_handler(signum, frame):
    # Signal handlers may run between Popen() and registration of its PID.
    # Defer shutdown until every started child is owned by the supervisor.
    global STOP_REQUESTED
    STOP_REQUESTED = True


def check_shutdown():
    if STOP_REQUESTED:
        raise StopRequested()


def stop_children(children):
    # Stop the viewer first, then allow the emulator to flush data while Xvfb lives.
    for child in reversed(children):
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            child.wait()
            continue
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            child.poll()  # Reap a dead leader before checking for remaining descendants.
            try:
                os.killpg(child.pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            with suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGKILL)
        child.wait()


def serve(info, env, emulator, adb):
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise ValueError("This kit requires Linux x86_64")
    if not os.access("/dev/kvm", os.R_OK | os.W_OK):
        raise ValueError("Enable KVM and grant this user access to /dev/kvm (see HOST.md)")
    viewer_root = Path(env.get("SAM_WEB_ROOT", "/usr/share/novnc"))
    if not (viewer_root / "vnc.html").is_file():
        raise ValueError(f"Cannot find noVNC in {viewer_root}")
    xvfb, xauth, xdpyinfo, x11vnc, websockify = (
        helper(n) for n in ["Xvfb", "xauth", "xdpyinfo", "x11vnc", "websockify"])
    free_ports(info)
    display = info["display"]
    if Path("/tmp/.X11-unix", "X" + display[1:]).exists():
        raise ValueError(f"X display {display} is already in use")
    subprocess.run([adb, "start-server"], env=env, check=True, timeout=20)
    children = []
    with tempfile.TemporaryDirectory(prefix="sam-display-") as temp:
        auth = Path(temp) / "Xauthority"
        auth.touch(mode=0o600)
        env = {**env, "DISPLAY": display, "XAUTHORITY": str(auth), "QT_QPA_PLATFORM": "xcb"}
        subprocess.run([xauth, "-f", str(auth)], text=True, check=True, env=env,
                       input=f"add {display} . {secrets.token_hex(16)}\n")

        def spawn(*args):
            check_shutdown()
            child = subprocess.Popen(args, env=env, start_new_session=True)
            children.append(child)
            return child

        try:
            xserver = spawn(xvfb, display, "-screen", "0", "900x1600x24",
                            "-nolisten", "tcp", "-auth", str(auth))
            for _ in range(100):
                check_shutdown()
                if xserver.poll() is not None:
                    raise ValueError("Xvfb failed to start")
                if subprocess.run([xdpyinfo], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  env=env, timeout=2).returncode == 0:
                    break
                time.sleep(0.1)
            else:
                raise ValueError("Timed out waiting for Xvfb")
            spawn(emulator, "-avd", info["name"], "-port", str(info["console"]),
                  "-accel", "on", "-gpu", "software", "-cores", "2", "-memory", "3072",
                  "-camera-back", "none", "-camera-front", "none", "-no-audio", "-no-boot-anim",
                  "-no-snapshot", "-no-metrics")
            spawn(x11vnc, "-display", display, "-auth", str(auth), "-localhost", "-no6",
                  "-rfbport", str(info["vnc"]), "-nopw", "-forever", "-shared", "-noxdamage")
            spawn(websockify, "--web", str(viewer_root), f"127.0.0.1:{info['web']}",
                  f"127.0.0.1:{info['vnc']}")
            while True:
                check_shutdown()
                for child in children:
                    if child.poll() is not None:
                        raise ValueError(f"{Path(child.args[0]).name} stopped (code {child.returncode})")
                time.sleep(0.5)
        finally:
            stop_children(children)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "run", "info"])
    parser.add_argument("slot", type=int, choices=range(1, 11))
    args = parser.parse_args()
    info = slot_info(args.slot)
    if args.action == "info":
        print(json.dumps(info))
        return
    os.umask(0o077)
    env = dict(os.environ)
    state = Path(env.get("XDG_STATE_HOME") or (Path.home() / ".local/state"))
    root = Path(env.get("SAM_AVD_ROOT") or (state / "sam-cloudespace/avds")).resolve()
    folder = root / info["name"]
    env["ANDROID_AVD_HOME"] = str(folder)
    manager, emulator, adb = sdk_paths(env)
    with slot_lock(folder):
        prepare(info, folder, env, manager)
        check_shutdown()
        if args.action == "run":
            serve(info, env, emulator, adb)


if __name__ == "__main__":
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, stop_handler)
    try:
        main()
    except StopRequested:
        pass
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        sys.exit(str(exc))
