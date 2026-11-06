# -*- coding: utf-8 -*-
"""กริดหกเหลี่ยม (hex) — แปลง raster / vector เป็น hex และไบแวเรียตบน hex

กริด: หกเหลี่ยมหัวแหลม (pointy-top) ระยะศูนย์กลางถึงศูนย์กลาง = d (กม.) · พื้นที่ช่อง = √3/2 · d²
  สร้างบนพิกัดฉายแบบเมตร (UTM โซนกลางพื้นที่ · พื้นที่กว้างเกิน 12° → Lambert equal-area) ให้ทุกช่องพื้นที่เท่ากัน
  แลตทิซยึดจุด (0, 0) ของพิกัดฉาย → สร้างกี่ครั้งก็ได้ช่องเดิม (ขนาด+พิกัดฉายเดียวกัน = ต่อกันด้วย hex_id ได้)

raster → hex (นับค่าที่ความละเอียดต้นทางของแต่ละชุด ไม่แตกพิกเซล): พิกเซลเป็นของช่องที่ศูนย์กลางพิกเซลตก
  count = ผลรวม (+ ต่อ ตร.กม.) · density = ค่าเฉลี่ยถ่วงพื้นที่ · class = ค่าที่กินพื้นที่มากสุด (+ % ของค่านั้น)
vector → hex: polygon = % พื้นที่ที่ทับ · line = ความยาว (กม.) · point = จำนวนจุด
"""
import math
import re
import time
from fractions import Fraction

import numpy as np

from . import db, engine
from .engine import EngineError

HEX_MAX = 600_000
SQ3 = math.sqrt(3)


# ---------- กริด ----------
def hex_area_km2(d_km):
    return SQ3 / 2 * d_km * d_km


def pick_crs(b4326):
    """พิกัดฉายเมตรที่พื้นที่เท่ากันพอ: UTM โซนกลางพื้นที่ (กว้าง ≤ 12°) · กว้างกว่า → Lambert Azimuthal Equal Area กลางพื้นที่ (ปัดองศาเต็ม)"""
    x0, y0, x1, y1 = b4326
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if x1 - x0 <= 12 and abs(cy) < 80:
        zone = int((cx + 180) // 6) + 1
        return f'EPSG:{32600 + zone if cy >= 0 else 32700 + zone}', f'UTM โซน {zone}{"N" if cy >= 0 else "S"}'
    lat0, lon0 = round(cy), round(cx)
    return f'+proj=laea +lat_0={lat0} +lon_0={lon0} +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs', f'Lambert equal-area ({lat0}°, {lon0}°)'


def grid_sig(crs, d_m):
    return f'{crs}|{int(round(d_m))}'


def build(geom_in_crs, d_m, max_n=HEX_MAX):
    """หกเหลี่ยมที่ทับรูป geom (ในพิกัดฉายเดียวกัน) → (q, r, polygons, centers)"""
    import shapely
    R = d_m / SQ3                                   # รัศมีถึงมุม
    x0, y0, x1, y1 = geom_in_crs.bounds
    est = (x1 - x0 + d_m) * (y1 - y0 + d_m) / (SQ3 / 2 * d_m * d_m)
    if est > max_n * 1.6:
        raise EngineError(f'หกเหลี่ยมประมาณ {est:,.0f} ช่อง เกินขีด {max_n:,} — เพิ่มขนาดช่อง หรือเลือกพื้นที่ศึกษาเล็กลง')
    r0, r1 = math.floor(y0 / (1.5 * R)) - 1, math.ceil(y1 / (1.5 * R)) + 1
    qs, rs = [], []
    for r in range(r0, r1 + 1):
        qa = math.floor(x0 / d_m - r / 2) - 1
        qb = math.ceil(x1 / d_m - r / 2) + 1
        q = np.arange(qa, qb + 1)
        qs.append(q)
        rs.append(np.full(q.size, r))
    q = np.concatenate(qs)
    r = np.concatenate(rs)
    cx = d_m * (q + r / 2.0)
    cy = 1.5 * R * r
    ang = np.radians(30 + 60 * np.arange(6))
    vx = cx[:, None] + R * np.cos(ang)[None, :]
    vy = cy[:, None] + R * np.sin(ang)[None, :]
    rings = np.stack([vx, vy], axis=-1)
    polys = shapely.polygons(np.concatenate([rings, rings[:, :1]], axis=1))
    shapely.prepare(geom_in_crs)
    keep = shapely.intersects(geom_in_crs, polys)
    if keep.sum() > max_n:
        raise EngineError(f'หกเหลี่ยม {int(keep.sum()):,} ช่อง เกินขีด {max_n:,} — เพิ่มขนาดช่อง หรือเลือกพื้นที่ศึกษาเล็กลง')
    if not keep.any():
        raise EngineError('ไม่มีหกเหลี่ยมในพื้นที่')
    return q[keep], r[keep], polys[keep], np.stack([cx[keep], cy[keep]], axis=1)


def make_gdf(extent_geom_4326, d_km, crs=None):
    """GeoDataFrame หกเหลี่ยม (พิกัดฉายเมตร) ทับพื้นที่ที่ให้ ; crs=None → เลือกเอง"""
    import geopandas as gpd
    from shapely.ops import transform as stransform
    from pyproj import Transformer
    label = None
    if crs is None:
        crs, label = pick_crs(extent_geom_4326.bounds)
    tr = Transformer.from_crs('EPSG:4326', crs, always_xy=True)
    g = stransform(tr.transform, extent_geom_4326)
    d_m = float(d_km) * 1000
    q, r, polys, cen = build(g, d_m)
    gdf = gpd.GeoDataFrame(dict(hex_id=[f'{a}_{b}' for a, b in zip(q, r)], q=q.astype('int64'), r=r.astype('int64')), geometry=polys, crs=crs)
    gdf['area_km2'] = hex_area_km2(float(d_km))
    gdf.attrs.update(crs=crs, crs_label=label or crs, d_m=d_m, d_km=float(d_km), sig=grid_sig(crs, d_m))
    return gdf


def extent_4326(dss, aoi_id=None):
    """พื้นที่ที่จะทำ hex: พื้นที่ศึกษา (ถ้ามี) ไม่งั้น = ส่วนที่ทับกันของทุกชุด"""
    from shapely.geometry import box
    if aoi_id:
        from . import aoi as aoimod
        return aoimod.geom_in(int(aoi_id), 'EPSG:4326')
    g = None
    for d in dss:
        b = d['meta'].get('bounds_wgs84')
        if not b:
            raise EngineError(f'"{d["name"]}" ไม่มีขอบเขต WGS84')
        g = box(*b) if g is None else g.intersection(box(*b))
    if g is None or g.is_empty:
        raise EngineError('ข้อมูลไม่ทับกัน — เลือกพื้นที่ศึกษา')
    x0, y0, x1, y1 = g.bounds
    if x1 - x0 > 60 or y1 - y0 > 60:
        raise EngineError('ข้อมูลครอบคลุมกว้างมาก (ระดับทวีป/ทั้งโลก) — เลือกพื้นที่ศึกษาก่อนทำหกเหลี่ยม')
    return g


def geod_area_km2(g4326):
    from pyproj import Geod
    return abs(Geod(ellps='WGS84').geometry_area_perimeter(g4326)[0]) / 1e6


# ---------- raster → hex ----------
def col_name(d, used):
    n = re.sub(r'[^0-9A-Za-zก-๙_]+', '_', d['name']).strip('_')[:28] or f'ds{d["id"]}'
    base, i = n, 2
    while n in used:
        n = f'{base}_{i}'
        i += 1
    used.add(n)
    return n


def agg_raster(hexes, d, P=None, log=None):
    """ค่าของชุด raster d ในแต่ละหกเหลี่ยม ที่ความละเอียดต้นทาง → dict(คอลัมน์ → array) + ข้อมูลการคำนวณ"""
    from rasterio.features import rasterize
    import shapely
    vt = d['value_type']
    src = engine.Source(d)
    try:
        grid = engine.make_grid([src], Fraction(d['meta']['res_exact']))
        og = engine.OnGrid(src, grid, 'any')
        hx = hexes.to_crs(grid.crs)
        grid.set_window(hx.total_bounds, 1)
        N = len(hx)
        geoms = hx.geometry.values
        tree = shapely.STRtree(geoms)
        px_area = None
        T = engine.check_tiles(grid, [og])
        tiles = list(engine.iter_tiles(grid, T))
        cover = np.zeros(N + 1)
        num = np.zeros(N + 1)
        den = np.zeros(N + 1)
        npx = np.zeros(N + 1)
        cls_pairs = {}
        t0 = time.time()
        for ti, (r0, c0, h, w) in enumerate(tiles):
            tt = grid.tile_transform(r0, c0)
            idx = tree.query(shapely.box(tt.c, tt.f - h * grid.ry, tt.c + w * grid.rx, tt.f))
            if len(idx):
                z = rasterize(zip(geoms[idx], idx + 1), out_shape=(h, w), transform=tt, fill=0, all_touched=False, dtype='int32')
                if z.any():
                    v, ok = og.values(r0, c0, h, w)
                    area = np.broadcast_to(grid.area_rows(r0, h)[:, None], (h, w))
                    px_area = float(area.mean())
                    m = ok & (z > 0)
                    zz = z[m]
                    cover += np.bincount(zz, weights=area[m], minlength=N + 1)
                    npx += np.bincount(zz, minlength=N + 1)
                    if vt == 'count':
                        num += np.bincount(zz, weights=v[m], minlength=N + 1)
                    elif vt == 'density':
                        num += np.bincount(zz, weights=(v * area)[m], minlength=N + 1)
                        den += np.bincount(zz, weights=area[m], minlength=N + 1)
                    else:
                        key = zz.astype('int64') * 1_000_003 + np.round(v[m]).astype('int64') % 1_000_003
                        u, c = np.unique(key, return_counts=True)
                        for k, n in zip(u.tolist(), c.tolist()):
                            cls_pairs[k] = cls_pairs.get(k, 0) + n
            if P and (ti % 5 == 0 or ti == len(tiles) - 1):
                P((ti + 1) / len(tiles), f'{d["name"]}: ไทล์ {ti + 1:,}/{len(tiles):,} · {time.time() - t0:,.0f} วินาที')
        hex_area = float(hexes['area_km2'].iloc[0])
        out, note = {}, ''
        cov = cover[1:] / hex_area * 100
        with np.errstate(divide='ignore', invalid='ignore'):
            if vt == 'count':
                s = np.where(npx[1:] > 0, num[1:], np.nan)
                out[''] = s
                out['_km2'] = s / hex_area
                note = 'ผลรวมของพิกเซลที่ศูนย์กลางตกในช่อง (+ ต่อ ตร.กม. = ÷ พื้นที่ช่อง)'
            elif vt == 'density':
                out[''] = np.where(den[1:] > 0, num[1:] / den[1:], np.nan)
                note = 'ค่าเฉลี่ยถ่วงพื้นที่ของพิกเซลที่ศูนย์กลางตกในช่อง'
            else:
                best = np.full(N + 1, np.nan)
                bestn = np.zeros(N + 1)
                for k, n in cls_pairs.items():
                    hid, val = divmod(k, 1_000_003)
                    if n > bestn[hid] or (n == bestn[hid] and val > best[hid]):
                        best[hid], bestn[hid] = val, n
                out[''] = best[1:]
                out['_pct'] = np.where(npx[1:] > 0, bestn[1:] / npx[1:] * 100, np.nan)
                note = 'ค่าที่มีพิกเซลมากสุดในช่อง (เสมอ → ค่ามากกว่า) + % ของค่านั้น'
        out['_cover'] = cov
        empty = int((npx[1:] == 0).sum())
        warn = []
        if px_area and hex_area < px_area * 4:
            warn.append(f'"{d["name"]}": ช่องหกเหลี่ยม ({hex_area:,.3g} ตร.กม.) เล็กกว่า 4 พิกเซลของข้อมูล ({px_area:,.3g} ตร.กม./พิกเซล) — ช่องส่วนใหญ่ได้ค่าจากพิกเซลเดียวหรือไม่มีเลย ควรใช้ช่องใหญ่ขึ้น')
        if empty:
            warn.append(f'"{d["name"]}": {empty:,} ช่องไม่มีศูนย์กลางพิกเซลตก (ขอบข้อมูล / nodata / ช่องเล็กกว่าพิกเซล) → ว่าง')
        return out, dict(dataset_id=d['id'], name=d['name'], value_type=vt, rule=note, res=d['meta'].get('res_label')), warn
    finally:
        src.close()


# ---------- vector → hex ----------
def agg_vector(hexes, d, log=None):
    import shapely
    from .dsinfo import read_vector
    g = read_vector(d)
    g = g[g.geometry.notna() & ~g.geometry.is_empty].to_crs(hexes.crs)
    gt = (d['meta'].get('geometry_type') or '').lower()
    hg = hexes.geometry.values
    hex_area_m2 = float(hexes['area_km2'].iloc[0]) * 1e6
    if 'polygon' in gt:
        u = shapely.make_valid(shapely.union_all(g.geometry.values))          # ทับกันเองไม่นับซ้ำ
        val = shapely.area(shapely.intersection(hg, u)) / hex_area_m2 * 100
        return {'_pct': np.where(val > 0, val, 0.0)}, dict(dataset_id=d['id'], name=d['name'], rule='% พื้นที่หกเหลี่ยมที่ถูกทับ (รวมรูปที่ซ้อนกันก่อน)'), []
    if 'line' in gt:
        tree = shapely.STRtree(g.geometry.values)
        hi, li = tree.query(hg, predicate='intersects')
        ln = shapely.length(shapely.intersection(hg[hi], g.geometry.values[li])) / 1000
        val = np.bincount(hi, weights=ln, minlength=len(hg))
        return {'_km': val}, dict(dataset_id=d['id'], name=d['name'], rule='ความยาวเส้นในช่อง (กม.)'), []
    tree = shapely.STRtree(hg)
    pi, hi = tree.query(g.geometry.values, predicate='within')
    val = np.bincount(hi, minlength=len(hg)).astype(float)
    return {'_n': val}, dict(dataset_id=d['id'], name=d['name'], rule='จำนวนจุดในช่อง'), []


def read_hex(d):
    """ชุดข้อมูล hex ที่แอปสร้าง → GeoDataFrame + ข้อมูลกริด"""
    from .dsinfo import read_vector
    hx = (d['meta'] or {}).get('hex')
    if not hx:
        raise EngineError(f'"{d["name"]}" ไม่ใช่ชุด hex ที่แอปสร้าง')
    g = read_vector(d)
    return g, hx
