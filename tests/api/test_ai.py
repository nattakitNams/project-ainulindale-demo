# -*- coding: utf-8 -*-
"""ผู้ช่วย AI ขั้นที่ 1 — ทดสอบกับเซิร์ฟเวอร์จำลองแบบ OpenAI-compatible ในเครื่อง (ไม่ต้องมี API key จริง ไม่ออกอินเทอร์เน็ต)
ล็อกอิน (key ผิด/ถูก) · key ไม่ถูกส่งกลับ/ไม่อยู่ในไฟล์แบบอ่านออก · แชต + บริบทคลัง · เปลี่ยนรุ่น · ออกจากระบบ · ปิดใช้"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ENGINE, Results, session as s, wait_engine  # noqa: E402

KEY = 'mock-test-key'
LAST = {}


class Mock(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _ok(self):
        if self.headers.get('Authorization') == f'Bearer {KEY}':
            return True
        self._send(401, {'error': {'message': 'bad key'}})

    def do_GET(self):
        if self.path == '/v1/models' and self._ok():
            self._send(200, {'data': [{'id': 'mock-small'}, {'id': 'mock-large'}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
        if self.path == '/v1/chat/completions' and self._ok():
            LAST.clear(); LAST.update(body)
            self._send(200, {'choices': [{'message': {'content': f'ok:{body["model"]}:{body["messages"][-1]["content"]}'}}]})

    def log_message(self, *a):
        pass


srv = ThreadingHTTPServer(('127.0.0.1', 0), Mock)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f'http://127.0.0.1:{srv.server_address[1]}/v1'

wait_engine()
R = Results()


def api(path, body=None, method=None):
    r = s.request(method or ('POST' if body is not None else 'GET'), ENGINE + path, json=body, timeout=60)
    try:
        return r.status_code, r.json()
    except ValueError:                       # เช่น 405 ของ Flask เป็น HTML
        return r.status_code, {}


api('/api/ai', dict(enabled=False), 'PATCH')
c, j = api('/api/ai/chat', dict(messages=[dict(role='user', content='hi')]))
R.check('ปิดอยู่ → แชตไม่ได้', c == 400 and 'ปิด' in j['error'], j.get('error'))
api('/api/ai', dict(enabled=True), 'PATCH')
c, j = api('/api/ai/login', dict(provider='compat', api_key='wrong', base_url=BASE))
R.check('key ผิด → ปฏิเสธ', c == 400 and 'ไม่ถูกต้อง' in j['error'], j.get('error'))
c, j = api('/api/ai/login', dict(provider='compat', api_key=KEY, base_url=BASE))
R.check('key ถูก → เชื่อมต่อ + รายการรุ่น', c == 200 and j['connected'] and j['models'] == ['mock-small', 'mock-large'], j.get('model'))
c, st = api('/api/ai')
R.check('สถานะไม่มี key/secret_id', KEY not in json.dumps(st) and 'secret_id' not in st)
c, sysi = api('/api/system')
ws = Path(sysi['dirs']['aoi']['path']).parent
plain = [p.name for p in (ws / 'secrets.json', ws / 'ai.json') if p.exists() and KEY in p.read_text(encoding='utf-8')]
R.check('key ไม่อยู่ในไฟล์แบบอ่านออก (เข้ารหัส DPAPI)', not plain, plain)
c, j = api('/api/ai/chat', dict(messages=[dict(role='user', content='สวัสดี')], page='#/biv'))
sysmsg = ' '.join(m.get('content', '') for m in LAST.get('messages', []) if m.get('role') == 'system')
R.check('แชต → ตอบ + ส่ง system prompt พร้อมบริบทคลัง/หน้า', c == 200 and j['reply'] == 'ok:mock-small:สวัสดี' and 'Ainulindalë' in sysmsg and '#/biv' in sysmsg,
        f'{len(sysmsg):,} ตัวอักษร')
api('/api/ai', dict(model='mock-large'), 'PATCH')
c, j = api('/api/ai/chat', dict(messages=[dict(role='user', content='a'), dict(role='assistant', content='b'), dict(role='user', content='c')]))
R.check('เปลี่ยนรุ่น + ส่งประวัติต่อเนื่อง', j.get('reply') == 'ok:mock-large:c' and len([m for m in LAST['messages'] if m['role'] != 'system']) == 3)
c, j = api('/api/ai/models')
R.check('รายการรุ่นต้องเป็น POST (GET ไม่มี Origin กระตุ้นใช้ key ไม่ได้)', c == 405)
c, j = api('/api/ai/logout', {})
c2, j2 = api('/api/ai/chat', dict(messages=[dict(role='user', content='hi')]))
R.check('ออกจากระบบ → ลบ key · แชตไม่ได้', not j['connected'] and c2 == 400)
api('/api/ai', dict(enabled=False), 'PATCH')
srv.shutdown()
sys.exit(R.done())
