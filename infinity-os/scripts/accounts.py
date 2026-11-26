"""Local single-owner account registry. No shared default client password."""
import hashlib,hmac,json,os,re,secrets,threading
from pathlib import Path
class Accounts:
 def __init__(self,path):self.path=Path(path);self.lock=threading.RLock()
 def read(self):
  if not self.path.exists():return {}
  if self.path.stat().st_mode & 0o077:raise ValueError('Account file must be mode 0600')
  return json.loads(self.path.read_text())
 def authenticate(self,username,password):
  row=self.read().get(username)
  if not row:return None
  value=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(row['salt']),300000).hex()
  if not hmac.compare_digest(value,row['hash']):return None
  return {'username':username,'role':'client','vms':row['vms'],'android':False}
 def public(self):return [{'username':k,'vms':v['vms']} for k,v in self.read().items()]
 def create(self,username,password,vms):
  if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]{2,31}',username):raise ValueError('Username must be 3-32 safe characters')
  if not isinstance(password,str) or not 16<=len(password)<=128:raise ValueError('Use a unique password of 16-128 characters')
  if not isinstance(vms,list) or any(not isinstance(v,str) for v in vms):raise ValueError('Invalid VM assignment')
  with self.lock:
   rows=self.read()
   if username in rows:raise ValueError('Account exists; never overwritten')
   if any(set(vms)&set(row['vms']) for row in rows.values()):raise ValueError('VM already assigned to another client')
   salt=secrets.token_bytes(16)
   rows[username]={'salt':salt.hex(),'hash':hashlib.pbkdf2_hmac('sha256',password.encode(),salt,300000).hex(),'vms':vms}
   self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
   temp=self.path.with_suffix('.new')
   fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
   with os.fdopen(fd,'w') as f:json.dump(rows,f);f.flush();os.fsync(f.fileno())
   os.replace(temp,self.path)
  return {'username':username,'vms':vms}
 def assign(self,username,vms):
  if not isinstance(vms,list) or any(not isinstance(v,str) for v in vms):raise ValueError('Invalid VM assignment')
  with self.lock:
   rows=self.read()
   if username not in rows:raise ValueError('Unknown client')
   if any(set(vms)&set(row['vms']) for other,row in rows.items() if other!=username):raise ValueError('VM already assigned to another client')
   rows[username]['vms']=list(dict.fromkeys(vms))
   temp=self.path.with_suffix('.new');fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
   with os.fdopen(fd,'w') as f:json.dump(rows,f);f.flush();os.fsync(f.fileno())
   os.replace(temp,self.path)
  return {'username':username,'vms':vms}
