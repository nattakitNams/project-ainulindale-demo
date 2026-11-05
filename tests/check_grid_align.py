# -*- coding: utf-8 -*-
"""ทดสอบกริดมุมไม่ตรง / เส้นกริดเหลื่อม (night light × WorldPop) + เกณฑ์ควอนไทล์ที่ทนค่าซ้ำ

python -m tests.check_grid_align <worldpop_3as.tif> <workdir>
สร้างข้อมูลทดสอบจาก WorldPop จริง (ตัดเฉพาะกทม.) + แสงไฟกลางคืนจำลอง 2 แบบ:
  vnl_center : 15″ จุดกึ่งกลางพิกเซลอยู่บนเส้น −180° (แบบ VIIRS VNL) → เส้นกริดเหลื่อม WorldPop 2.5 พิกเซล (ต้องถ่วงพื้นที่)
  vnl_edge   : 15″ ขอบพิกเซลอยู่บนเส้น −180° (แบบ Black Marble) → เส้นกริดตรงกัน แต่มุมเริ่มต่าง (อ่านตรงพิกเซล)
"""
import math
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.windows import Window, from_bounds

from app import dsinfo, engine

BKK = (100.33, 13.49, 100.94, 13.96)             # กรอบกรุงเทพฯ (ไม่ตรงเส้นกริดใดๆ โดยตั้งใจ)
S15 = 15 / 3600
fails = []


def check(name, ok, detail=''):
    print(('  ✔ ' if ok else '  ✘ ') + name + (f' — {detail}' if detail else ''))
    if not ok:
        fails.append(name)


def src_of(path, vt):
    m = dsinfo.raster_meta(str(path))
    return engine.Source(dict(id=None, name=Path(path).stem, path=str(path), meta=m, value_type=vt))


def make_data(wp_path, work):
    work.mkdir(parents=True, exist_ok=True)
    with rasterio.open(wp_path) as s:
        win = from_bounds(*BKK, s.transform).round_offsets().round_lengths()
        a = s.read(1, window=win)
        tr = s.window_transform(win)
        prof = dict(driver='GTiff', width=a.shape[1], height=a.shape[0], count=1, dtype='float32', crs=s.crs, transform=tr, nodata=-99999.0)
        with rasterio.open(work / 'wp_bkk.tif', 'w', **prof) as d:
            d.write(a, 1)
        pop = np.where(a == -99999, 0, a).astype('float64')
        x0, y0, rx = tr.c, tr.f, tr.a
    rng = np.random.default_rng(7)
    for kind, off in (('vnl_center', -S15 / 2), ('vnl_edge', 0.0)):
        lx0 = -180 + off + math.floor((BKK[0] + 0.011 - (-180 + off)) / S15) * S15     # ตัดคนละขอบกับ WorldPop
        ly0 = 75 - off - math.floor((75 - off - (BKK[3] - 0.013)) / S15) * S15
        W = int((BKK[2] - 0.007 - lx0) / S15)
        H = int((ly0 - (BKK[1] + 0.009)) / S15)
        v = np.zeros((H, W), 'float32')
        for i in range(H):                               # ความสว่าง ~ log(คนในพื้นที่รอบพิกเซล) ทำให้เป็น 0–1 + พื้นที่มืด = 0
            cy = ly0 - (i + .5) * S15
            r = int((y0 - cy) / rx)
            for j in range(W):
                cx = lx0 + (j + .5) * S15
                c = int((cx - x0) / rx)
                blk = pop[max(r - 2, 0):r + 3, max(c - 2, 0):c + 3]
                v[i, j] = np.log1p(blk.sum()) if blk.size else 0
        v = v / v.max()
        v = np.where(v < np.quantile(v, 0.65), 0, v + rng.normal(0, 0.002, v.shape)).clip(0, 1).astype('float32')
        with rasterio.open(work / f'{kind}.tif', 'w', driver='GTiff', width=W, height=H, count=1, dtype='float32',
                           crs='EPSG:4326', transform=from_origin(lx0, ly0, S15, S15), nodata=-1.0) as d:
            d.write(v, 1)
    return work / 'wp_bkk.tif', work / 'vnl_center.tif', work / 'vnl_edge.tif'


def full(og, grid, fn):
    H, W = grid.out_shape
    return fn(og, 0, 0, H, W)


def main():
    wp_path, work = Path(sys.argv[1]), Path(sys.argv[2])
    wp_p, vc_p, ve_p = make_data(wp_path, work)
    wp = src_of(wp_p, 'count')
    vc = src_of(vc_p, 'density')
    ve = src_of(ve_p, 'density')
    with rasterio.open(ve_p) as d:
        VE, ve_tr = d.read(1).astype('float64'), d.transform
    with rasterio.open(vc_p) as d:
        VC, vc_tr = d.read(1).astype('float64'), d.transform
    with rasterio.open(wp_p) as d:
        WP, wp_tr = d.read(1).astype('float64'), d.transform
    WP[WP == -99999] = 0

    print('\n[1] เส้นกริดตรงกัน มุมเริ่มต่าง (Black Marble × WorldPop)')
    g = engine.make_grid([wp, ve], 3)
    o_wp, o_ve = engine.OnGrid(wp, g), engine.OnGrid(ve, g)
    check('โหมด WorldPop = same · night light = up×5 (ไม่ต้องถ่วงพื้นที่)', (o_wp.mode, o_ve.mode, o_ve.k) == ('same', 'up', 5), f'{o_wp.mode}, {o_ve.mode}×{o_ve.k}')
    v, ok = full(o_ve, g, lambda o, *a: o.values(*a))
    H, W = v.shape
    rr, cc = np.meshgrid(np.arange(H), np.arange(W), indexing='ij')
    xs, ys = g.x0 + (cc + .5) * g.rx, g.y0 - (rr + .5) * g.ry       # จุดกึ่งกลางพิกเซลเป้าหมาย → พิกเซล night light ที่ครอบ
    jc = np.floor((xs - ve_tr.c) / ve_tr.a).astype(int)
    ir = np.floor((ve_tr.f - ys) / -ve_tr.e).astype(int)
    inside = (jc >= 0) & (jc < VE.shape[1]) & (ir >= 0) & (ir < VE.shape[0])
    exp = np.where(inside, VE[ir.clip(0, VE.shape[0] - 1), jc.clip(0, VE.shape[1] - 1)], np.nan)
    check('ทุกพิกเซลตรงกับพิกเซล night light ที่ครอบจุดกึ่งกลาง', np.array_equal(v[inside & ok], exp[inside & ok]), f'{int((inside & ok).sum()):,} พิกเซล')
    g15 = engine.make_grid([wp, ve], 15)
    o = engine.OnGrid(wp, g15)
    s, ok = full(o, g15, lambda o, *a: o.values(*a))
    c0 = round((g15.x0 - wp_tr.c) / wp_tr.a)
    r0 = round((wp_tr.f - g15.y0) / -wp_tr.e)
    Hh, Ww = g15.out_shape
    exp = WP[r0:r0 + Hh * 5, c0:c0 + Ww * 5].sum()
    check('15″: รวมพิกเซลประชากร 5×5 — ผลรวมเท่าค่าในกรอบเดียวกัน', abs(s.sum() - exp) < 1e-6 * max(exp, 1), f'{s.sum():,.2f} vs {exp:,.2f}')

    print('\n[2] เส้นกริดเหลื่อม 2.5 พิกเซล (VIIRS VNL × WorldPop) → ถ่วงพื้นที่')
    g = engine.make_grid([wp, vc], 3)
    o_wp, o_vc = engine.OnGrid(wp, g), engine.OnGrid(vc, g)
    check('ประชากรอ่านตรงพิกเซล (ไม่ถูกแก้) · night light ถ่วงพื้นที่', (o_wp.mode, o_vc.mode) == ('same', 'warp'), f'{o_wp.mode}, {o_vc.mode} เหลื่อม {o_vc.misalign:.2f}')
    v, ok = full(o_vc, g, lambda o, *a: o.values(*a))
    # ตรวจอิสระ: ค่าเป้าหมาย = เฉลี่ยถ่วงพื้นที่ของพิกเซล night light ที่ทับ (คำนวณตรงจากพิกัด)
    rng = np.random.default_rng(1)
    pts = [(int(rng.integers(5, v.shape[0] - 5)), int(rng.integers(5, v.shape[1] - 5))) for _ in range(400)]
    worst = 0
    for r, c in pts:
        tx0, tx1 = g.x0 + c * g.rx, g.x0 + (c + 1) * g.rx
        ty1, ty0 = g.y0 - r * g.ry, g.y0 - (r + 1) * g.ry
        num = den = 0.0
        for i in range(int((vc_tr.f - ty1) / S15) - 1, int((vc_tr.f - ty0) / S15) + 2):
            for j in range(int((tx0 - vc_tr.c) / S15) - 1, int((tx1 - vc_tr.c) / S15) + 2):
                if 0 <= i < VC.shape[0] and 0 <= j < VC.shape[1]:
                    sx0, sy1 = vc_tr.c + j * S15, vc_tr.f - i * S15
                    ov = max(0, min(tx1, sx0 + S15) - max(tx0, sx0)) * max(0, min(ty1, sy1) - max(ty0, sy1 - S15))
                    if ov > 0:
                        lat = sy1 - S15 / 2
                        w = ov * math.cos(math.radians(lat))
                        num += VC[i, j] * w
                        den += w
        if den > 0:
            worst = max(worst, abs(v[r, c] - num / den))
    check('ค่าถ่วงพื้นที่ตรงกับการคำนวณอิสระ (400 จุดสุ่ม)', worst < 1e-6, f'คลาดสูงสุด {worst:.2e}')
    # count ถ่วงพื้นที่: ประชากรบนกริดของ night light ต้องรวมได้เท่าเดิม
    gv = engine.make_grid([vc], 15)
    gv.set_window((gv.x0 + 3 * gv.rx, gv.y0 - (gv.height - 3) * gv.ry, gv.x0 + (gv.width - 3) * gv.rx, gv.y0 - 3 * gv.ry))
    ow = engine.OnGrid(wp, gv)
    r0w, c0w, hw, ww = gv.win
    s, ok = ow.values(r0w, c0w, hw, ww)
    X0, X1 = gv.x0 + c0w * gv.rx, gv.x0 + (c0w + ww) * gv.rx
    Y1, Y0 = gv.y0 - r0w * gv.ry, gv.y0 - (r0w + hw) * gv.ry
    fx = np.clip((np.minimum(wp_tr.c + (np.arange(WP.shape[1]) + 1) * wp_tr.a, X1) - np.maximum(wp_tr.c + np.arange(WP.shape[1]) * wp_tr.a, X0)) / wp_tr.a, 0, 1)
    fy = np.clip((np.minimum(wp_tr.f - np.arange(WP.shape[0]) * -wp_tr.e, Y1) - np.maximum(wp_tr.f - (np.arange(WP.shape[0]) + 1) * -wp_tr.e, Y0)) / -wp_tr.e, 0, 1)
    exp = float(fy @ WP @ fx)
    check('ประชากรถ่วงพื้นที่ลงกริดที่เหลื่อม: ผลรวมไม่หาย', ow.mode == 'warp' and abs(s.sum() - exp) < 1e-6 * exp, f'{s.sum():,.3f} vs {exp:,.3f}')
    clf = engine.Classifier(dict(n=3, method='breaks', breaks=[0.05, 0.3], metric='value'))
    c, = [o_vc.classes(clf, 0, 0, *g.out_shape)]
    check('จัดชั้นหลังถ่วงพื้นที่ได้ 3 ชั้น + ไม่มีข้อมูล', set(np.unique(c)) <= {-1, 0, 1, 2} and len(set(np.unique(c)) - {-1}) == 3, str(np.unique(c)))

    print('\n[3] เกณฑ์ควอนไทล์ทนค่าซ้ำ (ค่า 0–1 ที่ 65% เป็นศูนย์)')
    vals = VC[VC >= 0]
    b = engine.quantile_breaks(vals, 3)
    cls = np.digitize(vals, b)
    cnt = np.bincount(cls, minlength=3)
    check('ไม่มีชั้นว่าง', (cnt > 0).all(), f'เกณฑ์ {[f"{x:.4g}" for x in b]} · จำนวนต่อชั้น {cnt.tolist()}')
    check('ศูนย์ (พื้นที่มืด) อยู่ชั้นแรกทั้งหมด', (cls[vals == 0] == 0).all() and (cls[vals > 0] >= 1).all())
    lit = cnt[1:]
    check('ส่วนที่มีแสงแบ่ง 2 ชั้นใกล้เคียงกัน', abs(lit[0] - lit[1]) <= 0.02 * lit.sum(), str(lit.tolist()))
    for n in (3, 5):
        x = np.random.default_rng(n).lognormal(size=50000)
        check(f'ข้อมูลทั่วไป {n} ชั้น = np.quantile เดิมทุกค่า', engine.quantile_breaks(x, n) == [float(np.quantile(x, i / n)) for i in range(1, n)])
    lb = engine.fmt_breaks([0.0031, 0.0048, 0.00481, 0.5])
    check('ป้ายเกณฑ์ไม่ซ้ำกัน (0.0031 / 0.0048 / 0.00481)', len(set(lb)) == 4, str(lb))
    try:
        engine.quantile_breaks(np.array([0, 0, 0, 1, 1.0]), 3)
        check('ค่าต่างกันน้อยกว่าจำนวนชั้น → แจ้งชัดเจน', False)
    except engine.EngineError as e:
        check('ค่าต่างกันน้อยกว่าจำนวนชั้น → แจ้งชัดเจน', 'แบ่งได้ไม่เกิน' in str(e), str(e))

    print('\nผล:', 'ผ่านทั้งหมด ✔' if not fails else f'ไม่ผ่าน {len(fails)} ข้อ: {fails}')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
