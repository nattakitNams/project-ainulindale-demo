# -*- coding: utf-8 -*-
"""ความละเอียดเป็นเมตร (1.1.1): ช่องความละเอียดส่ง target_res (กริดต้นทาง) + out_res_m + out_crs=UTM 47N

- ปรับความละเอียด WorldPop 3″ → 250 ม.: ผลเป็น EPSG:32647 · พิกเซล 250 × 250 ม. · ผลรวมคนคงเดิม (± 0.5%)
- ค่าที่พิมพ์เอง (ไม่ใช่ขนาดกลม เช่น 120 ม.) ใช้ได้ · ผลประเมินแสดงขนาดเมตรสุดท้าย
- ไบแวเรียตที่ 500 ม. → แผนที่ชั้นเป็นเมตร ไม่เกิดรหัสชั้นใหม่
- ชุดที่เป็น UTM 47N อยู่แล้ว (30 ม.) ขอผล 100 ม. → ยังแปลงขนาดให้ (เดิมข้ามเพราะ CRS ตรงกัน)
- ค่าผิด (ติดลบ / CRS อื่น) → ปฏิเสธชัดเจน

    python tests/api/test_res_m.py
"""
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, ENGINE, Results, session, wait_engine  # noqa: E402

if DATA is None or not (DATA / 'wp_bkk.tif').exists():
    print('ข้าม: ต้องตั้ง AINU_TEST_DATA (wp_bkk.tif)')
    sys.exit(0)
wait_engine()
R = Results()


def api(path, body=None, method=None):
    return session.request(method or ('POST' if body is not None else 'GET'), ENGINE + path, json=body, timeout=900).json()


def add(path, vt):                                        # รูปแบบเดียวกับ test_reproject.py
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


def read(d):
    with rasterio.open(d['path']) as r:
        a = r.read(1, masked=True).astype('float64')
        return float(a.sum()), a, r.crs.to_string(), r.res


def src_sum(p):
    with rasterio.open(p) as r:
        return float(r.read(1, masked=True).astype('float64').sum())


pop = add(DATA / 'wp_bkk.tif', 'count')
s0 = src_sum(pop['path'])

# 1) 250 ม. → กริดต้นทางที่ไม่หยาบกว่า 250 ม. คือ 6″ (~185 ม.)
p = dict(dataset_id=pop['id'], target_res='6', out_crs='EPSG:32647', out_res_m=250)
e = api('/api/estimate', dict(kind='resample', params=p))
R.check('ผลประเมินแสดงขนาดเมตรสุดท้าย', e.get('ok') and e['grid']['res_label'].startswith('250 ม.') and 'UTM 47N' in e['grid']['res_label'], e['grid']['res_label'])
d, err = run('resample', p)
if d:
    t, a, crs, rr = read(d)
    R.check('ปรับความละเอียด → UTM 47N 250 ม. ผลรวมคนคงเดิม', crs == 'EPSG:32647' and rr == (250, 250) and abs(t - s0) / s0 < 0.005,
            f'{crs} {rr} {t:,.0f} vs {s0:,.0f}')
else:
    R.check('ปรับความละเอียด → UTM 47N 250 ม.', False, err)

# 2) ค่าที่พิมพ์เอง 120 ม. (กริด 3″ ~92 ม.)
d, err = run('resample', dict(dataset_id=pop['id'], target_res='3', out_crs='EPSG:32647', out_res_m=120))
if d:
    t, a, crs, rr = read(d)
    R.check('ค่าที่พิมพ์เอง 120 ม. ได้พิกเซล 120 ม. เป๊ะ ผลรวมคงเดิม', crs == 'EPSG:32647' and rr == (120, 120) and abs(t - s0) / s0 < 0.005, f'{rr} {t:,.0f}')
else:
    R.check('ค่าที่พิมพ์เอง 120 ม.', False, err)

# 3) ไบแวเรียต 500 ม.
nd = add(DATA / 'ndvi_bkk.tif', 'density')
cols = ['#e8e8e8', '#b0d5df', '#64acbe', '#e4acac', '#ad9ea5', '#627f8c', '#c85a5a', '#985356', '#574249']
d, err = run('bivariate', dict(x=dict(dataset_id=pop['id'], n=3, method='quantile', metric='density'),
                               y=dict(dataset_id=nd['id'], n=3, method='quantile', metric='value'),
                               target_res='15', out_crs='EPSG:32647', out_res_m=500, colors=cols, name='biv_500m'))
if d:
    t, a, crs, rr = read(d)
    R.check('ไบแวเรียต 500 ม. → แผนที่ UTM 47N 500 ม. รหัสชั้น 1–9 เท่านั้น', crs == 'EPSG:32647' and rr == (500, 500)
            and set(np.unique(a.compressed()).astype(int)) <= set(range(1, 10)), f'{crs} {rr} {sorted(set(np.unique(a.compressed()).astype(int)))}')
else:
    R.check('ไบแวเรียต 500 ม.', False, err)

# 4) ชุดที่เป็น 47N อยู่แล้ว 30 ม. → ขอ 100 ม.
tmp = Path(DATA) / 'utm47_30m.tif'
if not tmp.exists():
    rng = np.random.default_rng(3)
    with rasterio.open(tmp, 'w', driver='GTiff', width=400, height=300, count=1, dtype='float32', crs='EPSG:32647',
                       transform=from_origin(660000, 1530000, 30, 30), nodata=-1) as w:
        w.write(rng.gamma(2, 3, (300, 400)).astype('float32'), 1)
u = add(tmp, 'count')
su = src_sum(u['path'])
d, err = run('resample', dict(dataset_id=u['id'], target_res='30', out_crs='EPSG:32647', out_res_m=100))
if d:
    t, a, crs, rr = read(d)
    R.check('ชุด 47N 30 ม. ขอผล 100 ม. → ได้ 100 ม. ผลรวมคงเดิม', crs == 'EPSG:32647' and rr == (100, 100) and abs(t - su) / su < 0.005, f'{rr} {t:,.0f} vs {su:,.0f}')
else:
    R.check('ชุด 47N 30 ม. ขอผล 100 ม.', False, err)

# 4b) ความละเอียดเท่าเดิม + พื้นที่ศึกษา = ตัดพื้นที่อย่างเดียว (ตัวตรวจยอมมาตลอด แต่ตัวทำงานเคย error ทุกครั้ง)
aoi = [a for a in api('/api/aoi') if a.get('builtin')][0]
d, err = run('resample', dict(dataset_id=pop['id'], target_res='3', aoi_id=aoi['id']))
if d:
    t, a, crs, rr = read(d)
    R.check('เท่าเดิม + พื้นที่ศึกษา → ตัดพื้นที่ได้ (กริดเดิม ค่าไม่เกินต้นฉบับ)', crs == 'EPSG:4326' and t <= s0 * 1.0001 and t > 0, f'{crs} {t:,.0f} vs {s0:,.0f}')
else:
    R.check('เท่าเดิม + พื้นที่ศึกษา → ตัดพื้นที่ได้', False, err)

# 5) ค่าผิด
for bad, why in ((dict(out_res_m=-5), 'ติดลบ'), (dict(out_res_m=100, out_crs='EPSG:32648'), 'CRS อื่น'), (dict(out_res_m='abc'), 'ไม่ใช่ตัวเลข')):
    e = api('/api/estimate', dict(kind='resample', params=dict(dataset_id=pop['id'], target_res='6', **bad)))
    R.check(f'ค่าเมตรผิด ({why}) → ปฏิเสธ', not e.get('ok'), e.get('error'))

sys.exit(R.done())
