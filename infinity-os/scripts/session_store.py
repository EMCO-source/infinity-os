import json,os,time,hashlib,threading
from pathlib import Path
class SessionStore:
    def __init__(self,path):
        self.path=Path(path);self.lock=threading.RLock()
        try:self.rows=json.loads(self.path.read_text())
        except FileNotFoundError:self.rows={}
    def key(self,k):return hashlib.sha256(k.encode()).hexdigest()
    def __contains__(self,k):return self.key(k) in self.rows
    def __getitem__(self,k):return self.rows[self.key(k)]
    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        p=self.path.with_suffix('.new');fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'w') as f:json.dump(self.rows,f)
        os.replace(p,self.path)
    def __setitem__(self,k,v):
        with self.lock:self.rows[self.key(k)]=v;self.save()
    def pop(self,k,default=None):
        with self.lock:
            v=self.rows.pop(self.key(k),default);self.save();return v
