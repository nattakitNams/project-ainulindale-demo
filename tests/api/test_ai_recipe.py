# -*- coding: utf-8 -*-
"""สูตรงาน + ประหยัดโทเคน (โมเดลจำลองแบบ OpenAI ในตัว)
- ผู้ช่วยเสนอสูตร 4 ขั้น (calc → calc อ้าง $s1 → ไบแวเรียต target_res auto → สถิติ) → ยืนยันครั้งเดียว → แอปรันเองครบ ไม่เรียกโมเดลระหว่างทาง
- ขั้นพลาด → หยุด ขั้นถัดไป "ข้าม" + สรุปบอกสาเหตุ · อ้างขั้นที่ไม่มี → ปฏิเสธตั้งแต่ตอนเสนอ
- ประหยัดโทเคน: ประวัติเก่าถูกย่อ · ส่วนคงที่ของ system แยกไว้ต้น (แคชได้) · นับโทเคนจาก usage ของผู้ให้บริการ"""
import json
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ENGINE, Results, session as s, wait_engine  # noqa: E402

wait_engine()
R = Results()
KEY = 'mock-test-key'
SEEN = dict(calls=0)
STATE = {}


def call(name, args, i=0):
    return {'id': f'c{i}_{name}', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}


class Mock(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, o):
        b = json.dumps(o, ensure_ascii=False).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        self._send({'data': [{'id': 'mock-recipe'}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)))
        m = body['messages']
        SEEN['calls'] += 1
        SEEN['roles'] = [x['role'] for x in m[:3]]
        SEEN['first_user'] = next((x['content'] for x in m if x['role'] == 'user'), '')
        lu = max(i for i, x in enumerate(m) if x['role'] == 'user')
        after = m[lu + 1:]
        usage = {'prompt_tokens': 15000, 'completion_tokens': 300, 'prompt_tokens_details': {'cached_tokens': 12000}}
        r = lambda calls=None, text=None: self._send({'choices': [{'message': {'role': 'assistant', 'content': text, 'tool_calls': calls}}], 'usage': usage})
        u = m[lu]['content']
        if u.startswith('RECIPE'):
            if not after:
                return r([call('propose_recipe', dict(title='ทดสอบสูตร', purpose='ทดสอบรันเอง', steps_json=json.dumps(STATE['steps'], ensure_ascii=False)))])
            SEEN['propose_result'] = json.loads(after[-1]['content'])
            return r(text='เสนอสูตรแล้ว')
        r(text='ok')


srv = ThreadingHTTPServer(('127.0.0.1', 0), Mock)
threading.Thread(target=srv.serve_forever, daemon=True).start()


def api(path, body=None, method=None):
    return s.request(method or ('POST' if body is not None else 'GET'), ENGINE + path, json=body, timeout=600).json()


api('/api/ai', dict(enabled=True, mode='propose'), 'PATCH')
api('/api/ai/login', dict(provider='compat', api_key=KEY, base_url=f'http://127.0.0.1:{srv.server_address[1]}/v1'))

TMP = Path(tempfile.mkdtemp(prefix='ainu_recipe_'))
rng = np.random.default_rng(5)


def tif(name, a):
    p = TMP / name
    with rasterio.open(p, 'w', driver='GTiff', width=80, height=60, count=1, dtype='float32', crs='EPSG:4326',
                       transform=from_origin(100, 14, 1 / 120, 1 / 120), nodata=-1) as d:
        d.write(a.astype('float32'), 1)
    api('/api/datasets', dict(paths=[str(p)]))
    did = [x for x in api('/api/datasets') if x['path'] == str(p)][-1]['id']
    api(f'/api/datasets/{did}', dict(value_type='density', value_type_confirmed=True), 'PATCH')
    return did


X = rng.uniform(0, 10, (60, 80))
xa, ya = tif('rc_x.tif', X), tif('rc_y.tif', 3 * X + rng.normal(0, 1, (60, 80)))
src = [o for o in api(f'/api/res-options?ids={xa}')['options'] if o['is_source']][0]['value']
STATE['steps'] = [
    dict(id='s1', title='สองเท่า', kind='calc', params=dict(expr='A * 2', vars=dict(A=dict(dataset_id=xa)), target_res=src, name='rc_s1')),
    dict(id='s2', title='ลบต้นฉบับ', kind='calc', params=dict(expr='B - A', vars=dict(A=dict(dataset_id=xa), B=dict(dataset_id='$s1')), target_res='auto', name='rc_s2')),
    dict(id='s3', title='ไบแวเรียต', kind='bivariate', params=dict(x=dict(dataset_id='$s2', n=3, method='quantile', metric='value'),
                                                                  y=dict(dataset_id=ya, n=3, method='quantile', metric='value'), target_res='auto', name='rc_biv')),
    dict(id='s4', title='สถิติ', kind='stats', params=dict(dataset_id='$s3'))]


def chat(text, hist):
    hist.append(dict(role='user', content=text))
    out = api('/api/ai/chat', dict(messages=hist, chat_id='crecipe'))
    hist.append(dict(role='assistant', content=out.get('reply') or ''))
    return out


def run_recipe():
    n0 = SEEN['calls']
    out = chat('RECIPE ทำให้หน่อย', [])
    pr = out['proposals'][0]
    c = api('/api/ai/confirm', dict(id=pr['id']))
    rid = c['recipe_id']
    t0 = time.time()
    while time.time() - t0 < 600:
        r = api(f'/api/recipes/{rid}')
        if r['status'] not in ('queued', 'running'):
            break
        time.sleep(2)
    return out, pr, r, SEEN['calls'] - n0


out, pr, r, ncalls = run_recipe()
st = {x['id']: x for x in r['steps']}
with rasterio.open([d for d in api('/api/datasets') if d['id'] == st['s2']['output']][0]['path']) as d:
    s2 = d.read(1, masked=True)
R.check('ยืนยันครั้งเดียว → แอปรันครบ 4 ขั้นเอง (calc → calc อ้าง $s1 → ไบแวเรียต auto → สถิติ)', r['status'] == 'done' and all(x['status'] == 'done' for x in r['steps']),
        ' · '.join(f'{x["id"]}:{x["status"]}→#{x["output"]}' for x in r['steps']))
R.check('ผลถูก: s2 = 2X − X = X ทุกพิกเซล · สถิติ ρ > 0.9 (Y = 3X + noise)', np.allclose(s2.compressed(), X.astype('float32').ravel(), atol=1e-4)
        and st['s4']['review']['stats']['spearman_rho'] > 0.9, f'ρ {st["s4"]["review"]["stats"]["spearman_rho"]:.3f}')
R.check('ระหว่างรันไม่เรียกโมเดลเลย (เรียกแค่ตอนเสนอ 2 รอบ)', ncalls == 2, f'{ncalls} รอบ')
R.check('สรุปผลรวมสำหรับส่งกลับแชต มีทุกขั้น + #ชุด + ค่าสถิติ', all(f'#{x["output"]}' in r['summary'] for x in r['steps'][:3]) and 'spearman_rho' in r['summary'], r['summary'][:160])
R.check('การ์ดสูตรงานมีขั้นตอนครบ + ตรวจขั้นที่ไม่พึ่งขั้นก่อนแล้ว', pr['action'] == 'recipe' and len(pr['args']['steps']) == 4 and pr['estimate']['checks'][0]['ok'])

STATE['steps'] = [dict(id='s1', title='สูตรผิด', kind='calc', params=dict(expr='A * 2', vars=dict(A=dict(dataset_id=999999)), target_res=src)),
                  dict(id='s2', title='ต่อจาก s1', kind='calc', params=dict(expr='A + 1', vars=dict(A=dict(dataset_id='$s1')), target_res='auto'))]
out = chat('RECIPE', [])
R.check('ขั้นที่ตรวจได้แต่ผิด (ชุดไม่มีอยู่) → ปฏิเสธตั้งแต่ตอนเสนอ ไม่สร้างการ์ด', not out['proposals'] and 'error' in SEEN['propose_result'], str(SEEN['propose_result'])[:120])
STATE['steps'] = [dict(id='s1', title='ดี', kind='calc', params=dict(expr='A * 2', vars=dict(A=dict(dataset_id=xa)), target_res=src)),
                  dict(id='s2', title='อ้างผิด', kind='calc', params=dict(expr='A + 1', vars=dict(A=dict(dataset_id='$s9')), target_res='auto'))]
out = chat('RECIPE', [])
R.check('อ้าง $s9 ที่ไม่มี → ปฏิเสธตั้งแต่ตอนเสนอ', not out['proposals'] and 's9' in str(SEEN['propose_result']))
STATE['steps'] = [dict(id='s1', title='ดี', kind='calc', params=dict(expr='A * 2', vars=dict(A=dict(dataset_id=xa)), target_res=src)),
                  dict(id='s2', title='พังตอนรัน', kind='calc', params=dict(expr='nope(A)', vars=dict(A=dict(dataset_id='$s1')), target_res='auto')),
                  dict(id='s3', title='ต่อจาก s2', kind='calc', params=dict(expr='A', vars=dict(A=dict(dataset_id='$s2')), target_res='auto'))]
out, pr, r, _ = run_recipe()
R.check('ขั้นพังตอนรัน → หยุด · ขั้นถัดไป "ข้าม" · สรุปบอกสาเหตุ', r['status'] == 'failed' and [x['status'] for x in r['steps']] == ['done', 'failed', 'skipped'] and 'nope' in r['summary'],
        r['summary'][:200])

# ---------- 1.0.44 งานรายปี: for_years · "$s1.{year}" · summary (ผลรวม + % เทียบ) · trend "items":"$sN" ----------
STATE['steps'] = [
    dict(id='s1', title='ค่าคงที่ = ปี', kind='calc', for_years=[2015, 2016, 2017], params=dict(expr='A * 0 + {year}', vars=dict(A=dict(dataset_id=xa)), target_res=src, name='ry_year_{year}')),
    dict(id='s2', title='สองเท่า รายปี', kind='calc', for_years='$s1', params=dict(expr='A * 2', vars=dict(A=dict(dataset_id='$s1.{year}')), target_res='auto', name='ry_double_{year}')),
    dict(id='s3', title='สรุป', kind='summary', params=dict(dataset_ids='$s2', ratio_to='$s1')),
    dict(id='s4', title='แนวโน้ม', kind='trend', params=dict(items='$s2', stat='slope', target_res='auto', name='ry_slope'))]
out, pr, r, _ = run_recipe()
st = {x['id']: x for x in r['steps']}
R.check('for_years: ทำซ้ำทุกปี ผลเป็น {ปี: #id} · "$s1.{year}" อ้างผลปีเดียวกัน', r['status'] == 'done' and sorted(map(str, (st['s2']['output'] or {}).keys())) == ['2015', '2016', '2017'],
        ' · '.join(f'{x["id"]}:{x["status"]}→{x.get("output")}{" " + x["error"] if x.get("error") else ""}' for x in r['steps']))
tbl = (st['s3'].get('review') or {}).get('table') or []
npx = X.size
R.check('summary: ผลรวมถูก (2 × ปี × จำนวนพิกเซล) และ % เทียบ s1 = 200%', len(tbl) == 3 and all(abs(t['sum'] - 2 * int(t['key']) * npx) < 1e-3 * npx * int(t['key']) and abs(t['pct_of_ref'] - 200) < 1e-6 for t in tbl),
        [(t['key'], t.get('sum'), t.get('pct_of_ref')) for t in tbl])
if r['status'] == 'done':
    with rasterio.open([d for d in api('/api/datasets') if d['id'] == st['s4']['output']][0]['path']) as d:
        sl = d.read(1, masked=True)
    R.check('trend "items":"$s2" → ใช้ทุกปีเรียงเอง (ความชัน = 2 ต่อปีทุกพิกเซล)', np.allclose(sl.compressed(), 2, atol=1e-4), float(sl.mean()))
R.check('สรุปส่งกลับแชตมีตาราง % ต่อปี', '200.00%' in (r.get('summary') or ''), (r.get('summary') or '')[-200:])

# ---------- ประหยัดโทเคน ----------
hist = []
for i in range(20):
    hist += [dict(role='user', content=f'คำถามเก่า {i} ' + 'ก' * 2000), dict(role='assistant', content='คำตอบยาว ' + 'ข' * 3000)]
out = chat('สวัสดี', hist)
R.check('ประวัติเก่าถูกย่อ (ข้อความแรกเหลือ ≤ 2,050 ตัวอักษร — 1.0.44 คืนจาก 400) · ส่วนคงที่ของ system แยกขึ้นก่อน', 450 < len(SEEN['first_user']) <= 2050 and SEEN['roles'][:2] == ['system', 'system'],
        f'{len(SEEN["first_user"])} ตัวอักษร · {SEEN["roles"]}')
R.check('นับโทเคนจาก usage ของผู้ให้บริการ (ส่ง/แคช/ตอบ/รอบ)', out.get('usage') == dict(calls=1, input=15000, cached=12000, output=300), str(out.get('usage')))
api('/api/ai/logout', {})
sys.exit(R.done())
