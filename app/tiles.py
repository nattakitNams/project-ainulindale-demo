# -*- coding: utf-8 -*-
"""พรีวิวมินิแมพ: ไทล์ XYZ ของ raster (rio-tiler) + GeoJSON ของ vector ตามกรอบที่มอง + อ่านค่าที่จุดคลิก"""
import io
import math
import threading
from collections import OrderedDict
from contextlib import contextmanager

import numpy as np
import rasterio
from PIL import Image
from rasterio.warp import transform as warp_transform, transform_bounds
from rasterio.windows import Window
# import ที่หัวไฟล์ — import ครั้งแรกพร้อมกันหลายเธรดทำให้ import deadlock (บทเรียนจาก mp_viewer)
from rio_tiler.io import Reader
from rio_tiler.errors import TileOutsideBounds

from . import gridmath as gm

DENS_BINS = [10, 50, 100, 300, 600, 1500, 3000]
POP_COLS = ['#fff7bc', '#fee391', '#fec44f', '#fe9929', '#ec7014', '#cc4c02', '#993404', '#662506']
SEQ_COLS = ['#f7fbff', '#deebf7', '#c6dbef', '#9ecae1', '#6baed6', '#4292c6', '#2171b5', '#08519c', '#08306b']
CONT_COLS = ['#440154', '#482878', '#3e4989', '#31688e', '#26828e', '#1f9e89', '#35b779', '#6ece58', '#b5de2b', '#fde725']
CAT_COLS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf',
            '#aec7e8', '#ffbb78', '#98df8a', '#ff9896', '#c5b0d5', '#c49c94', '#f7b6d2', '#c7c7c7', '#dbdb8d', '#9edae5']


def hex2rgba(h, a=255):
    h = h.lstrip('#')
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


def png(rgba):
    b = io.BytesIO()
    Image.fromarray(rgba, 'RGBA').save(b, 'PNG')
    return b.getvalue()


EMPTY = png(np.zeros((256, 256, 4), 'uint8'))

# ---------- พูล reader (GDAL dataset ใช้ข้ามเธรดพร้อมกันไม่ได้ → ยืมทีละเธรด) ----------
_pool, _plock = {}, threading.Lock()


@contextmanager
def borrow(kind, path):
    k = (kind, path)
    with _plock:
        q = _pool.setdefault(k, [])
        o = q.pop() if q else None
    if o is None:
        o = Reader(path) if kind == 'rd' else rasterio.open(path)
    try:
        yield o
    finally:
        with _plock:
            _pool.setdefault(k, []).append(o)


def drop_pool(path):
    with _plock:
        for k in [k for k in _pool if k[1] == path]:
            for o in _pool.pop(k):
                try:
                    o.close()
                except Exception:
                    pass


# ---------- แคชไทล์ ----------
_tc, _tlock = OrderedDict(), threading.Lock()


def tc_get(k):
    with _tlock:
        v = _tc.get(k)
        if v is not None:
            _tc.move_to_end(k)
        return v


def tc_put(k, v, cap=3000):
    with _tlock:
        _tc[k] = v
        while len(_tc) > cap:
            _tc.popitem(last=False)


def tile_row_lat(y, z, n=256):
    t = (y + (np.arange(n) + 0.5) / n) / 2 ** z
    return np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * t))))


def choose_path(ds, z):
    """ใช้สำเนาพรีวิว (มี overview) ตอนซูมออก ; ซูมเข้าจนพิกเซลจอละเอียดกว่าพรีวิว → อ่านไฟล์จริง"""
    m = ds['meta']
    pv = ds.get('preview_path')
    src = ds.get('read_path') or ds['path']
    band = int(ds.get('band') or 1)
    if not pv:
        return src, band, abs(m['transform'][0])
    F = int(pv.rsplit('_F', 1)[1].split('.')[0])
    res = abs(m['transform'][0])
    if F == 1:
        return pv, 1, res
    deg_px = 360 / (256 * 2 ** z)
    if m.get('geographic') and deg_px < res * F:
        return src, band, res
    if not m.get('geographic') and deg_px * 111320 < res * F:
        return src, band, res
    return pv, 1, res * F



def colorize(ds, a, valid, res, y, z, cols=None):
    vt = ds.get('value_type')
    m = ds['meta']
    rgba = np.zeros(a.shape + (4,), 'uint8')
    if cols is not None or m.get('has_colormap'):
        lut = np.zeros((256, 4), 'uint8')
        if cols is not None:
            for i, c in enumerate(cols, 1):
                if c:
                    lut[i] = hex2rgba(c)
        else:
            for k, v in ds.get('_cmap', {}).items():
                lut[int(k)] = v
        idx = np.clip(a, 0, 255).astype('uint8')
        rgba = lut[idx]
        rgba[~valid] = 0
        return rgba
    if vt == 'count':
        if m.get('geographic'):
            area = gm.row_area_km2(res, tile_row_lat(y, z, a.shape[0]))[:, None]
        else:
            area = res * res / 1e6
        dens = a / area
        ok = valid & (a > 0)
        lut = np.array([hex2rgba(c, 225) for c in POP_COLS], 'uint8')
        rgba[ok] = lut[np.digitize(dens, DENS_BINS)[ok]]
        return rgba
    st = ds.get('stats') or {}
    vals = [v for v, _ in (st.get('hist_int') or [])]
    if vt == 'class' and vals and len(vals) <= 20:
        n = len(vals)
        # จำนวนเต็มเรียงติดกัน (เช่น จำนวนปีท่วม 1–14) = ลำดับ → ไล่สีเดียว ; ไม่ติดกัน (เช่น รหัส land cover) = สีแยกหมวด
        ordinal = vals[-1] - vals[0] == n - 1
        if ordinal:
            lut = np.array([hex2rgba(SEQ_COLS[3 + round(i * (len(SEQ_COLS) - 4) / max(n - 1, 1))], 235) for i in range(n)], 'uint8')
        else:
            lut = np.array([hex2rgba(CAT_COLS[i], 230) for i in range(n)], 'uint8')
        idx = np.searchsorted(vals, a)
        ok = valid & (idx < n)
        ok[ok] &= np.asarray(vals)[idx[ok]] == a[ok]
        rgba[ok] = lut[idx[ok]]
        return rgba
    pct = st.get('pct') or {}
    lo, hi = pct.get('2'), pct.get('98')
    if lo is None or hi is None or hi <= lo:
        f = a[valid]
        lo, hi = (float(f.min()), float(f.max())) if f.size else (0, 1)
        if hi <= lo:
            hi = lo + 1
    t = np.clip((a - lo) / (hi - lo), 0, 1)
    lut = np.array([hex2rgba(c, 230) for c in CONT_COLS], 'uint8')
    rgba[valid] = lut[np.minimum((t * len(CONT_COLS)).astype(int), len(CONT_COLS) - 1)[valid]]
    return rgba


_cmaps = {}


def load_cmap(ds):
    """ตารางสีในไฟล์ (แคชตาม fingerprint — แก้สีแล้ว fingerprint เปลี่ยน → อ่านใหม่)"""
    if ds['meta'].get('has_colormap') and '_cmap' not in ds:
        k = (ds['id'], ds.get('fingerprint'))
        if k not in _cmaps:
            with borrow('ds', ds.get('read_path') or ds['path']) as d:
                _cmaps[k] = {k2: v for k2, v in d.colormap(1).items() if k2 < 256}
        ds['_cmap'] = _cmaps[k]
    return ds


_defaults = {}


def style_of(ds):
    """สไตล์ที่บันทึกไว้ หรือสไตล์เริ่มต้น (แคชตาม fingerprint + สถิติ + ประเภทค่า)"""
    if ds.get('style'):
        return ds['style']
    k = (ds['id'], ds.get('fingerprint'), ds.get('value_type'), bool(ds.get('stats')), ds['meta'].get('has_colormap'))
    if k not in _defaults:
        from . import symbology
        try:
            _defaults[k] = symbology.jsonable(symbology.default_style(ds))
        except Exception as e:
            print('[สไตล์เริ่มต้น]', e)
            _defaults[k] = None
    return _defaults[k]


def render(ds, z, x, y, cols=None, style=None):
    import json
    from . import symbology
    path, band, res = choose_path(ds, z)
    if cols is None:
        style = style or style_of(ds)
    sk = json.dumps(style, sort_keys=True) if style else None
    key = (ds['id'], ds.get('fingerprint'), ds.get('preview_key'), ds.get('value_type'), path, z, x, y, tuple(cols) if cols else None, sk)
    hit = tc_get(key)
    if hit is not None:
        return hit, True
    try:
        with borrow('rd', path) as r:
            if not r.tile_exists(x, y, z):
                return EMPTY, True
            img = r.tile(x, y, z, indexes=band, resampling_method='nearest', reproject_method='nearest')
    except TileOutsideBounds:
        return EMPTY, True
    arr = img.array[0]
    a = np.asarray(arr.filled(0)).astype('float64')
    valid = ~np.ma.getmaskarray(arr) & np.isfinite(a)
    load_cmap(ds)
    if style and cols is None:
        data = png(symbology.render(ds, style, a, valid, res, tile_row_lat(y, z, a.shape[0])))
    else:
        data = png(colorize(ds, a, valid, res, y, z, cols))
    tc_put(key, data)
    return data, True


# ---------- อ่านค่าที่จุด ----------
def point_raster(ds, lon, lat):
    m = ds['meta']
    path = ds.get('read_path') or ds['path']
    with borrow('ds', path) as d:
        if d.crs is not None and d.crs.to_epsg() != 4326:
            xs, ys = warp_transform('EPSG:4326', d.crs, [lon], [lat])
            X, Y = xs[0], ys[0]
        else:
            X, Y = lon, lat
        col, row = ~d.transform * (X, Y)
        col, row = int(math.floor(col)), int(math.floor(row))
        if not (0 <= row < d.height and 0 <= col < d.width):
            return dict(outside=True)
        vals = d.read(window=Window(col, row, 1, 1))[:, 0, 0]
        nod = d.nodata
        out = dict(row=row, col=col, bands=[])
        for i, v in enumerate(vals, 1):
            v = v.item()
            isnod = (nod is not None and (v == nod or (isinstance(nod, float) and math.isnan(nod) and math.isnan(v))))
            out['bands'].append(dict(band=i, value=v, nodata=bool(isnod), desc=d.descriptions[i - 1]))
        res = abs(d.transform.a)
    if m.get('geographic'):
        a = float(gm.row_area_km2(res, m['transform'][5] - abs(m['transform'][4]) * (row + 0.5)))
    else:
        a = abs(m['transform'][0] * m['transform'][4]) / 1e6
    out['pixel_area_km2'] = a
    b = out['bands'][(ds.get('band') or 1) - 1]
    if ds.get('value_type') == 'count' and not b['nodata']:
        out['density'] = b['value'] / a
    if b['nodata'] and ds.get('nodata_as') is not None:
        out['nodata_as'] = ds['nodata_as']
    if m.get('has_colormap'):
        load_cmap(ds)
        c = ds['_cmap'].get(int(b['value'])) if not b['nodata'] else None
        out['color'] = '#%02x%02x%02x' % c[:3] if c else None
    return out


# ---------- vector ----------
def _bbox_to_crs(bbox, crs_wkt):
    if not crs_wkt:
        return bbox
    from rasterio.crs import CRS
    c = CRS.from_wkt(crs_wkt)
    if c.to_epsg() == 4326:
        return bbox
    return transform_bounds('EPSG:4326', c, *bbox)


def features(ds, bbox, z, limit=4000, fields=None):
    import pyogrio
    m = ds['meta']
    bb = _bbox_to_crs(bbox, m.get('crs'))
    from .dsinfo import read_vector
    df = read_vector(ds, bbox=tuple(bb), max_features=limit + 1)
    trunc = len(df) > limit
    df = df.iloc[:limit]
    if df.crs is not None and df.crs.to_epsg() != 4326:
        df = df.to_crs(4326)
    tol = 360 / (256 * 2 ** z) * 0.7
    df['geometry'] = df.geometry.simplify(tol, preserve_topology=True)
    keep = [c for c in (fields or []) if c in df.columns] or [c for c in df.columns if c != 'geometry'][:3]
    df = df[keep + ['geometry']]
    for c in keep:
        df[c] = df[c].astype(str)
    return df.to_json(drop_id=True), trunc, len(df)


def point_vector(ds, lon, lat, z):
    import pyogrio
    from shapely.geometry import Point
    tol = 360 / (256 * 2 ** z) * 4
    bb = _bbox_to_crs((lon - tol, lat - tol, lon + tol, lat + tol), ds['meta'].get('crs'))
    from .dsinfo import read_vector
    df = read_vector(ds, bbox=tuple(bb), max_features=500)
    if not len(df):
        return []
    if df.crs is not None and df.crs.to_epsg() != 4326:
        df = df.to_crs(4326)
    p = Point(lon, lat)
    d = df.geometry.distance(p)
    df = df[d <= tol].assign(_d=d[d <= tol]).sort_values('_d').head(10)
    out = []
    for _, r in df.iterrows():
        attrs = {k: (None if v is None or (isinstance(v, float) and math.isnan(v)) else str(v))
                 for k, v in r.items() if k not in ('geometry', '_d')}
        out.append(dict(attrs=attrs, geom_type=r.geometry.geom_type if r.geometry is not None else None))
    return out
