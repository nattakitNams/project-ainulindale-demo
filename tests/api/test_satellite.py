# -*- coding: utf-8 -*-
"""ภาพดาวเทียมจาก Planetary Computer (อินเทอร์เน็ตจริง · พื้นที่เล็ก กทม. 20×20 กม.)
- ค้นภาพ Sentinel-2 ตามช่วงวันที่ + เมฆ → จำนวนภาพ/วันที่/เมฆ
- ดึง B04+B08 ที่ ≈ 38 ม. → ไฟล์ 2 แบนด์ ความละเอียดเศษส่วนฐานสอง (ต่อเครื่องคำนวณได้) · ค่าในช่วงค่าสะท้อน
- NDVI ด้วยสูตร → อยู่ใน −1…1 · SAR Sentinel-1 VV/VH ค่าบวก
- ประเมินผลงาน (review_output) ไม่มีปัญหา · ป้ายบัญชี/โทเคนใน Data hub"""
import sys
import time
from pathlib import Path

import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import ENGINE, Results, session as s, wait_engine  # noqa: E402

wait_engine()
R = Results()


def api(path, body=None, method=None):
    return s.request(method or ('POST' if body is not None else 'GET'), ENGINE + path, json=body, timeout=900).json()


def run(kind, p):
    e = api('/api/estimate', dict(kind=kind, params=p))
    assert e.get('ok'), e
    jid = api('/api/jobs', dict(kind=kind, params=p))['job']
    t = time.time()
    while True:
        j = api(f'/api/jobs/{jid}')
        j = j.get('job', j)
        if j['status'] in ('done', 'failed', 'cancelled'):
            break
        time.sleep(1)
    assert j['status'] == 'done', j.get('error')
    return j['result'], time.time() - t


gj = dict(type='Polygon', coordinates=[[[100.45, 13.65], [100.65, 13.65], [100.65, 13.85], [100.45, 13.85], [100.45, 13.65]]])
aid = api('/api/aoi', dict(name='test_sat_bkk', geojson=gj))['id']
q = dict(collection='sentinel-2-l2a', aoi_id=aid, date_from='2025-01-01', date_to='2025-03-31', cloud_max=20)
f = api('/api/satellite/search', q)
R.check('ค้นภาพ Sentinel-2 ม.ค.–มี.ค. 2568 เมฆ ≤ 20%', f.get('n', 0) > 0 and f['cloud']['max'] <= 20, f'{f.get("n")} ภาพ {f.get("first")}–{f.get("last")} · เมฆสูงสุด {f.get("cloud", {}).get("max")}')

r, sec = run('satellite', dict(q, bands=['B04', 'B08'], zoom=10, name='test_s2'))
with rasterio.open(r['output']) as d:
    a = d.read(masked=True)
    desc = d.descriptions
d2 = api(f'/api/datasets/{r["dataset_id"]}')
R.check('ดึง B04+B08 ≈ 38 ม. → 2 แบนด์ ค่าสะท้อน 0–20000 · ความละเอียดเศษส่วน', a.shape[0] == 2 and 0 <= a.min() and a.max() < 20000 and d2['meta'].get('res_exact'),
        f'{sec:.0f} วิ · {a.shape} · {desc} · res {d2["meta"].get("res_exact")}')

src = [o for o in api(f'/api/res-options?ids={r["dataset_id"]}')['options'] if o['is_source']][0]['value']
nd, _ = run('calc', dict(expr='(NIR - RED) / (NIR + RED)', vars=dict(NIR=dict(dataset_id=r['dataset_id'], band=2), RED=dict(dataset_id=r['dataset_id'], band=1)),
                         target_res=src, name='test_ndvi_s2'))
R.check('NDVI จากภาพที่ดึงมา อยู่ใน −1…1', -1 <= nd['summary']['min'] and nd['summary']['max'] <= 1, f'{nd["summary"]["min"]:.3f} – {nd["summary"]["max"]:.3f} เฉลี่ย {nd["summary"]["mean"]:.3f}')

sr, sec = run('satellite', dict(collection='sentinel-1-rtc', aoi_id=aid, date_from='2025-03-01', date_to='2025-03-31', bands=['vv', 'vh'], zoom=10, name='test_s1'))
b = sr['summary']['bands']
R.check('SAR Sentinel-1 VV/VH ค่าบวก (backscatter)', b['vv']['min'] > 0 and b['vh']['min'] > 0, f'{sec:.0f} วิ · VV เฉลี่ย {b["vv"]["mean"]:.3f}')

e = api('/api/estimate', dict(kind='satellite', params=dict(q, bands=['B04'], zoom=12, aoi_id=[a for a in api('/api/aoi') if a.get('builtin')][0]['id'])))
R.check('ทั้งประเทศที่ 10 ม. → ปฏิเสธ (ไทล์เกิน)', not e.get('ok'), (e.get('error') or '')[:80])
e = api('/api/estimate', dict(kind='satellite', params=dict(q, bands=['XX'])))
R.check('แบนด์ที่ไม่มี → ปฏิเสธ', not e.get('ok'), (e.get('error') or '')[:80])

from app import ai_tools  # noqa: E402  (เรียกผ่าน test client ของเซิร์ฟเวอร์ทดสอบไม่ได้ → ใช้ API จริง)
import requests  # noqa: E402


class _C:
    def open(self, path, method='GET', json=None, query_string=None):
        return s.request(method, ENGINE + path, json=json, params=query_string, timeout=300)


def _call(method, path, body=None, params=None):
    rr = s.request(method, ENGINE + path, json=body, params=params, timeout=300)
    return rr.json()


ai_tools._call = _call
rv = ai_tools.t_review_output(r['dataset_id'], 'ภาพ Sentinel-2 กทม. ครบพื้นที่')
names = [c['item'] for c in rv['checks']]
R.check('ประเมินผลงาน: ตรวจไทล์/เมฆ/แบนด์ ไม่มีปัญหา', not rv['problems'] and 'ไทล์มีภาพครบ' in names, '; '.join(f'{c["item"]}: {c["detail"]}' for c in rv['checks'])[:300])
hub = ai_tools.t_search_data_hub('sentinel-1', 5) + ai_tools.t_search_data_hub('viirs nighttime', 8)
lv = {h['key']: h['access']['level'] for h in hub}
R.check('ป้ายบัญชี/โทเคน: GEE = account · PC ที่ดึงได้ = app', any(k.startswith('gee:') and v == 'account' for k, v in lv.items()) and lv.get('pc:sentinel-1-rtc') == 'app', str(lv)[:300])
sys.exit(R.done())
