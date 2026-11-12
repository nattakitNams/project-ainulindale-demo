# -*- coding: utf-8 -*-
"""แปลงระบบพิกัดราสเตอร์ (reproject) — ค่าเริ่ม UTM 47N (EPSG:32647) ทั้งประเทศไทย

ทำไมเป็นงานแยก (ไม่แปลงในตัวคำนวณไบแวเรียต): ตัวคำนวณจับกริดที่ซ้อนกันพอดีเป็นพหุคูณจำนวนเต็ม (แม่นยำ ผลรวมไม่หาย)
การแปลง CRS = resample ข้ามกริดที่ไม่ซ้อนกัน → ทำครั้งเดียวได้ชุดใหม่ในคลัง แล้วงานเดิมทุกงานใช้ต่อได้ทันที
กริดผลลัพธ์ยึดมุมที่พหุคูณของขนาดพิกเซล (x0, y0 หารลงตัว) → ชุด 47N ทุกชุดที่ 10 / 100 / 1,000 ม. ซ้อนกันพอดี

กติกาตามประเภทค่า (GDAL warp):
- จำนวนนับ (count) → sum: ถ่วงตามพื้นที่ทับซ้อน ผลรวมคงเดิม (ทดสอบ: หยาบขึ้น / เท่ากัน / ละเอียดขึ้น ผลรวมเท่าเดิม)
  + ปรับสัดส่วนทั้งชั้นให้ผลรวมตรงต้นทางพอดี (ขอบภาพ/ทศนิยม) และบันทึกค่าที่ปรับใน lineage
- ค่าต่อเนื่อง (density) → average (เฉลี่ยถ่วงพื้นที่)
- ชั้น (class) → mode (เสียงข้างมาก) ถ้าหยาบลงเกิน 1.5 เท่า · ไม่งั้น nearest (ขนาดใกล้กัน mode ไม่ต่างแต่ช้ากว่ามาก)
ไทล์ที่ต้นทางว่างทั้งหมดข้าม (น้ำท่วม 10 ม. ทั้งประเทศ ~17,700 ล้านพิกเซล ส่วนใหญ่ว่าง)"""
import concurrent.futures as cf
import math
from fractions import Fraction
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import Window, from_bounds

from . import db, engine, export, gridmath as gm
from .engine import EngineError, band_scale

TARGET = 'EPSG:32647'
NICE = [1, 2, 5, 10, 20, 25, 30, 50, 100, 200, 250, 500, 1000, 2000, 2500, 5000, 10000]
TILE = 2048                                       # พหุคูณ 512 (บล็อก GeoTIFF ของ OutWriter)
CRS_TH = {'EPSG:32647': 'UTM 47N (WGS 84)', 'EPSG:32648': 'UTM 48N (WGS 84)', 'EPSG:4326': 'WGS 84 (องศา)'}


def native_m(ds):
    """ขนาดพิกเซลต้นทางเป็นเมตร (ด้านเหนือ–ใต้) — องศา: ฟิลิปดา × 30.87 ม."""
    m = ds['meta']
    r = abs(m['transform'][0])
    return r * 111_320 if m.get('geographic') else r


def suggest_res(ds):
    """ความละเอียดเมตรที่ใกล้ต้นทางที่สุดในชุดเลขกลม (0.3″ → 10 ม. · 3″ → 100 ม. · 30″ → 1,000 ม.)"""
    n = native_m(ds)
    return min(NICE, key=lambda x: abs(math.log(x / n)))


def plan(ds, target_res=None, crs=TARGET, aoi_bounds=None):
    """กริดผลลัพธ์ (ยังไม่อ่านข้อมูล) — ใช้ทั้งตอนประเมินงานและตอนรัน"""
    m = ds['meta']
    if (m.get('crs_key') or '').upper() == crs.upper():
        raise EngineError(f'"{ds["name"]}" อยู่ใน {CRS_TH.get(crs, crs)} แล้ว')
    res = float(target_res or suggest_res(ds))
    if res <= 0:
        raise EngineError('ความละเอียดต้องมากกว่า 0 เมตร')
    t = m['transform']
    b = (t[2], t[5] - m['height'] * abs(t[4]), t[2] + m['width'] * abs(t[0]), t[5])
    xb = transform_bounds(m.get('crs') or m.get('crs_key'), crs, *b, densify_pts=41)
    if aoi_bounds:                                 # พื้นที่ศึกษา (ใน CRS เป้าหมาย) → ตัดกรอบ
        xb = (max(xb[0], aoi_bounds[0]), max(xb[1], aoi_bounds[1]), min(xb[2], aoi_bounds[2]), min(xb[3], aoi_bounds[3]))
        if xb[2] <= xb[0] or xb[3] <= xb[1]:
            raise EngineError('พื้นที่ศึกษาไม่ทับกับขอบเขตข้อมูล')
    x0, y1 = math.floor(xb[0] / res) * res, math.ceil(xb[3] / res) * res        # มุมเป็นพหุคูณของขนาดพิกเซล → ทุกชุดซ้อนกันพอดี
    W, H = math.ceil((xb[2] - x0) / res), math.ceil((y1 - xb[1]) / res)
    rf = Fraction(res).limit_denominator(1000)
    return engine.Grid(x0, y1, res, res, W, H, crs, False, rf)


def _method(vt, src_m, res):
    if vt == 'count':
        return Resampling.sum
    if vt == 'density':
        return Resampling.average
    return Resampling.mode if res > 1.5 * src_m else Resampling.nearest


def convert(ds, outp, crs=TARGET, target_res=None, aoi_b=None, P=None, log=print):
    """แปลงไฟล์ของชุด ds → outp (CRS เป้าหมาย) · คืน (summary, warnings, grid) — ใช้ทั้งงาน reproject และขั้นท้ายของทุกงาน (ผลลัพธ์เป็น UTM)"""
    P = P or (lambda f, m=None: None)
    if ds['kind'] != 'raster':
        raise EngineError('แปลงระบบพิกัดได้เฉพาะราสเตอร์ (เวกเตอร์แปลงให้อัตโนมัติตอนใช้งานอยู่แล้ว)')
    vt = ds['value_type'] or 'density'
    sm = ds['meta']
    path = ds.get('read_path') or ds['path']
    band = int(ds.get('band') or 1)
    exclude = [float(x) for x in (ds.get('exclude_values') or [])]
    with rasterio.open(path) as d0:
        sc, of = band_scale(d0, band)
        SW, SH = d0.width, d0.height
        try:
            cmap = d0.colormap(band) if sm.get('has_colormap') else None    # แผนที่ไบแวเรียต/ชั้นที่มีตารางสี → คงสีเดิม
        except ValueError:
            cmap = None
    nod = sm.get('nodata')
    grid = plan(ds, target_res, crs, aoi_b)
    res = grid.rx
    src_m = native_m(ds)
    rs = _method(vt, src_m, res)
    from .ops import OutWriter, workers_for
    dt = sm['dtypes'][band - 1]
    if vt in ('count', 'density') or (sc, of) != (1.0, 0.0) or dt.startswith('float'):
        odt, onod = 'float32', -99999.0
    elif dt == 'uint8':
        odt, onod = 'uint8', 255 if nod is None else int(nod)      # ชั้นไบแวเรียต 1–25 / รหัสการใช้ที่ดิน
    else:
        odt, onod = 'int32', -2147483648
    W = OutWriter(outp, grid, odt, onod, colormap=cmap if odt == 'uint8' else None)
    tiles = list(engine.iter_tiles(grid, TILE))
    log(f'{ds["name"]} ({sm.get("crs_key")} · {sm.get("res_label", "")}) → {CRS_TH.get(crs, crs)} · {gm.fmt_num(res)} ม.')
    log(f'กริดผลลัพธ์ {grid.width:,} × {grid.height:,} · วิธี {rs.name} ({ {"count": "จำนวนนับ: ถ่วงพื้นที่ ผลรวมคงเดิม", "density": "เฉลี่ยถ่วงพื้นที่", "class": "ชั้น"}[vt]}) · {len(tiles):,} ไทล์')
    s_crs = sm.get('crs') or sm.get('crs_key')
    s_tr = rasterio.Affine(*sm['transform'][:6])
    import threading
    tl, opened = threading.local(), []

    def rds():
        d = getattr(tl, 'd', None)
        if d is None:
            d = tl.d = rasterio.open(path)                # GDAL dataset ใช้ข้ามเธรดไม่ได้ → เปิดแยกต่อเธรด
            opened.append(d)
        return d

    def work(t):
        r0, c0, h, w = t
        tt = grid.tile_transform(r0, c0)
        tb = (tt.c, tt.f - h * res, tt.c + w * res, tt.f)
        sb = transform_bounds(crs, s_crs, *tb, densify_pts=21)
        win = from_bounds(*sb, transform=s_tr)
        pad = 2                                         # เผื่อพิกเซลขอบ (sum/average ต้องเห็นพิกเซลที่ทับบางส่วน)
        cc0, rr0 = max(math.floor(win.col_off) - pad, 0), max(math.floor(win.row_off) - pad, 0)
        cc1, rr1 = min(math.ceil(win.col_off + win.width) + pad, SW), min(math.ceil(win.row_off + win.height) + pad, SH)
        if cc1 <= cc0 or rr1 <= rr0:
            return t, None
        a = rds().read(band, window=Window(cc0, rr0, cc1 - cc0, rr1 - rr0)).astype('float64')
        ok = np.isfinite(a)
        if nod is not None and not (isinstance(nod, float) and math.isnan(nod)):
            ok &= a != nod
        if exclude:
            ok &= ~np.isin(a * sc + of, exclude)
        if not ok.any():
            return t, None                          # ต้นทางว่าง → ข้าม (ไม่ต้อง warp)
        a = np.where(ok, a * sc + of, np.nan)
        dst = np.full((h, w), np.nan, 'float64')
        reproject(a, dst, src_transform=s_tr * rasterio.Affine.translation(cc0, rr0), src_crs=s_crs, src_nodata=np.nan,
                  dst_transform=tt, dst_crs=crs, dst_nodata=np.nan, resampling=rs)
        return t, dst

    n = workers_for(TILE * TILE * 8 * 6)
    tot_out, n_px, done = 0.0, 0, 0
    with cf.ThreadPoolExecutor(n, thread_name_prefix='reproj') as ex:          # GDAL warp ปล่อย GIL → ขนานได้จริง
        for t, dst in ex.map(work, tiles):
            done += 1
            if dst is not None:
                okd = np.isfinite(dst)
                if okd.any():
                    r0, c0, h, w = t
                    if vt == 'count':
                        tot_out += float(dst[okd].sum())
                    n_px += int(okd.sum())
                    W.write(r0, c0, np.where(okd, dst, onod).astype(odt))
            if done % 8 == 0 or done == len(tiles):
                P(done / len(tiles) * 0.9, f'แปลงเป็น UTM: ไทล์ {done:,}/{len(tiles):,}')
    for d in opened:
        d.close()
    W.close({'count': Resampling.average, 'density': Resampling.average}.get(vt, Resampling.mode), P=lambda f, msg: P(0.93, msg))
    summary = dict(valid_pixels=n_px, grid=grid.describe(), method=rs.name, crs=crs, res_m=res, workers=n)
    warnings = []
    if vt == 'count':
        s_tot = (ds.get('stats') or {}).get('sum')
        summary.update(sum=tot_out, source_sum=s_tot)
        if s_tot and not aoi_b:
            d = (tot_out - s_tot) / s_tot * 100
            summary['sum_diff_pct'] = d
            log(f'ผลรวม: ต้นทาง {s_tot:,.2f} → ผลลัพธ์ {tot_out:,.2f} (ต่าง {d:+.4f}%)')
            if abs(d) > 0.5:
                warnings.append(f'ผลรวมต่างจากต้นทาง {d:+.2f}% — ตรวจขอบภาพ/ค่า nodata ของต้นทาง')
    if res > 1.5 * src_m:
        warnings.append(f'หยาบลงจากต้นทาง (~{src_m:.0f} ม. → {res:g} ม.)')
    elif res < src_m / 1.5:
        warnings.append(f'ละเอียดกว่าต้นทาง (~{src_m:.0f} ม. → {res:g} ม.) — ดูละเอียดขึ้นแต่ไม่มีข้อมูลใหม่')
    return summary, warnings, grid


def _tag(crs):
    return {'EPSG:32647': 'utm47', 'EPSG:32648': 'utm48'}.get(crs, crs.replace(':', '').lower())


def op_reproject(job, P, log):
    p = job['params']
    ds = db.get('datasets', p['dataset_id'])
    crs = p.get('crs') or TARGET
    aoi_b = None
    if p.get('aoi_id'):
        from . import aoi as aoimod
        aoi_b = aoimod.geom_in(int(p['aoi_id']), crs).bounds
    from .ops import register_output
    res = float(p.get('target_res') or suggest_res(ds))
    out_dir = Path(job['out_dir'])
    outp = out_dir / f"{export.slug(ds['name'], 60)}_{_tag(crs)}_{gm.fmt_num(res)}m.tif"
    summary, warnings, grid = convert(ds, outp, crs, res, aoi_b, P, log)
    params = dict(p, value_type=ds['value_type'], crs=crs, target_res=res, resampling=summary['method'])
    export.write_lineage(out_dir, 'reproject', [export.lineage_input(ds)], params, [outp], summary, warnings)
    did = register_output(outp, f"{ds['name']} → {_tag(crs).upper()} {gm.fmt_num(res)} ม.", ds['value_type'], job['id'], 'derived')
    return dict(output=str(outp), dataset_id=did, summary=summary, warnings=warnings)


# ---------- ขั้นท้ายของทุกงาน: ผลลัพธ์เป็น UTM 47N ----------
SKIP_KINDS = {'reproject', 'prepare'}


def out_crs(job):
    """CRS ผลลัพธ์ของงาน: params.out_crs ("source" = ตามต้นทาง) > ค่าตั้งระบบ settings.json out_crs > ตามต้นทาง"""
    from .config import load_settings
    v = (job.get('params') or {}).get('out_crs')
    if v is None:
        v = load_settings().get('out_crs')
    return None if v in (None, '', 'source') else v


def finalize(job, res, P, log):
    """งานเสร็จแล้วได้ราสเตอร์ที่ไม่ใช่ CRS ผลลัพธ์ → แปลง แล้วให้ชุดเดิมชี้ไฟล์ใหม่ (ชื่อ/สไตล์/โฟลเดอร์/ประวัติเดิม) · ลบไฟล์เดิมของงานนี้"""
    crs = out_crs(job)
    if not crs or job['kind'] in SKIP_KINDS or not isinstance(res, dict) or not res.get('dataset_id'):
        return None
    from . import catalog
    from .ops import WRITER_STATS, preview_factor, preview_key
    from .config import DIRS
    did = int(res['dataset_id'])
    ds = db.get('datasets', did)
    if not ds or ds['kind'] != 'raster' or (ds['meta'].get('crs_key') or '').upper() == crs.upper():
        return None
    src = Path(ds['path'])
    res_m = (job.get('params') or {}).get('out_res_m') or suggest_res(ds)
    outp = src.with_name(f'{src.stem}_{_tag(crs)}_{gm.fmt_num(float(res_m))}m.tif')
    log(f'ผลลัพธ์เป็น {CRS_TH.get(crs, crs)} (ค่าตั้ง "ระบบพิกัดผลลัพธ์") — แปลงตอนท้าย')
    summary, warnings, _g = convert(ds, outp, crs, res_m, None, lambda f, m=None: P(0.95 + 0.05 * (f or 0), m), log)
    catalog.relink(ds, str(outp))
    d1 = db.get('datasets', did)                             # relink อ่าน meta ใหม่จากไฟล์ → คืนค่าที่งานเติมไว้ (hub_key, purpose, hex ฯลฯ)
    db.update('datasets', did, meta={**{k: v for k, v in ds['meta'].items() if k not in d1['meta']}, **d1['meta'], 'warnings': []})
    got = WRITER_STATS.pop(str(outp), None)                  # สถิติจากตอนเขียน → ไม่ต้องอ่านไฟล์ใหม่ทั้งไฟล์
    if got:
        st, (sv, sr) = got
        sp = DIRS['cache'] / 'samples' / f'ds{did}.npz'
        sp.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(sp, v=sv, r=sr)
        d = db.get('datasets', did)
        db.update('datasets', did, stats=dict(st, sample_path=str(sp)), preview_key=preview_key(d, preview_factor(d['meta'])))
    if job.get('out_dir') and Path(job['out_dir']) in src.parents:   # ไฟล์ที่งานนี้สร้างเอง (ไม่ใช่ข้อมูลผู้ใช้) → ลบ
        for f in (src, src.with_suffix(src.suffix + '.ovr'), src.with_suffix(src.suffix + '.aux.xml')):
            try:
                f.unlink()
            except OSError:
                pass
    lp = Path(job['out_dir'] or '') / 'lineage.json'
    try:
        import json
        L = json.loads(lp.read_text(encoding='utf-8'))
        L['outputs'] = [str(outp) if o == str(src) else o for o in L.get('outputs') or []]
        L['output_crs'] = dict(crs=crs, res_m=float(res_m), method=summary['method'], from_crs=ds['meta'].get('crs_key'),
                               sum_before=summary.get('source_sum'), sum_after=summary.get('sum'))
        L['warnings'] = (L.get('warnings') or []) + warnings
        lp.write_text(json.dumps(L, ensure_ascii=False, indent=1), encoding='utf-8')
    except (OSError, ValueError):
        pass
    res['output'] = str(outp)
    return dict(crs=crs, res_m=float(res_m), method=summary['method'], warnings=warnings, sum_diff_pct=summary.get('sum_diff_pct'))


OPS_PROJ = dict(reproject=op_reproject)
