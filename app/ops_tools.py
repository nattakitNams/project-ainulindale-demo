# -*- coding: utf-8 -*-
"""เครื่องมือข้อมูล: คำนวณราสเตอร์ด้วยสูตร · รวมราสเตอร์ (mosaic) · รวมเวกเตอร์ · อนุกรมเวลา / ตรวจการเปลี่ยนแปลง

calc   — ตัวแปร (A, B, …) = ชุดข้อมูล + แบนด์ · สูตร เช่น (B - A) / (B + A) (NDVI) · ทุกชุดลงกริดเดียวกันตามประเภทค่า
         สูตรผ่านตัวตรวจ AST: ตัวเลข ตัวแปร + − × ÷ ** % เปรียบเทียบ and/or และฟังก์ชันในรายการเท่านั้น (ไม่ eval โค้ด)
mosaic — ต่อไฟล์ราสเตอร์หลายแผ่น (CRS เดียวกัน) เป็นไฟล์เดียว · first / last / min / max · เขียนลงดิสก์ตรง (rasterio.merge dst_path)
vmerge — รวมเวกเตอร์หลายชั้น → GeoPackage (แปลงพิกัดตามชั้นแรก + คอลัมน์ source) · รวมรูป (dissolve) ทั้งหมด/ตามฟิลด์ได้
trend  — ราสเตอร์ N ปี (ชุด + ปี) → ต่อพิกเซล: แนวโน้มต่อปี (ถดถอยเชิงเส้น) · เปลี่ยน (ปีท้าย − ปีแรก) · % เปลี่ยน · เฉลี่ย ·
         ส่วนเบี่ยงเบน · ปีที่ค่าสูง/ต่ำสุด · จำนวนปีที่เกิน/ต่ำกว่าเกณฑ์ (เช่น ความถี่น้ำท่วม)
"""
import ast
import math
from fractions import Fraction
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling

from . import db, engine, export
from .engine import EngineError, Source
from .ops import OutWriter, overview_factors, parallel_tiles, register_output, setup_aoi, workers_for

NODATA = -9999.0
FUNCS = {'abs': np.abs, 'sqrt': np.sqrt, 'log': np.log, 'log10': np.log10, 'exp': np.exp, 'where': np.where,
         'min': np.minimum, 'max': np.maximum, 'clip': np.clip, 'round': np.round, 'floor': np.floor, 'ceil': np.ceil}
CONSTS = {'pi': math.pi, 'e': math.e}
_BIN = {ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply, ast.Div: np.divide, ast.Pow: np.power, ast.Mod: np.mod, ast.FloorDiv: np.floor_divide}
_CMP = {ast.Lt: np.less, ast.LtE: np.less_equal, ast.Gt: np.greater, ast.GtE: np.greater_equal, ast.Eq: np.equal, ast.NotEq: np.not_equal}
PRESETS = [
    dict(key='ndvi', name='NDVI (พืชพรรณ)', expr='(NIR - RED) / (NIR + RED)', vars=['NIR', 'RED']),
    dict(key='ndwi', name='NDWI (น้ำ)', expr='(GREEN - NIR) / (GREEN + NIR)', vars=['GREEN', 'NIR']),
    dict(key='ndbi', name='NDBI (สิ่งปลูกสร้าง)', expr='(SWIR - NIR) / (SWIR + NIR)', vars=['SWIR', 'NIR']),
    dict(key='diff', name='ผลต่าง (B − A)', expr='B - A', vars=['A', 'B']),
    dict(key='ratio', name='อัตราส่วน (A ÷ B)', expr='A / B', vars=['A', 'B']),
    dict(key='thr', name='เกินเกณฑ์ → 1 / 0', expr='where(A > 0.3, 1, 0)', vars=['A']),
]


# ---------- สูตร ----------
def parse_expr(expr, names):
    """ตรวจสูตร → AST (ยกเว้นถ้ามีอะไรนอกรายการที่อนุญาต)"""
    expr = (expr or '').strip()
    if not expr or len(expr) > 500:
        raise EngineError('ใส่สูตร (ไม่เกิน 500 ตัวอักษร)')
    try:
        tree = ast.parse(expr, mode='eval')
    except SyntaxError as e:
        raise EngineError(f'สูตรผิดรูปแบบ: {e.msg} (ตำแหน่ง {e.offset})')
    used = set()

    def chk(n):
        if isinstance(n, ast.Expression):
            return chk(n.body)
        if isinstance(n, ast.Constant):
            if not isinstance(n.value, (int, float)) or isinstance(n.value, bool):
                raise EngineError('ใช้ได้เฉพาะตัวเลข')
            return
        if isinstance(n, ast.Name):
            if n.id in names:
                used.add(n.id)
                return
            if n.id in CONSTS:
                return
            raise EngineError(f'ไม่รู้จัก "{n.id}" — ตัวแปรที่มี: {", ".join(sorted(names)) or "(ไม่มี)"}')
        if isinstance(n, ast.BinOp) and type(n.op) in _BIN:
            return chk(n.left), chk(n.right)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd, ast.Not)):
            return chk(n.operand)
        if isinstance(n, ast.Compare) and all(type(o) in _CMP for o in n.ops):
            chk(n.left)
            return [chk(c) for c in n.comparators]
        if isinstance(n, ast.BoolOp):
            return [chk(v) for v in n.values]
        if isinstance(n, ast.IfExp):
            return chk(n.test), chk(n.body), chk(n.orelse)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in FUNCS and not n.keywords:
            return [chk(a) for a in n.args]
        raise EngineError(f'ใช้ "{ast.unparse(n) if hasattr(ast, "unparse") else type(n).__name__}" ในสูตรไม่ได้ — '
                          f'ใช้ได้: ตัวเลข ตัวแปร + - * / ** % < > == and or และฟังก์ชัน {", ".join(FUNCS)}')
    chk(tree)
    if not used:
        raise EngineError('สูตรต้องใช้ตัวแปรอย่างน้อย 1 ตัว')
    return tree, used


def evaluate(tree, vals):
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant):
            return float(n.value)
        if isinstance(n, ast.Name):
            return vals[n.id] if n.id in vals else CONSTS[n.id]
        if isinstance(n, ast.BinOp):
            return _BIN[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp):
            v = ev(n.operand)
            return -v if isinstance(n.op, ast.USub) else (np.logical_not(v) if isinstance(n.op, ast.Not) else v)
        if isinstance(n, ast.Compare):
            left, out = ev(n.left), True
            for op, c in zip(n.ops, n.comparators):
                right = ev(c)
                out = np.logical_and(out, _CMP[type(op)](left, right))
                left = right
            return out.astype('float64') if isinstance(out, np.ndarray) else float(out)
        if isinstance(n, ast.BoolOp):
            f = np.logical_and if isinstance(n.op, ast.And) else np.logical_or
            out = ev(n.values[0])
            for v in n.values[1:]:
                out = f(out, ev(v))
            return np.asarray(out, 'float64')
        if isinstance(n, ast.IfExp):
            return np.where(ev(n.test), ev(n.body), ev(n.orelse))
        return FUNCS[n.func.id](*[ev(a) for a in n.args])
    return ev(tree)


# ---------- ช่วยร่วม ----------
def _raster(i):
    d = db.get('datasets', int(i))
    if d is None or d['kind'] != 'raster' or d.get('trashed_at'):
        raise EngineError(f'ชุด #{i} ต้องเป็นราสเตอร์ในคลัง')
    if not d.get('value_type_confirmed'):
        raise EngineError(f'ยืนยันประเภทค่าของ "{d["name"]}" ก่อน (หน้าชุดข้อมูล)')
    return d


def _grid(dss_bands, target_res, p, log=None):
    if not target_res:
        raise EngineError('เลือกความละเอียดผลลัพธ์')
    srcs = [Source(dict(d, band=int(b or d.get('band') or 1))) for d, b in dss_bands]
    grid = engine.make_grid(srcs, Fraction(str(target_res)))
    ogs = [engine.OnGrid(s, grid) for s in srcs]
    return srcs, grid, ogs


def _run(grid, ogs, compute, outp, p, log, P, vt='density', each=False):
    """เดินไทล์ขนาน → เขียน float32 (nodata −9999) · compute(vals, ok) → (ค่า, ใช้ได้)
    each=False: ok = ทุกชุดมีค่า (และอยู่ในพื้นที่ศึกษา) · each=True: ok = รายการ ok ของแต่ละชุด (อนุกรมเวลาที่บางปีขาดได้)"""
    masker, mf, aoi_info = setup_aoi(p, grid, ogs, log)
    W = OutWriter(outp, grid, 'float32', NODATA)
    T = engine.tile_size(ogs, W.inmem, mf)
    tiles = list(engine.iter_tiles(grid, T))
    log(f'กริด {grid.out_shape[1]:,} × {grid.out_shape[0]:,} พิกเซล · {grid.describe()["res_label"]} · {len(tiles):,} ไทล์')
    acc = dict(n=0, s=0.0, mn=math.inf, mx=-math.inf)

    def work(r0, c0, h, w):
        vals, oks = [], []
        for o in ogs:
            v, ok = o.values(r0, c0, h, w)
            vals.append(np.asarray(v, 'float64'))
            oks.append(ok)
        m = masker(r0, c0, h, w) if masker is not None else np.ones((h, w), bool)
        if each:
            arg = [ok & m for ok in oks]
        else:
            arg = m.copy()
            for ok in oks:
                arg &= ok
        with np.errstate(all='ignore'):
            r, good = compute(vals, arg)
        r = np.broadcast_to(np.asarray(r, 'float64'), (h, w))
        good = good & np.isfinite(r)
        return np.where(good, r, NODATA).astype('float32'), good
    nth = workers_for(T * T * 8 * (len(ogs) + 2))
    for i, (r0, c0, h, w), (a, good) in parallel_tiles(tiles, work, nth):
        if good.any():
            W.write(r0, c0, a)
            g = a[good].astype('float64')
            acc['n'] += g.size
            acc['s'] += float(g.sum())
            acc['mn'], acc['mx'] = min(acc['mn'], float(g.min())), max(acc['mx'], float(g.max()))
        P((i + 1) / len(tiles) * 0.9, f'ไทล์ {i + 1:,}/{len(tiles):,}')
    W.close(Resampling.average if vt != 'class' else Resampling.mode, P=lambda f, msg: P(0.93, msg))
    if not acc['n']:
        raise EngineError('ไม่มีพิกเซลที่คำนวณได้ (ข้อมูลไม่ทับกัน / ทุกพิกเซลเป็น nodata / สูตรได้ค่าไม่จำกัด)')
    return dict(valid_pixels=acc['n'], min=acc['mn'], max=acc['mx'], mean=acc['s'] / acc['n'], grid=grid.describe(), aoi=aoi_info)


# ---------- calc ----------
def _calc_inputs(p):
    vars_ = p.get('vars') or {}
    if not vars_ or len(vars_) > 12:
        raise EngineError('กำหนดตัวแปร 1–12 ตัว')
    for k in vars_:
        if not (k[:1].isalpha() and k.replace('_', '').isalnum() and len(k) <= 16) or k in FUNCS or k in CONSTS:
            raise EngineError(f'ชื่อตัวแปร "{k}" ใช้ไม่ได้ (ตัวอักษรอังกฤษ/ตัวเลข/_ ขึ้นต้นด้วยตัวอักษร · ห้ามชื่อฟังก์ชัน)')
    tree, used = parse_expr(p.get('expr'), set(vars_))
    keys = [k for k in vars_ if k in used]
    dss = [(_raster(vars_[k]['dataset_id']), vars_[k].get('band')) for k in keys]
    for (d, b) in dss:
        if b and not 1 <= int(b) <= int(d['meta'].get('count') or 1):
            raise EngineError(f'"{d["name"]}" มี {d["meta"].get("count")} แบนด์ — ไม่มีแบนด์ {b}')
    return tree, keys, dss


def op_calc(job, P, log):
    p = job['params']
    tree, keys, dss = _calc_inputs(p)
    srcs, grid, ogs = _grid(dss, p['target_res'], p, log)
    log(f'สูตร: {p["expr"]} · ' + ' · '.join(f'{k} = {d["name"]} (แบนด์ {b or d.get("band") or 1})' for k, (d, b) in zip(keys, dss)))
    out_dir = Path(job['out_dir'])
    outp = out_dir / f'{export.slug(p.get("name") or "calc", 60)}.tif'
    vt = p.get('value_type') if p.get('value_type') in ('count', 'density', 'class') else 'density'
    summary = _run(grid, ogs, lambda vals, ok: (evaluate(tree, dict(zip(keys, vals))), ok), outp, p, log, P, vt)
    for s in srcs:
        s.close()
    inputs = [dict(export.lineage_input(d), variable=k, band=int(b or d.get('band') or 1)) for k, (d, b) in zip(keys, dss)]
    export.write_lineage(out_dir, 'calc', inputs, dict(p, value_type=vt), [outp], summary)
    did = register_output(outp, p.get('name') or f'คำนวณ: {p["expr"][:60]}', vt, job['id'], 'derived')
    return dict(output=str(outp), dataset_id=did, summary=summary)


# ---------- trend ----------
STATS = {'slope': 'แนวโน้มต่อปี (ความชันถดถอยเชิงเส้น)', 'change': 'เปลี่ยนแปลง (ปีท้าย − ปีแรก)', 'pct': 'เปลี่ยนแปลง % (เทียบปีแรก)',
         'mean': 'ค่าเฉลี่ยทุกปี', 'std': 'ส่วนเบี่ยงเบนมาตรฐาน', 'max_year': 'ปีที่ค่าสูงสุด', 'min_year': 'ปีที่ค่าต่ำสุด',
         'count_above': 'จำนวนปีที่ค่า > เกณฑ์', 'count_below': 'จำนวนปีที่ค่า < เกณฑ์'}


def _trend_inputs(p):
    items = sorted(p.get('items') or [], key=lambda x: float(x.get('year') or 0))
    if len(items) < 2:
        raise EngineError('อนุกรมเวลาต้องมีอย่างน้อย 2 ชุด (แต่ละชุดใส่ปี)')
    if p.get('stat') not in STATS:
        raise EngineError(f'สถิติต้องเป็นหนึ่งใน {", ".join(STATS)}')
    if p['stat'].startswith('count_') and p.get('threshold') in (None, ''):
        raise EngineError('ใส่เกณฑ์ (threshold) สำหรับนับจำนวนปี')
    years = [float(x['year']) for x in items]
    if len(set(years)) != len(years):
        raise EngineError('ปีซ้ำกัน — แต่ละชุดต้องเป็นคนละปี')
    return items, np.array(years), [(_raster(x['dataset_id']), x.get('band')) for x in items]


def op_trend(job, P, log):
    p = job['params']
    items, years, dss = _trend_inputs(p)
    srcs, grid, ogs = _grid(dss, p['target_res'], p, log)
    stat, thr = p['stat'], float(p.get('threshold') or 0)
    need = int(p.get('min_years') or len(items))                  # ต้องมีค่ากี่ปีขึ้นไปจึงคำนวณ (ค่าเริ่ม = ทุกปี · change/pct ใช้แค่ปีแรก+ปีท้าย)
    log(f'{STATS[stat]} · {len(items)} ปี ({int(years[0])}–{int(years[-1])}) · ต้องมีค่าอย่างน้อย {need} ปี')

    def compute(vals, ok):
        Y = np.stack(vals)                                        # (ปี, h, w)
        V = np.stack(ok) & np.isfinite(Y)                         # มีค่าปีไหนบ้าง (ต่อพิกเซล)
        n = V.sum(0)
        good = n >= need
        x = years[:, None, None]
        w = V.astype('float64')
        Yz = np.where(V, Y, 0.0)
        if stat in ('slope', 'mean', 'std'):
            xm = (w * x).sum(0) / np.maximum(n, 1)
            ym = (w * Yz).sum(0) / np.maximum(n, 1)
            if stat == 'mean':
                return ym, good
            if stat == 'std':
                return np.sqrt((w * (Yz - ym) ** 2).sum(0) / np.maximum(n, 1)), good
            var = (w * (x - xm) ** 2).sum(0)
            return (w * (x - xm) * (Yz - ym)).sum(0) / np.where(var > 0, var, np.nan), good & (var > 0)
        if stat in ('change', 'pct'):
            first, last = Y[0], Y[-1]
            g = (good if p.get('min_years') else True) & V[0] & V[-1]   # ค่าเริ่ม: ใช้แค่ปีแรก + ปีท้าย ปีกลางขาดได้
            return (last - first if stat == 'change' else (last - first) / np.where(first != 0, np.abs(first), np.nan) * 100), g
        if stat in ('max_year', 'min_year'):
            Ym = np.where(V, Y, -np.inf if stat == 'max_year' else np.inf)
            idx = Ym.argmax(0) if stat == 'max_year' else Ym.argmin(0)
            return years[idx], good
        cmp = (Y > thr) if stat == 'count_above' else (Y < thr)
        return (cmp & V).sum(0).astype('float64'), good
    out_dir = Path(job['out_dir'])
    outp = out_dir / f'{export.slug(p.get("name") or f"trend_{stat}", 60)}.tif'
    summary = _run(grid, ogs, compute, outp, p, log, P, 'density', each=True)
    for s in srcs:
        s.close()
    inputs = [dict(export.lineage_input(d), year=it['year']) for it, (d, b) in zip(items, dss)]
    export.write_lineage(out_dir, 'trend', inputs, dict(p, stat_label=STATS[stat]), [outp], summary)
    did = register_output(outp, p.get('name') or f'{STATS[stat]} {int(years[0])}–{int(years[-1])}', 'density', job['id'], 'derived')
    return dict(output=str(outp), dataset_id=did, summary=summary)


# ---------- mosaic ----------
def _mosaic_inputs(p):
    ids = p.get('dataset_ids') or []
    if len(ids) < 2:
        raise EngineError('เลือกราสเตอร์อย่างน้อย 2 ชุด')
    dss = [db.get('datasets', int(i)) for i in ids]
    if any(d is None or d['kind'] != 'raster' for d in dss):
        raise EngineError('รวมได้เฉพาะราสเตอร์')
    keys = {d['meta'].get('crs_key') for d in dss}
    if len(keys) > 1:
        raise EngineError('ทุกชุดต้องอยู่ระบบพิกัดเดียวกัน — แปลงความละเอียด/พิกัดก่อน')
    counts = {int(d['meta'].get('count') or 1) for d in dss}
    if len(counts) > 1:
        raise EngineError('ทุกชุดต้องมีจำนวนแบนด์เท่ากัน')
    if p.get('method', 'first') not in ('first', 'last', 'min', 'max'):
        raise EngineError('วิธีรวมต้องเป็น first / last / min / max')
    return dss


def op_mosaic(job, P, log):
    from rasterio.merge import merge
    p = job['params']
    dss = _mosaic_inputs(p)
    out_dir = Path(job['out_dir'])
    outp = out_dir / f'{export.slug(p.get("name") or "mosaic", 60)}.tif'
    paths = [d.get('read_path') or d['path'] for d in dss]
    log(f'รวม {len(paths)} ไฟล์ · วิธีซ้อนทับ {p.get("method", "first")} · ความละเอียดตามชุดแรก')
    P(0.1, 'กำลังรวม…')
    merge(paths, method=p.get('method', 'first'), dst_path=str(outp),
          dst_kwds=dict(tiled=True, blockxsize=512, blockysize=512, compress='deflate', BIGTIFF='IF_SAFER'))
    P(0.85, 'กำลังสร้าง overview…')
    with rasterio.open(outp, 'r+') as d:
        fac = overview_factors(d.width, d.height)
        if fac:
            d.build_overviews(fac, Resampling.mode if dss[0].get('value_type') == 'class' else Resampling.average)
        summary = dict(width=d.width, height=d.height, bounds=list(d.bounds))
    vt = dss[0].get('value_type') if all(d.get('value_type') == dss[0].get('value_type') for d in dss) else None
    export.write_lineage(out_dir, 'mosaic', [export.lineage_input(d) for d in dss], p, [outp], summary)
    did = register_output(outp, p.get('name') or f'รวม {len(dss)} ไฟล์: {dss[0]["name"]} …', vt, job['id'], 'derived')
    return dict(output=str(outp), dataset_id=did, summary=summary)


# ---------- vmerge ----------
def _vmerge_inputs(p):
    ids = p.get('dataset_ids') or []
    if len(ids) < 2:
        raise EngineError('เลือกเวกเตอร์อย่างน้อย 2 ชุด')
    dss = [db.get('datasets', int(i)) for i in ids]
    if any(d is None or d['kind'] != 'vector' for d in dss):
        raise EngineError('รวมได้เฉพาะเวกเตอร์ (shapefile / GeoPackage / GeoJSON ในคลัง)')
    return dss


def op_vmerge(job, P, log):
    import geopandas as gpd
    import pandas as pd
    from .dsinfo import read_vector
    p = job['params']
    dss = _vmerge_inputs(p)
    gdfs, crs = [], None
    for i, d in enumerate(dss):
        g = read_vector(d)
        if g.crs is None:
            raise EngineError(f'"{d["name"]}" ไม่มีระบบพิกัด (.prj)')
        crs = crs or g.crs
        g = g.to_crs(crs)
        g['source'] = d['name']
        gdfs.append(g)
        P(0.6 * (i + 1) / len(dss), f'อ่าน {i + 1}/{len(dss)}: {d["name"]} ({len(g):,} feature)')
    out = gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True), crs=crs)
    if p.get('dissolve'):
        f = p.get('dissolve_field') or None
        if f and f not in out.columns:
            raise EngineError(f'ไม่มีฟิลด์ "{f}" ในชุดที่รวม')
        out = out.dissolve(by=f).reset_index() if f else out.dissolve().reset_index(drop=True)
        log(f'รวมรูป (dissolve) {"ตามฟิลด์ " + f if f else "ทั้งหมด"} → {len(out):,} รูป')
    out_dir = Path(job['out_dir'])
    name = export.slug(p.get('name') or 'merged', 60)
    outp = out_dir / f'{name}.gpkg'
    P(0.8, f'เขียน GeoPackage {len(out):,} feature')
    out.to_file(outp, layer=name, driver='GPKG')
    summary = dict(features=len(out), sources=len(dss), crs=str(crs))
    export.write_lineage(out_dir, 'vmerge', [export.lineage_input(d) for d in dss], p, [outp], summary)
    did = register_output(outp, p.get('name') or f'รวม {len(dss)} ชั้น: {dss[0]["name"]} …', None, job['id'], 'derived', kind='vector')
    return dict(output=str(outp), dataset_id=did, summary=summary)


# ---------- ประเมินก่อนรัน (server.validate_job) ----------
def estimate(kind, p):
    warns = []
    if kind in ('calc', 'trend'):
        if kind == 'calc':
            tree, keys, dss = _calc_inputs(p)
        else:
            items, years, dss = _trend_inputs(p)
        srcs, grid, ogs = _grid(dss, p['target_res'], p)
        aoi = None
        if p.get('aoi_id'):
            from . import aoi as aoimod
            setup_aoi(p, grid, ogs, lambda m: None)
            aoi = aoimod.get(int(p['aoi_id']))['name']
        engine.check_tiles(grid, ogs)
        for s in srcs:
            s.close()
        if kind == 'trend' and len(dss) > 30:
            warns.append(f'{len(dss)} ปี — อ่านทุกชุดพร้อมกันต่อไทล์ ใช้หน่วยความจำมากขึ้น')
        for (d, b), o in zip(dss, ogs):
            if o.mode == 'up' and d['value_type'] == 'count':
                warns.append(f'ความแม่นยำเทียม: "{d["name"]}" ถูกแบ่งลงพิกเซลละเอียดขึ้น {o.k}×{o.k}')
        return dict(grid=grid.describe(), aoi=aoi, warnings=warns)
    if kind == 'mosaic':
        dss = _mosaic_inputs(p)
        b = [d['meta']['bounds'] for d in dss]
        return dict(grid=dict(res_label=dss[0]['meta'].get('res_label'), width=0, height=0, bounds=[min(x[0] for x in b), min(x[1] for x in b), max(x[2] for x in b), max(x[3] for x in b)]),
                    warnings=warns)
    if kind == 'vmerge':
        dss = _vmerge_inputs(p)
        crs = {d['meta'].get('crs_name') for d in dss}
        if len(crs) > 1:
            warns.append(f'ระบบพิกัดต่างกัน — จะแปลงทุกชั้นเป็นของชั้นแรก ({dss[0]["meta"].get("crs_name")})')
        return dict(grid=dict(res_label=f'{sum(d["meta"].get("features") or 0 for d in dss):,} feature', width=0, height=0), warnings=warns)
    raise EngineError(f'ไม่รู้จักงาน {kind}')


OPS_TOOLS = dict(calc=op_calc, trend=op_trend, mosaic=op_mosaic, vmerge=op_vmerge)
KINDS = set(OPS_TOOLS)
