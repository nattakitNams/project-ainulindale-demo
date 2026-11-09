# ทดสอบหกเหลี่ยมผ่าน API จริง
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
s = session
wait_engine()
res = []


def api(path, body=None, method=None):
    r = s.request(method or ('POST' if body is not None else 'GET'), B + path, json=body, timeout=600)
    j = r.json()
    assert r.ok, f'{path}: {j}'
    return j


def check(name, cond, extra=''):
    res.append(bool(cond))
    print(('✔' if cond else '✘'), name, extra)


def run(kind, p):
    e = api('/api/estimate', dict(kind=kind, params=p))
    assert e.get('ok'), e
    jid = api('/api/jobs', dict(kind=kind, params=p))['job']
    for _ in range(900):
        j = api(f'/api/jobs/{jid}')
        j = j.get('job', j)
        if j['status'] in ('done', 'failed', 'cancelled'):
            break
        time.sleep(1)
    assert j['status'] == 'done', f'{kind}: {j.get("error")}'
    return e, j['result']


ds = api('/api/datasets')
by = lambda n: [d for d in ds if d['name'] == n][-1]
wp = by('wp_bkk')
ntl = [d for d in ds if 'v20250904' in d['name'] and '→' not in d['name'] and d['kind'] == 'raster'][-1]
ndvi = by('ndvi_bkk')
for d in (wp, ntl, ndvi):
    print(d['id'], d['name'], d['value_type'], d['value_type_confirmed'])

# 1) ทั้งขอบเขต (ไม่มี AOI) → ผลรวมประชากรต้องเท่ากับ raster ทุกคน
e, r = run('hex', dict(dataset_ids=[wp['id']], size_km=2, drop_empty=False))
g = gpd.read_file(r['output'])
col = [c for c in g.columns if c.startswith('wp_bkk') and not c.endswith(('_km2', '_cover'))][0]
with rasterio.open(wp['path']) as f:
    a = f.read(1, masked=True).astype('float64')
tot = float(a.sum())
check('ผลรวมประชากรในหกเหลี่ยม = raster (ไม่หาย ไม่ซ้ำ)', abs(g[col].sum() - tot) / tot < 1e-9, f'{g[col].sum():,.1f} vs {tot:,.1f} · {len(g):,} ช่อง · {e["hex"]["crs"]}')
check('พื้นที่ช่องเท่ากัน 2 กม. → √3/2·4 = 3.464 ตร.กม.', abs(g.geometry.area.mean() / 1e6 - 3.4641) < 1e-3 and g.geometry.area.std() / 1e6 < 1e-6, f'{g.geometry.area.mean() / 1e6:.4f}')
check('ต่อ ตร.กม. = ผลรวม ÷ พื้นที่ช่อง', np.allclose(g[col + '_km2'].dropna(), (g[col] / 3.4641016).dropna(), rtol=1e-6))

# 2) AOI + หลายชุด (นับ / ต่อเนื่อง ไฟล์จริง scale ×10 / ดัชนี)
a = api('/api/aoi', dict(name='hex test', coords='100.45 13.70\n100.65 13.70\n100.65 13.85\n100.45 13.85'))
aid = a['id']
e, r = run('hex', dict(dataset_ids=[wp['id'], ntl['id'], ndvi['id']], size_km=1, aoi_id=aid, name='hex_test_1km'))
g = gpd.read_file(r['output'])
print('   columns:', [c for c in g.columns if c != 'geometry'])
ncol = [c for c in g.columns if c.startswith('nightlights') and not c.endswith('_cover')][0]
check('night light ใช้ค่าหลังคูณ scale (กทม. หลายร้อย)', g[ncol].max() > 300, f'max {g[ncol].max():,.0f}')
hex_id = r['dataset_id']
d = api(f'/api/datasets/{hex_id}')
check('ลงทะเบียนเป็น vector + meta.hex', d['kind'] == 'vector' and d['meta'].get('hex', {}).get('d_km') == 1.0, d['meta'].get('hex', {}).get('crs_label'))

# 3) ไบแวเรียต hex จาก raster ตรงๆ
p = dict(x=dict(dataset_id=wp['id'], n=3, method='quantile', metric='density', label='ประชากร'), y=dict(dataset_id=ntl['id'], n=3, method='quantile', label='แสงไฟ'),
         size_km=1, aoi_id=aid, colors=['#e8e8e8', '#e4acac', '#c85a5a', '#b0d5df', '#ad9ea5', '#985356', '#64acbe', '#627f8c', '#574249'], highlight=[9], name='hexbiv_raster')
e, r1 = run('hexbiv', p)
s1 = r1['summary']
check('ไบแวเรียต hex จาก raster', s1['hexes'] > 100 and sum(s1['hexes_by_code'].values()) == s1['hexes'], f"{s1['hexes']:,} ช่อง · คน {s1.get('weight_total', 0):,.0f}")
check('ควอนไทล์แบ่งช่องใกล้เคียงกัน', min(sum(v for k, v in s1['hexes_by_code'].items() if (int(k) - 1) % 3 == i) for i in range(3)) > s1['hexes'] * 0.2)

# 4) ไบแวเรียตจากชุด hex (เลือกฟิลด์) — ต้องได้ผลเดียวกับข้อ 3
p2 = dict(p, x=dict(p['x'], dataset_id=hex_id, field=[c for c in g.columns if c.startswith('wp_bkk') and c.endswith('_km2')][0]),
          y=dict(p['y'], dataset_id=hex_id, field=ncol), name='hexbiv_from_hex')
e, r2 = run('hexbiv', p2)
s2 = r2['summary']
check('จากชุด hex = จาก raster (รหัสเท่ากันทุกช่อง)', s1['hexes_by_code'] == s2['hexes_by_code'], f"{s2['hexes_by_code']}")

# 5) กันกริดคนละแบบ
e = api('/api/estimate', dict(kind='hexbiv', params=dict(p2, y=dict(p['y'], dataset_id=ntl['id']), size_km=2)))
check('ชุด hex + raster → ใช้กริดของชุด hex (ไม่สนขนาดที่ใส่)', e.get('ok') and e['hex']['d_km'] == 1.0, str(e.get('warnings'))[:120])

# 6) hex → raster (งานแปลงเป็นราสเตอร์ที่มีอยู่)
opts = api(f'/api/res-options?ids={wp["id"]}')['options']
e, r6 = run('rasterize', dict(dataset_id=hex_id, ref_dataset_id=wp['id'], target_res=[o for o in opts if o['is_source']][0]['value'], mode='attribute', field=ncol, rule='center', aoi_id=aid))
with rasterio.open(r6['output']) as f:
    z = f.read(1, masked=True)
check('hex → raster', z.count() > 1000 and float(z.max()) > 300, f'{z.count():,} พิกเซล max {float(z.max()):,.0f}')

# 7) vector → hex (% พื้นที่ทับ) ใช้ขอบเขต AOI เป็นชั้นโพลิกอน
aoi_path = a['aoi']['path']
vid = api('/api/datasets', dict(paths=[aoi_path]))['added'][0]
e, r7 = run('hex', dict(dataset_ids=[vid], size_km=1, aoi_id=aid, drop_empty=False))
g7 = gpd.read_file(r7['output'])
pc = [c for c in g7.columns if c.endswith('_pct')][0]
check('vector polygon → % พื้นที่ทับ (ช่องในสุด = 100%)', abs(g7[pc].max() - 100) < 1e-6 and g7[pc].min() >= 0, f'{(g7[pc] > 99.99).sum()} ช่องเต็ม / {len(g7)}')

# 8) กันงานใหญ่เกิน
e = api('/api/estimate', dict(kind='hex', params=dict(dataset_ids=[ntl['id']], size_km=0.05)))
check('กันกริดใหญ่เกินขีด / ทั้งโลกไม่มี AOI', not e.get('ok') and ('เกินขีด' in e.get('error', '') or 'กว้างมาก' in e.get('error', '')), e.get('error', '')[:80])
e = api('/api/estimate', dict(kind='hex', params=dict(dataset_ids=[ntl['id']], size_km=0.02, aoi_id=aid)))
check('กันจำนวนช่องเกินขีด (มี AOI)', not e.get('ok') and 'เกินขีด' in e.get('error', ''), e.get('error', '')[:80])
print(f'\nผล: ผ่าน {sum(res)}/{len(res)}')
sys.exit(0 if all(res) else 1)
