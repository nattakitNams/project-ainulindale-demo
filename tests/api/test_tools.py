# -*- coding: utf-8 -*-
"""เครื่องมือข้อมูล (ข้อมูลสังเคราะห์ — รู้คำตอบล่วงหน้าทุกพิกเซล)
- calc: NDVI จากภาพ 4 แบนด์ = (b4 − b3)/(b4 + b3) · สูตรอันตราย/ตัวแปรไม่รู้จักถูกปฏิเสธตั้งแต่ตอนตรวจ
- trend: 3 ปี ค่า = 2·ปี + c → ความชัน 2 ทุกพิกเซล · change/count_above ถูกต้อง · พิกเซลที่ขาดบางปีใช้ min_years ได้
- mosaic: 2 แผ่นติดกัน → ไฟล์เดียวครอบทั้งสอง ค่าไม่เปลี่ยน
- vmerge: 2 ชั้น → feature รวมครบ + คอลัมน์ source · dissolve → 1 รูป
- ประวัติไฟล์ (profile) ของผลลัพธ์บอกไฟล์ต้นทาง + สูตร"""
import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ENGINE, Results, session as s, wait_engine  # noqa: E402

wait_engine()
R = Results()
TMP = Path(tempfile.mkdtemp(prefix='ainu_tools_'))
RES = 1 / 120                                         # 30″ (เศษส่วนแม่น)
X0, Y0, H, W = 100.0, 14.0, 60, 80


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


def tif(name, arrs, x0=X0, nodata=-1.0):
    p = TMP / name
    arrs = arrs if isinstance(arrs, list) else [arrs]
    with rasterio.open(p, 'w', driver='GTiff', width=arrs[0].shape[1], height=arrs[0].shape[0], count=len(arrs), dtype='float32',
                       crs='EPSG:4326', transform=from_origin(x0, Y0, RES, RES), nodata=nodata) as d:
        for i, a in enumerate(arrs):
            d.write(a.astype('float32'), i + 1)
    return p


def add(p, vt='density'):
    api('/api/datasets', dict(paths=[str(p)]))
    d = [d for d in api('/api/datasets') if d['path'] == str(p)][-1]
    if vt:
        api(f'/api/datasets/{d["id"]}', dict(value_type=vt, value_type_confirmed=True), 'PATCH')
    return d['id']


rng = np.random.default_rng(7)
# ---------- calc: NDVI ----------
red, nir = rng.uniform(0.05, 0.3, (H, W)), rng.uniform(0.2, 0.6, (H, W))
img = add(tif('s2_like.tif', [rng.uniform(0, 1, (H, W)), rng.uniform(0, 1, (H, W)), red, nir]))
src = [o for o in api(f'/api/res-options?ids={img}')['options'] if o['is_source']][0]['value']
r = run('calc', dict(expr='(NIR - RED) / (NIR + RED)', vars=dict(NIR=dict(dataset_id=img, band=4), RED=dict(dataset_id=img, band=3)),
                     target_res=src, name='ndvi_test'))
with rasterio.open(r['output']) as f:
    a = f.read(1)
want = ((nir - red) / (nir + red)).astype('float32')
R.check('NDVI จากแบนด์ 4/3 ตรงกับคำตอบทุกพิกเซล', a.shape == want.shape and np.allclose(a, want, atol=1e-6), f'max diff {np.abs(a - want).max():.2e}')
d = api(f'/api/datasets/{r["dataset_id"]}')
st = d.get('stats') or {}
s.get(f'{ENGINE}/api/datasets/{r["dataset_id"]}/tile/8/200/120.png')          # เปิดดูแผนที่ = จุดที่เคยสั่งงานเตรียมข้อมูล
prep = [j for j in api('/api/jobs') if j['kind'] == 'prepare' and j['title'].endswith(d['name'])]
R.check('สถิติได้ตั้งแต่ตอนเขียนไฟล์ (ค่าตรงกับไฟล์จริง) → ไม่มีงาน "เตรียมข้อมูล" อ่านไฟล์ซ้ำ',
        st.get('from_writer') and st['valid'] == a.size and abs(st['sum'] - float(a.astype('float64').sum())) < 1e-3 * a.size and
        abs(st['min'] - float(a.min())) < 1e-6 and abs(st['max'] - float(a.max())) < 1e-6 and st['sample_n'] > 0 and not prep,
        f"valid {st.get('valid')} · งานเตรียม {len(prep)}")

bad = [api('/api/estimate', dict(kind='calc', params=dict(expr=e, vars=dict(A=dict(dataset_id=img)), target_res=src)))
       for e in ('__import__("os").system("x")', 'A.real', 'B + 1', 'open(1)')]
R.check('สูตรอันตราย / ตัวแปรไม่รู้จัก → ปฏิเสธตอนตรวจ', all(not b.get('ok') for b in bad), ' | '.join((b.get('error') or '')[:40] for b in bad))

thr = run('calc', dict(expr='where(A > 0.4, 1, 0)', vars=dict(A=dict(dataset_id=r['dataset_id'])), target_res=src, value_type='class', name='ndvi_hi'))
with rasterio.open(thr['output']) as f:
    t = f.read(1)
R.check('where(เกณฑ์) → 1/0 · ประเภทค่าเป็นชั้น', np.array_equal(t, (want > 0.4).astype('float32')) and api(f'/api/datasets/{thr["dataset_id"]}')['value_type'] == 'class')

prof = api(f'/api/datasets/{r["dataset_id"]}/profile')
txt = json.dumps(prof, ensure_ascii=False)
R.check('ประวัติไฟล์บอกไฟล์ต้นทาง + สูตร', img in [x['id'] for x in prof['made_by']['parents']] and '(NIR - RED)' in txt)

# ---------- trend ----------
years = [2015, 2020, 2024]
base = rng.uniform(0, 10, (H, W))
yr = []
for y in years:
    a = (2 * (y - 2015) + base).astype('float32')
    if y == 2020:
        a[:5, :5] = -1                                # ขาดปีกลางมุมซ้ายบน
    yr.append(add(tif(f'v_{y}.tif', a)))
items = [dict(dataset_id=i, year=y) for i, y in zip(yr, years)]
sl = run('trend', dict(items=items, stat='slope', target_res=src, min_years=2))
with rasterio.open(sl['output']) as f:
    a = f.read(1)
R.check('แนวโน้มต่อปี = 2 ทุกพิกเซล (รวมพิกเซลที่ขาดปีกลาง เมื่อ min_years=2)', np.allclose(a, 2, atol=1e-4), f'min {a.min():.4f} max {a.max():.4f}')
sl2 = run('trend', dict(items=items, stat='slope', target_res=src))
with rasterio.open(sl2['output']) as f:
    m = f.read(1, masked=True)
R.check('ค่าเริ่ม (ต้องมีทุกปี) → พิกเซลที่ขาดปีกลาง = ไม่มีข้อมูล', int(m.mask.sum()) == 25, f'nodata {int(m.mask.sum())}')
ch = run('trend', dict(items=items, stat='change', target_res=src))
with rasterio.open(ch['output']) as f:
    a = f.read(1, masked=True)
R.check('เปลี่ยนแปลง ปีท้าย − ปีแรก = 18 ทุกพิกเซล (ใช้แค่ปีแรก+ปีท้าย ปีกลางขาดได้)', np.allclose(a.compressed(), 18, atol=1e-4) and int(a.mask.sum()) == 0)
ca = run('trend', dict(items=items, stat='count_above', threshold=15, target_res=src, min_years=2))
with rasterio.open(ca['output']) as f:
    a = f.read(1)
vals = np.stack([2 * (y - 2015) + base for y in years])
want = (vals > 15).sum(0).astype('float32')
want[:5, :5] = ((vals[[0, 2], :5, :5]) > 15).sum(0)
R.check('จำนวนปีที่ค่า > เกณฑ์ ตรงกับคำตอบ', np.array_equal(a, want))
e = api('/api/estimate', dict(kind='trend', params=dict(items=items[:1], stat='slope', target_res=src)))
R.check('อนุกรมเวลาปีเดียว → ปฏิเสธ', not e.get('ok'), e.get('error', '')[:60])

# ---------- เปรียบเทียบ: ไฟล์เดียวกัน = ไม่ต่าง · ต่างเล็กน้อย = บอก % พิกเซลที่ต่าง ----------
same_a = add(tif('cmp_a.tif', base.astype('float32')))
same_b = add(tif('cmp_a_copy.tif', base.astype('float32')))
pert = base.copy(); pert[:6, :] *= 1.05                       # 6 จาก 60 แถว = 10% ของพิกเซล ค่าเพิ่ม 5%
same_c = add(tif('cmp_a_pert.tif', pert.astype('float32')))
c1 = run('change', dict(a_id=same_a, b_id=same_b, mode='diff', target_res=src))['summary']
c2 = run('change', dict(a_id=same_a, b_id=same_c, mode='diff', target_res=src))['summary']
R.check('ไฟล์เดียวกันสองชุด → พิกเซลต่าง 0% · ผลรวมเท่ากัน · r = 1', c1['pct_pixels_changed'] == 0 and abs(c1['pct']) < 1e-9 and abs(c1['correlation'] - 1) < 1e-9,
        f"{c1['pct_pixels_changed']}% · ผลรวม {c1['pct']:.2e}% · r {c1['correlation']}")
R.check('แก้ 10% ของพิกเซล +5% → พิกเซลต่าง 10% · บอกผลรวมต่าง/ต่างเฉลี่ย/สหสัมพันธ์', abs(c2['pct_pixels_changed'] - 10) < 0.01 and c2['pixels_up'] == 6 * W and c2['correlation'] > 0.99,
        f"{c2['pct_pixels_changed']:.2f}% · ผลรวม +{c2['pct']:.3f}% · |Δ| เฉลี่ย {c2['mean_abs_diff']:.4f} · r {c2['correlation']:.5f}")

# ---------- mosaic ----------
L_, Rt = rng.uniform(0, 5, (H, W)), rng.uniform(5, 9, (H, W))
t1, t2 = add(tif('tile_l.tif', L_), 'density'), add(tif('tile_r.tif', Rt, x0=X0 + W * RES), 'density')
mo = run('mosaic', dict(dataset_ids=[t1, t2], method='first', name='mosaic_test'))
with rasterio.open(mo['output']) as f:
    a = f.read(1)
R.check('รวม 2 แผ่นติดกัน → ไฟล์เดียว ค่าเดิมครบ', a.shape == (H, 2 * W) and np.allclose(a[:, :W], L_) and np.allclose(a[:, W:], Rt), f'{a.shape}')

# ---------- vmerge ----------
def gjson(name, polys):
    fs = [dict(type='Feature', properties=dict(code=i), geometry=dict(type='Polygon', coordinates=[[[x, y], [x + .1, y], [x + .1, y + .1], [x, y + .1], [x, y]]]))
          for i, (x, y) in enumerate(polys)]
    p = TMP / name
    p.write_text(json.dumps(dict(type='FeatureCollection', features=fs)), encoding='utf-8')
    return add(p, None)


v1, v2 = gjson('a.geojson', [(100, 13), (100.1, 13)]), gjson('b.geojson', [(100.2, 13), (100.3, 13), (100.4, 13)])
vm = run('vmerge', dict(dataset_ids=[v1, v2], name='merged_test'))
import geopandas as gpd  # noqa: E402
g = gpd.read_file(vm['output'])
R.check('รวมเวกเตอร์ → 5 feature + คอลัมน์ source', len(g) == 5 and set(g['source']) == {'a', 'b'} or len(g) == 5 and g['source'].nunique() == 2, f'{len(g)} · {sorted(set(g["source"]))}')
vd = run('vmerge', dict(dataset_ids=[v1, v2], dissolve=True, name='dissolved_test'))
g = gpd.read_file(vd['output'])
R.check('dissolve → 1 รูป', len(g) == 1 and abs(g.geometry.union_all().area - 0.05) < 1e-9, f'{len(g)} · {len(g.geometry)}')
# รูปซ้อน/แตะกันหลายกลุ่ม + รูปเสีย (bow-tie) → รวมแบบกลุ่มที่แตะกัน ต้องเท่ากับ union_all ทั้งก้อน
import shapely  # noqa: E402
rng2 = np.random.default_rng(5)
boxes = [shapely.box(x, y, x + rng2.uniform(.005, .03), y + rng2.uniform(.005, .03)) for x, y in zip(rng2.uniform(100, 100.5, 3000), rng2.uniform(13, 13.5, 3000))]
bow = shapely.Polygon([(101, 13), (101.1, 13.1), (101.1, 13), (101, 13.1), (101, 13)])
fs = [dict(type='Feature', properties=dict(grp=i % 3), geometry=shapely.geometry.mapping(b)) for i, b in enumerate(boxes + [bow])]
(TMP / 'many1.geojson').write_text(json.dumps(dict(type='FeatureCollection', features=fs[::2])), encoding='utf-8')
(TMP / 'many2.geojson').write_text(json.dumps(dict(type='FeatureCollection', features=fs[1::2])), encoding='utf-8')
vmn = [add(TMP / 'many1.geojson', None), add(TMP / 'many2.geojson', None)]
t0 = time.time()
vx = run('vmerge', dict(dataset_ids=vmn, dissolve=True, name='many_dissolved'))
gx = gpd.read_file(vx['output'])
ref = shapely.union_all(shapely.make_valid(np.array(boxes + [bow])))
sd = shapely.symmetric_difference(gx.geometry.iloc[0], ref).area
R.check('dissolve รูปซ้อนหลายพันรูป + รูปเสีย = union_all ทั้งก้อน (ต่าง < 1e-9 ของพื้นที่)', len(gx) == 1 and gx.geometry.iloc[0].is_valid and sd < 1e-9 * ref.area,
        f'{time.time() - t0:.1f} วิ · พื้นที่ {gx.geometry.iloc[0].area:.6f} vs {ref.area:.6f}')
vf = run('vmerge', dict(dataset_ids=vmn, dissolve=True, dissolve_field='grp', name='many_by_grp'))
gf = gpd.read_file(vf['output'])
okf = len(gf) == 3 and all(abs(r.geometry.area - shapely.union_all(shapely.make_valid(np.array([f for i, f in enumerate(boxes + [bow]) if i % 3 == r.grp]))).area) < 1e-9 for r in gf.itertuples())
R.check('dissolve ตามฟิลด์ → 1 รูปต่อค่า พื้นที่ตรงทุกกลุ่ม', okf, f'{len(gf)} กลุ่ม {sorted(gf.grp.tolist())}')
sys.exit(R.done())
