#!/usr/bin/env python3
"""One-shot credential provisioning. GitHub-private HTTPS forwarding only in development."""
from http.server import HTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs
import os,sys
path=Path(sys.argv[1])
if path.exists(): raise SystemExit('Refusing to replace an existing secret')
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers()
        self.wfile.write(b'<title>INFINITY credential setup</title><h1>INFINITY private panel</h1><form method=post><label>Password<input name=password type=password minlength=12 autocomplete=new-password></label><button>Provision once</button></form>')
    def do_POST(self):
        n=int(self.headers.get('Content-Length','0'))
        if not 0<n<4096: self.send_error(400);return
        password=parse_qs(self.rfile.read(n).decode()).get('password',[''])[0]
        if len(password)<12: self.send_error(400);return
        path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:f.write(password)
        self.send_response(200);self.end_headers();self.wfile.write(b'Provisioned. This setup process will close.')
        self.server.done=True
    def log_message(self,*args):pass
s=HTTPServer(('127.0.0.1',8088),H);s.done=False
while not s.done:s.handle_request()
s.server_close()
