# -*- coding: utf-8 -*-
"""งานประมวลผล (รันใน process แยกผ่าน worker.py): prepare / resample / bivariate"""
import math
import os
import time
from fractions import Fraction
from pathlib import Path

import numpy as np
import rasterio
import shapely
from rasterio.enums import Resampling
from rasterio.windows import Window

from . import db, engine, export, gridmath as gm, palettes
from .config import DIRS, PREVIEW_MAX_PX, PREVIEW_NEED_PX, SAMPLE_N
from .engine import EngineError, Source


class Cancelled(Exception):
    pass


def overview_factors(w, h):
    f, out = 2, []
    while max(w, h) / f >= 256:
        out.append(f)
        f *= 2
    return out


# ======================================================================
# prepare: สถิติ + ฮิสโทแกรม + ค่าสุ่ม + สำเนาพรีวิว (overview) ของ raster
# ======================================================================
def preview_factor(meta):
    px = meta['pixels']
    if meta.get('overviews') or px <= PREVIEW_NEED_PX:
        return 0                               # ไม่ต้องทำสำเนา (เล็ก หรือมี overview แล้ว)
    if px <= PREVIEW_MAX_PX:
        return 1
    f = math.ceil(math.sqrt(px / PREVIEW_MAX_PX))
    for nice in (2, 4, 5, 8, 10, 16, 20, 25, 32, 40, 50, 64, 100):
        if nice >= f:
            return nice
    return f


def preview_key(ds, F):
    return f"{ds.get('fingerprint')}|{ds.get('value_type')}|{ds.get('band') or 1}|F{F}|v2"


def op_prepare(job, P, log):
    ds = db.get('datasets', job['params']['dataset_id'])
    if ds is None:
        raise EngineError('ไม่พบชุดข้อมูล')
    if ds['kind'] != 'raster':
        return dict(note='vector: ไม่ต้องเตรียม')
    m = ds['meta']
    src = Source(dict(ds, nodata_as=None))       # สถิติคิดจากค่าจริง (ไม่แทน nodata)
    F = preview_factor(m)
    vt = ds['value_type']
    dt = m['dtypes'][(ds.get('band') or 1) - 1]
    is_int = 'int' in dt
    W, H = src.w, src.h
    log(f'ขนาด {W:,} × {H:,} พิกเซล · ประเภทค่า {vt} · สำเนาพรีวิว F={F}')

    # ขนาดบล็อก: ถ้าทำพรีวิว บล็อกต้องตรงกับบล็อก 512 ของไฟล์พรีวิว
    Pp = 512 * max(1, 4 // F) if F else 0
    B = Pp * F if F else 2048
    pv_path = None
    pv = None
    if F:
        pv_path = DIRS['cache'] / 'preview' / f"ds{ds['id']}_F{F}.tif"
        pv_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = pv_path.with_suffix('.tmp.tif')
        PW, PH = math.ceil(W / F), math.ceil(H / F)
        if vt == 'class':
            pdt = dt if is_int else 'float32'
            pnod = m.get('nodata')
        else:
            pdt, pnod = 'float32', (None if vt == 'count' else float('nan'))
        prof = dict(driver='GTiff', width=PW, height=PH, count=1, dtype=pdt, crs=src.ds.crs,
                    transform=rasterio.Affine(src.rx * F, 0, src.x0, 0, -src.ry * F, src.y0), nodata=pnod,
                    tiled=True, blockxsize=512, blockysize=512, compress='deflate', BIGTIFF='IF_SAFER')
        pv = rasterio.open(tmp, 'w', **prof)

    n_valid = n_nodata = 0
    s_sum, vmin, vmax = 0.0, math.inf, -math.inf
    ihist = {}
    total_px = W * H
    rate = min(1.0, SAMPLE_N * 8 / max(total_px, 1))       # เก็บเผื่อ (nodata อาจมีมาก) แล้วสุ่มลดเหลือ SAMPLE_N ตอนท้าย
    rng = np.random.default_rng(0)
    samp_v, samp_r = [], []
    blocks = [(r0, c0) for r0 in range(0, H, B) for c0 in range(0, W, B)]
    t0 = time.time()
    for i, (r0, c0) in enumerate(blocks):
        h, w = min(B, H - r0), min(B, W - c0)
        hh, ww = (math.ceil(h / F) * F, math.ceil(w / F) * F) if F else (h, w)
        v, ok = src.read_raw(r0, c0, hh, ww)
        okc = ok[:h, :w]
        vv = v[:h, :w][okc]
        nv = int(vv.size)
        n_valid += nv
        n_nodata += h * w - nv
        if nv:
            s_sum += float(vv.sum())
            vmin, vmax = min(vmin, float(vv.min())), max(vmax, float(vv.max()))
            if is_int and vmax - vmin <= 4096:
                u, c = np.unique(vv, return_counts=True)
                for a, b in zip(u.tolist(), c.tolist()):
                    ihist[a] = ihist.get(a, 0) + b
            k = rng.binomial(nv, rate) if rate < 1 else nv
            if k:
                sel = rng.choice(nv, size=min(k, nv), replace=False)
                rows = np.nonzero(okc)[0][sel] + r0
                samp_v.append(vv[sel])
                samp_r.append(rows.astype('int32'))
        if pv is not None:
            if F == 1:
                if vt == 'count':
                    a = np.where(ok, v, 0).astype('float32')
                elif vt == 'class':
                    a = v.copy()
                    if pnod is not None:
                        a[~ok] = pnod
                    a = a.astype(pdt)
                else:
                    a = np.where(ok, v, np.nan).astype('float32')
            else:
                if vt == 'count':
                    a = engine.block_sum(np.where(ok, v, 0.0), F).astype('float32')
                elif vt == 'class':
                    try:
                        a, aok = engine.majority_values(v, ok, F, 'high')
                    except EngineError:                       # ค่าหลากหลายเกิน → เลือกพิกเซลกลางบล็อก
                        a, aok = v[F // 2::F, F // 2::F], ok[F // 2::F, F // 2::F]
                    if pnod is not None:
                        a = np.where(aok, a, pnod)
                    a = a.astype(pdt)
                else:
                    s = engine.block_sum(np.where(ok, v, 0.0), F)
                    n = engine.block_sum(ok.astype('float64'), F)
                    a = np.where(n > 0, s / np.where(n > 0, n, 1), np.nan).astype('float32')
            pr, pc = r0 // F, c0 // F
            ph, pw = min(a.shape[0], pv.height - pr), min(a.shape[1], pv.width - pc)
            pv.write(a[:ph, :pw], 1, window=Window(pc, pr, pw, ph))
        if i % 5 == 0 or i == len(blocks) - 1:
            P((i + 1) / len(blocks) * (0.85 if pv is not None else 1.0),
              f'อ่านบล็อก {i + 1:,}/{len(blocks):,} · {time.time() - t0:,.0f} วินาที')

    if pv is not None:
        P(0.86, 'กำลังสร้าง overview ของสำเนาพรีวิว…')
        pv.close()
        with rasterio.open(tmp, 'r+') as d:
            fac = overview_factors(d.width, d.height)
            if fac:
                d.build_overviews(fac, Resampling.mode if vt == 'class' else Resampling.average)
        if pv_path.exists():
            pv_path.unlink()
        tmp.rename(pv_path)

    sv = np.concatenate(samp_v) if samp_v else np.zeros(0)
    sr = np.concatenate(samp_r) if samp_r else np.zeros(0, 'int32')
    if sv.size > SAMPLE_N:
        keep = rng.choice(sv.size, SAMPLE_N, replace=False)
        sv, sr = sv[keep], sr[keep]
    sp = DIRS['cache'] / 'samples' / f"ds{ds['id']}.npz"
    sp.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(sp, v=sv, r=sr)
    stats = dict(valid=n_valid, nodata=n_nodata, sum=s_sum, min=vmin if n_valid else None,
                 max=vmax if n_valid else None, mean=s_sum / n_valid if n_valid else None,
                 hist_int=sorted(ihist.items()) if ihist and len(ihist) <= 4096 else None,
                 sample_n=int(sv.size), sample_path=str(sp),
                 pct={str(q): float(np.quantile(sv, q / 100)) for q in (1, 2, 5, 25, 50, 75, 95, 98, 99)} if sv.size else {},
                 computed_at=db.now())
    db.update('datasets', ds['id'], stats=stats, preview_path=str(pv_path) if pv_path else None,
              preview_key=preview_key(ds, F))
    log(f'เสร็จ: valid {n_valid:,} · nodata {n_nodata:,} · ผลรวม {s_sum:,.4f} · min {vmin} · max {vmax}')
    return dict(stats=stats, preview=str(pv_path) if pv_path else None)


def load_sample(ds, metric):
    """ค่าสุ่มของชุดข้อมูลในหน่วยที่ใช้จัดชั้น (count + density → คน/ตร.กม. ที่ความละเอียดต้นทาง)"""
    st = ds.get('stats') or {}
    p = st.get('sample_path')
    if not p or not Path(p).exists():
        return None
    z = np.load(p)
    v, r = z['v'], z['r']
    if ds['value_type'] == 'count' and metric == 'density':
        src = Source(ds)
        v = v / src.area_rows(0, src.h)[r]
    return v


def auto_breaks(ds, cfg):
    """quantile / equal → เกณฑ์ตัวเลข (คำนวณจากค่าสุ่ม ที่ความละเอียดต้นทาง)"""
    n = int(cfg.get('n', 3))
    v = load_sample(ds, cfg.get('metric', 'density'))
    if v is None or v.size == 0:
        raise EngineError(f'ชุดข้อมูล "{ds["name"]}" ยังไม่มีค่าสุ่ม — รอให้งานเตรียมข้อมูลเสร็จก่อน')
    if cfg['method'] == 'quantile':
        return engine.quantile_breaks(v, n)                 # ทนค่าซ้ำ (เช่น ศูนย์จำนวนมาก) — ไม่มีชั้นว่าง
    lo, hi = float(v.min()), float(v.max())
    b = [lo + (hi - lo) * i / n for i in range(1, n)]
    out = []
    for x in b:                                   # กันเกณฑ์ซ้ำ (ข้อมูลกองที่ค่าเดียว)
        if out and x <= out[-1]:
            x = math.nextafter(out[-1], math.inf)
        out.append(x)
    return out


# ======================================================================
# เขียนผลลัพธ์ raster
# ======================================================================
class OutWriter:
    def __init__(self, path, grid, dtype, nodata, colormap=None):
        """colormap ต้องเขียนก่อนข้อมูล (GDAL แก้ PhotometricInterpretation หลังเขียนข้อมูลแล้วไม่ได้)"""
        self.path, self.grid, self.dtype, self.nodata, self.colormap = Path(path), grid, dtype, nodata, colormap
        self.inmem = engine.is_inmem(grid)
        self.r_off, self.c_off = grid.win[0], grid.win[1]        # write() รับพิกัดกริดเต็ม → แปลงเป็นพิกัดในไฟล์
        H, Wd = grid.out_shape
        fill = nodata if nodata is not None else 0
        self.arr = np.full((H, Wd), fill, dtype) if self.inmem else None
        self.prof = dict(driver='GTiff', width=Wd, height=H, count=1, dtype=dtype, crs=grid.crs,
                         transform=grid.out_transform, nodata=nodata, tiled=True, blockxsize=512, blockysize=512,
                         compress='deflate', BIGTIFF='IF_SAFER', SPARSE_OK='TRUE', NUM_THREADS='ALL_CPUS')
        if dtype.startswith('float'):
            self.prof['predictor'] = 3
        self.ds = None if self.inmem else self._open()

    def _open(self):
        ds = rasterio.open(self.path, 'w', **self.prof)
        if self.colormap:
            ds.write_colormap(1, self.colormap)
        return ds

    def write(self, r0, c0, a):
        r0, c0 = r0 - self.r_off, c0 - self.c_off
        if self.inmem:
            self.arr[r0:r0 + a.shape[0], c0:c0 + a.shape[1]] = a
        else:
            self.ds.write(a.astype(self.dtype), 1, window=Window(c0, r0, a.shape[1], a.shape[0]))

    def close(self, resampling, P=None):
        if self.inmem:
            self.ds = self._open()
            self.ds.write(self.arr, 1)
        self.ds.close()
        if P:
            P(None, 'กำลังสร้าง overview…')
        with rasterio.open(self.path, 'r+') as d:
            fac = overview_factors(d.width, d.height)
            if fac:
                d.build_overviews(fac, resampling)


def workers_for(bytes_per_tile):
    """จำนวนเธรด = CPU − 2 (เหลือให้เครื่องใช้งาน) จำกัดด้วย RAM ว่าง (ใช้ไม่เกินครึ่ง) · อย่างน้อย 1 สูงสุด 8"""
    import ctypes
    n = max(1, (os.cpu_count() or 2) - 2)
    try:
        class MS(ctypes.Structure):
            _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong), ('ullTotalPhys', ctypes.c_ulonglong),
                        ('ullAvailPhys', ctypes.c_ulonglong), ('a', ctypes.c_ulonglong), ('b', ctypes.c_ulonglong),
                        ('c', ctypes.c_ulonglong), ('d', ctypes.c_ulonglong), ('e', ctypes.c_ulonglong)]
        ms = MS()
        ms.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
        n = min(n, max(1, int(ms.ullAvailPhys * 0.5 // max(bytes_per_tile * 3, 1))))
    except Exception:
        pass
    return int(min(n, 8))


def parallel_tiles(tiles, fn, nth):
    """yield (ลำดับ, ไทล์, ผล) ตามลำดับเดิม · คิวงานล่วงหน้าไม่เกิน 2×เธรด (คุมหน่วยความจำ)"""
    from concurrent.futures import ThreadPoolExecutor
    from collections import deque
    if nth <= 1:
        for i, t in enumerate(tiles):
            yield i, t, fn(*t)
        return
    with ThreadPoolExecutor(nth) as ex:
        q = deque()
        it = iter(enumerate(tiles))
        for i, t in it:
            q.append((i, t, ex.submit(fn, *t)))
            if len(q) >= nth * 2:
                break
        while q:
            i, t, f = q.popleft()
            yield i, t, f.result()
            nxt = next(it, None)
            if nxt is not None:
                q.append((nxt[0], nxt[1], ex.submit(fn, *nxt[1])))


def register_output(path, name, value_type, job_id, role, read_meta=True, kind='raster'):
    from . import catalog
    return catalog.register_derived(path, name, value_type, job_id, role, kind)


def setup_aoi(p, grid, ogs, log):
    """พื้นที่ศึกษา: ตัดหน้าต่างผลลัพธ์ตามกรอบ + คืนตัวทำ mask และตัวคูณ f (mask คิดที่พิกเซลใหญ่กว่า f เท่า)"""
    aid = p.get('aoi_id')
    if not aid:
        return None, 1, None
    from . import aoi as aoimod
    a = aoimod.get(int(aid))
    f = 1
    if p.get('aoi_mask_res'):
        r = gm.int_ratio(Fraction(p['aoi_mask_res']) / grid.res_frac)
        if r is None or r[0] == 'down':
            raise EngineError('ความละเอียดที่ใช้ตัดพื้นที่ศึกษาต้องเท่าหรือหยาบกว่าผลลัพธ์ เป็นพหุคูณจำนวนเต็ม')
        f = r[1]
    geom = aoimod.geom_in(int(aid), grid.crs)
    grid.set_window(geom.bounds, engine.snap_unit(ogs, f))
    rule = p.get('aoi_rule', 'center')
    log(f'พื้นที่ศึกษา "{a["name"]}" · กติกา {"ศูนย์กลางพิกเซล" if rule == "center" else "แตะ"} · '
        f'mask ที่ {f}× ความละเอียดผลลัพธ์ · หน้าต่าง {grid.win}')
    return aoimod.Masker(geom, grid, rule, f), f, dict(id=a['id'], name=a['name'], source=a['source'], rule=rule,
                                                       mask_factor=f, area_km2=a['area_km2'])


# ======================================================================
# resample: เพิ่ม/ลดความละเอียดในกลุ่มกริดเดียวกัน
# ======================================================================
def op_resample(job, P, log):
    p = job['params']
    ds = db.get('datasets', p['dataset_id'])
    src = Source(ds)
    vt = ds['value_type']
    target = Fraction(p['target_res'])
    grid = engine.make_grid([src], target)
    og = engine.OnGrid(src, grid, p.get('count_down_valid', 'any'), p.get('tie', 'high'))
    warnings = []
    if og.mode == 'same':
        raise EngineError('ความละเอียดเป้าหมายเท่ากับต้นฉบับ')
    if og.mode == 'up' and vt == 'count':
        warnings.append(f'ความแม่นยำเทียม: แบ่งค่านับลงพิกเซลละเอียดขึ้น {og.k}×{og.k} แบบเท่ากัน '
                        '— ดูละเอียดขึ้นแต่ไม่มีข้อมูลใหม่')
    dt = ds['meta']['dtypes'][(ds.get('band') or 1) - 1]
    if vt == 'count':
        odt, onod = ('float64' if og.mode == 'down' else 'float32'), -99999.0
    elif vt == 'density':
        odt, onod = 'float32', -99999.0
    else:
        st = ds.get('stats') or {}
        odt = dt
        onod = ds['meta'].get('nodata') if ds.get('nodata_as') is None else None
        if onod is None:
            mx = st.get('max')
            if dt == 'uint8' and (mx is None or mx < 255):
                onod = 255
            else:
                odt, onod = 'int32', -2147483648
    out_dir = Path(job['out_dir'])
    lbl = gm.res_label(target, grid.geographic)
    fn = f"{export.slug(ds['name'])}_{export.slug(gm.fmt_num(float(target)) + ('as' if grid.geographic else 'm'))}.tif"
    outp = out_dir / fn
    masker, mf, aoi_info = setup_aoi(p, grid, [og], log)
    W = OutWriter(outp, grid, odt, onod)
    T = engine.tile_size([og], W.inmem, mf)
    tiles = list(engine.iter_tiles(grid, T))
    log(f'กริดเป้าหมาย {grid.out_shape[1]:,} × {grid.out_shape[0]:,} · {lbl} · โหมด {og.mode} ×{og.k} · ไทล์ {T} · {len(tiles):,} ไทล์')
    total = 0.0
    nval = 0
    for i, (r0, c0, h, w) in enumerate(tiles):
        v, ok = og.values(r0, c0, h, w)
        if masker is not None and ok.any():
            ok &= masker(r0, c0, h, w)
        if ok.any():
            total += float(v[ok].sum())
            nval += int(ok.sum())
            a = np.where(ok, v, onod if onod is not None else 0)
            W.write(r0, c0, a.astype(odt))
        P((i + 1) / len(tiles) * 0.9, f'ไทล์ {i + 1:,}/{len(tiles):,}')
    rs = {'count': Resampling.average, 'density': Resampling.average}.get(vt, Resampling.mode)
    W.close(rs, P=lambda f, msg: P(0.92, msg))
    summary = dict(valid_pixels=nval, sum=total, grid=grid.describe(), aoi=aoi_info)
    params = dict(p, value_type=vt, method={'count': {'up': 'หารเท่ากัน ÷k²', 'down': 'ผลรวม'},
                                            'density': {'up': 'ทำซ้ำค่า', 'down': 'ค่าเฉลี่ยถ่วงพื้นที่'},
                                            'class': {'up': 'ทำซ้ำค่า', 'down': f'เสียงข้างมาก (เสมอ → {p.get("tie", "high")})'}}[vt][og.mode],
                  mode=og.mode, factor=og.k)
    export.write_lineage(out_dir, 'resample', [export.lineage_input(ds)], params, [outp], summary, warnings)
    new_id = register_output(outp, f"{ds['name']} → {lbl.split(' (')[0]}", vt, job['id'], 'derived')
    log(f'ผลรวมค่า (valid) = {total:,.4f}')
    return dict(output=str(outp), dataset_id=new_id, summary=summary, warnings=warnings)


# ======================================================================
# bivariate
# ======================================================================
def op_bivariate(job, P, log, stats_only=False):
    """stats_only=True → คิดสถิติอย่างเดียว ไม่เขียนไฟล์ (ใช้กับการเทียบหลายค่าที่ตั้ง 3.5)"""
    p = job['params']
    dsx, dsy = db.get('datasets', p['x']['dataset_id']), db.get('datasets', p['y']['dataset_id'])
    for d in (dsx, dsy):
        if d is None:
            raise EngineError('ไม่พบชุดข้อมูล')
        if not d.get('value_type_confirmed'):
            raise EngineError(f'ยังไม่ได้ยืนยันประเภทค่าของ "{d["name"]}"')
    cfgx, cfgy = dict(p['x']), dict(p['y'])
    for cfg, d in ((cfgx, dsx), (cfgy, dsy)):
        if cfg.get('method') in ('quantile', 'equal'):
            cfg['breaks'] = auto_breaks(d, cfg)
            log(f'เกณฑ์ {cfg["method"]} ของ "{d["name"]}" (จากค่าสุ่ม) = {cfg["breaks"]}')
            cfg['breaks_from'] = cfg['method']
    clx, cly = engine.Classifier(cfgx), engine.Classifier(cfgy)
    nx, ny = clx.n, cly.n
    sx, sy = Source(dsx), Source(dsy)
    target = Fraction(p['target_res'])
    grid = engine.make_grid([sx, sy], target)
    tie = p.get('tie', 'high')
    cdv = p.get('count_down_valid', 'positive')
    ogx, ogy = engine.OnGrid(sx, grid, cdv, tie), engine.OnGrid(sy, grid, cdv, tie)
    wid = p.get('weight_dataset_id')
    if wid is None:
        wid = next((d['id'] for d in (dsx, dsy) if d['value_type'] == 'count'), None)
    ogw = None
    dsw = None
    if wid:
        dsw = db.get('datasets', wid)
        ogw = ogx if wid == dsx['id'] else ogy if wid == dsy['id'] else engine.OnGrid(Source(dsw), grid, cdv, tie)
    colors = p['colors']
    if len(colors) != nx * ny:
        raise EngineError(f'ต้องมีสี {nx * ny} สี')
    highlight = [int(c) for c in p.get('highlight', [])]
    warnings = []
    for og, d in ((ogx, dsx), (ogy, dsy)):
        if og.mode == 'warp':
            warnings.append(f'จัดกริดถ่วงพื้นที่: เส้นกริดของ "{d["name"]}" เหลื่อม {og.misalign:.2f} พิกเซล — '
                            'ค่าแต่ละพิกเซลคิดจากพิกเซลต้นทางที่ทับตามสัดส่วนพื้นที่ (count ผลรวมไม่หาย · density เฉลี่ย · class ครองพื้นที่มากสุด)')
        if og.mode == 'up' and d['value_type'] == 'count':
            warnings.append(f'ความแม่นยำเทียม: "{d["name"]}" ถูกแบ่งลงพิกเซลละเอียดขึ้น {og.k}×{og.k} แบบเท่ากัน')
    if nx * ny > 16:
        warnings.append(f'ตาราง {nx}×{ny} ({nx * ny} สี) อ่านยาก — แนะนำไม่เกิน 4×4')

    degx = degy = None
    if clx.method == 'degurba':
        log('คำนวณ DEGURBA แกน X ทั้งกริด…')
        degx = engine.degurba_classes(ogx, grid, clx, lambda f: P(0.05 * f, 'DEGURBA แกน X'))
    if cly.method == 'degurba':
        log('คำนวณ DEGURBA แกน Y ทั้งกริด…')
        degy = engine.degurba_classes(ogy, grid, cly, lambda f: P(0.05 * f, 'DEGURBA แกน Y'))

    out_dir = Path(job['out_dir']) if job.get('out_dir') else None
    base = export.slug(p.get('name') or f"biv_{dsx['name']}_{dsy['name']}", 60)
    outp = out_dir / f'{base}.tif' if out_dir else None
    ncode = nx * ny
    cmap = {0: (0, 0, 0, 0)}
    for code in range(1, ncode + 1):
        h_ = colors[code - 1].lstrip('#')
        cmap[code] = (int(h_[0:2], 16), int(h_[2:4], 16), int(h_[4:6], 16), 255)
    masker, mf, aoi_info = setup_aoi(p, grid, [o for o in (ogx, ogy, ogw) if o], log)
    W = None if stats_only else OutWriter(outp, grid, 'uint8', 0, cmap)
    inmem = engine.is_inmem(grid) if W is None else W.inmem
    T = engine.tile_size([o for o in (ogx, ogy, ogw) if o], inmem, mf)
    tiles = list(engine.iter_tiles(grid, T))
    log(f'กริดผลลัพธ์ {grid.out_shape[1]:,} × {grid.out_shape[0]:,} · {grid.describe()["res_label"]} · X {ogx.mode}×{ogx.k} · '
        f'Y {ogy.mode}×{ogy.k} · ไทล์ {T} · {len(tiles):,} ไทล์ · {"สถิติอย่างเดียว" if W is None else "ในหน่วยความจำ" if W.inmem else "เขียนทีละไทล์"}')
    px_cnt = np.zeros(ncode + 1, 'int64')
    area = np.zeros(ncode + 1, 'float64')
    wsum = np.zeros(ncode + 1, 'float64')
    w_total = 0.0
    w_nocode = 0.0
    order = sorted([('x', ogx), ('y', ogy)], key=lambda t: t[1].src_px(T, T))
    t0 = time.time()
    p0 = 0.05 if (degx is not None or degy is not None) else 0.0

    def compute(r0, c0, h, w):
        # คำนวณไทล์เดียว (รันพร้อมกันหลายเธรด) — คืนรหัส + สถิติย่อย ให้เธรดหลักเขียนไฟล์/รวมยอด
        cls = {}
        empty = None                      # แกนแรกที่ไม่มีข้อมูลทั้งไทล์ → ข้ามแกนที่เหลือ
        m = masker(r0, c0, h, w) if masker is not None else None
        if m is not None and not m.any():
            return None                   # ไทล์อยู่นอกพื้นที่ศึกษาทั้งหมด
        for ax, og in order:
            deg = degx if ax == 'x' else degy
            c = deg[r0:r0 + h, c0:c0 + w] if deg is not None else og.classes(clx if ax == 'x' else cly, r0, c0, h, w)
            if m is not None:
                c = np.where(m, c, -1)
            if not (c >= 0).any():
                empty = og
                break
            cls[ax] = c
        out = dict(wt=0.0, code=None, px=None, area=None, ws=None, nocode=0.0)
        wv = None
        if ogw is not None and empty is not ogw:          # แกนน้ำหนักที่ไม่มีข้อมูลทั้งไทล์ = น้ำหนัก 0 → ไม่ต้องอ่าน
            wv, wok = ogw.values(r0, c0, h, w)
            wv = np.where(wok if m is None else wok & m, wv, 0.0)
            out['wt'] = float(wv.sum())
        if not empty:
            ok = (cls['x'] >= 0) & (cls['y'] >= 0)
            code = np.where(ok, cls['y'] * nx + cls['x'] + 1, 0).astype('uint8')
            if ok.any():
                out['code'] = code
            flat = code.ravel()
            out['px'] = np.bincount(flat, minlength=ncode + 1)
            rows = np.repeat(np.arange(h), w)
            cnt_rc = np.bincount(rows * (ncode + 1) + flat, minlength=h * (ncode + 1)).reshape(h, ncode + 1)
            out['area'] = grid.area_rows(r0, h) @ cnt_rc
            if wv is not None:
                out['ws'] = np.bincount(flat, weights=wv.ravel(), minlength=ncode + 1)
        elif wv is not None:
            out['nocode'] = out['wt']
        return out

    nth = workers_for(T * T * 8 * 6)
    log(f'คำนวณพร้อมกัน {nth} เธรด')
    for i, (r0, c0, h, w), o in parallel_tiles(tiles, compute, nth):
        if o is not None:
            w_total += o['wt']
            w_nocode += o['nocode']
            if o['code'] is not None and W is not None:
                W.write(r0, c0, o['code'])
            if o['px'] is not None:
                px_cnt += o['px']
                area += o['area']
            if o['ws'] is not None:
                wsum += o['ws']
        if i % 10 == 0 or i == len(tiles) - 1:
            el = time.time() - t0
            eta = el / (i + 1) * (len(tiles) - i - 1)
            P(p0 + (1 - p0) * 0.9 * (i + 1) / len(tiles),
              f'ไทล์ {i + 1:,}/{len(tiles):,} · ผ่านไป {el / 60:,.1f} นาที · เหลือ ~{eta / 60:,.1f} นาที')

    xl = export.class_labels(cfgx)
    yl = export.class_labels(cfgy)
    xname = p['x'].get('label') or dsx['name']
    yname = p['y'].get('label') or dsy['name']
    entries = []
    for code in range(1, ncode + 1):
        xi, yi = (code - 1) % nx, (code - 1) // nx
        entries.append((code, colors[code - 1], f'{code}: {yname} {yl[yi]} · {xname} {xl[xi]}'))
    if W is not None:
        W.close(Resampling.mode, P=lambda f, msg: P(0.93, msg))
        (out_dir / f'{base}.qml').write_text(export.qml_paletted(entries), encoding='utf-8')
        export.legend_png(out_dir / f'{base}_legend.png', nx, ny, colors, xname, yname, xl, yl, highlight)

    wname = dsw['name'] if dsw else ''
    rows = []
    for code in range(1, ncode + 1):
        xi, yi = (code - 1) % nx, (code - 1) // nx
        rows.append([code, yi, xi, yl[yi], xl[xi], int(px_cnt[code]), round(float(area[code]), 6),
                     round(float(wsum[code]), 6) if dsw else '', 'Y' if code in highlight else '',
                     colors[code - 1]])
    hl_w = float(sum(wsum[c] for c in highlight))
    hl_a = float(sum(area[c] for c in highlight))
    coded_w = float(wsum[1:].sum())
    rows.append([])
    rows.append(['รวมทุกรหัส', '', '', '', '', int(px_cnt[1:].sum()), round(float(area[1:].sum()), 6),
                 round(coded_w, 6) if dsw else '', '', ''])
    rows.append(['เขตเน้น ' + ','.join(map(str, highlight)), '', '', '', '', int(sum(px_cnt[c] for c in highlight)),
                 round(hl_a, 6), round(hl_w, 6) if dsw else '', '', ''])
    if dsw:
        rows.append([f'{wname} ทั้งหมดในกริด (รวมช่องไม่มีรหัส)', '', '', '', '', '', '', round(w_total, 6), '', ''])
    if W is not None:
        export.write_csv(out_dir / f'{base}_stats.csv',
                     ['รหัส', 'ชั้น Y', 'ชั้น X', f'Y: {yname}', f'X: {xname}', 'จำนวนพิกเซล', 'พื้นที่ (ตร.กม.)',
                      f'น้ำหนัก: {wname}' if dsw else 'น้ำหนัก', 'เขตเน้น', 'สี'], rows)
    by_y = {}
    if dsw:
        for yi in range(ny):
            by_y[yl[yi]] = float(sum(wsum[yi * nx + xi + 1] for xi in range(nx)))
    summary = dict(grid=grid.describe(), aoi=aoi_info, pixels_coded=int(px_cnt[1:].sum()), area_coded_km2=float(area[1:].sum()),
                   weight_dataset=wname or None, weight_total=w_total if dsw else None, weight_coded=coded_w if dsw else None,
                   weight_by_code={str(c): float(wsum[c]) for c in range(1, ncode + 1)} if dsw else None,
                   weight_by_y_class=by_y or None, highlight=highlight, highlight_weight=hl_w if dsw else None,
                   highlight_area_km2=hl_a)
    params = dict(p, x=dict(cfgx, resolved_breaks=clx.breaks, mode=ogx.mode, factor=ogx.k),
                  y=dict(cfgy, resolved_breaks=cly.breaks, mode=ogy.mode, factor=ogy.k),
                  code_formula=f'รหัส = ชั้นY × {nx} + ชั้นX + 1 (1–{ncode}) ; 0 = ไม่มีข้อมูล',
                  rules=dict(classify_order='เพิ่ม/เท่าเดิม: จัดชั้นที่ต้นทางแล้วทำซ้ำ · ลด: count รวมก่อน, density เฉลี่ยก่อน, '
                                            'class จัดชั้นก่อนแล้ว majority', tie=tie, count_down_valid=cdv),
                  palette_interp='OKLab bilinear' if (nx, ny) != (3, 3) else None)
    if stats_only:
        return dict(summary=summary, params=params, warnings=warnings)
    outs = [outp, out_dir / f'{base}.qml', out_dir / f'{base}_legend.png', out_dir / f'{base}_stats.csv']
    ins = [export.lineage_input(dsx), export.lineage_input(dsy)] + ([export.lineage_input(dsw)] if dsw and dsw['id'] not in (dsx['id'], dsy['id']) else [])
    export.write_lineage(out_dir, 'bivariate', ins, params, outs, summary, warnings)
    new_id = register_output(outp, p.get('name') or f"ไบแวเรียต {dsy['name']} × {dsx['name']}", 'class', job['id'], 'map')
    log(f'เสร็จ: น้ำหนักรวม {w_total:,.4f} · มีรหัส {coded_w:,.4f} · เขตเน้น {hl_w:,.4f}')
    return dict(output=str(outp), dataset_id=new_id, summary=summary, warnings=warnings)


# ======================================================================
# rasterize: vector → raster บนกริดของ raster อ้างอิง
# ======================================================================
CAT_COLS = ['#8dd3c7', '#ffffb3', '#bebada', '#fb8072', '#80b1d3', '#fdb462', '#b3de69', '#fccde5', '#d9d9d9', '#bc80bd',
            '#ccebc5', '#ffed6f', '#a6cee3', '#1f78b4', '#b2df8a', '#33a02c', '#fb9a99', '#e31a1c', '#fdbf6f', '#ff7f00']


def op_rasterize(job, P, log):
    import pyogrio
    from rasterio.features import rasterize
    p = job['params']
    vds, ref = db.get('datasets', p['dataset_id']), db.get('datasets', p['ref_dataset_id'])
    if vds is None or vds['kind'] != 'vector':
        raise EngineError('ต้องเลือกชุดข้อมูล vector')
    mode, field = p.get('mode', 'presence'), p.get('field') or None
    rule, ss = p.get('rule', 'center'), int(p.get('supersample', 10))
    if mode in ('attribute', 'majority') and not field:
        raise EngineError('โหมดนี้ต้องเลือกฟิลด์')
    src = Source(ref)
    grid = engine.make_grid([src], Fraction(p['target_res']))
    masker, mf, aoi_info = setup_aoi(p, grid, [], log)
    log(f'อ่าน vector "{vds["name"]}"…')
    use_index = field == '__index__'                  # ค่า = ลำดับ feature ในไฟล์ (1, 2, 3, …)
    from .dsinfo import read_vector
    gdf = read_vector(vds, columns=[field] if field and not use_index else [])
    if use_index:
        gdf['__index__'] = np.arange(1, len(gdf) + 1)
    if gdf.crs is None:
        raise EngineError('vector ไม่มี CRS (.prj)')
    gdf = gdf.to_crs(grid.crs)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
    t = grid.out_transform
    H, Wd = grid.out_shape
    gdf = gdf.cx[t.c:t.c + Wd * grid.rx, t.f - H * grid.ry:t.f]
    log(f'{len(gdf):,} feature ในขอบเขต')
    codes = None
    if mode in ('attribute', 'majority'):
        col = gdf[field]
        if col.dtype.kind in 'iub' or (col.dtype.kind == 'f' and mode == 'attribute'):
            vals = col.to_numpy()
        else:                                            # ข้อความ → รหัส 1..n
            uniq = sorted(col.dropna().astype(str).unique())
            codes = {v: i + 1 for i, v in enumerate(uniq)}
            vals = col.astype(str).map(codes).fillna(0).to_numpy()
        gdf = gdf.assign(_v=vals)
    else:
        gdf = gdf.assign(_v=1)
    vmax = float(np.nanmax(gdf['_v'])) if len(gdf) else 1
    isfloat = mode == 'fraction' or (mode == 'attribute' and gdf['_v'].dtype.kind == 'f'
                                     and not np.all(np.mod(gdf['_v'].dropna(), 1) == 0))
    if isfloat:
        odt, onod, vt = 'float32', -99999.0 if mode != 'fraction' else -1.0, 'density'
    elif vmax <= 254 and (len(gdf) == 0 or float(np.nanmin(gdf['_v'])) >= 0):
        odt, onod, vt = 'uint8', 255, 'class'
    else:
        odt, onod, vt = 'int32', -2147483648, 'class'
    sidx = gdf.sindex
    out_dir = Path(job['out_dir'])
    base = export.slug(p.get('name') or f"{vds['name']}_{mode}", 60)
    outp = out_dir / f'{base}.tif'
    if mode in ('presence', 'fraction') and masker is None:
        onod = None                                       # ไม่ตั้ง nodata → ไทล์ที่ข้าม (sparse) อ่านเป็น 0 = "ไม่มี"
    W = OutWriter(outp, grid, odt, onod)
    T = engine.tile_size([], W.inmem, mf)
    if mode in ('fraction', 'majority'):          # rasterize ละเอียดขึ้น ss เท่า → ไทล์เล็กลง
        L = mf if W.inmem else mf * 512 // math.gcd(mf, 512)
        T = L * max(1, 512 // L)
    tiles = list(engine.iter_tiles(grid, T))
    geoms, vals = gdf.geometry.values, gdf['_v'].to_numpy()
    bg = 0 if mode in ('presence', 'fraction') else onod
    # ไทล์ที่ไม่มี feature เลย (ส่วนใหญ่ของประเทศ) ไม่ต้อง rasterize/เขียน — ไฟล์ sparse อ่านช่องที่ไม่ได้เขียนเป็น nodata
    # (ไม่ใช้พื้นที่ศึกษา + มี/ไม่มี หรือ สัดส่วน → ไม่ตั้ง nodata เพื่อให้ช่องว่างอ่านเป็น 0 = "ไม่มี")
    sk = 0

    def compute(r0, c0, h, w):
        tt = grid.tile_transform(r0, c0)
        idx = sidx.query(shapely.box(tt.c, tt.f - h * grid.ry, tt.c + w * grid.rx, tt.f))
        m = masker(r0, c0, h, w) if masker is not None else None
        if m is not None and not m.any():
            return None
        if not len(idx) and (m is None or bg == onod):
            return None                                   # ว่างทั้งไทล์ → ข้าม
        if mode in ('presence', 'attribute'):
            if len(idx):
                a = rasterize(zip(geoms[idx], vals[idx]), out_shape=(h, w), transform=tt, fill=bg,
                              all_touched=rule == 'touch', dtype=odt)
            else:
                a = np.full((h, w), bg, odt)
        else:
            fine = grid.tile_transform(r0, c0, 1 / ss)
            if len(idx):
                fa = rasterize(zip(geoms[idx], vals[idx] if mode == 'majority' else np.ones(len(idx))),
                               out_shape=(h * ss, w * ss), transform=fine, fill=0, all_touched=False,
                               dtype='int32' if mode == 'majority' else 'uint8')
            else:
                fa = np.zeros((h * ss, w * ss), 'uint8')
            if mode == 'fraction':
                a = engine.block_sum(fa.astype('float64'), ss) / (ss * ss)
            else:
                mv, mok = engine.majority_values(fa.astype('float64'), np.ones(fa.shape, bool), ss, p.get('tie', 'high'))
                a = np.where(mok & (mv != 0), mv, onod)
        a = np.asarray(a).astype(odt)
        if m is not None:
            a = np.where(m, a, onod)
        return a

    # หลายเธรดคำนวณไทล์พร้อมกัน (GDAL rasterize ปล่อย GIL) · เธรดหลักเขียนไฟล์ตามลำดับ
    nth = workers_for(T * T * (ss * ss if mode in ('fraction', 'majority') else 1) * 8)
    log(f'คำนวณพร้อมกัน {nth} เธรด')
    for i, (r0, c0, h, w), a in parallel_tiles(tiles, compute, nth):
        if a is None:
            sk += 1
        else:
            W.write(r0, c0, a)
        if i % 20 == 0 or i == len(tiles) - 1:
            P((i + 1) / len(tiles) * 0.9, f'ไทล์ {i + 1:,}/{len(tiles):,} · ข้ามไทล์ว่าง {sk:,}')
    log(f'ข้ามไทล์ว่าง {sk:,} จาก {len(tiles):,}')
    W.close(Resampling.average if vt == 'density' else Resampling.mode, P=lambda f, msg: P(0.93, msg))
    entries = None
    if codes:
        entries = [(c, CAT_COLS[(c - 1) % len(CAT_COLS)], v) for v, c in codes.items()]
        export.write_csv(out_dir / f'{base}_codes.csv', ['รหัส', field], [[c, v] for v, c in codes.items()])
    elif mode == 'presence':
        entries = [(0, '#d9d9d9', 'ไม่มี'), (1, '#e7298a', 'มี')]
    if entries and len(entries) <= 256:
        (out_dir / f'{base}.qml').write_text(export.qml_paletted(entries), encoding='utf-8')
    params = dict(p, value_type=vt, dtype=odt, nodata=onod, background=bg,
                  overlap='feature ที่มาทีหลังทับ feature ก่อนหน้า' if mode in ('presence', 'attribute') else None,
                  codes=codes)
    export.write_lineage(out_dir, 'rasterize', [export.lineage_input(vds), export.lineage_input(ref)], params, [outp],
                         dict(grid=grid.describe(), aoi=aoi_info, features=len(gdf)))
    new_id = register_output(outp, p.get('name') or f"{vds['name']} → raster ({mode})", vt, job['id'], 'derived')
    return dict(output=str(outp), dataset_id=new_id, summary=dict(features=len(gdf), grid=grid.describe()))


# ======================================================================
# vgrid: raster → กริดเวกเตอร์ (โพลิกอนสี่เหลี่ยม) สำหรับวิชวลไลซ์
# ======================================================================
VGRID_MAX = 2_000_000


def qml_categorized(field, entries):
    """สไตล์ QGIS แบบ categorized สำหรับ vector (เติมสีตามรหัส ไม่มีเส้นขอบ)"""
    from xml.sax.saxutils import quoteattr
    cats = ''.join(f'<category symbol="{i}" value="{v}" label={quoteattr(l)} render="true"/>' for i, (v, c, l) in enumerate(entries))
    syms = ''
    for i, (v, c, l) in enumerate(entries):
        h = c.lstrip('#')
        rgb = f'{int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},255'
        syms += (f'<symbol type="fill" name="{i}" alpha="1" clip_to_extent="1" force_rhr="0"><layer class="SimpleFill" enabled="1" pass="0" locked="0">'
                 f'<Option type="Map"><Option name="color" type="QString" value="{rgb}"/><Option name="style" type="QString" value="solid"/>'
                 f'<Option name="outline_style" type="QString" value="no"/></Option></layer></symbol>')
    return ('<!DOCTYPE qgis PUBLIC \'http://mrcc.com/qgis.dtd\' \'SYSTEM\'>\n<qgis version="3.28" styleCategories="Symbology">\n'
            f'<renderer-v2 type="categorizedSymbol" attr="{field}" symbollevels="0" enableorderby="0" forceraster="0">'
            f'<categories>{cats}</categories><symbols>{syms}</symbols></renderer-v2>\n</qgis>\n')


def op_vgrid(job, P, log):
    import geopandas as gpd
    import shapely
    p = job['params']
    dss = [db.get('datasets', int(i)) for i in p['dataset_ids']]
    srcs = [Source(d) for d in dss]
    grid = engine.make_grid(srcs, Fraction(p['target_res']))
    ogs = [engine.OnGrid(s, grid, 'any', p.get('tie', 'high')) for s in srcs]
    masker, mf, aoi_info = setup_aoi(p, grid, ogs, log)
    H, Wd = grid.out_shape
    if H * Wd > VGRID_MAX * 4:
        raise EngineError(f'กริด {Wd:,} × {H:,} = {H * Wd:,} ช่อง ใหญ่เกิน — เลือกพื้นที่ศึกษาหรือความละเอียดหยาบขึ้น')
    T = engine.tile_size(ogs, True, mf)
    tiles = list(engine.iter_tiles(grid, T))
    names = []
    for d in dss:
        n = export.slug(d['name'], 24)
        while n in names:
            n += '_'
        names.append(n)
    rows, cols, vals = [], [], [[] for _ in dss]
    n = 0
    for i, (r0, c0, h, w) in enumerate(tiles):
        res = [og.values(r0, c0, h, w) for og in ogs]
        ok = np.zeros((h, w), bool)
        for v, k in res:
            ok |= k
        if p.get('skip_zero', True):
            ok &= np.any([np.where(k, v != 0, False) for v, k in res], axis=0)
        if masker is not None:
            ok &= masker(r0, c0, h, w)
        rr, cc = np.nonzero(ok)
        n += rr.size
        if n > VGRID_MAX:
            raise EngineError(f'เกิน {VGRID_MAX:,} ช่อง — เลือกพื้นที่ศึกษาเล็กลงหรือความละเอียดหยาบขึ้น')
        rows.append(rr + r0)
        cols.append(cc + c0)
        for j, (v, k) in enumerate(res):
            vals[j].append(np.where(k, v, np.nan)[rr, cc])
        P((i + 1) / len(tiles) * 0.6, f'ไทล์ {i + 1:,}/{len(tiles):,} · {n:,} ช่อง')
    rows = np.concatenate(rows) if rows else np.zeros(0, int)
    cols = np.concatenate(cols) if cols else np.zeros(0, int)
    x0 = grid.x0 + cols * grid.rx
    y1 = grid.y0 - rows * grid.ry
    P(0.65, f'สร้างโพลิกอน {rows.size:,} ช่อง…')
    geom = shapely.box(x0, y1 - grid.ry, x0 + grid.rx, y1)
    data = dict(row=rows, col=cols, area_km2=grid.area_rows(0, grid.height)[rows] if rows.size else np.zeros(0))
    for j, d in enumerate(dss):
        data[names[j]] = np.concatenate(vals[j]) if vals[j] else np.zeros(0)
    gdf = gpd.GeoDataFrame(data, geometry=geom, crs=grid.crs)
    first = dss[0]
    if first['meta'].get('has_colormap') and rows.size:
        with rasterio.open(first.get('read_path') or first['path']) as d:
            cm = d.colormap(1)
        codes = gdf[names[0]].fillna(0).astype(int)
        gdf['color'] = ['#%02x%02x%02x' % cm.get(c, (0, 0, 0, 0))[:3] for c in codes]
    out_dir = Path(job['out_dir'])
    base = export.slug(p.get('name') or f'grid_{first["name"]}', 60)
    outp = out_dir / f'{base}.gpkg'
    P(0.75, 'เขียน GeoPackage…')
    gdf.to_file(outp, layer=base, driver='GPKG')
    if first['meta'].get('has_colormap') and rows.size:
        u = sorted(set(gdf[names[0]].dropna().astype(int)))
        ent = [(c, '#%02x%02x%02x' % cm.get(c, (0, 0, 0, 0))[:3], str(c)) for c in u]
        (out_dir / f'{base}.qml').write_text(qml_categorized(names[0], ent), encoding='utf-8')
    export.write_lineage(out_dir, 'vgrid', [export.lineage_input(d) for d in dss],
                         dict(p, fields=dict(zip(names, [d['name'] for d in dss])),
                              rules='ค่าต่อช่องตามประเภทค่า: count รวม · density เฉลี่ย · class majority'),
                         [outp], dict(cells=int(rows.size), grid=grid.describe(), aoi=aoi_info))
    new_id = register_output(outp, p.get('name') or f'กริด {first["name"]}', None, job['id'], 'derived', kind='vector')
    return dict(output=str(outp), dataset_id=new_id, summary=dict(cells=int(rows.size), grid=grid.describe()))


OPS = dict(prepare=op_prepare, resample=op_resample, bivariate=op_bivariate, rasterize=op_rasterize, vgrid=op_vgrid)
