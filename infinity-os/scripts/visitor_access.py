"""Closed passkey-first invitations, with one visitor session at a time."""
import hashlib,os,secrets,sqlite3,time,json
from pathlib import Path
from contextlib import contextmanager
from urllib.parse import urlparse
from invited_identity import b64,unb64

def hashed(value):return hashlib.sha256(value.encode()).hexdigest()
class VisitorAccess:
 def __init__(self,path,origin,enabled=False,clock=time.time):
  u=urlparse(origin)
  if u.scheme!='https' or not u.hostname or u.path or u.query or u.fragment or u.username or u.port:raise ValueError('Exact HTTPS origin required')
  self.path=Path(path);self.origin=origin;self.rp=u.hostname;self.enabled=enabled;self.clock=clock
 @contextmanager
 def db(self):
  if not self.enabled:raise ValueError('Visitor access is closed')
  self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
  if not self.path.exists():
   fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
  if self.path.stat().st_mode&0o077:raise ValueError('Private database required')
  c=sqlite3.connect(self.path,timeout=10,isolation_level=None)
  try:
   c.executescript('''CREATE TABLE IF NOT EXISTS visitors(id TEXT PRIMARY KEY,label TEXT NOT NULL,enabled INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS invitations(hash TEXT PRIMARY KEY,visitor TEXT NOT NULL,expires REAL NOT NULL,used INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS credentials(id TEXT PRIMARY KEY,visitor TEXT NOT NULL,pub TEXT NOT NULL,counter INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS ceremonies(hash TEXT PRIMARY KEY,visitor TEXT,purpose TEXT NOT NULL,challenge TEXT NOT NULL,expires REAL NOT NULL,invitation TEXT);
CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY,visitor TEXT NOT NULL,expires REAL NOT NULL,last_seen REAL NOT NULL);
CREATE TABLE IF NOT EXISTS attempts(ts REAL NOT NULL);
CREATE TABLE IF NOT EXISTS shared_invite(hash TEXT PRIMARY KEY,expires REAL NOT NULL,enabled INTEGER NOT NULL);
''');c.execute('BEGIN IMMEDIATE');yield c;c.commit()
  except Exception:c.rollback();raise
  finally:c.close()
 def invite(self,label,expires_at):
  if not isinstance(label,str) or not 1<=len(label)<=40:raise ValueError('Short label required')
  if not self.clock()<expires_at<=self.clock()+86400:raise ValueError('Invitation expiry must be within24hours')
  token=secrets.token_urlsafe(32);uid=secrets.token_urlsafe(24)
  with self.db() as c:
   if c.execute('SELECT count(*) FROM visitors WHERE enabled=1').fetchone()[0]>=10:raise ValueError('Ten invitation limit')
   c.execute('INSERT INTO visitors VALUES(?,?,1)',(uid,label));c.execute('INSERT INTO invitations VALUES(?,?,?,0)',(hashed(token),uid,expires_at))
  return {'id':uid,'label':label,'token':token,'expires_at':expires_at}
 def shared(self,expires_at):
  if not self.clock()<expires_at<=self.clock()+86400:raise ValueError('Expiry within24hours required')
  token=secrets.token_urlsafe(32)
  with self.db() as c:
   c.execute('UPDATE shared_invite SET enabled=0');c.execute('INSERT INTO shared_invite VALUES(?,?,1)',(hashed(token),expires_at));c.execute("DELETE FROM ceremonies WHERE purpose='register'")
  return {'token':token,'expires_at':expires_at}
 def close_shared(self):
  with self.db() as c:c.execute('UPDATE shared_invite SET enabled=0');c.execute("DELETE FROM ceremonies WHERE purpose='register'")
 def list(self):
  with self.db() as c:return [{'id':r[0],'label':r[1],'enabled':bool(r[2]),'enrolled':bool(r[3])} for r in c.execute('SELECT v.id,v.label,v.enabled,EXISTS(SELECT 1 FROM credentials k WHERE k.visitor=v.id) FROM visitors v')]
 def revoke(self,uid):
  with self.db() as c:
   c.execute('UPDATE visitors SET enabled=0 WHERE id=?',(uid,));c.execute('DELETE FROM sessions WHERE visitor=?',(uid,));c.execute('DELETE FROM ceremonies WHERE visitor=?',(uid,))
 def end_session(self):
  with self.db() as c:c.execute('DELETE FROM sessions')
 def rate(self):
  rejected=False
  with self.db() as c:
   c.execute('DELETE FROM attempts WHERE ts<?',(self.clock()-300,))
   rejected=c.execute('SELECT count(*) FROM attempts').fetchone()[0]>=50
   if not rejected:c.execute('INSERT INTO attempts VALUES(?)',(self.clock(),))
  if rejected:raise ValueError('Too many requests; wait five minutes')
 def options(self,purpose,invitation=None):
  from webauthn import generate_registration_options,generate_authentication_options,options_to_json
  from webauthn.helpers.structs import AuthenticatorSelectionCriteria,UserVerificationRequirement,ResidentKeyRequirement
  self.rate();now=self.clock();uid=None;invhash=None
  with self.db() as c:
   if purpose=='register':
    invhash=hashed(invitation or '')
    if not c.execute('SELECT 1 FROM shared_invite WHERE hash=? AND expires>? AND enabled=1',(invhash,now)).fetchone():raise ValueError('Invalid or expired invitation')
    count=c.execute('SELECT count(*) FROM credentials').fetchone()[0]
    if count>=10:raise ValueError('All ten registration slots are filled')
    uid=secrets.token_urlsafe(24);label='Visitor '+str(count+1)
    o=generate_registration_options(rp_id=self.rp,rp_name='INFINITY OS',user_id=uid.encode(),user_name=label,authenticator_selection=AuthenticatorSelectionCriteria(user_verification=UserVerificationRequirement.REQUIRED,resident_key=ResidentKeyRequirement.REQUIRED))
   elif purpose=='authenticate':o=generate_authentication_options(rp_id=self.rp,user_verification=UserVerificationRequirement.REQUIRED)
   else:raise ValueError('Invalid ceremony')
   token=secrets.token_urlsafe(24);c.execute('DELETE FROM ceremonies WHERE expires<=?',(now,));c.execute('INSERT INTO ceremonies VALUES(?,?,?,?,?,?)',(hashed(token),uid,purpose,b64(o.challenge),now+120,invhash))
  return {'ceremony':token,'options':json.loads(options_to_json(o))}
 def finish(self,purpose,ceremony,credential):
  from webauthn import verify_registration_response,verify_authentication_response
  self.rate()
  with self.db() as c:
   row=c.execute('SELECT visitor,challenge,expires,invitation FROM ceremonies WHERE hash=? AND purpose=?',(hashed(ceremony),purpose)).fetchone();c.execute('DELETE FROM ceremonies WHERE hash=?',(hashed(ceremony),))
  if not row or row[2]<=self.clock():raise ValueError('Ceremony expired or used')
  uid,challenge,_,invhash=row
  if purpose=='register':
   v=verify_registration_response(credential=credential,expected_challenge=unb64(challenge),expected_rp_id=self.rp,expected_origin=self.origin,require_user_verification=True)
   with self.db() as c:
    valid=c.execute('SELECT 1 FROM shared_invite WHERE hash=? AND expires>? AND enabled=1',(invhash,self.clock())).fetchone()
    if not valid:raise ValueError('Invitation no longer available')
    count=c.execute('SELECT count(*) FROM credentials').fetchone()[0]
    if count>=10:raise ValueError('All ten registration slots are filled')
    c.execute('INSERT INTO visitors VALUES(?,?,1)',(uid,'Visitor '+str(count+1)))
    c.execute('INSERT INTO credentials VALUES(?,?,?,?)',(b64(v.credential_id),uid,b64(v.credential_public_key),v.sign_count))
   return {'registered':True}
  if purpose!='authenticate' or not isinstance(credential,dict):raise ValueError('Invalid ceremony')
  with self.db() as c:key=c.execute('SELECT k.visitor,k.pub,k.counter FROM credentials k JOIN visitors v ON k.visitor=v.id WHERE k.id=? AND v.enabled=1',(credential.get('id'),)).fetchone()
  if not key:raise ValueError('Passkey not recognized')
  uid,pub,count=key
  v=verify_authentication_response(credential=credential,expected_challenge=unb64(challenge),expected_rp_id=self.rp,expected_origin=self.origin,credential_public_key=unb64(pub),credential_current_sign_count=count,require_user_verification=True)
  now=self.clock();token=secrets.token_urlsafe(32)
  with self.db() as c:
   if not c.execute('SELECT 1 FROM visitors WHERE id=? AND enabled=1',(uid,)).fetchone():raise ValueError('Access revoked')
   c.execute('DELETE FROM sessions WHERE expires<=? OR last_seen<=?',(now,now-900))
   if c.execute('SELECT count(*) FROM sessions').fetchone()[0]:raise ValueError('Another visitor is using the shared devices. Try later.')
   updated=c.execute('UPDATE credentials SET counter=? WHERE id=? AND counter=?',(v.new_sign_count,credential['id'],count))
   if updated.rowcount!=1:raise ValueError('Passkey changed; retry')
   c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashed(token),uid,now+28800,now))
  return {'token':token}
 def session(self,token):
  now=self.clock()
  with self.db() as c:
   row=c.execute('SELECT v.id,v.label FROM sessions s JOIN visitors v ON s.visitor=v.id WHERE s.hash=? AND s.expires>? AND s.last_seen>? AND v.enabled=1',(hashed(token),now,now-900)).fetchone()
   if not row:raise ValueError('Visitor session expired')
   c.execute('UPDATE sessions SET last_seen=? WHERE hash=?',(now,hashed(token)))
  return {'username':row[1],'visitor_id':row[0],'role':'visitor','vms':['client-acceptance-vps'],'android':True}
 def logout(self,token):
  with self.db() as c:c.execute('DELETE FROM sessions WHERE hash=?',(hashed(token),))
