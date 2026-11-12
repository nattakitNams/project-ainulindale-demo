# -*- coding: utf-8 -*-
"""แปลงระบบพิกัดเป็น UTM 47N (งาน reproject, 1.0.45)
- WorldPop กทม. (จำนวนนับ 3″) → 100 ม. / 30 ม. / 1,000 ม.: ผลรวมคนคงเดิม (± 0.5%)
- ชั้น (รหัส 0/1/2/3) → ไม่เกิดค่าใหม่ · ค่าต่อเนื่อง → ค่าเฉลี่ยใกล้เดิม
- UTM 48N → 47N ได้ · ชุดที่เป็น 47N แล้ว → ปฏิเสธ
- สองชุดต่าง CRS ไขว้ไม่ได้ (บอกให้แปลง) → แปลงทั้งคู่เป็น 47N แล้วไขว้ได้ · กริด 10 ม. กับ 100 ม. ซ้อนกันพอดี"""
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, ENGINE, Results, session as s, wait_engine  # noqa: E402

if DATA is None or not (DATA / 'wp_bkk.tif').exists():
    print('ข้าม: ต้องตั้ง AINU_TEST_DATA (wp_bkk.tif)')
    sys.exit(0)
wait_engine()
R = Results()
TMP = Path(tempfile.mkdtemp(prefix='ainu_proj_'))


def api(path, body=None, method=None):
    r = s.request(method or ('POST' if body is not None else 'GET'), ENGINE + path, json=body, timeout=900)
    return r.json()


def add(path, vt):
    api('/api/datasets', dict(paths=[str(path)]))
    did = [x for x in api('/api/datasets') if x['path'] == str(path)][-1]['id']
    api(f'/api/datasets/{did}', dict(value_type=vt, value_type_confirmed=True), 'PATCH')
    for _ in range(120):
        d = api(f'/api/datasets/{did}')
        if (d.get('stats') or {}).get('sum') is not None:
            return d
        time.sleep(1)
    return d


def run(kind, params):
    r = api('/api/jobs', dict(kind=kind, params=params))
    if not r.get('job'):
        return None, r.get('error')
    for _ in range(900):
        j = api(f'/api/jobs/{r["job"]}')
        j = j.get('job', j)
        if j['status'] in ('done', 'failed', 'cancelled'):
            break
        time.sleep(1)
    if j['status'] != 'done':
        return None, j.get('error')
    return api(f'/api/datasets/{j["result"]["dataset_id"]}'), None


def tif(name, a, crs, tr, nodata, dtype):
    p = TMP / name
    with rasterio.open(p, 'w', driver='GTiff', width=a.shape[1], height=a.shape[0], count=1, dtype=dtype, crs=crs, transform=tr, nodata=nodata) as d:
        d.write(a.astype(dtype), 1)
    return p


def total(d):
    with rasterio.open(d['path']) as r:
        a = r.read(1, masked=True)
    return float(a.sum()), a, r.crs.to_string(), r.res, r.transform


pop = add(DATA / 'wp_bkk.tif', 'count')
s0 = pop['stats']['sum']
for res in (100, 30, 1000):
    d, err = run('reproject', dict(dataset_id=pop['id'], target_res=res))
    if d is None:
        R.check(f'WorldPop → UTM 47N {res} ม.', False, err)
        continue
    t, a, crs, rr, tr = total(d)
    R.check(f'WorldPop กทม. → UTM 47N {res} ม.: ผลรวมคนคงเดิม', crs == 'EPSG:32647' and rr == (res, res) and abs(t - s0) / s0 < 0.005,
            f'{s0:,.0f} → {t:,.0f} ({(t - s0) / s0 * 100:+.3f}%) · มุม {tr.c:.0f},{tr.f:.0f}')
    if res == 100:
        pop100 = d
        R.check('มุมกริดเป็นพหุคูณของขนาดพิกเซล (ซ้อนกับชุด 47N อื่นพอดี)', tr.c % res == 0 and tr.f % res == 0)

rng = np.random.default_rng(3)
cls = rng.integers(0, 4, (400, 400))
cls[:50] = 255
pc = tif('cls_4326.tif', cls, 'EPSG:4326', from_origin(100.45, 13.85, 0.3 / 3600 * 10, 0.3 / 3600 * 10), 255, 'uint8')   # 3″
dc = add(pc, 'class')
d, err = run('reproject', dict(dataset_id=dc['id']))
if d:
    _, a, crs, rr, _ = total(d)
    R.check('ชั้น: ค่าอัตโนมัติ 3″ → 100 ม. · ไม่เกิดรหัสใหม่ · nodata คงเป็นว่าง', rr == (100, 100) and set(np.unique(a.compressed())) <= {0, 1, 2, 3} and a.mask.any(),
            sorted(set(np.unique(a.compressed()).tolist())))
    cls100 = d
else:
    R.check('ชั้น → UTM 47N', False, err)

den = rng.uniform(10, 20, (300, 300))
pd_ = tif('den_48n.tif', den, 'EPSG:32648', from_origin(200000, 1550000, 50, 50), -1, 'float32')     # UTM 48N
dd = add(pd_, 'density')
d, err = run('reproject', dict(dataset_id=dd['id'], target_res=50))
if d:
    _, a, crs, rr, _ = total(d)
    R.check('UTM 48N → 47N (ค่าต่อเนื่อง): ค่าเฉลี่ยใกล้เดิม', crs == 'EPSG:32647' and abs(float(a.mean()) - den.mean()) < 0.2, f'{den.mean():.3f} → {float(a.mean()):.3f}')
else:
    R.check('UTM 48N → 47N', False, err)
e = api('/api/estimate', dict(kind='reproject', params=dict(dataset_id=d['id']))) if d else {}
R.check('ชุดที่เป็น 47N แล้ว → ปฏิเสธชัดเจน', not e.get('ok') and 'แล้ว' in (e.get('error') or ''), e.get('error'))

e = api('/api/estimate', dict(kind='bivariate', params=dict(x=dict(dataset_id=pop['id'], n=3, method='quantile', metric='density'),
                                                             y=dict(dataset_id=dd['id'], n=3, method='quantile', metric='value'), target_res='3')))
R.check('ต่าง CRS ไขว้ไม่ได้ → บอกให้แปลงเป็น UTM 47N', not e.get('ok') and 'UTM 47N' in (e.get('error') or ''), e.get('error'))
if 'pop100' in dir() and 'cls100' in dir():
    opts = api(f'/api/res-options?ids={pop100["id"]},{cls100["id"]}').get('options') or []
    tr = next((o['value'] for o in opts if o.get('is_source')), opts[0]['value'] if opts else None)
    b, err = run('bivariate', dict(x=dict(dataset_id=pop100['id'], n=3, method='quantile', metric='density', label='คน'),
                                   y=dict(dataset_id=cls100['id'], n=2, method='breaks', breaks=[2], metric='value', label='ชั้น'),
                                   target_res=tr, name='biv_utm47', colors=['#e8e8e8', '#b0d5df', '#64acbe', '#e4acac', '#ad9ea5', '#627f8c']))
    R.check('สองชุดที่แปลงเป็น 47N แล้ว → ไขว้ไบแวเรียตได้', b is not None and 'EPSG:32647' in (b['meta'].get('crs_key') or ''), err or (b['meta'].get('res_label') if b else ''))
# ---------- ค่าตั้ง "ระบบพิกัดผลลัพธ์ = UTM 47N": ทุกงานแปลงผลตอนท้าย ----------
api('/api/settings/out-crs', dict(out_crs='EPSG:32647'))
try:
    opts = api(f'/api/res-options?ids={pop["id"]}').get('options') or []
    coarse = next((o['value'] for o in opts if not o.get('is_source') and o['px'] < pop['meta']['width'] * pop['meta']['height']), None)
    r, err = run('resample', dict(dataset_id=pop['id'], target_res=coarse))
    if r:
        t, a, crs, rr, tr = total(r)
        R.check('ค่าตั้ง UTM 47N: ผลปรับความละเอียดออกมาเป็น EPSG:32647 · ผลรวมคนคงเดิม · ไฟล์เดิมของงานถูกลบ',
                crs == 'EPSG:32647' and abs(t - s0) / s0 < 0.005 and r['meta'].get('crs_key') == 'EPSG:32647' and not any(Path(r['path']).parent.glob('*as.tif')),
                f'{crs} {rr} {s0:,.0f} → {t:,.0f} · {Path(r["path"]).name}')
        R.check('ชุดผลลัพธ์มีสถิติทันที (ไม่ต้องอ่านไฟล์ใหม่)', (r.get('stats') or {}).get('sum') is not None)
    else:
        R.check('ค่าตั้ง UTM 47N: ปรับความละเอียด', False, err)
    tr0 = next((o['value'] for o in api(f'/api/res-options?ids={pop["id"]},{dc["id"]}').get('options') or [] if o.get('is_source')), None)
    b, err = run('bivariate', dict(x=dict(dataset_id=pop['id'], n=3, method='quantile', metric='density', label='คน'),
                                   y=dict(dataset_id=dc['id'], n=2, method='breaks', breaks=[2], metric='value', label='ชั้น'),
                                   target_res=tr0, name='biv_auto_utm', colors=['#e8e8e8', '#b0d5df', '#64acbe', '#e4acac', '#ad9ea5', '#627f8c']))
    if b:
        with rasterio.open(b['path']) as m:
            cm = m.colormap(1) if b['meta'].get('has_colormap') else {}
            vals = set(np.unique(m.read(1, masked=True).compressed()).tolist())
        R.check('ค่าตั้ง UTM 47N: แผนที่ไบแวเรียตเป็น EPSG:32647 · ตารางสีคงเดิม · รหัสชั้น 1–6', b['meta'].get('crs_key') == 'EPSG:32647' and cm.get(1) and vals <= set(range(1, 7)),
                f'{b["meta"].get("res_label")} · สีชั้น 1 {cm.get(1)} · {sorted(vals)}')
        st = api(f'/api/datasets/{b["id"]}/bivstats', dict(force=True))
        R.check('สถิติไบแวเรียตของแผนที่ที่แปลงแล้ว ยังคิดได้ (คิดจากชุดต้นทาง)', isinstance(st, dict) and 'correlation' in st, str(st)[:120])
    else:
        R.check('ค่าตั้ง UTM 47N: ไบแวเรียต', False, err)
    r2, err = run('resample', dict(dataset_id=pop['id'], target_res=coarse, out_crs='source'))
    R.check('งานเดียวสั่ง "out_crs":"source" → ตามต้นทาง (แทนค่าตั้งระบบ)', r2 is not None and r2['meta'].get('crs_key') == 'EPSG:4326', err or (r2 or {}).get('meta', {}).get('crs_key'))
finally:
    api('/api/settings/out-crs', dict(out_crs='source'))
sys.exit(R.done())
