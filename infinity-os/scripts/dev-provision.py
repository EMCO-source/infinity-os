#!/usr/bin/env python3
"""One-shot private test provisioning. NOT a production web service.
Bind loopback only and expose ONLY with authenticated PRIVATE forwarding.
Stop this server immediately after provisioning. No credentials are logged.
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs
from pathlib import Path
import subprocess
import os

PAGE=b'''<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>INFINITY setup</title><style>body{font:18px system-ui;max-width:420px;margin:5vh auto;padding:24px}input,button{font:inherit;padding:14px;margin:12px 0;width:100%;box-sizing:border-box}</style><h1>INFINITY OS</h1><p>Private temporary test setup. Use your unique INFINITY password.</p><form method="post"><label>Username<input name="username" value="infinity" readonly autocomplete="username"></label><label>Password<input name="password" type="password" required minlength="12" autocomplete="new-password"></label><button>Provision test login</button></form>'''
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        self.send_response(200);self.send_header('Content-Type','text/html');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(PAGE)
    def do_POST(self):
        if self.server.done: self.send_error(409);return
        n=int(self.headers.get('Content-Length','0'))
        if not 0<n<4096: self.send_error(400);return
        d=parse_qs(self.rfile.read(n).decode())
        password=d.get('password',[''])[0]
        if len(password)<12 or '\n' in password or '\r' in password: self.send_error(400);return
        try:
            subprocess.run(['id','infinity'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
            self.send_error(409,'Account exists; no password changed');return
        except subprocess.CalledProcessError: pass
        subprocess.run(['sudo','useradd','-m','-s','/bin/bash','-G','sudo,libvirt','infinity'],check=True)
        subprocess.run(['sudo','chpasswd'],input=('infinity:'+password+'\n').encode(),check=True)
        p=Path('/tmp/infinity-desktop-password')
        fd=os.open(str(p),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:f.write(password)
        subprocess.run(['docker','run','-d','--name','infinity-desktop-auth','--shm-size=1g','-p','127.0.0.1:3000:3000','-v','infinity-auth-home:/config','-v',str(p)+':/run/secrets/password:ro','-e','CUSTOM_USER=infinity','-e','FILE__PASSWORD=/run/secrets/password','lscr.io/linuxserver/webtop:debian-xfce'],check=True,stdout=subprocess.DEVNULL)
        self.server.done=True
        self.send_response(200);self.send_header('Content-Type','text/html');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(b'<h1>Login provisioned</h1><p>Private test account and authenticated desktop started. Stop the setup service now.</p>')
s=HTTPServer(('127.0.0.1',8088),Handler);s.done=False;s.serve_forever()
