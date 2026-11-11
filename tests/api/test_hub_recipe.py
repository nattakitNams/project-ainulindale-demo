# -*- coding: utf-8 -*-
"""Data hub เป็นทางหลัก: ผู้ช่วยดึงไฟล์ย่อยจากชุดที่ต้นทางลงไว้เป็น ZIP เอง แล้วคำนวณ % (เน็ตจริง · โมเดลจำลอง)
- WorldPop "Age and Gender Structures (2015-2030)" บน HDX มีแต่ ZIP ปีละไฟล์ → get_hub_item เปิดโฟลเดอร์ต้นทาง เจอ GeoTIFF รายช่วงอายุ/เพศ
- สูตรงาน: download years+match+must+combine sum (60+ = 7 ไฟล์ · ทั้งหมด = ทุกช่วงอายุ 20 ไฟล์) → summary ratio_to → % ผู้สูงอายุ
- ด่าน: URL นอกโฟลเดอร์ต้นทาง/นอก Data hub ถูกปฏิเสธ · match ที่ไม่มีไฟล์ถูกปฏิเสธตั้งแต่ตอนเสนอ"""
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ENGINE, Results, session as s, wait_engine  # noqa: E402

try:
    requests.head('https://data.worldpop.org/GIS/', timeout=30)
except requests.RequestException:
    print('ข้าม: ต่อ data.worldpop.org ไม่ได้')
    sys.exit(0)

wait_engine()
R = Results()
K = 'ckan:data:worldpop-age-and-gender-structures-2015-2030-tha'
STATE, SEEN = {}, {}


def call(name, args, i=0):
    return {'id': f'c{i}_{name}', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}


class Mock(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, o):
        b = json.dumps(o, ensure_ascii=False).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        self._send({'data': [{'id': 'mock-hub'}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)))
        m = body['messages']
        lu = max(i for i, x in enumerate(m) if x['role'] == 'user')
        after = [x for x in m[lu + 1:] if x['role'] == 'tool']
        r = lambda calls=None, text=None: self._send({'choices': [{'message': {'role': 'assistant', 'content': text, 'tool_calls': calls}}]})
        u = m[lu]['content']
        if u.startswith('ITEM'):
            if not after:
                return r([call('get_hub_item', dict(key=K)), call('get_hub_item', dict(key=K, years=[2020], match='_t_60_,_t_65_', must='1km'), 1)])
            SEEN['item'], SEEN['item_f'] = json.loads(after[0]['content']), json.loads(after[1]['content'])
            return r(text='ok')
        if u.startswith('BAD'):
            if not after:
                return r([call('propose_download_data', dict(hub_key=K, file_url='https://data.worldpop.org/GIS/evil/tha_t_60_2020.tif', name='x', purpose='p')),
                          call('propose_recipe', dict(title='ผิด', purpose='p', steps_json=json.dumps([dict(id='s1', kind='download', params=dict(
                              hub_key=K, years=[2020], match=['_q_99_'], value_type='count'))])), 1)])
            SEEN['bad'] = [json.loads(x['content']) for x in after]
            return r(text='ok')
        if u.startswith('RECIPE'):
            if not after:
                return r([call('propose_recipe', dict(title='ผู้สูงอายุ 2020', purpose='สัดส่วนผู้สูงอายุ 60+', steps_json=json.dumps(STATE['steps'], ensure_ascii=False)))])
            SEEN['prop'] = json.loads(after[-1]['content'])
            return r(text='เสนอแล้ว')
        r(text='ok')


srv = ThreadingHTTPServer(('127.0.0.1', 0), Mock)
threading.Thread(target=srv.serve_forever, daemon=True).start()


def api(path, body=None, method=None):
    return s.request(method or ('POST' if body is not None else 'GET'), ENGINE + path, json=body, timeout=900).json()


def chat(text):
    return api('/api/ai/chat', dict(messages=[dict(role='user', content=text)], chat_id='chub'))


api('/api/ai', dict(enabled=True, mode='propose'), 'PATCH')
api('/api/ai/login', dict(provider='compat', api_key='k', base_url=f'http://127.0.0.1:{srv.server_address[1]}/v1'))
aoi = [a for a in api('/api/aoi') if a.get('builtin')][0]['id']

chat('ITEM')
it, itf = SEEN.get('item') or {}, SEEN.get('item_f') or {}
R.check('ชุดที่ต้นทางมีแต่ ZIP → แอปเปิดโฟลเดอร์ต้นทาง เจอ GeoTIFF แยก + ปีครบ 2015–2030', (it.get('browsed_source_folders') or {}).get('files_found', 0) > 50
        and it.get('years_available', [None])[0] == 2015 and it['years_available'][-1] == 2030, it.get('browsed_source_folders'))
R.check('file_patterns บอกชนิดไฟล์ (ปี → {year}) แทนการส่งทุก URL', any(p['pattern'].startswith('tha_t_65_{year}') for p in it.get('file_patterns') or []))
R.check('years + match + must → เฉพาะไฟล์ที่ต้องการ', sorted(f['name'] for f in itf.get('downloadable_files') or []) == ['tha_t_60_2020_CN_1km_R2025A_UA_v1.tif', 'tha_t_65_2020_CN_1km_R2025A_UA_v1.tif'],
        [f['name'] for f in itf.get('downloadable_files') or []])
r = api(f'/api/hub/browse?key={K}&years=2020&match=_t_60_&must=1km')
R.check('หน้า Data hub: /api/hub/browse ได้ไฟล์เดียวกัน', r.get('total') == 1 and r['files'][0]['name'].startswith('tha_t_60_2020'), r.get('total'))

chat('BAD')
bad = SEEN.get('bad') or [{}, {}]
R.check('URL นอกรายการ (แม้โฮสต์เดียวกัน) → ปฏิเสธ', 'error' in bad[0], bad[0])
R.check('match ที่ไม่มีไฟล์ → ปฏิเสธตั้งแต่ตอนเสนอ', 'error' in bad[1] and 'ไม่พบไฟล์' in bad[1]['error'], bad[1])

STATE['steps'] = [
    dict(id='s1', title='60+ ปี 2020', kind='download', params=dict(hub_key=K, years=[2020], match=['_t_60_', '_t_65_', '_t_70_', '_t_75_', '_t_80_', '_t_85_', '_t_90_'],
                                                              must=['1km'], combine='sum', name='pop60plus_{year}', value_type='count', aoi_id=aoi)),
    dict(id='s2', title='ทั้งหมด 2020', kind='download', params=dict(hub_key=K, years=[2020], match=['_t_'], must=['1km'], combine='sum',     # 1 กม. ไม่มี T_F/T_M (มีแค่ 100 ม.) → รวมทุกช่วงอายุ 20 ไฟล์
                                                                name='pop_total_{year}', value_type='count', aoi_id=aoi)),
    dict(id='s3', title='% ผู้สูงอายุ', kind='summary', params=dict(dataset_ids='$s1', ratio_to='$s2'))]
out = chat('RECIPE')
if not out['proposals']:
    print('ข้อเสนอถูกปฏิเสธ:', SEEN.get('prop')); sys.exit(1)
pr = out['proposals'][0]
chk = {c['step']: c for c in pr['estimate']['checks']}
R.check('การ์ดสูตรงานบอกไฟล์ที่จะโหลดต่อปี + ขนาดรวม', len(chk['s1']['files']['2020']) == 7 and len(chk['s2']['files']['2020']) == 20 and chk['s1']['total_mb'] > 5,
        (chk['s1']['files'], chk['s1']['total_mb']))
t0 = time.time()
rid = api('/api/ai/confirm', dict(id=pr['id']))['recipe_id']
while time.time() - t0 < 1500:
    rr = api(f'/api/recipes/{rid}')
    if rr['status'] not in ('queued', 'running'):
        break
    time.sleep(3)
st = {x['id']: x for x in rr['steps']}
tbl = (st['s3'].get('review') or {}).get('table') or [{}]
pct = tbl[0].get('pct_of_ref')
R.check('ดาวน์โหลด 27 ไฟล์ + รวมต่อปี (20 ไฟล์ = calc 2 รอบ ทีละ ≤ 12) → ชุดเดียวต่อปี (ผล {ปี: #id})', rr['status'] == 'done' and list((st['s1']['output'] or {}).keys()) == ['2020'] and len(st['s1'].get('job_ids') or []) == 8,
        f'{rr["status"]} {time.time() - t0:.0f}s · ' + ' · '.join(f'{x["id"]}:{x["status"]} {x.get("error") or ""}' for x in rr['steps']))
R.check('% ผู้สูงอายุ 60+ ของไทยปี 2020 สมเหตุสมผล (15–25%)', pct is not None and 15 < pct < 25, f'{pct}' + (f' · 60+ {tbl[0]["sum"]:,.0f} คน' if tbl[0].get('sum') else ''))
api('/api/ai/logout', {})
sys.exit(R.done())
