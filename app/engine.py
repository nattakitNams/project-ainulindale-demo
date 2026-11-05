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
class OnGrid:
    def __init__(self, src, grid, count_down_valid='positive', tie='high'):
        if src.meta.get('crs_key') != _grid_crs_key(grid, src):
            raise EngineError(f'CRS ของ "{src.name}" ไม่ตรงกับกริดเป้าหมาย')
        tol = min(src.rx, grid.rx) * 1e-3
        if abs(src.x0 - grid.x0) > tol or abs(src.y0 - grid.y0) > tol:
            raise EngineError(f'มุมเริ่มของกริด "{src.name}" ไม่ตรงกับกริดเป้าหมาย — V1 รองรับเฉพาะกริดที่เริ่มมุมเดียวกัน')
        r = gm.int_ratio(src.res_frac / grid.res_frac)
        if r is None:
            raise EngineError(f'ความละเอียด "{src.name}" ({gm.frac_str(src.res_frac)}) กับเป้าหมาย '
                              f'({gm.frac_str(grid.res_frac)}) ไม่เป็นพหุคูณจำนวนเต็มของกัน')
        self.src, self.grid = src, grid
        self.mode, self.k = r
        self.count_down_valid = count_down_valid
        self.tie = tie

    def src_px(self, h, w):
        """จำนวนพิกเซลต้นทางที่ต้องอ่านต่อไทล์เป้าหมาย (ใช้เรียงลำดับอ่านตัวที่ถูกกว่าก่อน)"""
        if self.mode == 'up':
            return math.ceil(h / self.k) * math.ceil(w / self.k)
        if self.mode == 'down':
            return h * w * self.k * self.k
        return h * w

    def _raw_for(self, r0, c0, h, w):
        k = self.k
        if self.mode == 'same':
            return self.src.read_raw(r0, c0, h, w), r0
        if self.mode == 'up':
            assert r0 % k == 0 and c0 % k == 0
            sr0, sc0 = r0 // k, c0 // k
            return self.src.read_raw(sr0, sc0, math.ceil(h / k), math.ceil(w / k)), sr0
        return self.src.read_raw(r0 * k, c0 * k, h * k, w * k), r0 * k

    def _up(self, a, h, w):
        k = self.k
        return np.repeat(np.repeat(a, k, 0), k, 1)[:h, :w]

    # ค่า (สำหรับ resample / น้ำหนักสถิติ)
    def values(self, r0, c0, h, w):
        (v, ok), sr0 = self._raw_for(r0, c0, h, w)
        vt, k = self.src.vt, self.k
        if self.mode == 'same':
            return v, ok
        if self.mode == 'up':
            if vt == 'count':
                v = v / (k * k)
            return self._up(v, h, w), self._up(ok, h, w)
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
        (v, ok), sr0 = self._raw_for(r0, c0, h, w)
        vt, k = self.src.vt, self.k
        if self.mode in ('same', 'up'):
            c = clf.classify(metric_of(vt, clf.metric, v, self.src.area_rows(sr0, v.shape[0])), ok)
            return c if self.mode == 'same' else self._up(c, h, w)
        if vt == 'class' or clf.order == 'classify_first':
            c = clf.classify(metric_of(vt, clf.metric, v, self.src.area_rows(sr0, v.shape[0])), ok)
            return majority_classes(c, clf.n, k, self.tie)
        val, valid = self.values(r0, c0, h, w)
        return clf.classify(metric_of(vt, clf.metric, val, self.grid.area_rows(r0, h)), valid)


def _grid_crs_key(grid, src):
    return grid.crs_key if hasattr(grid, 'crs_key') else src.meta.get('crs_key')


# ---------- สร้างกริดเป้าหมายจากต้นทาง ----------
def make_grid(sources, res_frac):
    """กริดเป้าหมาย: มุมเริ่มเดียวกับต้นทาง, ความละเอียด res_frac, ขอบเขต = ส่วนที่ทับกันของทุกชุด"""
    s0 = sources[0]
    for s in sources[1:]:
        if s.meta.get('crs_key') != s0.meta.get('crs_key'):
            raise EngineError(f'CRS ไม่ตรงกัน: "{s0.name}" ({s0.meta.get("crs_key")}) กับ "{s.name}" ({s.meta.get("crs_key")}) '
                              '— V1 ยังไม่ reproject')
    res_frac = Fraction(res_frac)
    # ใช้ค่าทศนิยมแบบเดียวกับไฟล์ต้นทางที่ใกล้ที่สุด (เช่น 0.00083333333 × 10 = 0.0083333333 เหมือนไฟล์เดิม)
    ref = min(sources, key=lambda s: abs(math.log(float(s.res_frac / res_frac))))
    rx = ref.rx * float(res_frac / ref.res_frac)
    ry = ref.ry * float(res_frac / ref.res_frac)
    W = min(math.ceil(s.w * s.res_frac / res_frac - 1e-9) for s in sources)
    H = min(math.ceil(s.h * s.res_frac / res_frac - 1e-9) for s in sources)
    g = Grid(ref.x0, ref.y0, rx, ry, W, H, ref.ds.crs, ref.geographic, res_frac)
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
    maxm = max([o.k for o in ogs if o.mode == 'down'] or [1])
    cap = 2560 if maxm == 1 else max(1, 5120 // maxm)
    return max(L, cap // L * L)


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
