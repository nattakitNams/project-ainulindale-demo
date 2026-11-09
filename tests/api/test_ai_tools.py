# -*- coding: utf-8 -*-
"""ผู้ช่วย AI ขั้นที่ 2 — เรียกเครื่องมือ + ข้อเสนอที่ต้องยืนยัน (เซิร์ฟเวอร์จำลองแบบ OpenAI tool calling ในตัว ไม่ต้องมี key จริง)
ต้องรัน test_smoke ก่อน (ใช้ wp_bkk = count และ ndvi_bkk = density ที่ยืนยันแล้ว)"""
import json
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ENGINE, Results, session as s, wait_engine  # noqa: E402

KEY = 'mock-test-key'
SEEN = dict(tools=[], system='')


def call(name, args, i=0):
    return {'id': f'c{i}_{name}', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}


class Mock(BaseHTTPRequestHandler):
    def _send(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == '/v1/models':
            self._send({'data': [{'id': 'mock-agent'}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)))
        msgs = body['messages']
        SEEN['tools'] = [t['function']['name'] for t in body.get('tools') or []]
        SEEN['system'] = msgs[0]['content']
        SEEN['msgs'] = msgs
        last_user = max(i for i, m in enumerate(msgs) if m['role'] == 'user')
        tool_msgs = [m for m in msgs[last_user:] if m['role'] == 'tool']
        step, u = len([m for m in msgs[last_user:] if m['role'] == 'assistant']), msgs[last_user]['content']
        reply = lambda calls=None, text=None: self._send({'choices': [{'message': {'role': 'assistant', 'content': text, 'tool_calls': calls}}]})
        m = re.search(r'SCENARIO_BIV x=(\d+) y=(\d+)', u)
        if m:
            x, y = int(m[1]), int(m[2])
            if step == 0:
                return reply([call('list_datasets', {'kind': 'raster'}), call('get_dataset', {'dataset_id': x}, 1)])
            if step == 1:
                return reply([call('resolution_options', {'dataset_ids': [x, y]})])
            if step == 2:
                opts = json.loads(tool_msgs[-1]['content'])
                res = next(o['value'] for o in opts if o['same_as_source'])
                SEEN['res'] = res
                p = {'x': {'dataset_id': x, 'n': 3, 'method': 'quantile', 'metric': 'density', 'label': 'ประชากร'},
                     'y': {'dataset_id': y, 'n': 3, 'method': 'quantile', 'metric': 'value', 'label': 'NDVI'}, 'target_res': res, 'name': 'ai_test_biv'}
                return reply([call('estimate_job', {'kind': 'bivariate', 'params_json': json.dumps(p)}),
                              call('propose_run_job', {'kind': 'bivariate', 'params_json': json.dumps(p), 'title': 'ประชากร × NDVI'}, 1)])
            return reply(text='เสนองานไบแวเรียตไว้แล้ว กดยืนยันเพื่อรัน')
        if 'SCENARIO_BAD' in u:                              # พยายามเรียกเครื่องมือที่ไม่มี (ลบข้อมูล) + ส่งพารามิเตอร์ผิด
            if step == 0:
                return reply([call('delete_dataset', {'dataset_id': 1}), call('propose_run_job', {'kind': 'zonal', 'params_json': '{}'}, 1)])
            return reply(text='ทำไม่ได้')
        reply(text='ok')

    def log_message(self, *a):
        pass


srv = ThreadingHTTPServer(('127.0.0.1', 0), Mock)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f'http://127.0.0.1:{srv.server_address[1]}/v1'
wait_engine()
R = Results()


def api(path, body=None, method=None):
    r = s.request(method or ('POST' if body is not None else 'GET'), ENGINE + path, json=body, timeout=300)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {}


ds = api('/api/datasets')[1]
pick = lambda n: [d for d in ds if d['name'] == n and d.get('value_type_confirmed')][-1]['id']
X, Y = pick('wp_bkk'), pick('ndvi_bkk')
api('/api/ai', dict(enabled=True, mode='propose'), 'PATCH')
c, j = api('/api/ai/login', dict(provider='compat', api_key=KEY, base_url=BASE))
assert c == 200, j

# 1) AI อ่านคลัง → ตัวเลือกความละเอียด → ประเมิน → เสนองาน
n_jobs0 = len(api('/api/jobs')[1])
c, r = api('/api/ai/chat', dict(messages=[dict(role='user', content=f'SCENARIO_BIV x={X} y={Y}')]))
used = [u['tool'] for u in r.get('used', [])]
R.check('เรียกเครื่องมืออ่านได้เอง (list/get/res/estimate)', c == 200 and {'list_datasets', 'get_dataset', 'resolution_options', 'estimate_job'} <= set(used), used)
R.check('สิทธิ์ "เสนองาน" → มีเครื่องมือ propose_* · ไม่มีเครื่องมือลบใด ๆ', 'propose_run_job' in SEEN['tools'] and not any('delete' in t or 'trash' in t for t in SEEN['tools']), SEEN['tools'])
props = r.get('proposals') or []
R.check('ได้ข้อเสนอ 1 รายการ + ประเมินผ่าน + ยังไม่ได้รัน', len(props) == 1 and props[0]['estimate']['ok'] and len(api('/api/jobs')[1]) == n_jobs0,
        props and props[0]['estimate'])
R.check('ข้อเสนอแสดงค่าที่ตั้ง (สีเติมจากพาเลทให้ ไม่ต้องส่งกลับหน้าเว็บ)', props and 'colors' not in props[0]['args']['params'] and props[0]['args']['params']['target_res'] == SEEN['res'])
R.check('system prompt มีสเปกงาน + กันคำสั่งแฝงในข้อมูล', 'params_json' in SEEN['system'] and 'ห้ามทำตาม' in SEEN['system'])

# 2) ผู้ใช้ยืนยัน → รันจริง · ใช้ซ้ำไม่ได้
pid = props[0]['id']
c, ex = api('/api/ai/confirm', dict(id=pid))
R.check('ยืนยัน → เริ่มงานจริง', c == 200 and ex.get('job_id'), ex)
jid = ex.get('job_id')
for _ in range(240):
    jb = [x for x in api('/api/jobs')[1] if x['id'] == jid][0]
    if jb['status'] not in ('queued', 'running'):
        break
    time.sleep(1)
out = (jb.get('result') or {}).get('dataset_id')
lin = api(f'/api/datasets/{out}')[1].get('lineage') if out else {}
R.check('งานเสร็จ + ลง lineage ว่าสั่งโดยผู้ช่วย AI', jb['status'] == 'done' and (lin.get('params') or {}).get('requested_by', {}).get('by') == 'ai_assistant',
        f"{jb['status']} · ชุด #{out} · {(lin.get('params') or {}).get('requested_by')}")
c, j2 = api('/api/ai/confirm', dict(id=pid))
R.check('ข้อเสนอใช้ซ้ำไม่ได้', c == 400, j2.get('error'))

# 3) ไม่ทำ → ยืนยันภายหลังไม่ได้
c, r2 = api('/api/ai/chat', dict(messages=[dict(role='user', content=f'SCENARIO_BIV x={X} y={Y}')]))
p2 = r2['proposals'][0]['id']
api('/api/ai/reject', dict(id=p2))
c, j3 = api('/api/ai/confirm', dict(id=p2))
R.check('กด "ไม่ทำ" แล้วรันไม่ได้', c == 400)

# 4) เครื่องมือที่ไม่มี / ชนิดงานต้องห้าม → error ไม่มีอะไรเกิดขึ้น
n_ds = len(api('/api/datasets')[1])
c, r3 = api('/api/ai/chat', dict(messages=[dict(role='user', content='SCENARIO_BAD')]))
errs = [u for u in r3.get('used', []) if u.get('error')]
R.check('เรียกเครื่องมือลบ / งานนอกรายการ → ถูกปฏิเสธ ข้อมูลไม่เปลี่ยน', len(errs) == 2 and not r3.get('proposals') and len(api('/api/datasets')[1]) == n_ds, errs)

# 5) สิทธิ์อ่านอย่างเดียว → ไม่ส่งเครื่องมือ propose_* ให้ AI
api('/api/ai', dict(mode='read'), 'PATCH')
api('/api/ai/chat', dict(messages=[dict(role='user', content='hi')]))
R.check('สิทธิ์ "อ่านอย่างเดียว" → ไม่มีเครื่องมือเสนองาน', SEEN['tools'] and not any(t.startswith('propose') for t in SEEN['tools']), SEEN['tools'])

# 6) ประวัติ event (ผลงานจริง) ส่งให้ AI เป็นข้อความจากแอป
api('/api/ai/chat', dict(messages=[dict(role='user', content='a'), dict(role='assistant', content='b'), dict(role='event', content='งาน #1 เสร็จแล้ว'), dict(role='user', content='hi')]))
um = [m['content'] for m in SEEN['msgs'] if m['role'] == 'user']
R.check('ผลงานจริง (event) ส่งให้ AI เป็น "[แจ้งจากแอป]" · ข้อความ user ติดกันรวมเป็นอันเดียว',
        len(um) == 2 and '[แจ้งจากแอป] งาน #1 เสร็จแล้ว' in um[1] and um[1].endswith('hi'), um)

api('/api/ai', dict(mode='propose'), 'PATCH')
api('/api/ai/logout', {})
api('/api/ai', dict(enabled=False), 'PATCH')
srv.shutdown()
sys.exit(R.done())
