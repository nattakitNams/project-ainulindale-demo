# -*- coding: utf-8 -*-
"""ทดสอบ vector → raster แบบหลายเธรด + ข้ามไทล์ว่าง: ผลต้องตรงกับแบบเธรดเดียวทุกพิกเซล และวัดเวลา
รัน: python -m tests.check_rasterize_speed [ความละเอียด เช่น 3/10]"""
import os
import sys
import tempfile
import time

if 'AINU_WORKSPACE' not in os.environ:
    os.environ['AINU_WORKSPACE'] = tempfile.mkdtemp(prefix='ainu_rz_')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np  # noqa: E402
import rasterio  # noqa: E402

from app import catalog, config, db, export, ops  # noqa: E402
from tests.refdata import POP, PROJ  # noqa: E402

SHP = os.path.join(PROJ, 'raw_data', 'year_freq_flood', 'y2015.shp')


def run(vid, ref, res, nth):
    orig = ops.workers_for
    ops.workers_for = lambda b: nth
    try:
        p = dict(dataset_id=vid, ref_dataset_id=ref, target_res=res, mode='presence', rule='center', name=f'y2015_{nth}t')
        od = export.new_out_dir(config.DIRS['derived'], 'rasterize', p['name'], p)
        logs = []
        t0 = time.time()
        r = ops.op_rasterize(dict(id=0, params=p, out_dir=str(od)), lambda f, m=None: None, logs.append)
        return r['output'], time.time() - t0, [l for l in logs if 'ข้าม' in l]
    finally:
        ops.workers_for = orig


def main():
    res = sys.argv[1] if len(sys.argv) > 1 else '3'
    config.ensure_workspace()
    db.init()
    ref = catalog.add_path(POP)[0][0]
    db.update('datasets', ref, value_type='count', value_type_confirmed=1)
    vid = catalog.add_path(SHP)[0][0]
    a, t1, l1 = run(vid, ref, res, 1)
    b, tn, ln = run(vid, ref, res, ops.workers_for(2560 * 2560 * 8))
    with rasterio.open(a) as x, rasterio.open(b) as y:
        print(f'{res}″: {x.width:,} × {x.height:,} · nodata {x.nodata}')
        diff = n1 = 0
        for _, w in x.block_windows(1):
            ax, by = x.read(1, window=w), y.read(1, window=w)
            diff += int((ax != by).sum())
            n1 += int((by == 1).sum())
    print(f'เธรดเดียว {t1:,.1f} วินาที · หลายเธรด {tn:,.1f} วินาที · เร็วขึ้น {t1 / tn:,.1f} เท่า · {ln[-1] if ln else ""}')
    print(f'พิกเซลต่างกัน {diff:,} · พิกเซล "มี" {n1:,}')
    print('ผล:', 'ผ่าน ✔' if diff == 0 else 'ไม่ผ่าน ✘')
    return diff


if __name__ == '__main__':
    sys.exit(1 if main() else 0)
