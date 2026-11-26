import subprocess,threading,time
class Reboots:
    def __init__(self,engine,android,key):self.engine=engine;self.android=android;self.key=key;self.state={};self.lock=threading.Lock()
    def ssh(self,name,cmd):
        port=self.engine.metadata(name)['port']
        return subprocess.check_output(['ssh','-o','BatchMode=yes','-o','StrictHostKeyChecking=no','-o','UserKnownHostsFile=/dev/null','-o','ConnectTimeout=3','-i',self.key,'-p',str(port),'root@127.0.0.1',cmd],timeout=8,stderr=subprocess.DEVNULL,text=True).strip()
    def begin(self,target):
        if target=='all':targets=['client-acceptance-vps','android']
        else:targets=[target]
        known={r['name'] for r in self.engine.list()}|{'android'}
        if any(t not in known for t in targets):raise ValueError('Unknown guest')
        with self.lock:
            if any(self.state.get(t,{}).get('phase')=='booting' for t in targets):raise ValueError('Restart already in progress')
            for t in targets:self.state[t]={'phase':'booting','started':time.time(),'detail':'Requesting clean reboot'}
        for t in targets:threading.Thread(target=self.work,args=(t,),daemon=True).start()
        return self.state
    def work(self,t):
        try:
            if t=='android':
                old=self.android.run('shell','cat','/proc/sys/kernel/random/boot_id').strip();self.android.run('reboot')
            else:
                old=self.ssh(t,'cat /proc/sys/kernel/random/boot_id')
                self.ssh(t,'sudo systemctl reboot --no-block')
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                time.sleep(3)
                try:
                    if t=='android':
                        new=self.android.run('shell','cat','/proc/sys/kernel/random/boot_id').strip()
                        ready=new!=old and self.android.status()['boot_complete']
                    else:
                        new=self.ssh(t,'cat /proc/sys/kernel/random/boot_id');ready=new!=old
                    if ready:
                        self.state[t].update(phase='ready',detail='New boot verified',finished=time.time());return
                except Exception:pass
                self.state[t]['detail']='Waiting for operating system boot'
            raise ValueError('Boot not confirmed within 3 minutes. No forced reset was issued.')
        except Exception as e:self.state[t].update(phase='error',detail=str(e))
