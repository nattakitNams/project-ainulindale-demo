# -*- coding: utf-8 -*-
"""ทดสอบ V3 ใน workspace ชั่วคราว: zonal · change · sensitivity · รายงาน PDF
รัน:  python -m tests.check_v3"""
import os
import sys
import tempfile

if 'AINU_WORKSPACE' not in os.environ:
    os.environ['AINU_WORKSPACE'] = tempfile.mkdtemp(prefix='ainu_v3_')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import aoi, catalog, config, db, export, ops, ops3, palettes, report  # noqa: E402
from tests.refdata import FLOOD, POP, PROJ  # noqa: E402

P = lambda f, m=None: None  # noqa: E731
L = lambda m: None  # noqa: E731


def job(kind, params, base):
    return dict(id=0, params=params, out_dir=str(export.new_out_dir(config.DIRS[base], kind, kind, params)))


def main():
    config.ensure_workspace()
    db.init()
    pop = catalog.add_path(POP)[0][0]
    p15 = catalog.add_path(os.path.join(PROJ, 'raw_data', 'ข้อมูลประชากร', 'tha_pop_2015_CN_100m_R2025A_v1.tif'))[0][0]
    fl = catalog.add_path(FLOOD)[0][0]
    adm = catalog.add_path(os.path.join(PROJ, 'output', 'bivariate', 'gb_ADM1.gpkg'))[0][0]
    for i in (pop, p15):
        db.update('datasets', i, value_type='count', value_type_confirmed=1)
    db.update('datasets', fl, value_type='class', value_type_confirmed=1, nodata_as=0)
    box = aoi.create_from_geojson('ภาคกลางตอนบน', dict(type='Polygon', coordinates=[[[99.8, 14.3], [100.9, 14.3], [100.9, 15.6], [99.8, 15.6], [99.8, 14.3]]]))
    sb = aoi.create_from_dataset('สิงห์บุรี', db.get('datasets', adm), 'shapeName', ['Sing Buri Province'])
    fails = 0

    # zonal: จังหวัด × (ความหนาแน่น, % คนในพื้นที่เคยท่วม) ที่ 3″
    p = dict(zones_dataset_id=adm, zone_field='shapeName', target_res='3', aoi_id=sb, rule='center',
             x=dict(dataset_id=pop, stat='density', n=3, method='breaks', breaks=[300, 1500], label='ความหนาแน่น'),
             y=dict(dataset_id=fl, stat='share_weight', weight_dataset_id=pop, threshold=1, n=3, method='breaks', breaks=[10, 30], label='% คนในพื้นที่เคยท่วม'),
             colors=palettes.BY_ID['bluered']['colors'], highlight=[8, 9], name='zonal_test')
    r = ops3.op_zonal(job('zonal', p, 'maps'), P, L)
    import geopandas as gpd
    g = gpd.read_file(r['output'])
    row = g[g['shapeName'] == 'Sing Buri Province'].iloc[0]
    print(f'zonal: {len(g)} พื้นที่ · สิงห์บุรี ความหนาแน่น {row.x_value:,.1f} · % คนในพื้นที่เคยท่วม {row.y_value:,.1f} · รหัส {row.code} · คน {row.y_weight:,.0f}')
    # เทียบ: 100 ม. ทั้งจังหวัด = 165,900 คน (check_aoi) · คนในพื้นที่เคยท่วม (รหัส 4–9 ที่ 100 ม.) ต้องได้จาก bivariate
    pb = dict(x=dict(dataset_id=pop, n=3, method='breaks', breaks=[300, 1500], metric='density'),
              y=dict(dataset_id=fl, n=2, method='breaks', breaks=[1], metric='value'), target_res='3',
              colors=palettes.interpolate(palettes.BY_ID['bluered']['colors'], 3, 2), highlight=[4, 5, 6], aoi_id=sb, aoi_rule='center')
    s = ops.op_bivariate(dict(id=0, params=pb, out_dir=None), P, L, stats_only=True)['summary']
    want = s['highlight_weight'] / s['weight_total'] * 100
    ok = abs(row.y_weight - s['weight_total']) < 0.5 and abs(row.y_value - want) < 0.01
    fails += not ok
    print(f'{"✔" if ok else "✘"} zonal ตรงกับ bivariate สถิติ: คน {s["weight_total"]:,.1f} · % เคยท่วม {want:.3f}')

    # change: ประชากร 2015 → 2024 ในกรอบภาคกลาง
    pc = dict(a_id=p15, b_id=pop, mode='diff', target_res='30', aoi_id=box, name='pop_change')
    r = ops3.op_change(job('change', pc, 'derived'), P, L)
    s = r['summary']
    print(f'change: ก่อน {s["sum_before"]:,.0f} · หลัง {s["sum_after"]:,.0f} · ต่าง {s["diff"]:+,.0f} ({s["pct"]:+.2f}%) · เพิ่ม {s["pixels_up"]:,} ลด {s["pixels_down"]:,}')

    # sensitivity: 2 × 2 ชุดเกณฑ์ ที่ 3″ สิงห์บุรี
    base = dict(x=dict(dataset_id=pop, n=3, method='breaks', breaks=[300, 1500], metric='density'),
                y=dict(dataset_id=fl, n=3, method='breaks', breaks=[1, 5], metric='value'), target_res='3',
                colors=palettes.BY_ID['traffic']['colors'], highlight=[8, 9], aoi_id=sb, aoi_rule='center', aoi_mask_res='3')
    ps = dict(base=base, x_breaks_sets=[[300, 1500], [200, 1000]], y_breaks_sets=[[1, 5], [1, 3]], resolutions=['3', '3/10'])
    r = ops3.op_sensitivity(job('sensitivity', ps, 'maps'), P, L)
    for x in r['summary']['results']:
        print(f'  {x["label"]}: เขตเน้น {x["highlight_weight"]:,.2f}')
    first = [x for x in r['summary']['results'] if x['res'] == '3/10' and x['x_breaks'] == [300, 1500] and x['y_breaks'] == [1, 5]][0]
    ok = abs(first['highlight_weight'] - 341.16) < 0.01
    fails += not ok
    print(f'{"✔" if ok else "✘"} sensitivity ชุดค่าเดิม 10 ม. = {first["highlight_weight"]:,.2f} (คาด 341.16)')

    # รายงาน PDF
    d = db.get('datasets', r.get('dataset_id') or pop)
    pdf = report.make_pdf(db.get('datasets', pop))
    out = os.path.join(config.WORKSPACE, 'report_test.pdf')
    open(out, 'wb').write(pdf)
    print(f'รายงาน PDF {len(pdf):,} ไบต์ → {out}')
    zid = [x for x in db.query("SELECT id FROM datasets WHERE role='map' AND kind='vector'")][0]['id']
    open(os.path.join(config.WORKSPACE, 'report_zonal.pdf'), 'wb').write(report.make_pdf(db.get('datasets', zid)))
    print('ผล:', 'ผ่าน ✔' if not fails else 'ไม่ผ่าน ✘', '· workspace', config.WORKSPACE)
    return fails


if __name__ == '__main__':
    sys.exit(1 if main() else 0)
