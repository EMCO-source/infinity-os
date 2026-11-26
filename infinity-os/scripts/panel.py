#!/usr/bin/env python3
"""Private single-owner development panel, never bind publicly without a reviewed TLS proxy."""
import mimetypes
import argparse, base64, hmac, json, os, socket, threading, secrets, time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from engine import Engine

class Panel(BaseHTTPRequestHandler):
    def authenticated(self):
        owner={'username':self.server.username,'role':'owner','vms':None,'android':True}
        cookie=SimpleCookie(self.headers.get('Cookie',''))
        token=cookie.get('__Host-infinity_session')
        sessions=getattr(self.server,'sessions',{})
        if token and token.value in sessions:
            principal=sessions[token.value]
            if principal.get('expires_at',float('inf'))<time.time():
                sessions.pop(token.value,None);return self.reply(401,{'error':'Session expired'})
            if principal['role']=='client':
                # Re-read assignments on every request; session never grants stale access.
                row=self.server.accounts.read().get(principal['username'])
                if row is None:return self.reply(401,{'error':'Session expired'})
                principal=dict(principal,vms=row['vms'])
            self.principal=principal;return True
        # Legacy random owner token supports local fixtures, never emitted by login.
        if token and hmac.compare_digest(token.value,self.server.token):self.principal=owner;return True
        value=self.headers.get('Authorization','')
        expected='Basic '+base64.b64encode((self.server.username+':'+self.server.password).encode()).decode()
        if hmac.compare_digest(value,expected):self.principal=owner;return True
        self.reply(401,{'error':'Sign in required'});return False
    def owner_only(self):
        if self.principal['role']!='owner':raise ValueError('Owner access required')
    def allowed_vm(self,name):
        if self.principal['role']!='owner' and name not in self.principal['vms']:
            raise ValueError('Device not assigned to this account')
    def reply(self,status,value,kind='application/json'):
        data=(json.dumps(value) if kind=='application/json' else value).encode()
        self.send_response(status); self.send_header('Content-Type',kind); self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(data)
    def bytes_reply(self, data, kind):
        self.send_response(200); self.send_header('Content-Type',kind); self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/login':
            return self.reply(200,'<!doctype html><html lang=ar dir=rtl><meta name=viewport content=width=device-width,initial-scale=1><title>Infinity ♾️ OS | Sam Cloud-System</title><style>body{background:radial-gradient(ellipse at top,#253c72,#080c19 70%);color:#f5f7ff;font:16px system-ui;min-height:100vh;margin:0;display:grid;place-items:center}main{width:min(360px,85vw);padding:25px;border:1px solid #ffffff30;border-radius:25px;background:#ffffff0b}label{display:block;margin:20px 0}input,button{box-sizing:border-box;width:100%;font:inherit;border:1px solid #536681;border-radius:12px;background:#15213c;color:white;padding:13px;margin-top:8px}button{background:linear-gradient(135deg,#428bff,#7a5eff);cursor:pointer}p{color:#aab8d5;line-height:1.8}</style><main><h1 dir=ltr>Infinity ♾️ OS</h1><p dir=ltr>Sam Cloud-System</p><p>دخول المالك أو العميل. صلاحيات منفصلة، ونفس المساحة الخاصة.</p><form method=post action=/login><label>User<input name=username autocomplete=username required dir=ltr></label><label>Password<input name=password type=password autocomplete=current-password required dir=ltr></label><button>Sign in</button></form></main></html>','text/html; charset=utf-8')
        if not self.headers.get('Authorization') and not self.headers.get('Cookie'):
            self.send_response(303); self.send_header('Location','/login'); self.end_headers(); return
        if not self.authenticated(): return
        try:
            if path=='/admin' and self.principal['role']!='owner':
                return self.reply(403,{'error':'Owner access required'})
            if path=='/' and self.principal['role']=='owner':
                self.send_response(303);self.send_header('Location','/admin');self.end_headers();return
            if path in ('/admin','/client'): return self.reply(200,(Path(__file__).parents[1]/'web/panel.html').read_text(),'text/html; charset=utf-8')
            if path.startswith('/desktop/') and path.endswith('/ws'):
                from desktop_proxy import proxy
                return proxy(self,path.split('/')[2])
            if path.startswith('/vendor/novnc/'):
                root=(Path(__file__).parents[1]/'web/vendor/novnc').resolve(); target=(root/path.removeprefix('/vendor/novnc/')).resolve()
                if not target.is_relative_to(root) or not target.is_file() or target.suffix not in ('.js','.css','.svg','.txt'):return self.reply(404,{'error':'Not found'})
                return self.bytes_reply(target.read_bytes(),mimetypes.guess_type(str(target))[0] or 'application/octet-stream')
            if path=='/api/desktop':
                from desktop_proxy import mapping
                from urllib.parse import parse_qs
                name=parse_qs(urlparse(self.path).query).get('name',[''])[0];mapping(self,name)
                return self.reply(200,{'ready':True,'name':name})
            if path=='/api/session': return self.reply(200,{'username':self.principal['username'],'role':self.principal['role']})
            if path=='/api/accounts':
                self.owner_only()
                return self.reply(200,self.server.accounts.public())
            if path.startswith('/assets/'):
                root=(Path(__file__).parents[1]/'web/assets').resolve(); target=(root/path.removeprefix('/assets/')).resolve()
                if not target.is_relative_to(root) or not target.is_file() or target.suffix not in ('.png','.jpg','.svg','.webp'):return self.reply(404,{'error':'Not found'})
                return self.bytes_reply(target.read_bytes(),mimetypes.guess_type(str(target))[0] or 'application/octet-stream')
            if path=='/style.css': return self.reply(200,(Path(__file__).parents[1]/'web/style.css').read_text(),'text/css; charset=utf-8')
            if path=='/api/vms':
                rows=self.server.engine.list()
                if self.principal['role']!='owner': rows=[r for r in rows if r['name'] in self.principal['vms']]
                return self.reply(200,rows)
            if path.startswith('/api/android/'):
                if not self.principal['android']:raise ValueError('Android not assigned to this account')
                android=getattr(self.server,'android',None)
                if android is None: raise ValueError('Android bridge is not configured')
                if path=='/api/android/status': return self.reply(200,android.status())
                if path=='/api/android/catalog':
                    rows=json.loads((Path(__file__).parents[1]/'docs/Sam-AppCatalog.json').read_text())
                    installed={a:android.installed(p) for a,p in {'Telegram':'org.telegram.messenger.web','YouTube':'com.google.android.youtube'}.items()}
                    for row in rows:
                        row['installed']=installed.get(row['name'],False)
                        row['state']='Installed' if row['installed'] else 'Not available yet'
                        row['reason']=('Installed. App account state must be checked separately. Cloning not enabled.' if row['installed'] else
                            'Excluded from Android testing.' if row['kind']!='android' else
                            'Google account linked. This image contains LicenseChecker, not a usable Play Store. Not installed.' if row['category']=='payment' else
                            'Not installed or tested yet.')
                    return self.reply(200,rows)
                if path=='/api/android/live':
                    # Authenticated, bounded multipart preview. Never cache or record frames.
                    self.send_response(200);self.send_header('Content-Type','multipart/x-mixed-replace; boundary=infinityframe')
                    self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers()
                    self.close_connection=True
                    deadline=time.monotonic()+1800
                    try:
                        while time.monotonic()<deadline:
                            if not self.authenticated() or not self.principal['android']:break
                            data,kind=android.cached_preview()
                            self.wfile.write(b'--infinityframe\r\nContent-Type: '+kind.encode()+b'\r\nContent-Length: '+str(len(data)).encode()+b'\r\n\r\n'+data+b'\r\n')
                            self.wfile.flush();time.sleep(0.1)
                    except (BrokenPipeError,ConnectionResetError):pass
                    return
                if path=='/api/android/screen':
                    data,kind=android.preview()
                    return self.bytes_reply(data,kind)
            self.reply(404,{'error':'Not found'})
        except Exception as e: self.reply(400,{'error':str(e)})
    def do_POST(self):
        if urlparse(self.path).path=='/login':
            from urllib.parse import parse_qs
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<4096: return self.reply(400,{'error':'Invalid login size'})
            fields=parse_qs(self.rfile.read(length).decode())
            username=fields.get('username',[''])[0]; password=fields.get('password',[''])[0]
            attempts=getattr(self.server,'login_attempts',{})
            now=time.time();key=self.client_address[0];recent=[t for t in attempts.get(key,[]) if now-t<300]
            attempts[key]=recent;self.server.login_attempts=attempts
            if len(recent)>=10:return self.reply(429,{'error':'Too many login attempts; wait five minutes'})
            principal=None
            if hmac.compare_digest(username,self.server.username) and hmac.compare_digest(password,self.server.password):
                principal={'username':username,'role':'owner','vms':None,'android':True}
            elif getattr(self.server,'accounts',None):principal=self.server.accounts.authenticate(username,password)
            if principal is None:
                recent.append(now);return self.reply(403,{'error':'Invalid credentials'})
            attempts.pop(key,None)
            principal['expires_at']=time.time()+28800
            token=secrets.token_urlsafe(32)
            self.server.sessions[token]=principal
            self.send_response(303); self.send_header('Cache-Control','no-store'); self.send_header('Location',('/admin' if principal['role']=='owner' else '/client')+'?login='+secrets.token_hex(6)); self.send_header('Set-Cookie','__Host-infinity_session='+token+'; HttpOnly; Secure; SameSite=Strict; Path=/'); self.end_headers(); return
        if not self.authenticated(): return
        # A custom header forces browser cross-origin preflight. No CORS is enabled.
        if self.headers.get('X-Infinity-Request')!='1': return self.reply(403,{'error':'Request header required'})
        origin=self.headers.get('Origin')
        if origin and urlparse(origin).netloc!=self.headers.get('Host'): return self.reply(403,{'error':'Cross-origin request rejected'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<16384: raise ValueError('Invalid request size')
            body=json.loads(self.rfile.read(length)); action=body['action']; e=self.server.engine
            if action=='logout':
                cookie=SimpleCookie(self.headers.get('Cookie',''));token=cookie.get('__Host-infinity_session')
                if token:self.server.sessions.pop(token.value,None)
                return self.reply(200,{'result':'Signed out'})
            if action=='assign-client':
                self.owner_only()
                known={v['name'] for v in e.list()}
                if any(v not in known for v in body.get('vms',[])):raise ValueError('Unknown VM assignment')
                return self.reply(200,{'result':self.server.accounts.assign(body['username'],body.get('vms',[]))})
            if action=='create-client':
                self.owner_only()
                if body['username']==self.server.username:raise ValueError('Reserved owner username')
                known={v['name'] for v in e.list()}
                if any(v not in known for v in body.get('vms',[])):raise ValueError('Unknown VM assignment')
                result=self.server.accounts.create(body['username'],body['password'],body.get('vms',[]))
                return self.reply(200,{'result':result})
            if action in ('create','snapshot','restore'):self.owner_only()
            if action in ('start','stop','snapshot','restore','console'):self.allowed_vm(body['name'])
            if action=='create': result=e.create(body['name'],body['key'],int(body.get('memory',1024)),int(body.get('cpus',1)))
            elif action=='start': result=({'running':True} if e.active(body['name']) else e.start(body['name']))
            elif action=='stop': result=e.stop(body['name'])
            elif action=='snapshot': result=e.snapshot(body['name'],body['label'])
            elif action=='restore':
                if body.get('confirm')!='RESTORE': raise ValueError('Explicit RESTORE confirmation required')
                result=e.snapshot(body['name'],body['label'],True)
            elif action=='android-launch':
                if not self.principal['android']:raise ValueError('Android not assigned to this account')
                result=self.server.android.launch(body['app'])
            elif action=='android-launch-telegram':
                if not self.principal['android']:raise ValueError('Android not assigned to this account')
                result=self.server.android.launch_telegram()
            elif action=='android-app':
                if not self.principal['android']:raise ValueError('Android not assigned to this account')
                result=self.server.android.app_menu(body)
            elif action=='android-input':
                if not self.principal['android']:raise ValueError('Android not assigned to this account')
                android=getattr(self.server,'android',None)
                if android is None: raise ValueError('Android bridge is not configured')
                result=android.input(body)
            elif action=='console':
                d=e.directory(body['name'])
                # One short-lived serial connection per request, real guest I/O, no shell command evaluation.
                with socket.socket(socket.AF_UNIX) as s:
                    s.settimeout(0.2); s.connect(str(d/'console.sock'))
                    text=body.get('input','')
                    if len(text)>2048: raise ValueError('Input too long')
                    if text: s.sendall(text.encode())
                    chunks=[]
                    try:
                        while sum(map(len,chunks))<65536:
                            b=s.recv(4096)
                            if not b: break
                            chunks.append(b)
                    except socket.timeout: pass
                    result=b''.join(chunks).decode(errors='replace')
            else: raise ValueError('Unknown action')
            self.reply(200,{'result':result})
        except Exception as e: self.reply(400,{'error':str(e)})
    def log_message(self,*args): pass

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--root',required=True); p.add_argument('--image',required=True)
    p.add_argument('--password-file',required=True); p.add_argument('--username',default='infinity'); p.add_argument('--port',type=int,default=8080)
    p.add_argument('--desktop-config'); p.add_argument('--adb'); p.add_argument('--android-serial',default='emulator-5554')
    a=p.parse_args(); secret=Path(a.password_file)
    if secret.stat().st_mode & 0o077: p.error('Password file must be mode 0600')
    password=secret.read_text().strip()
    if len(password)<12: p.error('Use a unique password of at least 12 characters')
    server=ThreadingHTTPServer(('127.0.0.1',a.port),Panel); server.engine=Engine(a.root,a.image); server.username=a.username; server.password=password; server.token=secrets.token_urlsafe(32); server.sessions={}
    from accounts import Accounts
    server.accounts=Accounts(Path(a.root)/'accounts.json');server.desktop_config=a.desktop_config
    if a.adb:
        from android_bridge import Android
        server.android=Android(a.adb,a.android_serial)
    server.serve_forever()
