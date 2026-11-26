import http.client, json, sys, threading, unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from panel import Panel

class PanelTests(unittest.TestCase):
    def setUp(self):
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Panel)
        self.server.username='owner'; self.server.password='unique-test-value'; self.server.token='test-session'
        self.server.engine=Mock(); self.server.engine.create.return_value={'name':'guest'}
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self): self.server.shutdown();self.server.server_close();self.thread.join()
    def request(self,body,headers=None):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        h={'Cookie':'infinity_session=test-session','X-Infinity-Request':'1','Content-Type':'application/json'}
        if headers: h.update(headers)
        c.request('POST','/api/action',json.dumps(body),h);r=c.getresponse();data=r.read();c.close();return r.status,data
    def test_create_calls_real_engine_interface(self):
        status,_=self.request({'action':'create','name':'guest','key':'ssh-ed25519 fixture','memory':1024,'cpus':1})
        self.assertEqual(status,200);self.server.engine.create.assert_called_once_with('guest','ssh-ed25519 fixture',1024,1)
    def test_start_and_stop_dispatch(self):
        for action in ['start','stop']:
            getattr(self.server.engine,action).return_value={}
            self.assertEqual(self.request({'action':action,'name':'guest'})[0],200)
            getattr(self.server.engine,action).assert_called_once_with('guest')
    def test_cross_origin_rejected(self):
        self.assertEqual(self.request({'action':'start','name':'guest'},{'Origin':'https://attacker.invalid'})[0],403)
        self.server.engine.start.assert_not_called()
    def test_restore_requires_confirmation(self):
        self.assertEqual(self.request({'action':'restore','name':'guest','label':'baseline'})[0],400)
        self.server.engine.snapshot.assert_not_called()
    def test_unauthenticated_no_effect(self):
        self.assertEqual(self.request({'action':'start','name':'guest'},{'Cookie':''})[0],401)
        self.server.engine.start.assert_not_called()
