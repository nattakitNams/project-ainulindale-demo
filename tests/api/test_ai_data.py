# -*- coding: utf-8 -*-
"""ผู้ช่วย AI หาข้อมูลจาก Data hub → ดาวน์โหลดเข้าคลัง (ตัดตามพื้นที่ศึกษา) → ไบแวเรียต — ใช้อินเทอร์เน็ตจริง (Zenodo + WorldPop)
โมเดลจำลองเรียกเครื่องมือตามลำดับที่ system prompt กำหนด · ไม่มีเน็ต → ข้าม"""
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ENGINE, Results, session as s, wait_engine  # noqa: E402

for _try in range(3):                                      # Zenodo ช้าเป็นช่วง ๆ → ลองซ้ำก่อนสรุปว่าไม่มีเน็ต
    try:
        requests.head('https://zenodo.org', timeout=30)
        break
    except requests.RequestException:
        time.sleep(5)
else:
    raise SystemExit('ข้าม: ไม่มีอินเทอร์เน็ต / Zenodo ไม่ตอบ')

PURPOSE = 'ดูความสัมพันธ์ระหว่างแสงไฟกลางคืนกับประชากร ทั้งประเทศ'
STATE = {}


def call(name, args, i=0):
    return {'id': f'c{i}', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}


class Mock(BaseHTTPRequestHandler):
    def _send(self, o):
        b = json.dumps(o).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        self._send({'data': [{'id': 'mock-data'}]})

    def do_POST(self):
        m = json.loads(self.rfile.read(int(self.headers['Content-Length'])))['messages']
        lu = max(i for i, x in enumerate(m) if x['role'] == 'user')
        step = len([x for x in m[lu:] if x['role'] == 'assistant'])
        tools = [json.loads(x['content']) for x in m[lu:] if x['role'] == 'tool']
        r = lambda calls=None, text=None: self._send({'choices': [{'message': {'role': 'assistant', 'content': text, 'tool_calls': calls}}]})
        u = m[lu]['content']
        if u.startswith('NOTE '):
            if step == 0:
                return r([call('write_dataset_note', dict(dataset_id=int(u.split()[1]), text='ไบแวเรียตประชากร (WorldPop 2020, คน/ตร.กม.) × แสงไฟกลางคืน (VIIRS 2020) ทั้งประเทศ 30″ — ทำเพื่อดูความสัมพันธ์ระหว่างสองตัวแปร'))])
            return r(text='เขียนโน้ตแล้ว')
        if u.startswith('หาข้อมูล'):
            if step == 0:
                return r([call('search_data_hub', {'query': 'nighttime lights'}), call('search_data_hub', {'query': 'population worldpop'}, 1)])
            if step == 1:
                nl, pop = tools[-2]['results'][0]['key'], [x for x in tools[-1]['results'] if '2015-2030' in x['title']][0]['key']
                STATE.update(nl_key=nl, pop_key=pop)
                return r([call('get_hub_item', {'key': nl}), call('get_hub_item', {'key': pop}, 1)])
            if step == 2:
                nl, pop = tools[-2], tools[-1]
                STATE['nl_years'], STATE['pop_years'] = nl['years_available'], pop['years_available']
                f_nl = [f for f in nl['downloadable_files'] if f['year'] == 2020 and 'average_viirs' in f['name']][0]
                f_pop = [f for f in pop['downloadable_files'] if f['name'] == 'tha_pop_2020_cn_1km.tif'][0]
                STATE['pop2018'] = [f['url'] for f in pop['downloadable_files'] if f['name'] == 'tha_pop_2018_cn_1km.tif'][0]
                return r([call('propose_download_data', dict(hub_key=STATE['nl_key'], file_url=f_nl['url'], name='night_light_2020', purpose=PURPOSE, aoi_id=STATE['aoi'], value_type='density')),
                          call('propose_download_data', dict(hub_key=STATE['pop_key'], file_url=f_pop['url'], name='worldpop_2020_1km', purpose=PURPOSE, aoi_id=STATE['aoi'], value_type='count'), 1),
                          call('propose_download_data', dict(hub_key=STATE['pop_key'], file_url='https://example.com/evil.tif', name='x', purpose=PURPOSE), 2)])
            return r(text='เสนอดาวน์โหลดสองชุดแล้ว')
        r(text='ok')

    def log_message(self, *a):
        pass


srv = ThreadingHTTPServer(('127.0.0.1', 0), Mock)
threading.Thread(target=srv.serve_forever, daemon=True).start()
wait_engine()
R = Results()


def api(path, body=None, method=None):
    q = s.request(method or ('POST' if body is not None else 'GET'), ENGINE + path, json=body, timeout=600)
    return q.status_code, q.json()


def wait_job(jid, sec=600):
    for _ in range(sec):
        j = [x for x in api('/api/jobs')[1] if x['id'] == jid][0]
        if j['status'] not in ('queued', 'running'):
            return j
        time.sleep(1)
    return j


th = [a for a in api('/api/aoi')[1] if a.get('builtin')]
if not th:
    raise SystemExit('ข้าม: ยังไม่มีพื้นที่ศึกษาพื้นฐาน "ประเทศไทย"')
STATE['aoi'] = th[0]['id']
api('/api/ai', dict(enabled=True, mode='propose'), 'PATCH')
api('/api/ai/login', dict(provider='compat', api_key='', base_url=f'http://127.0.0.1:{srv.server_address[1]}/v1'))

c, r = api('/api/ai/chat', dict(messages=[dict(role='user', content='หาข้อมูล night light กับประชากรมาวิเคราะห์ความสัมพันธ์')]))
used = [u['tool'] for u in r.get('used', [])]
errs = [u for u in r.get('used', []) if u.get('error')]
R.check('ค้น Data hub → ได้ night light (Zenodo) + WorldPop พร้อมปีที่มี', STATE.get('nl_key') == 'zenodo:8277198' and 2020 in (STATE.get('nl_years') or []) and 2020 in (STATE.get('pop_years') or []),
        f"{STATE.get('nl_key')} {STATE.get('nl_years', [])[-3:]} · {STATE.get('pop_key')}")
props = r.get('proposals') or []
R.check('เสนอดาวน์โหลด 2 ไฟล์ (ตัดตามประเทศไทย) · URL นอกรายการถูกปฏิเสธ', len(props) == 2 and len(errs) == 1 and 'ไม่อยู่ในรายการ' in errs[0]['error'],
        [(p['title'], (p.get('estimate') or {}).get('crs')) for p in props])
R.check('การ์ดดาวน์โหลด: Zenodo อ่านบางส่วนได้ (COG) · WorldPop ไม่รองรับ range → แจ้งว่าจะโหลดทั้งไฟล์แล้วตัด',
        all(((p.get('estimate') or {}).get('ok') and p['estimate'].get('type') == 'cog') or 'ช้า' in (p['estimate'].get('error') or '') for p in props)   # Zenodo ช้า → แจ้งแล้วยังดาวน์โหลดได้
        and any(p['estimate'].get('range') is False and 'ทั้งไฟล์' in (p['estimate'].get('note') or '') for p in props),
        [(p['args']['name'], p['estimate'].get('range'), p['estimate'].get('file_mb')) for p in props])

out = {}
for p in props:
    c, ex = api('/api/ai/confirm', dict(id=p['id']))
    j = wait_job(ex['job_id'])
    out[p['args']['name']] = (j, (j.get('result') or {}).get('dataset_id'))
ok = all(j['status'] == 'done' and did for j, did in out.values())
info = {}
for n, (j, did) in out.items():
    if did:
        d = api(f'/api/datasets/{did}')[1]
        info[n] = (d['value_type'], bool(d['value_type_confirmed']), [round(x, 1) for x in d['meta']['bounds_wgs84']], d['meta'].get('purpose') == PURPOSE)
R.check('ดาวน์โหลดเสร็จ → เข้าคลังเป็นราสเตอร์ · ประเภทค่าตามที่ยืนยัน · กรอบประเทศไทย · บันทึกวัตถุประสงค์',
        ok and info.get('night_light_2020', ('',))[0] == 'density' and info.get('worldpop_2020_1km', ('',))[0] == 'count'
        and all(v[1] and v[3] and 96 < v[2][0] < 98.5 and 104.5 < v[2][2] < 106.5 for v in info.values()), info)

# ปุ่ม "นำเข้าคลัง" ในหน้า Data hub (ไม่ผ่าน AI): URL นอกรายการถูกปฏิเสธ · ไฟล์จริงเข้าคลัง (ผู้ใช้เป็นคนสั่ง)
pk = STATE.get('pop_key')
c, bad = api('/api/hub/import', dict(hub_key=pk, url='https://example.com/x.tif', aoi_id=STATE['aoi']))
c2, ok_imp = api('/api/hub/import', dict(hub_key=pk, url=STATE['pop2018'], aoi_id=STATE['aoi'], value_type='count')) if STATE.get('pop2018') else (0, {})
ji = wait_job(ok_imp['job_id']) if ok_imp.get('job_id') else {}
di = api(f"/api/datasets/{(ji.get('result') or {}).get('dataset_id')}")[1] if ji.get('status') == 'done' else {}
R.check('นำเข้าจากหน้า Data hub: URL นอกรายการ → ปฏิเสธ · ไฟล์จริง → เข้าคลัง (ประเภทค่า count · สั่งโดยผู้ใช้)',
        c == 400 and ji.get('status') == 'done' and di.get('value_type') == 'count' and di.get('value_type_confirmed'),
        f"{bad.get('error', '')[:50]} · งาน {ji.get('status')} · ชุด #{di.get('id')} {di.get('name')}")

# ไบแวเรียตจากชุดที่โหลดมา (ประชากร count × แสงไฟ density)
if ok:
    X, Y = out['worldpop_2020_1km'][1], out['night_light_2020'][1]
    for did in (X, Y):                                      # รอเตรียมข้อมูลเสร็จ
        for _ in range(300):
            if api(f'/api/datasets/{did}')[1].get('stats'):
                break
            time.sleep(1)
    opts = api(f'/api/res-options?ids={X},{Y}')[1]['options']
    res = [o for o in opts if '30″' in o['label']] or opts
    job = dict(x=dict(dataset_id=X, n=3, method='quantile', metric='density', label='ประชากร'), y=dict(dataset_id=Y, n=3, method='quantile', metric='value', label='แสงไฟ'),
               target_res=res[0]['value'], aoi_id=STATE['aoi'], name='ai_ntl_pop_2020', purpose=PURPOSE,
               colors=['#e8e8e8', '#e4acac', '#c85a5a', '#b0d5df', '#ad9ea5', '#985356', '#64acbe', '#627f8c', '#574249'], highlight=[9])
    e = api('/api/estimate', dict(kind='bivariate', params=job))[1]
    jb = wait_job(api('/api/jobs', dict(kind='bivariate', params=job))[1]['job']) if e.get('ok') else dict(status='estimate', error=e.get('error'))
    sm = (jb.get('result') or {}).get('summary') or {}
    R.check('ไบแวเรียตประชากร × แสงไฟ ทั้งประเทศจากชุดที่โหลดมา', jb['status'] == 'done', f"{jb['status']} · {e.get('grid', {}).get('res_label')} · คนรวม {sm.get('weight_total') or 0:,.0f} · {jb.get('error') or ''}")
    # ประวัติชุดข้อมูล: ผลไบแวเรียตรู้พ่อแม่ + ค่าที่ตั้ง · ชุดที่โหลดรู้ที่มา (Data hub, สัญญาอนุญาต, วัตถุประสงค์) และรู้ว่ามีลูก
    biv = (jb.get('result') or {}).get('dataset_id')
    pb = api(f'/api/datasets/{biv}/profile')[1] if biv else {}
    pn = api(f'/api/datasets/{Y}/profile')[1]
    org = dict(pn.get('origin') or [])
    R.check('ประวัติชุดข้อมูล: พ่อแม่/ค่าที่ตั้งของผลลัพธ์ · ที่มา/สัญญาอนุญาต/ลูกของชุดที่โหลด',
            {x['id'] for x in (pb.get('made_by') or {}).get('parents', [])} == {X, Y} and any(k == 'แกน X' for k, _ in pb['made_by']['settings'])
            and 'zenodo' in str(org.get('ดาวน์โหลดจาก', '')) and org.get('สัญญาอนุญาต') == 'cc-by-4.0' and org.get('วัตถุประสงค์') == PURPOSE
            and any(c['id'] == biv for c in pn.get('children') or []), dict(parents=[x['id'] for x in (pb.get('made_by') or {}).get('parents', [])], origin=list(org)))
    # โน้ตจากผู้ช่วย AI (เครื่องมือ write_dataset_note) ขึ้นในประวัติ
    c, rn = api('/api/ai/chat', dict(messages=[dict(role='user', content=f'NOTE {biv}')]))
    pb2 = api(f'/api/datasets/{biv}/profile')[1]
    R.check('ผู้ช่วยเขียนโน้ตในประวัติชุดข้อมูลได้ (ระบุรุ่นที่เขียน)', (pb2['notes'].get('ai') or {}).get('text', '').startswith('ไบแวเรียตประชากร')
            and pb2['notes']['ai'].get('model') == 'mock-data', pb2['notes'].get('ai'))

api('/api/ai/logout', {})
api('/api/ai', dict(enabled=False), 'PATCH')
srv.shutdown()
sys.exit(R.done())
