# -*- coding: utf-8 -*-
"""สำเนาพรีวิว (ใช้ตอนซูมออก): ต้องเป็นแบบย่อ ไม่ใช่สำเนาเต็มขนาด · สำเนาแบบเก่า (F=1) ถูกลบ/ล้างการอ้างอิงตอนเปิดเซิร์ฟเวอร์
เดิม: raster 4–200 ล้านพิกเซลที่ไม่มี overview ถูกคัดลอกทั้งไฟล์ (WorldPop 100 ม. ปีละ ~124 MB → 17 ปี ≈ 2 GB)"""
import math
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import ENGINE, Results, session as s, wait_engine  # noqa: E402

wait_engine()
R = Results()


def api(path, body=None, method=None):
    return s.request(method or ('POST' if body is not None else 'GET'), ENGINE + path, json=body, timeout=600).json()


p = Path(tempfile.mkdtemp(prefix='ainu_pv_')) / 'big_noovr.tif'
H, W = 3000, 3200                                               # 9.6 ล้านพิกเซล > เกณฑ์ทำพรีวิว · ไม่มี overview
with rasterio.open(p, 'w', driver='GTiff', width=W, height=H, count=1, dtype='float32', crs='EPSG:4326',
                   transform=from_origin(100, 15, 1 / 1200, 1 / 1200), nodata=-1, tiled=True, blockxsize=512, blockysize=512) as d:
    d.write(np.random.default_rng(1).uniform(0, 50, (H, W)).astype('float32'), 1)
api('/api/datasets', dict(paths=[str(p)]))
did = [x for x in api('/api/datasets') if x['path'] == str(p)][-1]['id']
api(f'/api/datasets/{did}', dict(value_type='density', value_type_confirmed=True), 'PATCH')
t0 = time.time()
while time.time() - t0 < 300:
    d = api(f'/api/datasets/{did}')
    if d.get('preview_path') and d.get('stats'):
        break
    time.sleep(1)
pv = d.get('preview_path') or ''
R.check('พรีวิวเป็นแบบย่อ 1/4 ต่อด้าน (ไม่ใช่สำเนาเต็มขนาด) และเล็กกว่าต้นฉบับมาก', pv.endswith('_F4.tif') and os.path.getsize(pv) < os.path.getsize(p) / 8,
        f'{Path(pv).name} {os.path.getsize(pv) / 1e6:.1f} MB vs ต้นฉบับ {os.path.getsize(p) / 1e6:.1f} MB')


def xy(z, lat, lon):
    n = 2 ** z
    return int((lon + 180) / 360 * n), int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)


ok = True
for z in (6, 9, 12):
    x, y = xy(z, 14.0, 101.3)
    r = s.get(f'{ENGINE}/api/datasets/{did}/tile/{z}/{x}/{y}.png?v=t{z}')
    ok &= r.status_code == 200 and len(r.content) > 100
R.check('ไทล์แผนที่ได้ทุกระดับซูม (ซูมออกใช้พรีวิว ซูมเข้าใช้ต้นฉบับ)', ok)

# สำเนาแบบเก่า F=1 ที่ยังถูกอ้าง → migrate ลบไฟล์ + ล้างการอ้าง (ทำงานเดียวกับตอนเปิดเซิร์ฟเวอร์)
from app import db, ops  # noqa: E402
old = Path(pv).with_name(f'ds{did}_F1.tif')
shutil.copy(pv, old)
db.update('datasets', did, preview_path=str(old), preview_key='old')
n, freed = ops.migrate_previews()
d = api(f'/api/datasets/{did}')
R.check('สำเนาเต็มขนาดแบบเก่า → ลบไฟล์ + ล้างการอ้าง (เปิดชุดอีกครั้งสร้างแบบย่อใหม่)', n >= 1 and not old.exists() and d.get('preview_key') in (None, 'old') and
        (d.get('preview_path') is None or d['preview_path'].endswith('_F4.tif')), f'{n} ไฟล์ · {freed / 1e6:.1f} MB')
sys.exit(R.done())
