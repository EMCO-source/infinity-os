"""Authenticated per-VM websocket reverse proxy. Upstreams MUST be loopback-only."""
import base64,json,select,socket,time
from pathlib import Path
from urllib.parse import urlparse

def mapping(handler,name):
    handler.allowed_vm(name)
    path=getattr(handler.server,'desktop_config',None)
    rows=json.loads(Path(path).read_text()) if path else {}
    port=rows.get(name)
    if type(port) is not int or not 1024<=port<=65535:raise ValueError('Desktop is not configured for this device yet')
    return port

def proxy(handler,name):
    port=mapping(handler,name)
    if handler.headers.get('Origin') not in ('https://'+handler.headers.get('Host',''),'http://'+handler.headers.get('Host','')):
        return handler.reply(403,{'error':'Desktop origin rejected'})
    key=handler.headers.get('Sec-WebSocket-Key','')
    try:valid=len(base64.b64decode(key,validate=True))==16
    except Exception:valid=False
    if not valid or handler.headers.get('Upgrade','').lower()!='websocket':
        return handler.reply(400,{'error':'Websocket upgrade required'})
    upstream=socket.create_connection(('127.0.0.1',port),timeout=8)
    with upstream:
        request=('GET / HTTP/1.1\r\nHost: 127.0.0.1:'+str(port)+'\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: '+key+'\r\nSec-WebSocket-Version: 13\r\n\r\n')
        upstream.sendall(request.encode())
        head=b''
        while b'\r\n\r\n' not in head and len(head)<16384:
            data=upstream.recv(4096)
            if not data:raise ValueError('Desktop transport closed')
            head+=data
        if not head.startswith(b'HTTP/1.1 101') and not head.startswith(b'HTTP/1.0 101'):raise ValueError('Desktop transport unavailable')
        handler.connection.sendall(head)
        handler.close_connection=True
        expiry=time.time()+3600
        while time.time()<expiry:
            # Refresh the principal and assignment so revocation ends an open desktop too.
            if not handler.authenticated():break
            try:mapping(handler,name)
            except Exception:break
            ready,_,_=select.select([handler.connection,upstream],[],[],1)
            for source in ready:
                data=source.recv(65536)
                if not data:return
                (upstream if source is handler.connection else handler.connection).sendall(data)
