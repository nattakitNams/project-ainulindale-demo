# ทดสอบเปิดแผนที่ + แปลง vector → raster ด้วยไฟล์จริงของผู้ใช้
import json
import time

import geopandas as gpd
import numpy as np
import rasterio
import requests
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, ENGINE, NTL, VECTORS, need, session, wait_engine  # noqa: E402


B = ENGINE
wait_engine()
s = session
D = str(need(VECTORS, 'AINU_TEST_VECTORS'))
F = {'building': D + r'\building\Building 23_16.shp', 'lu': D + r'\เชียงใหม่2553\การใช้ที่ดิน\LU_CMI_2553.shp'}
res = []
for _ in range(30):
    try:
        s.get(B + '/api/engine/hello', timeout=2)
        break
    except requests.RequestException:
        time.sleep(1)


def api(path, body=None, method=None, **kw):
    r = s.request(method or ('POST' if body is not None else 'GET'), B + path, json=body, timeout=900, **kw)
    return r


def check(name, cond, extra=''):
    res.append(bool(cond))
    print(('✔' if cond else '✘'), name, extra)


def run(p):
    e = api('/api/estimate', dict(kind='rasterize', params=p)).json()
    assert e.get('ok'), e
    jid = api('/api/jobs', dict(kind='rasterize', params=p)).json()['job']
    t = time.time()
    while True:
        j = api(f'/api/jobs/{jid}').json()
        j = j.get('job', j)
        if j['status'] in ('done', 'failed', 'cancelled'):
            break
        time.sleep(1)
    assert j['status'] == 'done', j.get('error')
    return e, j['result'], time.time() - t


ds = api('/api/datasets').json()
ids = {k: [d['id'] for d in ds if d['path'] == f][-1] for k, f in F.items()}
print('ids', ids)
# 1) เปิดแผนที่ building
d = api(f'/api/datasets/{ids["building"]}').json()
b = d['meta']['bounds_wgs84']
for z in (8, 12, 16):
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    w = 360 / 2 ** z * 3
    t = time.time()
    r = api(f'/api/datasets/{ids["building"]}/features', params=dict(bbox=f'{cx - w},{cy - w / 2},{cx + w},{cy + w / 2}', z=z, limit=4000))
    dt = time.time() - t
    check(f'แผนที่ building z{z} เร็ว (< 3 วิ)', r.ok and dt < 3, f'{dt:.2f}s · {r.headers.get("X-Count")} รูป · ซ่อนเล็กกว่าพิกเซล {r.headers.get("X-Hidden")} · {len(r.content) / 1e6:.2f} MB')

# 2) building → มี/ไม่มี 10 ม. (กริดเอง UTM 47N)
g = gpd.read_file(F['building'])
area = g.geometry.area.sum()
e, r2, dt = run(dict(dataset_id=ids['building'], grid='own', target_res='10', mode='presence', rule='center', name='bld_presence_10m'))
with rasterio.open(r2['output']) as f:
    a = f.read(1)
    crs = f.crs.to_epsg()
n1 = int((a == 1).sum())
check('building → มี/ไม่มี 10 ม. (ขอบเขตตาม vector, UTM 47N)', crs == 32647 and abs(n1 * 100 - area) / area < 0.15,
      f'{dt:.0f}s · {a.shape[1]}×{a.shape[0]} · พิกเซลอาคาร {n1:,} ≈ {n1 * 100 / 1e6:.2f} ตร.กม. vs จริง {area / 1e6:.2f}')

# 3) building → สัดส่วนพื้นที่อาคาร 100 ม.
e, r3, dt = run(dict(dataset_id=ids['building'], grid='own', target_res='100', mode='fraction', name='bld_frac_100m'))
with rasterio.open(r3['output']) as f:
    a = f.read(1, masked=True)
check('building → สัดส่วนพื้นที่อาคาร 100 ม.', abs(float(a.sum()) * 1e4 - area) / area < 0.05, f'{dt:.0f}s · รวม {float(a.sum()) * 1e4 / 1e6:.2f} ตร.กม. · max {float(a.max()):.2f}')

# 4) building + กริดอ้างอิง raster ที่อยู่คนละจังหวัด (เดิมได้ไฟล์ว่าง)
wp = [d for d in ds if d['name'] == 'wp_bkk'][-1]
opts = api(f'/api/res-options?ids={wp["id"]}').json()['options']
e, r4, dt = run(dict(dataset_id=ids['building'], grid='ref', ref_dataset_id=wp['id'], target_res=[o for o in opts if o['is_source']][0]['value'], mode='presence', name='bld_on_wp_grid'))
with rasterio.open(r4['output']) as f, rasterio.open(wp['path']) as w:
    a = f.read(1)
    off = ((f.transform.c - w.transform.c) / w.transform.a, (f.transform.f - w.transform.f) / w.transform.e)
check('กริดอ้างอิงคนละพื้นที่ → ยังได้ข้อมูล + พิกเซลตรงแลตทิซ', (a == 1).sum() > 500 and all(abs(x - round(x)) < 1e-3 for x in off), f'{(a == 1).sum():,} พิกเซล · เลื่อน {off}')

# 5) LU เชียงใหม่: ฟิลด์ตัวเลข (LU_ID_L3) 30 ม.
d = api(f'/api/datasets/{ids["lu"]}').json()
print('   LU encoding', d['meta'].get('encoding'), '· fields', [f['name'] for f in d['meta']['fields']])
e, r5, dt = run(dict(dataset_id=ids['lu'], grid='own', target_res='30', mode='attribute', field='LU_ID_L3', name='lu_l3_30m'))
with rasterio.open(r5['output']) as f:
    a = f.read(1, masked=True)
u = np.unique(a.compressed())
check('LU → ค่าจากฟิลด์ตัวเลข LU_ID_L3 30 ม.', len(u) > 20 and u.min() >= 1000, f'{dt:.0f}s · {len(u)} รหัส เช่น {u[:6].tolist()}')

# 6) LU: ฟิลด์ข้อความไทย (LU_DES_TH) ค่าที่กินพื้นที่มากสุด 100 ม. → รหัส + ตารางรหัส (ภาษาไทยต้องไม่เพี้ยน)
e, r6, dt = run(dict(dataset_id=ids['lu'], grid='own', target_res='100', mode='majority', field='LUL1_CODE', name='lu_l1_major_100m'))
import csv, os
cf = r6['output'].replace('.tif', '_codes.csv')
rows = list(csv.reader(open(cf, encoding='utf-8-sig'))) if os.path.exists(cf) else []
check('LU → ฟิลด์ข้อความ LUL1_CODE (majority 100 ม.) + ตารางรหัส', len(rows) > 3, f'{dt:.0f}s · {rows[:6]}')
e, r7, dt = run(dict(dataset_id=ids['lu'], grid='own', target_res='100', mode='attribute', field='LU_DES_TH', name='lu_desth_100m'))
cf = r7['output'].replace('.tif', '_codes.csv')
rows = list(csv.reader(open(cf, encoding='utf-8-sig')))
thai_ok = any('ป่า' in x[1] or 'นา' in x[1] for x in rows[1:])
check('ฟิลด์ภาษาไทย (TIS-620) → ตารางรหัสอ่านไทยถูก', thai_ok, f'{dt:.0f}s · {rows[1:4]}')
print(f'\nผล: ผ่าน {sum(res)}/{len(res)}')
sys.exit(0 if all(res) else 1)
