"""Staged invitation and passkey backend, NOT connected to the live HTTP panel.

No mail is sent here. An approved mail adapter must deliver the separate email
verification code before activation. All methods fail closed unless enabled.
Provisioning is separate: new identities always have zero device assignments.
"""
import hashlib,hmac,json,re,secrets,sqlite3,time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse


def digest(value):return hashlib.sha256(value.encode()).hexdigest()
def b64(value):
    import base64
    return base64.urlsafe_b64encode(value).decode().rstrip('=')
def unb64(value):
    import base64
    return base64.urlsafe_b64decode(value+'='*((-len(value))%4))

class InvitedIdentity:
    def __init__(self,path,origin,enabled=False,clock=time.time):
        parsed=urlparse(origin)
        if parsed.scheme!='https' or not parsed.hostname or parsed.path not in ('','/') or parsed.query or parsed.fragment or parsed.username or parsed.password or parsed.port:
            raise ValueError('An exact HTTPS relying-party origin is required')
        self.path=Path(path);self.origin=origin.rstrip('/');self.rp_id=parsed.hostname;self.enabled=enabled;self.clock=clock
    def require_enabled(self):
        if not self.enabled:raise ValueError('Invitations and passkeys are closed')
    @contextmanager
    def db(self):
        import os
        self.require_enabled();self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if not self.path.exists():
            fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
        if self.path.stat().st_mode&0o077:raise ValueError('Identity database must be private')
        conn=sqlite3.connect(self.path,timeout=10,isolation_level=None)
        try:
            conn.execute('PRAGMA foreign_keys=ON')
            conn.executescript('''CREATE TABLE IF NOT EXISTS identities(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,state TEXT NOT NULL,verified_at REAL);
CREATE TABLE IF NOT EXISTS invites(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES identities(id),expires REAL NOT NULL,used INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS email_checks(user_id TEXT PRIMARY KEY REFERENCES identities(id),code_hash TEXT NOT NULL,expires REAL NOT NULL,attempts INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS credentials(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES identities(id),public_key TEXT NOT NULL,counter INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS challenges(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES identities(id),purpose TEXT NOT NULL,challenge TEXT NOT NULL,expires REAL NOT NULL);
''')
            conn.execute('BEGIN IMMEDIATE');yield conn;conn.commit()
        except Exception:conn.rollback();raise
        finally:conn.close()
    @staticmethod
    def email(value):
        if not isinstance(value,str) or len(value)>254 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',value):raise ValueError('A valid email address is required')
        return value.strip().lower()
    def invite(self,email):
        """Owner-approved caller only. Return a bearer invitation, not email proof."""
        email=self.email(email);token=secrets.token_urlsafe(32);uid=secrets.token_urlsafe(24)
        with self.db() as db:
            # Pending and expired identities reserve slots until explicitly revoked.
            if db.execute("SELECT count(*) FROM identities WHERE state!='revoked'").fetchone()[0]>=2:raise ValueError('Exactly two invitation slots are available')
            db.execute('INSERT INTO identities VALUES(?,?,?,NULL)',(uid,email,'pending'))
            db.execute('INSERT INTO invites VALUES(?,?,?,0)',(digest(token),uid,self.clock()+86400))
        return {'user_id':uid,'email':email,'invitation':token,'expires_in':86400}
    def revoke(self,uid):
        with self.db() as db:
            db.execute("UPDATE identities SET state='revoked' WHERE id=?",(uid,))
            db.execute('DELETE FROM challenges WHERE user_id=?',(uid,));db.execute('DELETE FROM email_checks WHERE user_id=?',(uid,))
    def invitation(self,db,token):
        row=db.execute("SELECT i.user_id,u.email FROM invites i JOIN identities u ON u.id=i.user_id WHERE i.token_hash=? AND i.expires>? AND i.used=0 AND u.state='pending'",(digest(token),self.clock())).fetchone()
        if not row:raise ValueError('Invalid or expired invitation')
        return row
    def prepare_email_check(self,token):
        """Return a code ONLY to a trusted approved mail adapter, never HTTP/UI/logs.
        This does not mark email verified. The adapter must send to returned email.
        """
        code=secrets.token_urlsafe(24)
        with self.db() as db:
            uid,email=self.invitation(db,token)
            db.execute('INSERT OR REPLACE INTO email_checks VALUES(?,?,?,0)',(uid,digest(code),self.clock()+600))
        return {'email':email,'code':code,'expires_in':600}
    def activate(self,token,email_code):
        failed=False;uid=None
        with self.db() as db:
            uid,_=self.invitation(db,token)
            row=db.execute('SELECT code_hash,expires,attempts FROM email_checks WHERE user_id=?',(uid,)).fetchone()
            if not row or row[1]<=self.clock() or row[2]>=5:failed=True
            elif not isinstance(email_code,str) or not hmac.compare_digest(digest(email_code),row[0]):
                db.execute('UPDATE email_checks SET attempts=attempts+1 WHERE user_id=?',(uid,));failed=True
            else:
                db.execute("UPDATE identities SET state='active',verified_at=? WHERE id=?",(self.clock(),uid))
                db.execute('UPDATE invites SET used=1 WHERE user_id=?',(uid,));db.execute('DELETE FROM email_checks WHERE user_id=?',(uid,))
        if failed:raise ValueError('Email verification failed')
        return self.principal(uid)
    def principal(self,uid):
        with self.db() as db:
            row=db.execute("SELECT email FROM identities WHERE id=? AND state='active' AND verified_at IS NOT NULL",(uid,)).fetchone()
        if not row:raise ValueError('Identity is not active')
        return {'user_id':uid,'username':row[0],'role':'client','vms':[],'android':False}
    def options(self,uid,purpose,session_uid=None):
        # A trusted authenticated principal is required for enrollment. Calling
        # HTTP adapter must check matching session and CSRF before this method.
        from webauthn import generate_registration_options,generate_authentication_options,options_to_json
        from webauthn.helpers.structs import AuthenticatorSelectionCriteria,UserVerificationRequirement,PublicKeyCredentialDescriptor,ResidentKeyRequirement
        who=self.principal(uid)
        if purpose=='register' and session_uid!=uid:raise ValueError('Matching authenticated session required')
        if purpose not in ('register','authenticate'):raise ValueError('Invalid ceremony')
        with self.db() as db:
            credentials=[PublicKeyCredentialDescriptor(id=unb64(r[0])) for r in db.execute('SELECT id FROM credentials WHERE user_id=?',(uid,))]
            if purpose=='register':
                opts=generate_registration_options(rp_id=self.rp_id,rp_name='INFINITY OS',user_id=uid.encode(),user_name=who['username'],exclude_credentials=credentials,authenticator_selection=AuthenticatorSelectionCriteria(user_verification=UserVerificationRequirement.REQUIRED,resident_key=ResidentKeyRequirement.REQUIRED))
            else:
                if not credentials:raise ValueError('No passkey enrolled')
                opts=generate_authentication_options(rp_id=self.rp_id,allow_credentials=credentials,user_verification=UserVerificationRequirement.REQUIRED)
            ceremony=secrets.token_urlsafe(24)
            db.execute('DELETE FROM challenges WHERE expires<=? OR (user_id=? AND purpose=?)',(self.clock(),uid,purpose))
            db.execute('INSERT INTO challenges VALUES(?,?,?,?,?)',(ceremony,uid,purpose,b64(opts.challenge),self.clock()+120))
        return {'ceremony':ceremony,'options':json.loads(options_to_json(opts))}
    def finish(self,ceremony,credential,purpose,session_uid=None):
        from webauthn import verify_registration_response,verify_authentication_response
        if purpose not in ('register','authenticate'):raise ValueError('Invalid ceremony')
        # Consume first, including failed attempts, so replay cannot reuse it.
        with self.db() as db:
            row=db.execute('SELECT user_id,challenge,expires FROM challenges WHERE id=? AND purpose=?',(ceremony,purpose)).fetchone()
            db.execute('DELETE FROM challenges WHERE id=?',(ceremony,))
        if not row or row[2]<=self.clock():raise ValueError('Expired or already used ceremony')
        uid,challenge,_=row;self.principal(uid)
        if purpose=='register' and session_uid!=uid:raise ValueError('Matching authenticated session required')
        if purpose=='register':
            result=verify_registration_response(credential=credential,expected_challenge=unb64(challenge),expected_rp_id=self.rp_id,expected_origin=self.origin,require_user_verification=True)
            with self.db() as db:
                if not db.execute("SELECT 1 FROM identities WHERE id=? AND state='active'",(uid,)).fetchone():raise ValueError('Identity revoked')
                db.execute('INSERT INTO credentials VALUES(?,?,?,?)',(b64(result.credential_id),uid,b64(result.credential_public_key),result.sign_count))
        else:
            if not isinstance(credential,dict):raise ValueError('Invalid credential')
            with self.db() as db:
                key=db.execute('SELECT public_key,counter FROM credentials WHERE id=? AND user_id=?',(credential.get('id'),uid)).fetchone()
            if not key:raise ValueError('Unknown passkey')
            result=verify_authentication_response(credential=credential,expected_challenge=unb64(challenge),expected_rp_id=self.rp_id,expected_origin=self.origin,credential_public_key=unb64(key[0]),credential_current_sign_count=key[1],require_user_verification=True)
            with self.db() as db:
                updated=db.execute('UPDATE credentials SET counter=? WHERE id=? AND counter=?',(result.new_sign_count,credential['id'],key[1]))
                if updated.rowcount!=1:raise ValueError('Concurrent passkey update; retry sign-in')
        return self.principal(uid)
