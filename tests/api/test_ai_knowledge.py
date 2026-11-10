# -*- coding: utf-8 -*-
"""ความรู้ข้อมูล · บัตรข้อมูล Data hub · สถิติความสัมพันธ์ของไบแวเรียต
- คลังความรู้: SAR → สูตรแปลง dB · LST → × 0.02 − 273.15 · ชื่อชุดจับคู่หัวข้อถูก (VIIRS LST ไม่ปนกับ night light)
- บัตรข้อมูล: MODIS LST มีตัวแปร LST_Day_1km (Kelvin, × 0.02) + ดึงด้วย satellite ได้ · night light Zenodo มีไฟล์รายปี 2000–2024 · GEE บอก gee_id + ต้องมีบัญชี
- สถิติไบแวเรียต (ข้อมูลสังเคราะห์รู้คำตอบ): Y = 2X + noise → ρ สูง, ช่องทแยงเกิดบ่อยเกินคาด · Y สุ่มอิสระ → ρ ≈ 0, V ≈ 0 · กราฟ 3 รูป + CSV/MD"""
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
from app import ai_tools, knowledge  # noqa: E402


def _call(method, path, body=None, params=None):
    return s.request(method, ENGINE + path, json=body, params=params, timeout=600).json()


ai_tools._call = _call


def api(path, body=None, method=None):
    return s.request(method or ('POST' if body is not None else 'GET'), ENGINE + path, json=body, timeout=900).json()


# ---------- คลังความรู้ ----------
k = ai_tools.t_get_data_knowledge(query='sentinel-1-rtc vv')
R.check('SAR → หัวข้อ sar_backscatter + สูตรแปลง dB', 'sar_backscatter' in k and any('10 * log10(A)' in c for c in k['sar_backscatter']['calibration']))
k = ai_tools.t_get_data_knowledge(topics=['lst'])
R.check('LST → สูตร °C = × 0.02 − 273.15', any('A * 0.02 - 273.15' in c for c in k['lst']['calibration']))
R.check('จับคู่หัวข้อ: VIIRS LST ไม่ปน night light · ประชากร/ที่ดินถูก',
        knowledge.match('VNP21A1D Day Land Surface Temperature') == ['lst'] and knowledge.match('tha_pop_2024_CN_100m') == ['population']
        and 'land_cover' in knowledge.match('esa-worldcover map'), str(knowledge.match('VNP21A1D Day Land Surface Temperature')))
idx = ai_tools.t_get_data_knowledge()
R.check('ไม่ระบุหัวข้อ → รายการหัวข้อทั้งหมด (หลักการ + ชนิดข้อมูล)', len(idx.get('topics', {})) >= 15 and 'reliability' in idx['topics'])

# ---------- บัตรข้อมูล ----------
c = ai_tools.t_get_hub_item('pc:modis-11a2-061')['card']
v = {x['name']: x for x in c['variables']['items']}
R.check('MODIS LST: ตัวแปร LST_Day_1km หน่วย Kelvin scale 0.02 · ดึงด้วย satellite ได้',
        v.get('LST_Day_1km', {}).get('unit') == 'Kelvin' and v['LST_Day_1km'].get('scale') == 0.02 and c['access']['satellite_collection'] == 'modis-11A2-061')
c = ai_tools.t_get_hub_item('zenodo:8277198')['card']
R.check('night light Zenodo: ไฟล์รายปีครบ 2000–2024 + แหล่ง/สัญญาอนุญาต', all(y in c['time']['years_with_files'] for y in range(2000, 2025)) and c['source']['license'],
        f'{len(c["time"]["years_with_files"])} ปี · {c["source"]["license"]}')
c = ai_tools.t_get_hub_item('gee:nasa-viirs-002-vnp21a1d')['card']
R.check('GEE: บอก gee_id + ต้องมีบัญชี + ช่วงเวลา/ความถี่ + แบนด์ LST_1KM', c['access']['level'] == 'account' and c['access']['gee_id'] == 'NASA/VIIRS/002/VNP21A1D'
        and c['time']['cadence'] and any(x['name'] == 'LST_1KM' for x in c['variables']['items']))
sr = ai_tools.t_search_data_hub('land surface temperature', 5)['results']
R.check('ผลค้นมีสรุปตัวแปร/ความละเอียด/ช่วงเวลา', any(x.get('n_variables') for x in sr) and any(x.get('start') for x in sr))

# ---------- สถิติไบแวเรียต ----------
TMP = Path(tempfile.mkdtemp(prefix='ainu_bs_'))
H, W, RES = 120, 120, 1 / 120


def tif(name, a):
    p = TMP / name
    with rasterio.open(p, 'w', driver='GTiff', width=W, height=H, count=1, dtype='float32', crs='EPSG:4326',
                       transform=from_origin(100, 14, RES, RES), nodata=-1) as d:
        d.write(a.astype('float32'), 1)
    return p


def add(p, vt='density'):
    api('/api/datasets', dict(paths=[str(p)]))
    d = [x for x in api('/api/datasets') if x['path'] == str(p)][-1]
    api(f'/api/datasets/{d["id"]}', dict(value_type=vt, value_type_confirmed=True), 'PATCH')
    return d['id']


def biv(xi, yi, name):
    from app import palettes
    src = [o for o in api(f'/api/res-options?ids={xi},{yi}')['options'] if o['is_source']][0]['value']
    p = dict(x=dict(dataset_id=xi, n=3, method='quantile', metric='value'), y=dict(dataset_id=yi, n=3, method='quantile', metric='value'),
             target_res=src, name=name, colors=palettes.interpolate(palettes.BY_ID[palettes.DEFAULT_PALETTE]['colors'], 3, 3), highlight=[9])
    jid = api('/api/jobs', dict(kind='bivariate', params=p))['job']
    while True:
        j = api(f'/api/jobs/{jid}'); j = j.get('job', j)
        if j['status'] in ('done', 'failed'):
            break
        time.sleep(1)
    assert j['status'] == 'done', j.get('error')
    return j['result']['dataset_id']


rng = np.random.default_rng(3)
yy, xx = np.mgrid[0:H, 0:W]
X = (xx + yy).astype(float) + rng.normal(0, 3, (H, W))                     # มีโครงสร้างเชิงพื้นที่ (เกาะกลุ่ม)
xid = add(tif('bs_x.tif', X))
yid = add(tif('bs_y.tif', 2 * X + rng.normal(0, 10, (H, W))))
zid = add(tif('bs_z.tif', rng.normal(50, 10, (H, W))))
m1, m2 = biv(xid, yid, 'bs_related'), biv(xid, zid, 'bs_independent')
r1 = api(f'/api/datasets/{m1}/bivstats', dict(force=True))
r2 = api(f'/api/datasets/{m2}/bivstats', dict(force=True))
c1, c2 = r1['correlation'], r2['correlation']
R.check('Y = 2X + noise → ρ > 0.9 · ช่องทแยง (1,1)(3,3) เกิดบ่อยเกินคาด', c1['spearman_rho'] > 0.9 and r1['crosstab']['obs_exp'][2][2] > 2 and r1['crosstab']['obs_exp'][0][0] > 2,
        f'ρ {c1["spearman_rho"]:.3f} · V {r1["crosstab"]["cramers_v"]:.2f} · ε² {r1["by_x_class"]["kruskal"]["epsilon2"]:.2f}')
R.check('Y สุ่มอิสระ → ขนาดผลเล็กมาก |ρ| < 0.05 · Cramér V < 0.05 · สรุปว่า "แทบไม่มี"', abs(c2['spearman_rho']) < 0.05 and r2['crosstab']['cramers_v'] < 0.05 and c2['strength'] == 'แทบไม่มี',
        f'ρ {c2["spearman_rho"]:.3f} · V {r2["crosstab"]["cramers_v"]:.3f} · p {c2["p_adjusted"]}')
R.check("X มีโครงสร้างเชิงพื้นที่ → Moran's I สูง · Y สุ่ม → ใกล้ 0 · n ประสิทธิผล < n", r2['spatial']['moran_x'] > 0.8 and abs(r2['spatial']['moran_y']) < 0.1
        and c1['n_effective'] < r1['sample']['n'], f"I_x {r2['spatial']['moran_x']:.2f} · I_y {r2['spatial']['moran_y']:.2f} · n_eff {c1['n_effective']} / {r1['sample']['n']}")
ok = all(s.get(f'{ENGINE}/api/datasets/{m1}/bivstats/{f}').status_code == 200 for f in ('scatter.png', 'crosstab.png', 'box.png', 'biv_stats.csv', 'biv_stats.md'))
R.check('กราฟ 3 รูป + CSV + รายงาน .md เปิดได้', ok)
t = ai_tools.t_analyze_bivariate(m1)
R.check('เครื่องมือผู้ช่วย analyze_bivariate คืนตัวเลขหลัก + การตีความ + คำเตือน', t['spearman_rho'] > 0.9 and t['interpretation'] and t['warnings'])
sys.exit(R.done())
