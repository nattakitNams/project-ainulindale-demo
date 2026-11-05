# -*- coding: utf-8 -*-
"""ทดสอบพื้นที่ศึกษา: ไบแวเรียตเฉพาะจังหวัดสิงห์บุรี (gb_ADM1, อิงศูนย์กลางพิกเซลแม่ 100 ม. แบบ Colab)
ต้องได้เขตแดง 10 ม. = 341.16 · 100 ม. = 123.30 · 1 กม. = 0 (PROJECT_BRIEF 2.4)
รันใน workspace ชั่วคราว:  set AINU_WORKSPACE=<โฟลเดอร์ทดสอบ> แล้ว python -m tests.check_aoi"""
import os
import sys
import tempfile

if 'AINU_WORKSPACE' not in os.environ:
    os.environ['AINU_WORKSPACE'] = tempfile.mkdtemp(prefix='ainu_test_')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import aoi, catalog, config, db, export, ops, palettes  # noqa: E402
from tests.refdata import FLOOD, POP, PROJ  # noqa: E402

EXPECT_RED = {'3/10': 341.16, '3': 123.30, '30': 0.0}


def main():
    config.ensure_workspace()
    db.init()
    q = lambda: None  # noqa: E731
    pop = catalog.add_path(POP)[0][0]
    fl = catalog.add_path(FLOOD)[0][0]
    adm = catalog.add_path(os.path.join(PROJ, 'output', 'bivariate', 'gb_ADM1.gpkg'))[0][0]
    db.update('datasets', pop, value_type='count', value_type_confirmed=1)
    db.update('datasets', fl, value_type='class', value_type_confirmed=1, nodata_as=0)
    aid = aoi.create_from_dataset('สิงห์บุรี', db.get('datasets', adm), 'shapeName', ['Sing Buri Province'])
    print('AOI พื้นที่', round(db.get('aoi', aid)['area_km2'], 1), 'ตร.กม.')
    fails = 0
    for res in ('3/10', '3', '30'):
        x = dict(dataset_id=pop, n=3, method='degurba' if res == '30' else 'breaks', breaks=[300, 1500], metric='density')
        p = dict(x=x, y=dict(dataset_id=fl, n=3, method='breaks', breaks=[1, 5], metric='value'), target_res=res,
                 colors=palettes.BY_ID['traffic']['colors'], highlight=[8, 9], name=f'singburi_{res.replace("/", "_")}',
                 aoi_id=aid, aoi_rule='center', aoi_mask_res='3')
        od = export.new_out_dir(config.DIRS['maps'], 'bivariate', p['name'], p)
        if res == '30':
            p['aoi_mask_res'] = None                      # 1 กม. หยาบกว่า 100 ม. → mask ที่ความละเอียดผลลัพธ์
        r = ops.op_bivariate(dict(id=0, params=p, out_dir=str(od)), lambda f, m=None: None, lambda m: None)
        red = r['summary']['highlight_weight']
        ok = abs(red - EXPECT_RED[res]) < 0.01
        fails += not ok
        print(f'{"✔" if ok else "✘"} {res}″ เขตแดงสิงห์บุรี = {red:,.2f} (คาด {EXPECT_RED[res]:,.2f}) · '
              f'คนทั้งจังหวัด {r["summary"]["weight_total"]:,.0f} · กริด {r["summary"]["grid"]["width"]}×{r["summary"]["grid"]["height"]}')
    print('ผล:', 'ผ่าน ✔' if not fails else 'ไม่ผ่าน ✘')
    return fails


if __name__ == '__main__':
    sys.exit(1 if main() else 0)
