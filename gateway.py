#!/usr/bin/env python3
"""Local controller for up to ten Android guests. Caddy authenticates all public traffic."""
import argparse
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import signal
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from slot import slot_info

HERE = Path(__file__).resolve().parent
PACKAGE = r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+"
PAGE = re.compile(rf"/s/(10|[1-9])/(home|app/({PACKAGE}))")
COMPONENT = re.compile(r"([A-Za-z0-9_.]+)/([.A-Za-z_][A-Za-z0-9_.$]*)")
CSRF_KEY = secrets.token_bytes(32)
WORKERS = {}
LAST_START = {}
LOCK = threading.Lock()
STOPPING = threading.Event()


def origin_value(value):
    address = urlsplit(value)
    if (address.scheme != "https" or not address.hostname or address.username or address.password
            or address.path or address.query or address.fragment or address.netloc != address.netloc.lower()
            or not re.fullmatch(r"[a-z0-9.-]+(?::[0-9]{1,5})?", address.netloc)):
        raise ValueError("Use a lowercase HTTPS origin such as https://sam.home.arpa")
    port = address.port  # Raises ValueError for out-of-range input.
    if port == 0:
        raise ValueError("Invalid HTTPS port")
    if port == 443:
        return f"https://{address.hostname}"
    return value


def csrf_token(path, interval):
    return hmac.new(CSRF_KEY, f"{interval}:{path}".encode(), hashlib.sha256).hexdigest()


def ensure_running(slot):
    """Serialize first launch and allow retry after a failed emulator startup."""
    with LOCK:
        if STOPPING.is_set():
            raise RuntimeError("يتم إيقاف السيرفر.")
        process = WORKERS.get(slot)
        if process and process.poll() is None:
            return
        if time.monotonic() - LAST_START.get(slot, -1000) < 30:
            raise RuntimeError("تعذّر بدء الجهاز. راجع سجل السيرفر الخاص بالمساحة ثم حاول مرة أخرى.")
        state_dir = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "sam-gateway"
        state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        with (state_dir / f"slot-{slot}.log").open("ab") as log:
            WORKERS[slot] = subprocess.Popen([sys.executable, str(HERE / "slot.py"), "run", str(slot)],
                                              stdin=subprocess.DEVNULL, stdout=log, stderr=log)
        LAST_START[slot] = time.monotonic()


def adb(slot, *args):
    tool = shutil.which("adb")
    if not tool and os.environ.get("ANDROID_HOME"):
        tool = os.path.join(os.environ["ANDROID_HOME"], "platform-tools", "adb")
    if not tool:
        raise RuntimeError("أداة adb غير متاحة على السيرفر.")
    serial = slot_info(slot)["serial"]
    result = subprocess.run([tool, "-s", serial, *args], capture_output=True, text=True, timeout=10)
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def viewer(slot):
    return f"/s/{slot}/view/vnc.html?" + urlencode({
        "path": f"s/{slot}/view/websockify", "autoconnect": "true", "resize": "scale",
    })


def open_guest(slot, package, action):
    ready, boot = adb(slot, "shell", "getprop", "sys.boot_completed")
    if not ready or boot != "1":
        ensure_running(slot)
        return 202, {"message": "جاري تشغيل أندرويد على السيرفر الخاص بك…"}
    # The guest boot flag can precede startup of the selected slot's web viewer.
    info = slot_info(slot)
    identity_ok, emulator_name = adb(slot, "emu", "avd", "name")
    if not identity_ok or emulator_name.splitlines()[:1] != [info["name"]]:
        return 409, {"message": "عنوان الجهاز مشغول بمحاكي مختلف. أوقف المحاكي المتعارض قبل المتابعة."}
    try:
        with socket.create_connection(("127.0.0.1", info["web"]), timeout=1):
            pass
    except OSError:
        ensure_running(slot)
        return 202, {"message": "جاري تجهيز عارض شاشة الجهاز…"}
    if action == "home" or not package:
        arguments = ["-a", "android.intent.action.MAIN", "-c", "android.intent.category.HOME"]
    elif action == "store":
        arguments = ["-a", "android.intent.action.VIEW", "-d", f"market://details?id={package}",
                     "-p", "com.android.vending"]
    else:
        ok, resolution = adb(slot, "shell", "cmd", "package", "resolve-activity", "--brief",
                             "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER",
                             "-p", package)
        component = resolution.splitlines()[-1] if resolution else ""
        match = COMPONENT.fullmatch(component)
        if not ok or not match or match[1] != package:
            return 409, {"message": "التطبيق غير مثبت أو لا يوفّر شاشة تشغيل. اختر المتجر أو شاشة أندرويد.",
                         "alternatives": True}
        # adb shell joins its arguments before invoking a shell on the guest; an activity
        # class can legitimately contain a dollar sign. Single quotes keep it literal.
        arguments = ["-n", "'" + component + "'"]
    ok, output = adb(slot, "shell", "am", "start", *arguments)
    if not ok or re.search(r"(^|\n)(error|exception|securityexception)", output, re.I):
        return 409, {"message": "تعذّر فتح الوجهة على الجهاز. تقدر تفتح شاشة أندرويد.",
                     "alternatives": bool(package)}
    return 200, {"viewer": viewer(slot)}


PAGE_STYLE = """body{margin:0;background:#20212b;color:#fff;font:18px/1.6 system-ui,sans-serif;
display:grid;place-items:center;min-height:100svh}main{box-sizing:border-box;width:min(92%,460px);
padding:24px;border-radius:20px;background:#2d4354}h1{margin:0}p{overflow-wrap:anywhere}
button{font:inherit;background:#fed7a5;color:#20212b;border:0;border-radius:12px;padding:10px 16px;margin:4px}"""
PAGE_JS = """const statusLine=document.querySelector('#status'), primary=document.querySelector('#open'),
alternatives=document.querySelector('#alternatives'); let busy=false;
async function launch(action){
 if(busy)return; busy=true; primary.disabled=true; alternatives.hidden=true;
 try {
  for(let attempt=0;attempt<150;attempt++){
   const response=await fetch(location.pathname,{method:'POST',redirect:'error',
    headers:{'Content-Type':'application/json','X-Sam-CSRF':document.querySelector('meta[name=csrf]').content},
    body:JSON.stringify({action})});
   const data=await response.json();
   if(data.viewer){location.assign(data.viewer);return;}
   statusLine.textContent=data.message;
   if(response.status!==202){alternatives.hidden=!data.alternatives;return;}
   await new Promise(resolve=>setTimeout(resolve,4000));
  }
  statusLine.textContent='الجهاز يستغرق وقتًا أطول. اضغط للمحاولة مجددًا.';
 } catch {statusLine.textContent='تعذّر الاتصال بالسيرفر. حدّث الصفحة وحاول مرة أخرى.';}
 finally{busy=false;primary.disabled=false;}
}
document.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>launch(b.value)));"""


class Controller(BaseHTTPRequestHandler):
    def respond(self, code, data, mime):
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def json(self, code, value):
        self.respond(code, json.dumps(value, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def do_GET(self):
        match = PAGE.fullmatch(self.path)
        if not match:
            self.send_error(404)
            return
        slot, _, package = match.groups()
        label = html.escape(package) if package else "شاشة أندرويد"
        token = csrf_token(self.path, int(time.time() // 1800))
        trusted_navigation = (
            self.headers.get("Sec-Fetch-Dest") == "document"
            and self.headers.get("Sec-Fetch-Mode") == "navigate"
            and self.headers.get("Sec-Fetch-Site") in ("none", "same-origin")
        )
        start = 'launch("launch");' if trusted_navigation else ""
        body = f"""<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="csrf" content="{token}">
<title>Sam-CloudeSpace</title><style>{PAGE_STYLE}</style><main><h1>المساحة {slot}</h1>
<p><bdi>{label}</bdi></p><button id="open" value="launch">فتح على جهازي الخاص</button>
<p id="status" role="status"></p><div hidden id="alternatives"><button value="store">فتح Google Play</button>
<button value="home">فتح شاشة أندرويد</button></div></main><script>{PAGE_JS}{start}</script></html>"""
        self.respond(200, body.encode(), "text/html; charset=utf-8")

    def do_POST(self):
        match = PAGE.fullmatch(self.path)
        if not match:
            self.send_error(404)
            return
        interval = int(time.time() // 1800)
        token = self.headers.get("X-Sam-CSRF", "")
        if self.headers.get("Origin") != self.server.public_origin or not any(
                hmac.compare_digest(token.encode(), csrf_token(self.path, t).encode()) for t in (interval, interval - 1)):
            self.json(403, {"message": "حدّث الصفحة من عنوان السيرفر وحاول مجددًا."})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size < 100 or self.headers.get_content_type() != "application/json":
                raise ValueError
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict) or data.get("action") not in ("launch", "home", "store"):
                raise ValueError
        except (ValueError, UnicodeDecodeError):
            self.send_error(400)
            return
        try:
            code, payload = open_guest(int(match[1]), match[3], data["action"])
        except RuntimeError as error:
            code, payload = 503, {"message": str(error)}
        except (OSError, subprocess.SubprocessError):
            code, payload = 503, {"message": "السيرفر لم يتمكّن من تشغيل الجهاز. راجع سجل المساحة."}
        self.json(code, payload)


def caddyfile(origin, controller_port=6090):
    routes = []
    for slot in range(1, 11):
        routes.append(f"""        handle_path /s/{slot}/view/* {{
            reverse_proxy 127.0.0.1:{6100 + slot}
        }}""")
    return """{
    admin off
    skip_install_trust
    auto_https disable_redirects
}
""" + origin + """ {
    bind {$SAM_BIND_IP:127.0.0.1}
    tls internal
    header {
        X-Frame-Options DENY
        Content-Security-Policy "frame-ancestors 'none'"
        Referrer-Policy no-referrer
        X-Content-Type-Options nosniff
    }
    route {
        @badOrigin {
            header Origin *
            not header Origin ORIGIN
        }
        respond @badOrigin 403
        basicauth {
            sam {$SAM_PASSWORD_HASH}
        }
ROUTES
        handle {
            reverse_proxy 127.0.0.1:PORT
        }
    }
}
""".replace("ORIGIN", origin).replace("ROUTES", "\n".join(routes)).replace(":PORT", f":{controller_port}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["serve", "caddyfile"])
    parser.add_argument("--origin", type=origin_value, required=True)
    parser.add_argument("--port", type=int, default=6090, choices=range(1024,65536), metavar="PORT")
    args = parser.parse_args()
    if args.command == "caddyfile":
        print(caddyfile(args.origin, args.port))
    else:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Controller)
        server.public_origin = args.origin
        def stop(signum, frame):
            raise SystemExit(0)

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGHUP, stop)
        try:
            server.serve_forever()
        finally:
            STOPPING.set()
            server.server_close()
            with LOCK:
                children = [child for child in WORKERS.values() if child.poll() is None]
            for child in children:
                child.terminate()
            # slot.py stops its viewer and emulator process groups, and flushes guest data.
            for child in children:
                child.wait()
