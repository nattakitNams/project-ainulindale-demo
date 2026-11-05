# -*- coding: utf-8 -*-
"""แกนคำนวณ: อ่าน raster ลงกริดเป้าหมาย ตามประเภทค่า + จัดชั้น

กติกา (ตรงกับวิธีที่ตรวจทานแล้วของโปรเจกต์เดิม):
  ประเภทค่า     เพิ่มความละเอียด (แม่ → ลูก k×k)   ลดความละเอียด (ลูก m×m → แม่)
  count         หารเท่ากัน ÷ k²                    ผลรวม
  density       ทำซ้ำค่า                           ค่าเฉลี่ยถ่วงพื้นที่
  class         ทำซ้ำค่า                           เสียงข้างมาก (เสมอ → ชั้นสูงกว่า/ต่ำกว่า)

ลำดับจัดชั้น (ไบแวเรียต):
  เพิ่ม/เท่าเดิม : จัดชั้นที่ความละเอียดต้นทาง แล้วทำซ้ำชั้น  (เช่น ความหนาแน่นของพิกเซลแม่ใช้กับลูกทุกช่อง)
  ลด           : count → รวมก่อนแล้วจัดชั้น (ความหนาแน่นคิดที่พิกเซลเป้าหมาย)
                 density → เฉลี่ยก่อนแล้วจัดชั้น
                 class → จัดชั้นก่อนแล้ว majority
                 order='classify_first' → ทุกประเภทจัดชั้นก่อนแล้ว majority
"""
import math
import threading
from fractions import Fraction

import numpy as np
import rasterio
from rasterio.windows import Window

from . import gridmath as gm
from .config import INMEM_OUT_PX


class EngineError(Exception):
    pass


# ---------- กริดเป้าหมาย ----------
class Grid:
    def __init__(self, x0, y0, rx, ry, width, height, crs, geographic, res_frac):
        self.x0, self.y0, self.rx, self.ry = x0, y0, rx, ry
        self.width, self.height, self.crs, self.geographic, self.res_frac = width, height, crs, geographic, res_frac
        self.win = (0, 0, height, width)          # หน้าต่างผลลัพธ์ (แถวเริ่ม, คอลัมน์เริ่ม, สูง, กว้าง) — ตัดตามพื้นที่ศึกษา

    @property
    def transform(self):
        return rasterio.Affine(self.rx, 0, self.x0, 0, -self.ry, self.y0)

    @property
    def out_transform(self):
        r0, c0 = self.win[0], self.win[1]
        return rasterio.Affine(self.rx, 0, self.x0 + c0 * self.rx, 0, -self.ry, self.y0 - r0 * self.ry)

    @property
    def out_shape(self):
        return self.win[2], self.win[3]

    def tile_transform(self, r0, c0, f=1):
        """transform ของไทล์ (พิกัดกริดเต็ม) ; f = ขนาดพิกเซลเป็นกี่เท่าของกริด"""
        return rasterio.Affine(self.rx * f, 0, self.x0 + c0 * self.rx, 0, -self.ry * f, self.y0 - r0 * self.ry)

    def set_window(self, bounds, snap=1):
        """ตัดหน้าต่างตามกรอบ (xmin, ymin, xmax, ymax ใน CRS ของกริด) ; มุมเริ่มปัดลงเป็นพหุคูณ snap"""
        x0, y0, x1, y1 = bounds
        c0 = max(0, math.floor((x0 - self.x0) / self.rx))
        r0 = max(0, math.floor((self.y0 - y1) / self.ry))
        c1 = min(self.width, math.ceil((x1 - self.x0) / self.rx))
        r1 = min(self.height, math.ceil((self.y0 - y0) / self.ry))
        c0, r0 = c0 // snap * snap, r0 // snap * snap
        if c1 <= c0 or r1 <= r0:
            raise EngineError('พื้นที่ศึกษาไม่ทับกับขอบเขตข้อมูล')
        self.win = (r0, c0, r1 - r0, c1 - c0)

    def area_rows(self, r0, n):
        return gm.pixel_area_rows(self.geographic, self.rx, self.ry, self.y0, r0, n)

    def describe(self):
        t = self.out_transform
        return dict(x0=t.c, y0=t.f, res=[self.rx, self.ry], width=self.win[3], height=self.win[2],
                    window=list(self.win), full=[self.width, self.height],
                    res_exact=gm.frac_str(self.res_frac), res_label=gm.res_label(self.res_frac, self.geographic))


# ---------- ชุดข้อมูลต้นทาง ----------
class Source:
    """ds = แถวจาก catalog (dict) หรือ dict ที่มี path/meta/value_type/nodata_as/band"""

    def __init__(self, ds):
        m = ds['meta']
        self.id = ds.get('id')
        self.name = ds.get('name', '')
        self.path = ds.get('read_path') or ds['path']
        self.meta = m
        self.vt = ds['value_type']
        self.nodata_as = ds.get('nodata_as')
        self.exclude = [float(x) for x in (ds.get('exclude_values') or [])]   # ค่าที่ไม่นับ = ไม่มีข้อมูล
        self.band = int(ds.get('band') or 1)
        self.geographic = m['geographic']
        t = m['transform']
        self.x0, self.y0, self.rx, self.ry = t[2], t[5], abs(t[0]), abs(t[4])
        self.w, self.h = m['width'], m['height']
        if not m.get('res_exact'):
            raise EngineError(f'ความละเอียดของ "{self.name}" ไม่ใช่ค่าที่แปลงเป็นเศษส่วนได้ — V1 ยังไม่รองรับ')
        if m.get('res_exact') != m.get('res_exact_y'):
            raise EngineError(f'พิกเซลของ "{self.name}" ไม่เป็นสี่เหลี่ยมจัตุรัส — V1 ยังไม่รองรับ')
        self.res_frac = Fraction(m['res_exact'])
        self.nodata = m.get('nodata')
        self._tl = threading.local()          # GDAL dataset ใช้ข้ามเธรดพร้อมกันไม่ได้ → เปิดแยกต่อเธรด
        self._all = []
        self._lock = threading.Lock()

    @property
    def ds(self):
        d = getattr(self._tl, 'ds', None)
        if d is None:
            d = self._tl.ds = rasterio.open(self.path)
            with self._lock:
                self._all.append(d)
        return d

    def close(self):
        with self._lock:
            for d in self._all:
                try:
                    d.close()
                except Exception:
                    pass
            self._all = []
        self._tl = threading.local()

    def area_rows(self, r0, n):
        return gm.pixel_area_rows(self.geographic, self.rx, self.ry, self.y0, r0, n)

    def read_raw(self, r0, c0, h, w):
        """อ่านหน้าต่าง (หน่วยพิกเซลต้นทาง) — นอกขอบภาพ = ไม่มีข้อมูล ; คืน (ค่า float64, valid)"""
        val = np.zeros((h, w), 'float64')
        ok = np.zeros((h, w), bool)
        rr0, cc0 = max(r0, 0), max(c0, 0)
        rr1, cc1 = min(r0 + h, self.h), min(c0 + w, self.w)
        if rr1 > rr0 and cc1 > cc0:
            a = self.ds.read(self.band, window=Window(cc0, rr0, cc1 - cc0, rr1 - rr0)).astype('float64')
            v = np.isfinite(a)
            if self.nodata is not None and not (isinstance(self.nodata, float) and math.isnan(self.nodata)):
                v &= a != self.nodata
            if self.nodata_as is not None:
                a[~v] = self.nodata_as
                v[:] = True
            if self.exclude:
                v &= ~np.isin(a, self.exclude)
            a[~v] = 0
            sl = (slice(rr0 - r0, rr1 - r0), slice(cc0 - c0, cc1 - c0))
            val[sl], ok[sl] = a, v
        return val, ok


# ---------- จัดชั้น ----------
class Classifier:
    """method: breaks / degurba ; metric: density (count → คน/ตร.กม.) / per_pixel / value"""

    def __init__(self, cfg):
        self.n = int(cfg.get('n', 3))
        self.method = cfg.get('method', 'breaks')
        self.breaks = [float(b) for b in cfg.get('breaks', [])]
        self.metric = cfg.get('metric', 'density')
        self.order = cfg.get('order', 'auto')
        self.degurba = cfg.get('degurba') or dict(dens=[300, 1500], minpop=[5000, 50000])
        if self.method == 'breaks' and len(self.breaks) != self.n - 1:
            raise EngineError(f'จำนวนเกณฑ์ต้องเท่ากับ (จำนวนคลาส − 1) = {self.n - 1} แต่ได้ {len(self.breaks)}')
        if self.method == 'breaks' and any(b2 <= b1 for b1, b2 in zip(self.breaks, self.breaks[1:])):
            raise EngineError('เกณฑ์ต้องเรียงจากน้อยไปมาก และห้ามซ้ำ')
        if self.method == 'degurba' and self.n != 3:
            raise EngineError('วิธี DEGURBA ใช้ได้กับ 3 คลาสเท่านั้น')

    def classify(self, metric_vals, valid):
        """ค่าเท่าเกณฑ์ขึ้นชั้นบน (np.digitize right=False) ; ไม่มีข้อมูล = -1"""
        c = np.digitize(metric_vals, self.breaks).astype('int16') if self.n > 1 else np.zeros(metric_vals.shape, 'int16')
        c[~valid] = -1
        return c


def quantile_breaks(v, n):
    """เกณฑ์ควอนไทล์ n ชั้น (n−1 ค่า) ที่ทนค่าซ้ำ
    ข้อมูลทั่วไป → เหมือน np.quantile(v, i/n) ทุกประการ (ผลเดิมไม่เปลี่ยน)
    ข้อมูลที่กองอยู่ค่าเดียวมาก (เช่น แสงไฟกลางคืนที่ 70% เป็น 0) → ค่าที่กองได้ชั้นของตัวเอง
    แล้วแบ่งค่าที่เหลือเป็นชั้นละเท่าๆ กัน — ไม่มีชั้นว่าง ไม่มีเกณฑ์ซ้ำ"""
    v = np.asarray(v, 'float64')
    v = np.sort(v[np.isfinite(v)])
    if v.size == 0:
        raise EngineError('ไม่มีค่าสำหรับคำนวณเกณฑ์')
    b = [float(np.quantile(v, i / n)) for i in range(1, n)]
    if all(x > v[0] for x in b) and all(y > x for x, y in zip(b, b[1:])):
        return b                                             # ไม่มีชั้นว่าง → แบบเดิม
    nu = np.unique(v).size
    if nu < n:
        raise EngineError(f'ข้อมูลมีค่าต่างกันเพียง {nu} ค่า — แบ่งได้ไม่เกิน {nu} ชั้น')
    out, lo = [], 0
    for i in range(1, n):
        rest = v[lo:]
        q = float(np.quantile(rest, 1 / (n - i + 1)))       # หนึ่งชั้นจากส่วนที่เหลือ
        if q <= rest[0]:                                     # ค่าต่ำสุดที่เหลือกองเกินหนึ่งชั้น → ให้มันเป็นชั้นเดียว
            up = rest[rest > rest[0]]
            if up.size == 0:
                raise EngineError(f'แบ่งได้ไม่ครบ {n} ชั้น — ค่าส่วนใหญ่ซ้ำกัน ลองลดจำนวนชั้น')
            q = float(up[0])
        out.append(q)
        lo = int(np.searchsorted(v, q, 'left'))              # ค่า ≥ เกณฑ์ ขึ้นชั้นถัดไป
        if lo >= v.size:
            raise EngineError(f'แบ่งได้ไม่ครบ {n} ชั้น — ลองลดจำนวนชั้น')
    return out


def fmt_breaks(vals):
    """จัดรูปตัวเลขชุดหนึ่งด้วยจำนวนหลักเท่ากัน มากพอให้ไม่มีสองค่าแสดงเหมือนกัน (เช่น 0.0031 กับ 0.0048 ไม่กลายเป็น 0 ทั้งคู่)"""
    def fin(x):
        return x is not None and math.isfinite(float(x))
    xs = sorted({float(x) for x in vals if fin(x)})
    if all(x.is_integer() for x in xs):
        return [f'{int(float(x)):,}' if fin(x) else '∞' for x in vals]
    for sig in range(3, 13):
        s = {x: f'{x:,.{sig}g}' for x in xs}
        if len(set(s.values())) == len(xs):
            break
    return [s[float(x)] if fin(x) else '∞' for x in vals]


def metric_of(src_vt, metric, vals, area_rows):
    if src_vt == 'count' and metric == 'density':
        return vals / area_rows[:, None]
    return vals


# ---------- ย่อ (รวมพิกเซล) ----------
def block_sum(a, m):
    h, w = a.shape
    return a.reshape(h // m, m, w // m, m).sum(axis=(1, 3))


def majority_classes(cls, n, m, tie='high'):
    """cls (H·m × W·m) int16, -1 = ไม่มีข้อมูล → ชั้นเสียงข้างมากของแต่ละบล็อก m×m"""
    H, W = cls.shape[0] // m, cls.shape[1] // m
    cnt = np.stack([block_sum((cls == k).astype('int32'), m) for k in range(n)], -1)
    if tie == 'high':
        out = (n - 1 - np.argmax(cnt[..., ::-1], -1)).astype('int16')
    else:
        out = np.argmax(cnt, -1).astype('int16')
    out[cnt.sum(-1) == 0] = -1
    return out


def majority_values(vals, valid, m, tie='high'):
    """เสียงข้างมากของค่าดิบ (resample ข้อมูลชั้น) ; เสมอ → ค่ามากกว่า/น้อยกว่า"""
    u = np.unique(vals[valid])
    if len(u) > 256:
        raise EngineError(f'ข้อมูลชั้นมีค่าต่างกัน {len(u)} ค่าในไทล์เดียว (> 256) — น่าจะไม่ใช่ข้อมูลชั้น ตรวจประเภทค่า')
    idx = np.full(vals.shape, -1, 'int16')
    if len(u):
        idx[valid] = np.searchsorted(u, vals[valid]).astype('int16')
    k = majority_classes(idx, len(u), m, tie) if len(u) else np.full((vals.shape[0] // m, vals.shape[1] // m), -1, 'int16')
    out = np.zeros(k.shape, 'float64')
    ok = k >= 0
    if len(u):
        out[ok] = u[k[ok]]
    return out, ok


# ---------- ต้นทางบนกริดเป้าหมาย ----------
ALIGN_TOL = 0.01          # ยอมให้มุมกริดคลาดได้ไม่เกิน 1% พิกเซล (≈1 ม. ที่ 3″) — ไฟล์จริงคลาดจากเศษทศนิยม เช่น WorldPop 0.0013 พิกเซล


def _offset(a, b, unit):
    """(a − b) / unit → (จำนวนเต็มที่ใกล้สุด, ส่วนที่ไม่ลงตัวเป็นสัดส่วนพิกเซล)"""
    f = (a - b) / unit
    n = round(f)
    return n, abs(f - n)


def _axis_weights(t0, tstep, n, s0, sstep, dirn):
    """น้ำหนักการทับกันบนแกนเดียว: พิกเซลเป้าหมาย n ช่อง (ขอบเริ่ม t0 ห่าง tstep) กับพิกเซลต้นทาง (ขอบเริ่ม s0 ห่าง sstep)
    dirn = +1 แกน x · −1 แกน y (ลงใต้) → (แถว/คอลัมน์ต้นทางแรก, จำนวน, csr n × จำนวน = สัดส่วนของพิกเซลต้นทางที่ทับ)"""
    from scipy import sparse
    ut = dirn * (t0 - s0) / sstep + np.arange(n + 1) * (tstep / sstep)     # ขอบเป้าหมายในหน่วยพิกเซลต้นทาง
    j0 = int(math.floor(ut[0] + 1e-9))
    j1 = int(math.ceil(ut[-1] - 1e-9))
    lo = np.floor(ut[:-1] + 1e-9).astype(np.int64)
    hi = np.ceil(ut[1:] - 1e-9).astype(np.int64)
    span = int((hi - lo).max())
    ii = np.repeat(np.arange(n), span)
    jj = (lo[:, None] + np.arange(span)[None, :]).ravel()
    ov = np.minimum(ut[1:][ii], jj + 1) - np.maximum(ut[:-1][ii], jj)
    keep = (ov > 1e-12) & (jj < hi[ii])
    return j0, j1 - j0, sparse.csr_matrix((ov[keep], (ii[keep], jj[keep] - j0)), shape=(n, j1 - j0))


def _area_majority(stack_fn, keys, tie):
    """พื้นที่ของแต่ละค่า (หรือชั้น) → ค่าที่ครองพื้นที่มากสุด (เสมอ → ค่าสูงกว่า/ต่ำกว่า) · คืน (ดัชนี, มีข้อมูล)"""
    a = np.stack([stack_fn(k) for k in keys], -1)
    idx = (len(keys) - 1 - np.argmax(a[..., ::-1], -1)) if tie == 'high' else np.argmax(a, -1)
    return idx, a.sum(-1) > 1e-12


class OnGrid:
    """ต้นทางบนกริดเป้าหมาย
    เส้นกริดอยู่บนแลตทิซเดียวกัน (มุมเลื่อนเป็นจำนวนเต็มพิกเซล) → อ่านตรงพิกเซล ไม่ resample (same/up/down)
      ระยะเลื่อน (dr, dc): โหมด same/up นับเป็นพิกเซลเป้าหมาย · โหมด down นับเป็นพิกเซลต้นทาง
    เส้นกริดเหลื่อมแบบไม่ลงตัว (เช่น VIIRS วางกึ่งกลางพิกเซลที่ −180°) → โหมด warp: ถ่วงพื้นที่ที่ทับกันจริง
      count = แบ่งตามสัดส่วนพื้นที่ (ผลรวมไม่หาย) · density = เฉลี่ยถ่วงพื้นที่ · class = ชั้นที่ครองพื้นที่มากสุด"""

    def __init__(self, src, grid, count_down_valid='positive', tie='high'):
        if src.meta.get('crs_key') != _grid_crs_key(grid, src):
            raise EngineError(f'CRS ของ "{src.name}" ไม่ตรงกับกริดเป้าหมาย')
        r = gm.int_ratio(src.res_frac / grid.res_frac)
        if r is None:
            raise EngineError(f'ความละเอียด "{src.name}" ({gm.frac_str(src.res_frac)}) กับเป้าหมาย '
                              f'({gm.frac_str(grid.res_frac)}) ไม่เป็นพหุคูณจำนวนเต็มของกัน')
        self.src, self.grid = src, grid
        self.mode, self.k = r
        ux, uy = (src.rx, src.ry) if self.mode == 'down' else (grid.rx, grid.ry)
        self.dc, ex = _offset(grid.x0, src.x0, ux)
        self.dr, ey = _offset(src.y0, grid.y0, uy)
        self.fine = self.mode == 'down'
        self.misalign = max(ex, ey) / (self.k if self.mode == 'up' else 1)   # วัดเป็นสัดส่วนพิกเซลต้นทาง
        if self.misalign > ALIGN_TOL:                        # เส้นกริดเหลื่อม → ถ่วงพื้นที่ (resample ระหว่างคำนวณ)
            self.mode = 'warp'
        self.count_down_valid = count_down_valid
        self.tie = tie

    def src_px(self, h, w):
        """จำนวนพิกเซลต้นทางที่ต้องอ่านต่อไทล์เป้าหมาย (ใช้เรียงลำดับอ่านตัวที่ถูกกว่าก่อน)"""
        if self.mode == 'up':
            return (math.ceil(h / self.k) + 1) * (math.ceil(w / self.k) + 1)
        if self.mode == 'down' or (self.mode == 'warp' and self.fine):
            return h * w * self.k * self.k
        if self.mode == 'warp':
            return (math.ceil(h / self.k) + 2) * (math.ceil(w / self.k) + 2)
        return h * w

    def _warp_read(self, r0, c0, h, w):
        g, s = self.grid, self.src
        sr0, R, Wy = _axis_weights(g.y0 - r0 * g.ry, g.ry, h, s.y0, s.ry, -1)
        sc0, C, Wx = _axis_weights(g.x0 + c0 * g.rx, g.rx, w, s.x0, s.rx, +1)
        v, ok = s.read_raw(sr0, sc0, R, C)
        a = s.area_rows(sr0, R)[:, None]                     # พื้นที่จริงของแถวต้นทาง (ละติจูดต่างกัน)
        WxT = Wx.T.tocsr()
        return v, ok, a, (lambda A: np.asarray(Wy @ A @ WxT))

    def _warp_values(self, r0, c0, h, w):
        v, ok, a, P = self._warp_read(r0, c0, h, w)
        vt = self.src.vt
        if vt == 'count':
            s = P(np.where(ok, v, 0.0))
            cov = P(ok.astype('float64'))
            valid = (s > 0) if (self.fine and self.count_down_valid == 'positive') else cov > 1e-12
            return s, valid
        if vt == 'density':
            wa = ok * a
            den = P(wa)
            valid = den > 1e-12
            return np.where(valid, P(np.where(ok, v, 0.0) * wa) / np.where(valid, den, 1), 0.0), valid
        u = np.unique(v[ok])
        if len(u) > 256:
            raise EngineError(f'ข้อมูลชั้นมีค่าต่างกัน {len(u)} ค่าในไทล์เดียว (> 256) — น่าจะไม่ใช่ข้อมูลชั้น ตรวจประเภทค่า')
        if not len(u):
            return np.zeros((h, w)), np.zeros((h, w), bool)
        idx, valid = _area_majority(lambda x: P(((v == x) & ok) * a), list(u), self.tie)
        return np.where(valid, u[idx], 0.0), valid

    def _warp_classes(self, clf, r0, c0, h, w):
        vt = self.src.vt
        if vt == 'class' or clf.order == 'classify_first':
            v, ok, a, P = self._warp_read(r0, c0, h, w)
            c = clf.classify(metric_of(vt, clf.metric, v, a[:, 0]), ok)
            idx, valid = _area_majority(lambda k: P((c == k) * a), list(range(clf.n)), self.tie)
            return np.where(valid, idx, -1).astype('int16')
        val, valid = self._warp_values(r0, c0, h, w)
        return clf.classify(metric_of(vt, clf.metric, val, self.grid.area_rows(r0, h)), valid)

    def _raw_for(self, r0, c0, h, w):
        """อ่านต้นทางที่ครอบไทล์ → ((ค่า, valid), แถวต้นทางแรก, เฟส (แถว, คอลัมน์) ภายในพิกเซลแม่ของโหมด up)"""
        k = self.k
        if self.mode == 'same':
            return self.src.read_raw(r0 + self.dr, c0 + self.dc, h, w), r0 + self.dr, (0, 0)
        if self.mode == 'up':
            ar, ac = r0 + self.dr, c0 + self.dc                  # ตำแหน่งนับจากมุมต้นทาง (หน่วยพิกเซลเป้าหมาย)
            sr0, sc0 = ar // k, ac // k
            nr, nc = (ar + h - 1) // k - sr0 + 1, (ac + w - 1) // k - sc0 + 1
            return self.src.read_raw(sr0, sc0, nr, nc), sr0, (ar - sr0 * k, ac - sc0 * k)
        sr0 = r0 * k + self.dr
        return self.src.read_raw(sr0, c0 * k + self.dc, h * k, w * k), sr0, (0, 0)

    def _up(self, a, h, w, ph=(0, 0)):
        k = self.k
        return np.repeat(np.repeat(a, k, 0), k, 1)[ph[0]:ph[0] + h, ph[1]:ph[1] + w]

    # ค่า (สำหรับ resample / น้ำหนักสถิติ)
    def values(self, r0, c0, h, w):
        if self.mode == 'warp':
            return self._warp_values(r0, c0, h, w)
        (v, ok), sr0, ph = self._raw_for(r0, c0, h, w)
        vt, k = self.src.vt, self.k
        if self.mode == 'same':
            return v, ok
        if self.mode == 'up':
            if vt == 'count':
                v = v / (k * k)
            return self._up(v, h, w, ph), self._up(ok, h, w, ph)
        # down
        if vt == 'count':
            s = block_sum(np.where(ok, v, 0.0), k)
            valid = s > 0 if self.count_down_valid == 'positive' else block_sum(ok.astype('int32'), k) > 0
            return s, valid
        if vt == 'density':
            a = self.src.area_rows(sr0, v.shape[0])[:, None] * ok
            wsum = block_sum(a, k)
            s = block_sum(np.where(ok, v, 0.0) * a, k)
            valid = wsum > 0
            return np.where(valid, s / np.where(valid, wsum, 1), 0.0), valid
        return majority_values(v, ok, k, self.tie)

    # ชั้น (สำหรับไบแวเรียต)
    def classes(self, clf, r0, c0, h, w):
        if self.mode == 'warp':
            return self._warp_classes(clf, r0, c0, h, w)
        (v, ok), sr0, ph = self._raw_for(r0, c0, h, w)
        vt, k = self.src.vt, self.k
        if self.mode in ('same', 'up'):
            c = clf.classify(metric_of(vt, clf.metric, v, self.src.area_rows(sr0, v.shape[0])), ok)
            return c if self.mode == 'same' else self._up(c, h, w, ph)
        if vt == 'class' or clf.order == 'classify_first':
            c = clf.classify(metric_of(vt, clf.metric, v, self.src.area_rows(sr0, v.shape[0])), ok)
            return majority_classes(c, clf.n, k, self.tie)
        val, valid = self.values(r0, c0, h, w)
        return clf.classify(metric_of(vt, clf.metric, val, self.grid.area_rows(r0, h)), valid)


def _grid_crs_key(grid, src):
    return grid.crs_key if hasattr(grid, 'crs_key') else src.meta.get('crs_key')


# ---------- สร้างกริดเป้าหมายจากต้นทาง ----------
class GridSpec:
    """ข้อมูลกริดของชุดข้อมูลจาก meta (ใช้ตรวจโดยไม่ต้องเปิดไฟล์)"""

    def __init__(self, meta, name='', vt=None):
        t = meta['transform']
        self.name, self.meta, self.vt = name, meta, vt
        self.x0, self.y0, self.rx, self.ry = t[2], t[5], abs(t[0]), abs(t[4])
        self.w, self.h = meta['width'], meta['height']
        self.res_frac = Fraction(meta['res_exact'])


def _align_axis(srcs, res_frac, ref, step, attr):
    """หาจุดเริ่มกริดเป้าหมายบนแกนเดียว: อยู่บนแลตทิซของ ref (ห่างทีละ step) · เริ่มที่หรือหลังขอบที่ทับกัน ·
    และทุกชุดเลื่อนเป็นจำนวนเต็มพิกเซลตามกติกาโหมด → (จุดเริ่ม, None) หรือ (None, รายละเอียดที่ไม่ลงตัว)"""
    sign = 1 if attr == 'x0' else -1                         # แกน x เพิ่มไปทางขวา · แกน y ลดลงไปทางใต้
    edge = max(getattr(s, attr) for s in srcs) if sign == 1 else min(getattr(s, attr) for s in srcs)
    t0 = math.ceil(sign * (edge - getattr(ref, attr)) / step - ALIGN_TOL)
    worst = None
    for t in range(t0, t0 + 2000):
        p = getattr(ref, attr) + sign * t * step
        bad = None
        for s in srcs:
            r = gm.int_ratio(s.res_frac / res_frac)
            unit = (s.rx if attr == 'x0' else s.ry) if r and r[0] == 'down' else step
            _, err = _offset(p, getattr(s, attr), unit)
            err /= r[1] if r and r[0] == 'up' else 1                       # คลาดวัดเทียบพิกเซลต้นทาง
            if err > ALIGN_TOL:
                bad = (s, err)
                break
        if bad is None:
            return p, None
        if worst is None:
            worst = bad
    return getattr(ref, attr) + sign * t0 * step, worst      # ไม่มีจุดที่ทุกชุดลงตัว → ยึดแลตทิซของ ref (ชุดอื่นถ่วงพื้นที่)


def align(srcs, res_frac):
    """จุดเริ่ม + ขนาดกริดเป้าหมาย (มุมเริ่มต่างกันได้)
    เลือกแลตทิซอ้างอิงที่: 1) ชุดที่ต้องถ่วงพื้นที่ (warp) น้อยที่สุด 2) ถ้าต้องมี warp ให้ชุด count (เช่น ประชากร) ตรงพิกเซล
    3) ความละเอียดใกล้เป้าหมายที่สุด (ทศนิยมของ transform เหมือนไฟล์เดิม) → dict + warp = [(ชื่อ, ระยะเหลื่อม)]"""
    res_frac = Fraction(res_frac)
    for s in srcs:
        if gm.int_ratio(s.res_frac / res_frac) is None:
            raise EngineError(f'ความละเอียด "{s.name}" ({gm.frac_str(s.res_frac)}) กับเป้าหมาย ({gm.frac_str(res_frac)}) ไม่เป็นพหุคูณจำนวนเต็มของกัน')
    best = None
    for ref in srcs:
        rx = ref.rx * float(res_frac / ref.res_frac)
        ry = ref.ry * float(res_frac / ref.res_frac)
        x0, _ = _align_axis(srcs, res_frac, ref, rx, 'x0')
        y0, _ = _align_axis(srcs, res_frac, ref, ry, 'y0')
        warp = []
        for s in srcs:
            r = gm.int_ratio(s.res_frac / res_frac)
            ux, uy = (s.rx, s.ry) if r[0] == 'down' else (rx, ry)
            err = max(_offset(x0, s.x0, ux)[1], _offset(s.y0, y0, uy)[1]) / (r[1] if r[0] == 'up' else 1)   # พิกเซลต้นทาง
            if err > ALIGN_TOL:
                warp.append((s, err))
        is_count = getattr(ref, 'vt', None) == 'count'
        key = (len(warp), (not is_count) if warp else 0, abs(math.log(float(ref.res_frac / res_frac))))
        if best is None or key < best[0]:
            best = (key, dict(x0=x0, y0=y0, rx=rx, ry=ry, ref=ref, warp=warp))
    a = best[1]
    x0, y0, rx, ry = a['x0'], a['y0'], a['rx'], a['ry']
    W = H = None
    for s in srcs:
        r = gm.int_ratio(s.res_frac / res_frac)
        if any(s is w for w, _ in a['warp']):                # ถ่วงพื้นที่: ใช้ขอบเขตจริง
            w = math.ceil((s.x0 + s.w * s.rx - x0) / rx - 1e-6)
            h = math.ceil((y0 - (s.y0 - s.h * s.ry)) / ry - 1e-6)
        else:
            if r[0] == 'down':                               # ระยะเลื่อน (พิกเซลต้นทาง) → พิกเซลเป้าหมาย
                ox = Fraction(_offset(x0, s.x0, s.rx)[0]) * s.res_frac / res_frac
                oy = Fraction(_offset(s.y0, y0, s.ry)[0]) * s.res_frac / res_frac
            else:
                ox, oy = _offset(x0, s.x0, rx)[0], _offset(s.y0, y0, ry)[0]
            w = math.ceil(Fraction(s.w) * s.res_frac / res_frac - ox - Fraction(1, 10 ** 9))
            h = math.ceil(Fraction(s.h) * s.res_frac / res_frac - oy - Fraction(1, 10 ** 9))
        W, H = (w if W is None else min(W, w)), (h if H is None else min(H, h))
    if W < 1 or H < 1:
        raise EngineError('ชุดข้อมูลไม่มีพื้นที่ทับกัน')
    a.update(W=W, H=H, warp=[(s.name, round(e, 3)) for s, e in a['warp']])
    return a


def make_grid(sources, res_frac):
    """กริดเป้าหมาย: ความละเอียด res_frac · ขอบเขต = ส่วนที่ทับกันของทุกชุด · มุมเริ่มอยู่บนแลตทิซร่วมของทุกชุด
    (ชุดที่มุมตรงกัน → มุมเริ่มเดิมทุกประการ ผลเหมือนเวอร์ชันก่อน)"""
    s0 = sources[0]
    for s in sources[1:]:
        if s.meta.get('crs_key') != s0.meta.get('crs_key'):
            raise EngineError(f'CRS ไม่ตรงกัน: "{s0.name}" ({s0.meta.get("crs_key")}) กับ "{s.name}" ({s.meta.get("crs_key")}) '
                              '— V1 ยังไม่ reproject')
    res_frac = Fraction(res_frac)
    a = align(sources, res_frac)
    ref = a['ref']
    g = Grid(a['x0'], a['y0'], a['rx'], a['ry'], a['W'], a['H'], ref.ds.crs, ref.geographic, res_frac)
    g.crs_key = ref.meta.get('crs_key')
    return g


def snap_unit(ogs, extra=1):
    """ตัวคูณร่วมน้อยของอัตราแตกพิกเซล (มุมไทล์/หน้าต่างต้องเป็นพหุคูณของค่านี้)"""
    L = extra
    for o in ogs:
        if o.mode == 'up':
            L = L * o.k // math.gcd(L, o.k)
    return L


def tile_size(ogs, inmem, extra=1):
    """ขนาดไทล์เป้าหมาย: หารด้วยอัตราแตกพิกเซลลงตัว · ถ้าเขียนทีละไทล์ต้องเป็นพหุคูณ 512 (บล็อก GeoTIFF)"""
    L = snap_unit(ogs, extra)
    if not inmem:
        L = L * 512 // math.gcd(L, 512)
    maxm = max([o.k for o in ogs if o.mode == 'down' or (o.mode == 'warp' and o.fine)] or [1])
    cap = 2560 if maxm == 1 else max(1, 5120 // maxm)
    return max(L, cap // L * L)


TILE_MAX_PX = 150_000_000      # ไทล์เดียวใหญ่กว่านี้ → อาร์เรย์ float64 หลายตัว เกินหน่วยความจำเครื่องทั่วไป


def check_tiles(grid, ogs, extra=1):
    """แตกพิกเซลละเอียดมาก (เช่น 15″ → 0.01″ = ×1500) → ไทล์ต้องเป็นพหุคูณของอัตราแตก × 512 จนทั้งงานกลายเป็นไทล์เดียวขนาดยักษ์
    → แจ้งตั้งแต่ประเมินงาน แทนการล้มกลางทางเพราะหน่วยความจำไม่พอ"""
    T = tile_size(ogs, is_inmem(grid), extra)
    _, _, H, W = grid.win
    if min(T, H) * min(T, W) > TILE_MAX_PX:
        k = max([o.k for o in ogs if o.mode == 'up'] or [1])
        raise EngineError(f'ความละเอียดเป้าหมายละเอียดกว่าข้อมูลต้นทาง {k:,} เท่า — ต้องประมวลผลทีละ {min(T, H):,} × {min(T, W):,} พิกเซล '
                          'เกินหน่วยความจำ · เลือกความละเอียดที่หยาบขึ้น (ข้อมูลพิกัดองศา ความละเอียดเป็นฟิลิปดา ″)')
    return T


def iter_tiles(grid, T, full=False):
    """ไทล์ในหน้าต่างผลลัพธ์ (พิกัดกริดเต็ม) ; full=True = ทั้งกริด"""
    R0, C0, H, W = (0, 0, grid.height, grid.width) if full else grid.win
    for r0 in range(R0, R0 + H, T):
        for c0 in range(C0, C0 + W, T):
            yield r0, c0, min(T, R0 + H - r0), min(T, C0 + W - c0)


def is_inmem(grid):
    return grid.win[2] * grid.win[3] <= INMEM_OUT_PX


# ---------- DEGURBA (GHSL Degree of Urbanisation แบบย่อ) ----------
def degurba_classes(og, grid, clf, progress=None):
    """ทั้งกริดในหน่วยความจำ: กลุ่มเมือง = ช่อง ≥dens[0] ติดกัน 8 ทิศ รวม ≥minpop[0]
    ศูนย์กลางเมือง = ช่อง ≥dens[1] ติดกัน 4 ทิศ รวม ≥minpop[1] ; ไม่มีขั้นเติมช่องว่าง/เกลาขอบ"""
    from scipy import ndimage
    if og.src.vt != 'count':
        raise EngineError('วิธี DEGURBA ใช้ได้กับข้อมูลประเภท "จำนวนนับ" เท่านั้น')
    if grid.width * grid.height > 30_000_000:
        raise EngineError('DEGURBA ต้องคำนวณทั้งกริดในหน่วยความจำ — ใช้ได้กับความละเอียดหยาบ (เช่น 1 กม.) เท่านั้น')
    P = np.zeros((grid.height, grid.width), 'float64')
    V = np.zeros(P.shape, bool)
    T = tile_size([og], True)
    tiles = list(iter_tiles(grid, T, full=True))
    for i, (r0, c0, h, w) in enumerate(tiles):
        v, ok = og.values(r0, c0, h, w)
        P[r0:r0 + h, c0:c0 + w] = np.where(ok, v, 0)
        V[r0:r0 + h, c0:c0 + w] = ok
        if progress:
            progress(i / len(tiles))
    D = P / grid.area_rows(0, grid.height)[:, None]
    d1, d2 = clf.degurba['dens']
    m1, m2 = clf.degurba['minpop']

    def clusters(mask, struct):
        lab, n = ndimage.label(mask, structure=struct)
        pops = np.zeros(n + 1)
        if n:
            pops[1:] = ndimage.sum(P, lab, index=np.arange(1, n + 1))
        return lab, pops

    uc_lab, uc_pop = clusters(D >= d1, np.ones((3, 3)))
    ce_lab, ce_pop = clusters(D >= d2, ndimage.generate_binary_structure(2, 1))
    cls = np.zeros(P.shape, 'int16')
    cls[uc_pop[uc_lab] >= m1] = 1
    cls[ce_pop[ce_lab] >= m2] = 2
    cls[~V] = -1
    return cls
