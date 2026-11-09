# -*- coding: utf-8 -*-
"""ขอบเขตผลลัพธ์ตอนแปลง vector → raster แล้วไขว้กับข้อมูลทั้งผืน (กรณีน้ำท่วมบางเดือน × ประชากร)
- ขอบเขตตามกรอบ vector → ไบแวเรียตได้แค่ส่วนที่ทับกัน → ตอนตรวจค่าต้องเตือน
- ขอบเขต = raster ทั้งผืน (extent_dataset_id) → กริดเท่ากับ raster นั้นทุกพิกเซล นอกรูป = 0 → ไม่เตือน"""
import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, ENGINE, Results, need, session as s, wait_engine  # noqa: E402

wait_engine()
R = Results()
WP = need(DATA, 'AINU_TEST_DATA') / 'wp_bkk.tif'


def api(path, body=None, method=None):
    r = s.request(method or ('POST' if body is not None else 'GET'), ENGINE + path, json=body, timeout=900)
    return r.json()


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


wp = [d for d in api('/api/datasets') if d['path'] == str(WP)]
wp = wp[-1] if wp else None
if wp is None:
    api('/api/datasets', dict(paths=[str(WP)]))
    wp = [d for d in api('/api/datasets') if d['path'] == str(WP)][-1]
with rasterio.open(WP) as f:
    b, wshape, wtr = f.bounds, f.shape, f.transform

# รูปน้ำท่วมเล็ก ๆ กลางพื้นที่ (กรอบ 10% ของ raster)
cx, cy, dx, dy = (b.left + b.right) / 2, (b.bottom + b.top) / 2, (b.right - b.left) * .05, (b.top - b.bottom) * .05
gj = dict(type='FeatureCollection', features=[dict(type='Feature', properties=dict(v=1), geometry=dict(
    type='Polygon', coordinates=[[[cx - dx, cy - dy], [cx + dx, cy - dy], [cx + dx, cy + dy], [cx - dx, cy + dy], [cx - dx, cy - dy]]]))])
vp = Path(tempfile.mkdtemp()) / 'flood_small.geojson'
vp.write_text(json.dumps(gj), encoding='utf-8')
api('/api/datasets', dict(paths=[str(vp)]))
vid = [d for d in api('/api/datasets') if d['path'] == str(vp)][-1]['id']
src = [o for o in api(f'/api/res-options?ids={wp["id"]}')['options'] if o['is_source']][0]['value']


def biv_est(oid):
    api(f'/api/datasets/{oid}', dict(value_type='class', value_type_confirmed=True), 'PATCH')
    job = dict(target_res=src, x=dict(dataset_id=wp['id'], n=2, method='quantile', metric='density'),
               y=dict(dataset_id=oid, n=2, method='breaks', breaks=[1], metric='value'))
    return api('/api/estimate', dict(kind='bivariate', params=job))


# 1) ขอบเขตตามกรอบ vector (แบบเดิม)
r1 = run('rasterize', dict(dataset_id=vid, grid='ref', ref_dataset_id=wp['id'], target_res=src, mode='presence'))
with rasterio.open(r1['output']) as f:
    sh1 = f.shape
e1 = biv_est(r1['dataset_id'])
w1 = [w for w in e1.get('warnings', []) if 'ครอบ' in w]
R.check('กรอบ vector → ผลเล็กกว่า raster และไบแวเรียตเตือนว่าทับกันแค่บางส่วน', sh1[0] < wshape[0] and w1, f'{sh1} vs {wshape} · {w1[:1]}')

# 2) ขอบเขต = raster ทั้งผืน
r2 = run('rasterize', dict(dataset_id=vid, grid='ref', ref_dataset_id=wp['id'], target_res=src, mode='presence', extent_dataset_id=wp['id']))
with rasterio.open(r2['output']) as f:
    a, tr = f.read(1), f.transform
same = a.shape == wshape and all(abs(x - y) < 1e-9 for x, y in zip(tr[:6], wtr[:6]))
R.check('ขอบเขต = raster ทั้งผืน → กริดเท่ากันทุกพิกเซล', same, f'{a.shape} vs {wshape}')
R.check('นอกรูป = 0, ในรูป = 1', set(np.unique(a).tolist()) == {0, 1} and 0 < (a == 1).mean() < 0.05, f'สัดส่วนท่วม {(a == 1).mean():.4f}')
e2 = biv_est(r2['dataset_id'])
R.check('ไบแวเรียตกับ raster ทั้งผืน → ไม่เตือนเรื่องขอบเขต', e2.get('ok') and not [w for w in e2.get('warnings', []) if 'ครอบ' in w],
        f"{e2['grid']['width']}×{e2['grid']['height']}")

# 3) กริดกำหนดเอง + ขอบเขตจาก raster ต่าง CRS ก็ได้ (แปลงกรอบให้)
e3 = api('/api/estimate', dict(kind='rasterize', params=dict(dataset_id=vid, grid='own', crs='EPSG:32647', target_res='100', mode='presence', extent_dataset_id=wp['id'])))
R.check('กริดเอง (UTM) + ขอบเขตจาก raster องศา', e3.get('ok') and e3['grid']['width'] > 100, f"{e3.get('grid', {}).get('width')}×{e3.get('grid', {}).get('height')}")

# 4) พื้นที่ศึกษาพื้นฐาน "ประเทศไทย" (สร้างจากชั้นจังหวัด GISTDA ตอนเปิดแอป — ต้องต่อเน็ต) ขึ้นก่อนในรายการ + ใช้เป็นขอบเขตผลลัพธ์
aois = api('/api/aoi')
th = [a for a in aois if a.get('builtin') and a['source'].get('base') == 'thailand']
if not th:
    print('ข้าม: ยังไม่มีพื้นที่ศึกษาพื้นฐาน "ประเทศไทย" (ออฟไลน์?)')
else:
    th = th[0]
    R.check('ประเทศไทยเป็นพื้นที่ศึกษาพื้นฐาน อยู่บนสุด · พื้นที่สมเหตุสมผล', aois[0]['id'] == th['id'] and 500_000 < th['area_km2'] < 530_000,
            f"{th['area_km2']:,.0f} ตร.กม. · bbox {[round(x, 2) for x in th['bbox']]}")
    r5 = run('rasterize', dict(dataset_id=vid, grid='own', crs='EPSG:4326', target_res='30', mode='presence',
                               extent_aoi_id=th['id'], aoi_id=th['id']))
    with rasterio.open(r5['output']) as f:
        a, nd, bb = f.read(1, masked=True), f.nodata, f.bounds
    full = bb.left <= th['bbox'][0] + .01 and bb.right >= th['bbox'][2] - .01 and bb.bottom <= th['bbox'][1] + .01 and bb.top >= th['bbox'][3] - .01
    R.check('ขอบเขต = ประเทศไทย → ครอบทั้งประเทศ · ในประเทศนอกรูป = 0 · ทะเล/เพื่อนบ้าน = ไม่มีข้อมูล',
            full and (a == 1).sum() > 0 and (a == 0).sum() > (a == 1).sum() * 50 and a.mask.sum() > 0,
            f'{a.shape[1]}×{a.shape[0]} · 1={int((a == 1).sum()):,} · 0={int((a == 0).sum()):,} · nodata={int(a.mask.sum()):,}')
sys.exit(R.done())
