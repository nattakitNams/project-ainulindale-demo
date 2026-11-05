# -*- coding: utf-8 -*-
"""รันไบแวเรียตทั้งประเทศ (แบบงานเดิม) ใน workspace ชั่วคราว แล้วเทียบไฟล์เดิมทีละพิกเซล + จับเวลา
รัน: python -m tests.full_bivariate 3      (หรือ 3/10 สำหรับ 10 ม. — ~10+ นาที)"""
import os
import sys
import tempfile
import time

os.environ.setdefault('GDAL_NUM_THREADS', 'ALL_CPUS')        # เหมือน worker จริง
if 'AINU_WORKSPACE' not in os.environ:
    os.environ['AINU_WORKSPACE'] = tempfile.mkdtemp(prefix='ainu_full_')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import catalog, config, db, export, ops, palettes  # noqa: E402
from tests import compare_output  # noqa: E402
from tests.refdata import FLOOD, POP  # noqa: E402


def main():
    res = sys.argv[1] if len(sys.argv) > 1 else '3'
    config.ensure_workspace()
    db.init()
    pop = catalog.add_path(POP)[0][0]
    fl = catalog.add_path(FLOOD)[0][0]
    db.update('datasets', pop, value_type='count', value_type_confirmed=1)
    db.update('datasets', fl, value_type='class', value_type_confirmed=1, nodata_as=0)
    p = dict(x=dict(dataset_id=pop, n=3, method='breaks', breaks=[300, 1500], metric='density'),
             y=dict(dataset_id=fl, n=3, method='breaks', breaks=[1, 5], metric='value'), target_res=res,
             colors=palettes.BY_ID['traffic']['colors'], highlight=[8, 9], name='full')
    od = export.new_out_dir(config.DIRS['maps'], 'bivariate', 'full', p)
    t0 = time.time()
    marks = {}

    def log(m):
        if 'พร้อมกัน' in m:
            print(m, flush=True)
    last = [0]

    def P(f, m=None):
        if m and 'overview' in m and 'ov' not in marks:
            marks['ov'] = time.time() - t0
    ops.op_bivariate(dict(id=0, params=p, out_dir=str(od)), P, log)
    total = time.time() - t0
    print(f'ไทล์ {marks.get("ov", total):,.0f} วินาที · overview {total - marks.get("ov", total):,.0f} วินาที · รวม {total:,.0f} วินาที', flush=True)
    return compare_output.main(od, res)


if __name__ == '__main__':
    sys.exit(1 if main() else 0)
