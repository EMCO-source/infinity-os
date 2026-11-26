"""HTTP adapter, kept separate so public auth paths can be tested in isolation."""
import json

def post(handler):
    store=getattr(handler.server,'visitors',None)
    if store is None:return handler.reply(404,{'error':'Visitor access is closed'})
    origin=handler.headers.get('Origin');forwarded=handler.headers.get('X-Forwarded-Host')
    # Codespaces rewrites same-origin Host and Origin to localhost, preserving
    # the external host in X-Forwarded-Host. Require exact configured host and
    # the browser-only custom header; no CORS is ever enabled.
    from urllib.parse import urlparse
    expected=urlparse(store.origin).netloc
    proxy_ok=(handler.client_address[0] in ('127.0.0.1','::1') and forwarded==expected and handler.headers.get('Host')=='localhost:8080' and origin=='https://localhost:8080')
    if not (origin==store.origin or proxy_ok) or handler.headers.get('X-Infinity-Request')!='1':return handler.reply(403,{'error':'Origin rejected'})
    try:
        n=int(handler.headers.get('Content-Length','0'))
        if not 0<n<=32768:raise ValueError('Invalid request size')
        b=json.loads(handler.rfile.read(n));action=b.get('action')
        if action in ('register-options','authenticate-options'):result=store.options(action.split('-')[0],b.get('invitation'))
        elif action in ('register-finish','authenticate-finish'):result=store.finish(action.split('-')[0],b['ceremony'],b['credential'])
        else:raise ValueError('Unknown authentication action')
        if 'token' in result:
            token=result.pop('token');data=json.dumps({'signed_in':True}).encode()
            handler.send_response(200);handler.send_header('Content-Type','application/json');handler.send_header('Cache-Control','no-store');handler.send_header('Content-Length',str(len(data)));handler.send_header('Set-Cookie','__Host-infinity_visitor='+token+'; HttpOnly; Secure; SameSite=Strict; Path=/');handler.end_headers();handler.wfile.write(data);return
        return handler.reply(200,result)
    except Exception as e:return handler.reply(400,{'error':str(e)})
