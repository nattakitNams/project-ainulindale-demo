# -*- coding: utf-8 -*-
"""แปลงเวกเตอร์ที่เป็น feature เดียวหลายหมื่นส่วน (เช่น น้ำท่วมที่รวมรูปแล้ว) — ต้องไม่ช้าและผลเท่าเดิม
เดิมทุกไทล์ rasterize ทั้งก้อน (3.8 วิ/ไทล์ กับไฟล์จริง 3.3 ล้านจุดยอด) → แตกส่วน + ดัชนี + ตัดรูปใหญ่ (0.002 วิ/ไทล์)"""
import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import rasterio
import shapely
from rasterio.features import rasterize

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ENGINE, Results, session as s, wait_engine  # noqa: E402

wait_engine()
R = Results()


def api(path, body=None, method=None):
    return s.request(method or ('POST' if body is not None else 'GET'), ENGINE + path, json=body, timeout=900).json()


rng = np.random.default_rng(11)
x0, y0 = 100.3, 13.6
sq = [shapely.box(x, y, x + rng.uniform(0.0005, 0.003), y + rng.uniform(0.0005, 0.003))
      for x, y in zip(rng.uniform(x0, x0 + 0.5, 15000), rng.uniform(y0, y0 + 0.5, 15000))]
ring = shapely.Point(x0 + 0.25, y0 + 0.25).buffer(0.2, quad_segs=8000).exterior.buffer(0.002)   # รูปเดียว ~ 64,000 จุดยอด (ต้องถูกตัดเป็นชิ้น)
mp = shapely.unary_union(sq + [ring])
gj = dict(type='FeatureCollection', features=[dict(type='Feature', properties=dict(v=1), geometry=shapely.geometry.mapping(mp))])
vp = Path(tempfile.mkdtemp()) / 'one_feature_many_parts.geojson'
vp.write_text(json.dumps(gj), encoding='utf-8')
api('/api/datasets', dict(paths=[str(vp)]))
vid = [x for x in api('/api/datasets') if x['path'] == str(vp)][-1]['id']
p = dict(dataset_id=vid, grid='own', crs='EPSG:4326', target_res='3/10', mode='presence', name='parts_test')
t0 = time.time()
jid = api('/api/jobs', dict(kind='rasterize', params=p))['job']
while True:
    j = api(f'/api/jobs/{jid}'); j = j.get('job', j)
    if j['status'] in ('done', 'failed'):
        break
    time.sleep(1)
sec = time.time() - t0
log = s.get(f'{ENGINE}/api/jobs/{jid}').json()
R.check('feature เดียว ' + f'{len(getattr(mp, "geoms", [mp])):,} ส่วน' + ' แปลงเสร็จเร็ว (< 90 วิ)', j['status'] == 'done' and sec < 90, f'{sec:.0f} วิ · {j.get("error") or ""}')
with rasterio.open(j['result']['output']) as d:
    a = d.read(1)
    ref = rasterize([(mp, 1)], out_shape=a.shape, transform=d.transform, fill=0, dtype='uint8')
d = api(f'/api/datasets/{j["result"]["dataset_id"]}')
st = d.get('stats') or {}
s.get(f'{ENGINE}/api/datasets/{d["id"]}/tile/9/398/236.png')
prep = [x for x in api('/api/jobs') if x['kind'] == 'prepare' and x['title'].endswith(d['name'])]
nod = d['meta'].get('nodata')
want_valid = int((a != nod).sum()) if nod is not None else a.size
R.check('สถิติจากตอนเขียน = นับจากไฟล์จริง และไม่มีงานเตรียมข้อมูลซ้ำ', st.get('from_writer') and st['valid'] == want_valid and not prep,
        f"valid {st.get('valid')} vs {want_valid} · nodata={nod} · งานเตรียม {len(prep)}")
R.check('ผลเท่ากับ rasterize ทั้งก้อนแบบเดิมทุกพิกเซล', np.array_equal(a, ref), f'ต่าง {int((a != ref).sum()):,} จาก {a.size:,} · มี {int((a == 1).sum()):,}')
sys.exit(R.done())
