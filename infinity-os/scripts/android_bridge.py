"""Single-owner Android screen and touch bridge. No arbitrary shell execution."""
import subprocess
import threading,time,shlex
from io import BytesIO

class Android:
    def __init__(self, adb, serial):
        self.adb = adb
        self.serial = serial
        self.frame_lock = threading.Lock()
        self.frame_time = 0
        self.frame = None
    def run(self, *args, binary=False):
        return subprocess.check_output([self.adb, '-s', self.serial, *args],
            timeout=20, stderr=subprocess.PIPE, text=not binary)
    def status(self):
        try:
            boot = self.run('shell', 'getprop', 'sys.boot_completed').strip()
            return {'serial': self.serial, 'boot_complete': boot == '1',
                    'boot_animation': self.run('shell', 'getprop', 'init.svc.bootanim').strip()}
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return {'serial': self.serial, 'boot_complete': False, 'boot_animation': 'unavailable'}
    def screen(self):
        data = self.run('exec-out', 'screencap', '-p', binary=True)
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('Invalid Android screen')
        return data
    def preview(self):
        try:
            from PIL import Image
        except ImportError:
            return self.screen(), "image/png"
        image = None
        try:
            raw = self.run('exec-out', 'screencap', binary=True)
            import struct as _s
            w, h, _f = _s.unpack('<III', raw[:12])
            body = raw[12:]
            if len(body) == w*h*4:
                image = Image.frombytes('RGBA', (w, h), body)
        except Exception:
            image = None
        if image is None:
            data = self.screen()
            image = Image.open(BytesIO(data))
        out = BytesIO()
        with image:
            img = image.convert("RGB")
            img.thumbnail((540, 1200))
            img.save(out, format="JPEG", quality=42)
        return out.getvalue(), "image/jpeg"
    def cached_preview(self):
        # One capture for all viewers, no unbounded producer or stored video.
        with self.frame_lock:
            if self.frame is None or time.monotonic()-self.frame_time > self._fmin():
                self.frame = self.preview()
                self.frame_time = time.monotonic()
            return self.frame
    def installed(self, package):
        try: return self.run('shell','pm','path',package).strip().startswith('package:')
        except Exception: return False
    APPS={'youtube':'com.google.android.youtube','telegram':'org.telegram.messenger.web','notes':'net.gsantner.markor','calendar':'org.fossify.calendar','music':'com.google.android.apps.youtube.music','settings':'com.android.settings','files':'com.google.android.documentsui','browser':'com.android.chrome'}
    def launch(self, app):
        package=self.APPS.get(app)
        if not package or not self.installed(package):raise ValueError('Android app is not available')
        self.run('shell','monkey','-p',package,'-c','android.intent.category.LAUNCHER','1')
        return {'launched':app}
    def launch_telegram(self):
        if not self.installed('org.telegram.messenger.web'):
            raise ValueError('Telegram is not installed')
        self.run('shell','monkey','-p','org.telegram.messenger.web','-c','android.intent.category.LAUNCHER','1')
        return {'launched':'Telegram'}
    def input(self, body):
        kind = body['kind']
        if kind == 'text':
            text=body.get('text','')
            if not isinstance(text,str) or len(text)>500 or any(ord(c)<32 or ord(c)>126 for c in text):
                raise ValueError('Android text input supports up to 500 printable ASCII characters')
            self.run('shell','input','text',shlex.quote(text.replace('%','').replace(' ','%s')))
        elif kind == 'key':
            key = body['key']
            if key not in ('HOME', 'BACK', 'APP_SWITCH', 'POWER', 'WAKEUP'):
                raise ValueError('Unsupported key')
            self.run('shell', 'input', 'keyevent', 'KEYCODE_' + key)
        elif kind in ('tap', 'swipe'):
            fields = ('x', 'y') if kind == 'tap' else ('x', 'y', 'x2', 'y2')
            values = []
            for field in fields:
                value = body[field]
                if type(value) is not int or not 0 <= value <= 8192:
                    raise ValueError('Invalid coordinate')
                values.append(str(value))
            self.run('shell', 'input', kind, *values, *(['300'] if kind == 'swipe' else []))
        else:
            raise ValueError('Unsupported input')
        return {'sent': kind}
    def _meta_path(self):
        import os
        return os.path.expanduser('~/.infinity-android-meta.json')
    def _meta(self):
        import json,os
        p=self._meta_path()
        try: return json.load(open(p))
        except Exception: return {'names':{},'folders':{},'clones':{}}
    def _save_meta(self,m):
        import json
        json.dump(m,open(self._meta_path(),'w'))
    def app_menu(self,body):
        import re
        op=body.get('op'); app=str(body.get('app',''))
        if op in ('fps','open_clone','open_original'): return self.app_switch(body)
        if not re.fullmatch(r'[a-z0-9_-]{1,60}',app): raise ValueError('Bad app id')
        package=self.APPS.get(app)
        m=self._meta()
        if op=='get': return m
        if op in ('clone','uninstall') and (not package or not self.installed(package)): raise ValueError('Not an installed Android app')
        if op=='rename':
            name=str(body.get('name','')).strip()[:30]
            if not name: raise ValueError('Name required')
            m['names'][app]=name
        elif op=='folder':
            f=str(body.get('folder','')).strip()[:30]
            if f: m['folders'][app]=f
            else: m['folders'].pop(app,None)
        elif op=='clone':
            out=self.run('shell','pm','create-user','--profileOf','0','--managed','x') if False else self.run('shell','pm','create-user','clone-'+app)
            mm=re.search(r'id (\d+)',out)
            if not mm: raise ValueError('Clone failed: '+out.strip()[:80])
            uid=mm.group(1)
            self.run('shell','pm','install-existing','--user',uid,package)
            m['clones'].setdefault(app,[]).append(uid)
        elif op=='uninstall':
            if body.get('confirm')!='UNINSTALL': raise ValueError('Explicit UNINSTALL confirmation required')
            if package in ('com.android.settings','com.android.chrome','com.google.android.gms','com.android.vending'): raise ValueError('Protected app')
            self.run('shell','pm','uninstall','--user','0',package)
        else: raise ValueError('Unsupported menu op')
        self._save_meta(m)
        return {'ok':op,'meta':m}
    def _fmin(self):
        import os
        try: return max(0.05,min(2.0,float(open(os.path.expanduser('~/.infinity-fps')).read().strip())))
        except Exception: return 0.10
    def app_switch(self,body):
        import re
        op=body.get('op')
        if op=='fps':
            import os
            v={'fast':'0.10','low':'0.45'}.get(body.get('mode'))
            if not v: raise ValueError('Bad mode')
            open(os.path.expanduser('~/.infinity-fps'),'w').write(v)
            return {'fps_interval':v}
        app=str(body.get('app',''))
        package=self.APPS.get(app)
        if not package: raise ValueError('Not an Android app')
        m=self._meta()
        if op=='open_original':
            self.run('shell','am','switch-user','0')
            self.run('shell','monkey','-p',package,'-c','android.intent.category.LAUNCHER','1')
            return {'opened':'original'}
        if op=='open_clone':
            cl=m.get('clones',{}).get(app)
            if not cl: raise ValueError('No clone for this app')
            uid=str(int(cl[-1]))
            self.run('shell','am','start-user',uid)
            self.run('shell','am','switch-user',uid)
            self.run('shell','sleep','2')
            comp=self.run('shell','cmd','package','resolve-activity','--brief','--user',uid,'-c','android.intent.category.LAUNCHER',package).strip().splitlines()[-1]
            self.run('shell','am','start','--user',uid,'-n',comp)
            return {'opened':'clone','user':uid}
        raise ValueError('Unsupported op')
Android.APPS=dict(Android.APPS,cash='com.squareup.cash')
