# -*- coding: utf-8 -*-
"""ผู้ช่วยทำงานจบ ไม่ไหล (จากบทสนทนาจริงที่ผู้ใช้บ่น)
- ค้น Data hub ด้วยคำที่ผู้ช่วยเคยใช้แล้วได้ 0 ผล → ต้องเจอ (PM2.5, built-up, flood recurrence) · LST ชี้ไป MODIS LST ในเครื่องมือภาพดาวเทียม
- แผนงานต่อแชต: เขียน → อ่านกลับ (API) → อยู่ใน system prompt
- โฟลเดอร์: เสนอสร้าง <งาน>/raw_data + <งาน>/output → ยืนยัน → ซ้อนชั้นถูก · ผลงาน (folder_id) เข้าโฟลเดอร์นั้น
- MODIS LST ดึงได้จริง (อินเทอร์เน็ต) ค่าสมเหตุสมผล (°C)
- คำเตือนขอบเขต: ประชากรเมือง × ข้อมูลทั้งโลก ไม่เตือน 0% · พื้นที่ศึกษาใหญ่กว่าข้อมูล → เตือน"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import DATA, ENGINE, NTL, Results, need, session as s, wait_engine  # noqa: E402

wait_engine()
R = Results()
from app import ai, ai_plan, ai_tools  # noqa: E402


def _call(method, path, body=None, params=None):
    return s.request(method, ENGINE + path, json=body, params=params, timeout=600).json()


ai_tools._call = _call


def api(path, body=None, method=None):
    return s.request(method or ('POST' if body is not None else 'GET'), ENGINE + path, json=body, timeout=900).json()


def run(kind, p):
    e = api('/api/estimate', dict(kind=kind, params=p))
    assert e.get('ok'), e
    jid = api('/api/jobs', dict(kind=kind, params=p))['job']
    while True:
        j = api(f'/api/jobs/{jid}')
        j = j.get('job', j)
        if j['status'] in ('done', 'failed', 'cancelled'):
            break
        time.sleep(1)
    assert j['status'] == 'done', j.get('error')
    return j['result']


# ---------- ค้น Data hub ----------
got = {}
for q in ('PM2.5 Thailand raster annual', 'built-up urban extent change', 'flood recurrence inundation frequency', 'land surface temperature thailand'):
    r = ai_tools.t_search_data_hub(q, 8)
    got[q] = r
R.check('คำค้นยาวที่เคยได้ 0 ผล → เจอ', all(got[q]['results'] for q in list(got)[:3]),
        ' | '.join(f'{q[:14]}: {", ".join(x["key"] for x in got[q]["results"][:2])}' for q in got))
R.check('built-up → GHSL ไทยที่นำเข้าได้ อยู่อันดับต้น', any(x['key'] == 'ckan:data:tha-ghsl' for x in got['built-up urban extent change']['results'][:5]))
R.check('ความร้อน/LST → ชี้ MODIS LST ในเครื่องมือภาพดาวเทียม', any(t['collection'] == 'modis-11A2-061' for t in got['land surface temperature thailand']['satellite_tool']),
        str([t['collection'] for t in got['land surface temperature thailand']['satellite_tool']]))
R.check('น้ำท่วมซ้ำ → ชี้ JRC GSW', any(t['collection'] == 'jrc-gsw' for t in got['flood recurrence inundation frequency']['satellite_tool']))

# ---------- แผนงาน ----------
cid = 'ctest' + str(int(time.time()))
ai_tools.CURRENT_CHAT['id'] = cid
ai_tools.t_update_plan(goal='Urban Expansion into Heat Hazard TH 2015–2024', purpose='ต้นแบบ methodology งานวิชาการ',
                       steps_json=json.dumps([dict(title='โหลด night light 2015/2024', status='done', outputs=[1]), dict(title='ดึง MODIS LST', status='doing')]),
                       decisions=['ใช้เฉพาะไฟล์ตรง', 'ประเทศไทย'])
ai_tools.t_update_plan(blockers=['PM2.5 ยังไม่มี'])                       # ส่งเฉพาะช่องที่เปลี่ยน → ที่เหลือคงเดิม
pl = api(f'/api/ai/plan?chat={cid}')['plan']
txt = ai_plan.as_text(pl)
R.check('แผนงานเก็บถาวร + อัปเดตบางช่องไม่ลบช่องอื่น', pl and len(pl['steps']) == 2 and pl['blockers'] == ['PM2.5 ยังไม่มี'] and pl['purpose'],
        txt.replace('\n', ' / ')[:200])
R.check('แผนงานบอกผู้ช่วยว่าห้ามถามซ้ำ', 'ห้ามถามซ้ำ' in txt and 'ใช้เฉพาะไฟล์ตรง' in txt)
R.check('prompt มีกฎลงมือ/ไม่ถามซ้ำ/ไม่จบด้วยเมนู', all(k in ai.TOOLS_PROPOSE for k in ('ลงมือทันที', 'ห้ามจบรอบด้วย', 'ไม่เกิน 1 คำถาม', 'ห้ามตั้งชื่อใหม่ให้ไอเดียเดิม')))

# ---------- โฟลเดอร์ ----------
root = f'TestUEH_{int(time.time())}'
pr = ai_tools.t_propose_create_folders([f'{root}/raw_data', f'{root}/output'], 'ทดสอบ')
res = ai_tools.execute(pr['proposal_id'], 'test')
fl = {f['path']: f for f in ai_tools.t_list_folders()}
ok = f'{root}/raw_data' in fl and f'{root}/output' in fl and fl[f'{root}/raw_data']['parent_id'] == fl[root]['id']
R.check('สร้างโฟลเดอร์ซ้อนชั้นในการ์ดเดียว', ok, res.get('message', ''))
pr2 = ai_tools.t_propose_create_folders([f'{root}/output'])
R.check('เสนอซ้ำ → รู้ว่ามีแล้ว', pr2 and not ai_tools._PROPOSALS[pr2['proposal_id']]['args']['new'])
out_id = fl[f'{root}/output']['id']

# ---------- MODIS LST + โฟลเดอร์ผลลัพธ์ ----------
gj = dict(type='Polygon', coordinates=[[[100.3, 13.5], [100.9, 13.5], [100.9, 14.1], [100.3, 14.1], [100.3, 13.5]]])
aid = api('/api/aoi', dict(name='test_lst_bkk', geojson=gj))['id']
r = run('satellite', dict(collection='modis-11A2-061', bands=['LST_Day_1km', 'LST_Night_1km'], aoi_id=aid, date_from='2024-03-01', date_to='2024-05-31',
                          zoom=7, pick='mean', name='test_modis_lst', folder_id=out_id))
b = r['summary']['bands']
dC, nC = b['LST_Day_1km']['mean'] * 0.02 - 273.15, b['LST_Night_1km']['mean'] * 0.02 - 273.15
d = api(f'/api/datasets/{r["dataset_id"]}')
R.check('MODIS LST ฤดูร้อน กทม.: กลางวัน 30–50 °C · กลางคืน 20–32 °C · กลางวัน > กลางคืน', 30 < dC < 50 and 20 < nC < 32 and dC > nC, f'กลางวัน {dC:.1f} °C · กลางคืน {nC:.1f} °C')
R.check('ผลลัพธ์ (folder_id) เข้าโฟลเดอร์ output', d.get('folder_id') == out_id, f'folder {d.get("folder_id")} vs {out_id}')

# ---------- คำเตือนขอบเขต ----------
WP = need(DATA, 'AINU_TEST_DATA') / 'wp_bkk.tif'
ds = api('/api/datasets')
wp = [x for x in ds if x['path'] == str(WP)][-1]
ntl = [x for x in ds if NTL and x['path'] == str(NTL)]
if ntl:
    for x in (wp, ntl[-1]):
        if not x.get('value_type_confirmed'):
            api(f'/api/datasets/{x["id"]}', dict(value_type='count' if x is wp else 'density', value_type_confirmed=True), 'PATCH')
    src = [o for o in api(f'/api/res-options?ids={wp["id"]},{ntl[-1]["id"]}')['options'] if o['is_source']][0]['value']
    job = dict(target_res=src, x=dict(dataset_id=wp['id'], n=3, method='quantile', metric='density'), y=dict(dataset_id=ntl[-1]['id'], n=3, method='quantile', metric='value'))
    e1 = api('/api/estimate', dict(kind='bivariate', params=job))
    th = [a for a in api('/api/aoi') if a.get('builtin')][0]['id']
    e2 = api('/api/estimate', dict(kind='bivariate', params=dict(job, aoi_id=th)))
    w1 = [w for w in e1.get('warnings', []) if 'ทับกัน' in w]
    w2 = [w for w in e2.get('warnings', []) if 'ทับกัน' in w]
    R.check('ประชากร กทม. × night light ทั้งโลก → ไม่เตือน 0%', e1.get('ok') and not w1, str(w1)[:120])
    R.check('ตั้งพื้นที่ศึกษา = ประเทศไทย แต่ข้อมูลมีแค่ กทม. → เตือน', bool(w2), (w2 or ['-'])[0][:120])
sys.exit(R.done())
