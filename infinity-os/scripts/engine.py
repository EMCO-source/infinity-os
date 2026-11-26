#!/usr/bin/env python3
"""Single-owner QEMU engine. Loopback panel only; libvirt integration is separate."""
import fcntl, json, os, re, socket, subprocess, time
from pathlib import Path

class Engine:
    def __init__(self, root, image):
        self.root=Path(root).resolve(); self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.image=Path(image).resolve()
    def run(self,*args):
        return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()
    def directory(self,name):
        if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]{0,31}', name): raise ValueError('Invalid name')
        return self.root/name
    def metadata(self,name): return json.loads((self.directory(name)/'vm.json').read_text())
    def qmp(self,name,command):
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(5); s.connect(str(self.directory(name)/'qmp.sock')); f=s.makefile('rwb')
            json.loads(f.readline())
            result=None
            for cmd in ['qmp_capabilities', command]:
                f.write((json.dumps({'execute':cmd})+'\n').encode()); f.flush()
                while True:
                    r=json.loads(f.readline())
                    if 'error' in r: raise ValueError(str(r['error']))
                    if 'return' in r: result=r['return']; break
            return result
    def active(self,name):
        # Fail closed when process state is ambiguous. An existing live PID blocks disk writes.
        p=self.directory(name)/'qemu.pid'
        if not p.exists(): return False
        pid=p.read_text().strip()
        if not pid.isdigit(): raise ValueError('Invalid PID state')
        try:
            state=Path('/proc',pid,'stat').read_text().split(') ',1)[1][0]
            return state!='Z'
        except FileNotFoundError: return False
    def locked(self,name):
        return open(self.directory(name)/'operation.lock','a+')
    def create(self,name,key,memory=1024,cpus=1):
        if not self.image.is_file(): raise ValueError('Configured verified base image missing')
        if memory not in (512,1024,2048,4096) or cpus not in (1,2,4): raise ValueError('Unsupported resources')
        if not re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/=]+(?: [^\r\n]*)?',key): raise ValueError('Use an ed25519 public key')
        d=self.directory(name); d.mkdir(mode=0o700, exist_ok=False)
        # Port assignment is serialized across creates and never replaces an existing guest.
        with open(self.root/'ports.lock','a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            used={x['port'] for x in self.list()}
            port=next((p for p in range(22300,22400) if p not in used),None)
            if port is None: raise ValueError('Instance limit reached')
            (d/'vm.json').write_text(json.dumps({'name':name,'memory':memory,'cpus':cpus,'port':port}))
        self.run('qemu-img','create','-f','qcow2','-F','qcow2','-b',str(self.image),str(d/'disk.qcow2'),'6G')
        cfg={'disable_root':False,'ssh_pwauth':False,'users':[{'name':'root','lock_passwd':True,'ssh_authorized_keys':[key]}],
             'write_files':[{'path':'/etc/systemd/system/serial-getty@ttyS0.service.d/autologin.conf','content':'[Service]\nExecStart=\nExecStart=-/sbin/agetty --autologin root --keep-baud 115200,38400,9600 %I $TERM\n'}],
             'runcmd':[['systemctl','daemon-reload'],['systemctl','restart','serial-getty@ttyS0']]}
        # Serial root autologin is only available to the authenticated single-owner panel.
        (d/'user-data').write_text('#cloud-config\n'+json.dumps(cfg))
        (d/'meta-data').write_text('instance-id: '+name+'\nlocal-hostname: '+name+'\n')
        self.run('cloud-localds',str(d/'seed.iso'),str(d/'user-data'),str(d/'meta-data'))
        return self.metadata(name)
    def list(self):
        result=[]
        for f in self.root.glob('*/vm.json'):
            m=json.loads(f.read_text()); m['running']=self.active(m['name']); result.append(m)
        return result
    def start(self,name):
        d=self.directory(name); m=self.metadata(name)
        with self.locked(name) as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            if self.active(name): raise ValueError('Already running')
            self.run('qemu-system-x86_64','-enable-kvm','-cpu','host','-m',str(m['memory']),'-smp',str(m['cpus']),
                '-drive',f'file={d}/disk.qcow2,if=virtio','-drive',f'file={d}/seed.iso,media=cdrom',
                '-nic',f'user,model=virtio-net-pci,hostfwd=tcp:127.0.0.1:{m["port"]}-:22',
                '-display','none','-serial',f'unix:{d}/console.sock,server,nowait',
                '-qmp',f'unix:{d}/qmp.sock,server,nowait','-daemonize','-pidfile',str(d/'qemu.pid'))
        return self.qmp(name,'query-kvm')
    def stop(self,name): return self.qmp(name,'system_powerdown')
    def snapshot(self,name,label,restore=False):
        if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]{0,31}',label): raise ValueError('Invalid snapshot')
        with self.locked(name) as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            if self.active(name): raise ValueError('Shut down guest first. Running disk never modified.')
            disk=str(self.directory(name)/'disk.qcow2')
            if restore:
                # Preserve current state before an explicitly requested offline revert.
                self.run('qemu-img','snapshot','-c','pre-restore-'+str(time.time_ns()),disk)
            return self.run('qemu-img','snapshot','-a' if restore else '-c',label,disk)
