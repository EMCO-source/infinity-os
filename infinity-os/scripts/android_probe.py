#!/usr/bin/env python3
"""Non-destructive Android AVD launch and boot diagnostics for a single owner.

Run as an account with /dev/kvm access. Never wipes data or breaks AVD locks.
This is a diagnostic helper, not yet a browser-streaming Android engine.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time


def launch_command(sdk, avd):
    return [str(Path(sdk) / 'emulator/emulator'), '-avd', avd,
            '-no-window', '-no-audio', '-gpu', 'swiftshader_indirect',
            '-no-snapshot', '-show-kernel']


def launch(sdk, avd_home, avd, state):
    state = Path(state).resolve()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Unique log per attempt. The emulator itself enforces its existing AVD lock.
    log = state / ('android-boot-' + str(time.time_ns()) + '.log')
    env = dict(os.environ, ANDROID_HOME=str(Path(sdk).resolve()),
               ANDROID_AVD_HOME=str(Path(avd_home).resolve()))
    with log.open('xb') as output:
        process = subprocess.Popen(launch_command(sdk, avd), env=env,
                                   stdin=subprocess.DEVNULL, stdout=output,
                                   stderr=subprocess.STDOUT,
                                   start_new_session=True, close_fds=True)
    result = {'pid': process.pid, 'log': str(log), 'avd': avd,
              'status': 'launched_not_boot_verified'}
    (state / ('attempt-' + str(process.pid) + '.json')).write_text(json.dumps(result))
    return result


def classify_process(stat_text):
    # comm may contain spaces and parentheses. The final close paren ends comm.
    state = stat_text.rsplit(') ', 1)[1].split()[0]
    if state in ('T', 't'):
        return 'job_control_or_tracer_stopped'
    if state == 'Z':
        return 'exited_zombie'
    return 'active_not_boot_verified'


def inspect_process(pid):
    """Read process facts only. A stopped state does not prove its signal cause."""
    if not isinstance(pid, int) or pid <= 0:
        raise ValueError('PID must be a positive integer')
    directory = Path('/proc', str(pid))
    status = {}
    for line in (directory / 'status').read_text().splitlines():
        key, separator, value = line.partition(':')
        if separator:
            status[key] = value.strip()
    result = {'pid': pid, 'state': status.get('State'),
              'parent_pid': status.get('PPid'), 'threads': status.get('Threads'),
              'classification': classify_process((directory / 'stat').read_text()),
              'signal_cause': 'not_established'}
    for field, filename in [('wait_channel', 'wchan'), ('command_line', 'cmdline')]:
        try:
            result[field] = (directory / filename).read_bytes().replace(b'\0', b' ').decode(errors='replace').strip()
        except OSError:
            result[field] = 'unavailable'
    return result


def diagnose(sdk, serial, pid=None, log=None):
    result = {'serial': serial, 'boot_complete': False}
    if pid is not None:
        try:
            result['process_details'] = inspect_process(pid)
            result['process'] = result['process_details']['classification']
        except FileNotFoundError:
            result['process'] = 'absent'
    adb = str(Path(sdk) / 'platform-tools/adb')
    for name, args in [('boot_property', ['getprop', 'sys.boot_completed']),
                       ('package_service', ['service', 'check', 'package'])]:
        try:
            completed = subprocess.run([adb, '-s', serial, 'shell'] + args,
                                       text=True, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, timeout=15)
            result[name] = completed.stdout.strip()
            result[name + '_exit'] = completed.returncode
        except subprocess.TimeoutExpired:
            result[name + '_error'] = 'timeout'
    result['boot_complete'] = (result.get('boot_property_exit') == 0 and
                               result.get('boot_property') == '1')
    if log:
        # Local diagnostic only. Logs can contain external guest text.
        with Path(log).open('rb') as source:
            source.seek(0, 2)
            source.seek(max(0, source.tell() - 12000))
            result['log_tail'] = source.read().decode(errors='replace')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sdk', required=True)
    sub = p.add_subparsers(dest='action', required=True)
    start = sub.add_parser('launch')
    start.add_argument('--avd-home', required=True)
    start.add_argument('--avd', required=True)
    start.add_argument('--state', required=True)
    check = sub.add_parser('diagnose')
    check.add_argument('--serial', required=True)
    check.add_argument('--pid', type=int)
    check.add_argument('--log')
    args = p.parse_args()
    if args.action == 'launch':
        result = launch(args.sdk, args.avd_home, args.avd, args.state)
    else:
        result = diagnose(args.sdk, args.serial, args.pid, args.log)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
