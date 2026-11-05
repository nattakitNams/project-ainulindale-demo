# -*- coding: utf-8 -*-
"""ตัวช่วยติดตั้ง (รันก่อนมีไลบรารีใดๆ — ใช้แค่ไลบรารีมาตรฐานของ Python)

ทำงานเมื่อยังไม่ได้ติดตั้งแพ็กเกจ: เปิดเซิร์ฟเวอร์ที่ 127.0.0.1:<PORT> ให้หน้าเว็บแสดง "ตัวช่วยติดตั้ง"
  1) เลือกที่เก็บผลลัพธ์ (ค่าเริ่มต้น = ในโฟลเดอร์แอป)
  2) ติดตั้งแพ็กเกจจาก PyPI ตามรายการที่ล็อกเวอร์ชัน + SHA-256 (installer/requirements.lock.txt)
     ลงใน python/Lib/site-packages ของแอปเอง — ไม่แตะ Python ของเครื่อง ไม่ใช้สิทธิ์ admin ไม่เก็บแคชนอกโฟลเดอร์
  3) ตรวจว่า import ได้ครบ → เปิดตัวประมวลผลจริง (app.server) แทนที่ตัวเอง
ความปลอดภัยเหมือนตัวประมวลผล: Host = localhost · Origin ต้องอยู่ใน engine.json · คำขอที่เปลี่ยนข้อมูลต้องมีโทเคนจับคู่
"""
import ctypes
import hmac
import json
import os
import re
import secrets
import shutil
import string
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import APP_NAME, APP_VERSION, PORT, ROOT, STATIC, load_settings, save_settings

INSTALLER = ROOT / 'installer'
LOCK = INSTALLER / 'requirements.lock.txt'
if not LOCK.exists():                                     # ยังไม่ได้ build (โฟลเดอร์พัฒนา) → ใช้รายการหลัก (ไม่มี hash)
    LOCK = INSTALLER / 'requirements.in'
MARKER = ROOT / '.installed.json'
IMPORTS = ['flask', 'numpy', 'rasterio', 'rio_tiler', 'pyogrio', 'geopandas', 'shapely', 'scipy', 'PIL', 'pyproj', 'matplotlib', 'requests']
CHILD_ENV = dict(os.environ, PYTHONNOUSERSITE='1', PIP_NO_CACHE_DIR='1', PIP_DISABLE_PIP_VERSION_CHECK='1',
                 PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
NOWIN = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

STATE = dict(state='idle', pct=0.0, step='', log=[], error=None)
_lock = threading.Lock()


# ---------- ค่าตั้ง / โทเคน ----------
def engine_cfg():
    try:
        return json.loads((ROOT / 'engine.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def token():
    p = ROOT / 'engine_token.txt'
    if not p.exists():
        p.write_text(secrets.token_urlsafe(24), encoding='utf-8')
    return p.read_text(encoding='utf-8').strip()


def self_origin(o):
    return o in (f'http://127.0.0.1:{PORT}', f'http://localhost:{PORT}')


def allowed_origin(o):
    return self_origin(o) or o in (engine_cfg().get('allowed_origins') or [])


# ---------- ข้อมูลเครื่อง ----------
def lock_packages():
    """[(ชื่อ, เวอร์ชัน)] จากไฟล์ล็อก"""
    out = []
    if LOCK.exists():
        for line in LOCK.read_text(encoding='utf-8').splitlines():
            m = re.match(r'^([A-Za-z0-9_.\-]+)==([^\s;\\]+)', line.strip())
            if m:
                out.append((m.group(1), m.group(2)))
    return out


def drives():
    out = []
    if os.name == 'nt':
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        for i, L in enumerate(string.ascii_uppercase):
            if mask >> i & 1:
                p = f'{L}:\\'
                try:
                    u = shutil.disk_usage(p)
                    out.append(dict(path=p, free_gb=round(u.free / 1e9, 1), total_gb=round(u.total / 1e9, 1)))
                except OSError:
                    pass
    return out


def edge():
    for c in (os.environ.get('AINU_BROWSER'), r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
              r'C:\Program Files\Microsoft\Edge\Application\msedge.exe', r'C:\Program Files\Google\Chrome\Application\chrome.exe'):
        if c and Path(c).exists():
            return c
    return None


def internet():
    try:
        urllib.request.urlopen(urllib.request.Request('https://pypi.org/simple/pip/', method='HEAD'), timeout=5)
        return True
    except Exception:
        return False


def imports_ok():
    r = subprocess.run([sys.executable, '-c', 'import ' + ', '.join(IMPORTS)], capture_output=True, text=True, env=CHILD_ENV, creationflags=NOWIN)
    return r.returncode == 0, (r.stderr or '')[-400:]


def check_path(p):
    """ตรวจที่เก็บผลลัพธ์ที่ผู้ใช้เลือก"""
    p = Path(p).expanduser()
    if not p.is_absolute():
        return dict(ok=False, error='ต้องเป็น path เต็ม เช่น D:\\Ainulindale\\workspace')
    inside = str(p.resolve()).lower().startswith(str(ROOT.resolve()).lower())
    anchor = Path(p.anchor)
    if not anchor.exists():
        return dict(ok=False, error=f'ไม่พบไดรฟ์ {p.anchor}')
    probe = p
    while not probe.exists():
        probe = probe.parent
    try:
        free = shutil.disk_usage(probe).free / 1e9
    except OSError:
        free = None
    rp = str(p.resolve()).lower()
    sysdirs = [os.environ.get(k, '') for k in ('WINDIR', 'ProgramFiles', 'ProgramFiles(x86)', 'ProgramData')]
    if any(d and (rp + '\\').startswith(d.lower().rstrip('\\') + '\\') for d in sysdirs):
        return dict(ok=False, error='ห้ามใช้โฟลเดอร์ของระบบ (Windows / Program Files / ProgramData)')
    # os.access บน Windows ไม่ดูสิทธิ์จริง → ลองเขียนไฟล์ชั่วคราวแล้วลบทันที
    try:
        t = probe / f'.ainu_write_test_{secrets.token_hex(4)}'
        t.write_bytes(b'')
        t.unlink()
        writable = True
    except OSError:
        writable = False
    warn = [] if inside else ['อยู่นอกโฟลเดอร์แอป — ตอนลบแอป ผลลัพธ์ในโฟลเดอร์นี้จะไม่ถูกลบตาม (ต้องลบเอง)']
    if free is not None and free < 5:
        warn.append(f'พื้นที่ว่างเหลือ {free:.1f} GB — ผลลัพธ์ความละเอียดสูงใช้หลาย GB')
    return dict(ok=writable, path=str(p), exists=p.exists(), inside_app=inside, free_gb=round(free, 1) if free is not None else None,
                writable=writable, warn=warn, error=None if writable else 'เขียนไฟล์ในตำแหน่งนี้ไม่ได้ (สิทธิ์ไม่พอ)')


def status():
    pk = lock_packages()
    s = load_settings()
    return dict(app=APP_NAME, version=APP_VERSION, root=str(ROOT), python=sys.version.split()[0], python_exe=sys.executable,
                default_workspace=str(ROOT / 'workspace'), workspace=s.get('workspace') or str(ROOT / 'workspace'),
                drives=drives(), packages=[dict(name=n, version=v) for n, v in pk], hashed=LOCK.exists() and '--hash=sha256:' in LOCK.read_text(encoding='utf-8'),
                download_mb_est=180, installed_mb_est=450, edge=edge(), internet=internet(), installed=MARKER.exists(),
                **{k: STATE[k] for k in ('state', 'pct', 'step', 'error')})


# ---------- ติดตั้ง ----------
def _log(msg):
    with _lock:
        STATE['log'].append(msg)
        del STATE['log'][:-300]


def _run(cmd, on_line=None):
    _log('$ ' + ' '.join(str(c) for c in cmd))
    pr = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                          env=CHILD_ENV, cwd=str(ROOT), creationflags=NOWIN)
    for line in pr.stdout:
        line = line.rstrip()
        if line:
            _log(line)
            if on_line:
                on_line(line)
    return pr.wait()


def install(workspace):
    try:
        STATE.update(state='running', pct=0.02, step='เตรียมโฟลเดอร์', error=None)
        ws = Path(workspace)
        ws.mkdir(parents=True, exist_ok=True)
        save_settings(workspace=str(ws))
        _log(f'ที่เก็บผลลัพธ์: {ws}')
        # 1) pip (Python แบบพกพาไม่มี pip มาให้)
        if subprocess.run([sys.executable, '-c', 'import pip'], env=CHILD_ENV, capture_output=True, creationflags=NOWIN).returncode != 0:
            STATE.update(pct=0.05, step='ติดตั้งตัวจัดการแพ็กเกจ (pip)')
            if _run([sys.executable, str(INSTALLER / 'get-pip.py'), '--no-warn-script-location', '--no-cache-dir']) != 0:
                raise RuntimeError('ติดตั้ง pip ไม่สำเร็จ — ตรวจการเชื่อมต่ออินเทอร์เน็ต')
        # 2) แพ็กเกจตามรายการล็อก (เฉพาะไฟล์ wheel สำเร็จรูป · ตรวจ SHA-256 ทุกไฟล์ถ้าไฟล์ล็อกมีค่า hash)
        pk = lock_packages()
        total = max(len(pk), 1)
        seen = set()

        def prog(line):
            m = re.match(r'^(?:Collecting|Downloading|Using cached)\s+([A-Za-z0-9_.\-]+?)(?:[=<>\[\s-]|-\d)', line)
            if m:
                seen.add(m.group(1).lower().replace('_', '-'))
                STATE.update(pct=0.1 + 0.75 * min(len(seen) / total, 1), step=f'ดาวน์โหลด {m.group(1)} ({len(seen)}/{total})')
            elif line.startswith('Installing collected packages'):
                STATE.update(pct=0.88, step='กำลังติดตั้งลงโฟลเดอร์แอป…')
        cmd = [sys.executable, '-m', 'pip', 'install', '--no-cache-dir', '--no-warn-script-location', '--only-binary=:all:',
               '--progress-bar', 'off', '--index-url', 'https://pypi.org/simple', '-r', str(LOCK)]
        if status()['hashed']:
            cmd.insert(4, '--require-hashes')
        STATE.update(pct=0.1, step='ดาวน์โหลดแพ็กเกจจาก PyPI')
        if _run(cmd, prog) != 0:
            raise RuntimeError('ติดตั้งแพ็กเกจไม่สำเร็จ — ดูบันทึกด้านล่าง')
        # 3) ตรวจ
        STATE.update(pct=0.95, step='ตรวจว่าใช้งานได้')
        ok, err = imports_ok()
        if not ok:
            raise RuntimeError('ติดตั้งแล้วแต่ import ไม่ได้: ' + err)
        MARKER.write_text(json.dumps(dict(version=APP_VERSION, at=time.strftime('%Y-%m-%dT%H:%M:%S'), workspace=str(ws)), ensure_ascii=False), encoding='utf-8')
        STATE.update(state='done', pct=1.0, step='ติดตั้งเสร็จ')
        _log('ติดตั้งเสร็จ ✔')
    except Exception as e:
        STATE.update(state='failed', error=str(e), step='ติดตั้งไม่สำเร็จ')
        _log('ผิดพลาด: ' + str(e))


# ---------- HTTP ----------
class H(BaseHTTPRequestHandler):
    server_version = 'AinulindaleSetup'

    def log_message(self, *a):
        pass

    def _send(self, code, body=b'', ctype='application/json; charset=utf-8', extra=None):
        o = self.headers.get('Origin')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Cache-Control', 'no-store')
        if o and allowed_origin(o):
            self.send_header('Access-Control-Allow-Origin', o)
            self.send_header('Vary', 'Origin')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Ainu-Token')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            if self.headers.get('Access-Control-Request-Private-Network'):
                self.send_header('Access-Control-Allow-Private-Network', 'true')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode('utf-8'))

    def _guard(self):
        if self.headers.get('Host') not in (f'127.0.0.1:{PORT}', f'localhost:{PORT}'):
            self._json(403, dict(error='host not allowed'))
            return False
        o = self.headers.get('Origin')
        if o and not allowed_origin(o):
            self._json(403, dict(error=f'หน้าเว็บ {o} ไม่ได้รับอนุญาต'))
            return False
        return True

    def _token_ok(self):
        return hmac.compare_digest(self.headers.get('X-Ainu-Token', ''), token())

    def do_OPTIONS(self):
        if self._guard():
            self._send(204)

    def do_GET(self):
        if not self._guard():
            return
        path = self.path.split('?')[0]
        if path == '/api/engine/hello':
            return self._json(200, dict(app=APP_NAME, version=APP_VERSION, engine=True, mode='setup', paired=self._token_ok(),
                                        machine=os.environ.get('COMPUTERNAME', ''), port=PORT))
        if path == '/api/setup/status':
            return self._json(200, status())
        if path == '/api/setup/progress':
            with _lock:
                return self._json(200, dict(STATE, log=STATE['log'][-60:]))
        if path == '/':
            return self._send(302, extra={'Location': '/ui/'})
        if path.startswith('/ui/') or path.startswith('/static/'):        # หน้าเว็บสำรอง (ตัวช่วยติดตั้งแสดงในนี้ได้)
            rel = path.split('/', 2)[2] or 'index.html'
            f = (STATIC / rel).resolve()
            if not str(f).startswith(str(STATIC.resolve())) or not f.is_file():
                return self._json(404, dict(error='not found'))
            body = f.read_bytes()
            if rel == 'index.html':
                body = body.replace(b'<head>', b'<head>\n<meta name="ainu-engine" content="same-origin">', 1)
            ct = {'.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.png': 'image/png'}.get(f.suffix, 'application/octet-stream')
            return self._send(200, body, ct + ('; charset=utf-8' if ct.startswith('text') else ''))
        self._json(404, dict(error='ยังไม่ได้ติดตั้ง — ใช้ตัวช่วยติดตั้งก่อน', setup=True))

    def do_POST(self):
        if not self._guard():
            return
        if not self_origin(self.headers.get('Origin') or '') and not self._token_ok():
            return self._json(401, dict(error='ยังไม่ได้จับคู่กับตัวประมวลผลในเครื่อง', pair=True))
        n = int(self.headers.get('Content-Length') or 0)
        try:
            b = json.loads(self.rfile.read(n) or b'{}')
        except ValueError:
            return self._json(400, dict(error='JSON ไม่ถูกต้อง'))
        path = self.path.split('?')[0]
        if path == '/api/setup/check_path':
            return self._json(200, check_path(b.get('path') or ''))
        if path == '/api/setup/install':
            if STATE['state'] == 'running':
                return self._json(409, dict(error='กำลังติดตั้งอยู่'))
            c = check_path(b.get('workspace') or str(ROOT / 'workspace'))
            if not c['ok']:
                return self._json(400, dict(error=c['error']))
            with _lock:
                STATE['log'] = []
            threading.Thread(target=install, args=(c['path'],), daemon=True).start()
            return self._json(200, dict(ok=True))
        if path == '/api/setup/start_engine':
            if not MARKER.exists():
                return self._json(400, dict(error='ยังติดตั้งไม่เสร็จ'))
            self._json(200, dict(ok=True))
            threading.Thread(target=_handoff, daemon=True).start()
            return
        self._json(404, dict(error='not found'))


SERVER = None
HANDOFF = threading.Event()


class _Server(ThreadingHTTPServer):
    allow_reuse_address = False          # Windows: SO_REUSEADDR ทำให้สองโปรแกรมฟังพอร์ตเดียวกันได้ → คำขอไปผิดตัว
    daemon_threads = True


def _handoff():
    """หยุดรับคำขอ → (main) ปิด socket → เปิดตัวประมวลผลจริงที่พอร์ตเดิม"""
    time.sleep(0.5)
    HANDOFF.set()
    SERVER.shutdown()


def main():
    global SERVER
    tok = token()
    web = (engine_cfg().get('web_url') or '').strip()
    url = f'{web}#pair={tok}&engine=http://127.0.0.1:{PORT}' if web else f'http://127.0.0.1:{PORT}/ui/'
    SERVER = _Server(('127.0.0.1', PORT), H)
    print(f'{APP_NAME} {APP_VERSION} — ตัวช่วยติดตั้ง')
    print(f'โฟลเดอร์แอป: {ROOT}')
    print(f'เปิดหน้าเว็บ: {url}')
    if '--no-browser' not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    SERVER.serve_forever()
    SERVER.server_close()                                   # ปล่อยพอร์ตก่อน แล้วค่อยเปิดตัวประมวลผล
    if HANDOFF.is_set():
        print('ติดตั้งเสร็จ — กำลังเปิดตัวประมวลผล…', flush=True)
        sys.exit(subprocess.call([sys.executable, '-m', 'app.server', '--wait-port', '--no-browser'], cwd=str(ROOT), env=CHILD_ENV))


if __name__ == '__main__':
    main()
