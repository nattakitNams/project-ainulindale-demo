# -*- coding: utf-8 -*-
"""ทดสอบ vector → raster: rasterize จังหวัด gb_ADM1 (ศูนย์กลางพิกเซล, ค่า = ลำดับ feature) แล้วเทียบไทล์ *_pid.tif ของ Colab
  ก) ที่ 0.3″ (10 ม.) เฉพาะพื้นที่ศึกษาสิงห์บุรี+ข้างเคียง → เทียบทีละพิกเซล
  ข) ที่ 3″ (100 ม.) ทั้งประเทศ → นับพิกเซลแม่ที่รหัสต่างจาก Colab (ต่างได้เฉพาะแนวขอบจังหวัด ถ้า Colab ทำที่ 10 ม.)"""
import glob
import os
import sys
import tempfile

if 'AINU_WORKSPACE' not in os.environ:
    os.environ['AINU_WORKSPACE'] = tempfile.mkdtemp(prefix='ainu_test_')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from rasterio.windows import from_bounds  # noqa: E402

from app import aoi, catalog, config, db, export, ops  # noqa: E402
from tests.refdata import FLOOD, POP, PROJ  # noqa: E402

def read_pid(bounds, shape):
    """อ่านรหัส Colab จากไทล์ _pid ที่ทับกรอบ (อยู่ในกริด 10 ม. เดียวกับ VRT น้ำท่วม)"""
    with rasterio.open(FLOOD) as f:
        T = f.transform
    out = np.zeros(shape, 'int32')
    x0, y1 = bounds[0], bounds[3]
    C0 = round((x0 - T.c) / T.a)
    R0 = round((T.f - y1) / -T.e)
    for t in glob.glob(os.path.join(PROJ, 'raw', 'tiles_thailand_10m', '*_pid.tif')):
        with rasterio.open(t) as d:
            c = round((d.transform.c - T.c) / T.a)
            r = round((T.f - d.transform.f) / -T.e)
            rr0, cc0 = max(r, R0), max(c, C0)
            rr1, cc1 = min(r + d.height, R0 + shape[0]), min(c + d.width, C0 + shape[1])
            if rr1 <= rr0 or cc1 <= cc0:
                continue
            a = d.read(1, window=rasterio.windows.Window(cc0 - c, rr0 - r, cc1 - cc0, rr1 - rr0))
            out[rr0 - R0:rr1 - R0, cc0 - C0:cc1 - C0] = a
    return out


def run(adm, ref, res, aoi_id=None):
    p = dict(dataset_id=adm, ref_dataset_id=ref, target_res=res, mode='attribute', field='__index__', rule='center',
             name=f'pid_{res.replace("/", "_")}', aoi_id=aoi_id)
    od = export.new_out_dir(config.DIRS['derived'], 'rasterize', p['name'], p)
    return ops.op_rasterize(dict(id=0, params=p, out_dir=str(od)), lambda f, m=None: None, lambda m: None)['output']


def main():
    config.ensure_workspace()
    db.init()
    pop = catalog.add_path(POP)[0][0]
    fl = catalog.add_path(FLOOD)[0][0]
    adm = catalog.add_path(os.path.join(PROJ, 'output', 'bivariate', 'gb_ADM1.gpkg'))[0][0]
    db.update('datasets', pop, value_type='count', value_type_confirmed=1)
    db.update('datasets', fl, value_type='class', value_type_confirmed=1)
    fails = 0
    # ก) 10 ม. ในกรอบภาคกลาง (ใช้ AOI = สิงห์บุรี + อ่างทอง + ลพบุรี เพื่อจำกัดกรอบ แต่เทียบทั้งกรอบโดยไม่ mask)
    aid = aoi.create_from_dataset('กลาง', db.get('datasets', adm), 'shapeName',
                                  ['Sing Buri Province', 'Ang Thong Province', 'Lopburi Province'])
    a_id = aoi.create_from_geojson('กรอบ', dict(type='Polygon', coordinates=[[[100.0, 14.4], [100.9, 14.4], [100.9, 15.3], [100.0, 15.3], [100.0, 14.4]]]))
    out = run(adm, fl, '3/10', a_id)
    with rasterio.open(out) as d:
        mine = d.read(1).astype('int32')
        mine[mine == 255] = 0
        pid = read_pid(d.bounds, mine.shape)
    inside = mine > 0
    bad = int((mine[inside] != pid[inside]).sum())
    print(f'ก) 10 ม. กรอบภาคกลาง {mine.shape[1]:,}×{mine.shape[0]:,}: พิกเซลในพื้นที่ {int(inside.sum()):,} · รหัสต่างจาก Colab {bad:,}')
    fails += bad > 0
    # ข) 100 ม. ทั้งประเทศ
    out = run(adm, pop, '3')
    with rasterio.open(out) as d:
        mine = d.read(1).astype('int32')
        mine[mine == 255] = 0
        T = d.transform
    tiles = glob.glob(os.path.join(PROJ, 'raw', 'tiles_thailand_10m', '*_pid.tif'))
    n = diff = 0
    for t in tiles:
        with rasterio.open(t) as d:
            a = d.read(1)[5::10, 5::10]                # ช่องลูกกลางพิกเซลแม่
            R = round((T.f - d.transform.f) / -T.e)
            C = round((d.transform.c - T.c) / T.a)
        h, w = min(a.shape[0], mine.shape[0] - R), min(a.shape[1], mine.shape[1] - C)
        m = mine[R:R + h, C:C + w]
        a = a[:h, :w]
        n += m.size
        diff += int((m != a).sum())
    print(f'ข) 100 ม. ทั้งประเทศ: พิกเซลแม่ {n:,} · รหัสต่าง {diff:,} ({diff / n * 100:.4f}%) — ต่างได้เฉพาะแนวขอบ')
    print('ผล:', 'ผ่าน ✔' if not fails else 'ไม่ผ่าน ✘')
    return fails


if __name__ == '__main__':
    sys.exit(1 if main() else 0)
