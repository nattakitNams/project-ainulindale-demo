# -*- coding: utf-8 -*-
"""พื้นที่ศึกษา (AOI): เลือกโพลิกอนจากชุดข้อมูลขอบเขต (จังหวัด/อำเภอ/ตำบล หรือชั้นใดก็ได้) หรือวาดเอง
เก็บเป็น GeoJSON (EPSG:4326) ใน workspace/aoi/ ; กติกาตัด: ศูนย์กลางพิกเซล (center) หรือ แตะ (touch)
ใช้กติกาเดียวกันทั้งตัดภาพและคิดสถิติ (ช่องที่อยู่นอกพื้นที่ = nodata)"""
import re
import json
import math

import numpy as np

from . import db
from .config import DIRS


class AoiError(Exception):
    pass


def _gdf(ds):
    import pyogrio
    from .dsinfo import read_vector
    return read_vector(ds)


def field_values(ds, field, q='', limit=300):
    import pyogrio
    from .dsinfo import read_vector
    df = read_vector(ds, columns=[field], read_geometry=False)
    vals = sorted({str(v) for v in df[field].dropna().tolist()})
    if q:
        ql = q.lower()
        vals = [v for v in vals if ql in v.lower()]
    return vals[:limit], len(vals)


def text_lost(vals):
    """ข้อความในไฟล์กลายเป็น "?" จริง (โปรแกรมที่บันทึกแปลงไทยทิ้งไปแล้ว — เลือก encoding ไหนก็กู้ไม่ได้)
    เกณฑ์: ค่าข้อความ ≥ 60% มี "??" ติดกัน และไม่มีอักษรที่ไม่ใช่ ASCII เลย"""
    vs = [v for v in vals if isinstance(v, str) and v.strip()]
    if len(vs) < 3 or any(any(ord(c) > 127 for c in v) for v in vs):
        return False
    return sum('??' in v for v in vs) >= 0.6 * len(vs)


def extent_of(ds, field, values):
    """กรอบ (WGS84) ของ feature ที่ field อยู่ในรายการ — ใช้ซูมแผนที่ไปพื้นที่ที่เลือก"""
    import pyogrio
    from rasterio.warp import transform_bounds
    vals = [str(v) for v in values]
    from .dsinfo import read_vector
    df = read_vector(ds, columns=[field])
    df = df[df[field].astype(str).isin(vals)]
    if not len(df):
        return None
    b = df.total_bounds
    if df.crs is not None and df.crs.to_epsg() != 4326:
        b = transform_bounds(df.crs, 'EPSG:4326', *b)
    return [float(x) for x in b]


def _save(name, geom, source):
    """geom = shapely (EPSG:4326)"""
    import geopandas as gpd
    if geom is None or geom.is_empty:
        raise AoiError('พื้นที่ว่าง')
    if geom.geom_type not in ('Polygon', 'MultiPolygon'):
        raise AoiError(f'พื้นที่ศึกษาต้องเป็นโพลิกอน (ได้ {geom.geom_type})')
    g = gpd.GeoSeries([geom], crs=4326)
    from pyproj import Geod                                          # พื้นที่บนทรงรี WGS84 (แม่นกว่า Mollweide ~0.5%) — ตรงกับพรีวิวพิมพ์พิกัด
    area = abs(Geod(ellps='WGS84').geometry_area_perimeter(geom)[0]) / 1e6
    aid = db.insert('aoi', name=name, source=source, bbox=list(geom.bounds), area_km2=area, created_at=db.now())
    p = DIRS['aoi'] / f'aoi_{aid}.geojson'
    gpd.GeoDataFrame({'name': [name]}, geometry=g).to_file(p, driver='GeoJSON')
    db.update('aoi', aid, path=str(p))
    return aid


def create_from_dataset(name, ds, field, values):
    if ds['kind'] != 'vector':
        raise AoiError('ต้องเลือกชุดข้อมูล vector (โพลิกอน)')
    df = _gdf(ds)
    if field:
        sel = df[df[field].astype(str).isin([str(v) for v in values])]
        if not len(sel):
            raise AoiError('ไม่พบ feature ที่เลือก')
    else:
        sel = df
    if sel.crs is not None and sel.crs.to_epsg() != 4326:
        sel = sel.to_crs(4326)
    geom = sel.geometry.make_valid().union_all()
    if geom.geom_type == 'GeometryCollection':
        from shapely.geometry import MultiPolygon
        geom = MultiPolygon([p for g in geom.geoms for p in (g.geoms if hasattr(g, 'geoms') else [g]) if p.geom_type == 'Polygon'])
    src = dict(type='dataset', dataset_id=ds['id'], dataset_name=ds['name'], path=ds['path'], layer=ds.get('layer'),
               field=field, values=[str(v) for v in values], fingerprint=ds.get('fingerprint'))
    return _save(name, geom, src)


def create_from_link(name, ds, field, values):
    """พื้นที่ศึกษาจากลิงก์ขอบเขต (ArcGIS Feature layer / WFS / GeoJSON) — ดึงเฉพาะโพลิกอนที่เลือกจากบริการ"""
    import geopandas as gpd
    from . import links
    m = ds['meta']
    if not values:
        raise AoiError('เลือกพื้นที่อย่างน้อย 1 รายการ')
    feats = links.fetch_where_in(m, field, values)
    if not feats:
        raise AoiError('บริการไม่คืน feature ที่เลือก')
    g = gpd.GeoDataFrame.from_features(feats, crs='EPSG:4326')
    geom = g.geometry.make_valid().union_all()
    if geom.geom_type == 'GeometryCollection':
        from shapely.geometry import MultiPolygon
        geom = MultiPolygon([p for x in geom.geoms for p in (x.geoms if hasattr(x, 'geoms') else [x]) if p.geom_type == 'Polygon'])
    src = dict(type='link', link_id=ds['id'], dataset_name=ds['name'], url=m['url'], layer=m.get('layer'), field=field,
               values=[str(v) for v in values], fetched_at=__import__('datetime').datetime.now().isoformat(timespec='seconds'))
    return _save(name, geom, src)


def create_from_geojson(name, gj, source=None):
    from shapely.geometry import shape
    from shapely.ops import unary_union
    feats = gj['features'] if gj.get('type') == 'FeatureCollection' else [gj if gj.get('type') == 'Feature' else {'geometry': gj}]
    geom = unary_union([shape(f['geometry']) for f in feats]).buffer(0)
    return _save(name, geom, source or dict(type='drawn'))


def get(aid):
    a = db.get('aoi', aid)
    if a is None:
        raise AoiError(f'ไม่พบพื้นที่ศึกษา #{aid}')
    return a


def geojson(aid):
    a = get(aid)
    with open(a['path'], encoding='utf-8') as f:
        return f.read()


def geom_in(aid, crs):
    """เรขาคณิตของพื้นที่ศึกษาใน CRS ของกริด"""
    import geopandas as gpd
    a = get(aid)
    g = gpd.read_file(a['path'])
    if crs is not None:
        g = g.to_crs(crs)
    return g.geometry.union_all()


class Masker:
    """mask ของพื้นที่ศึกษาบนกริดเป้าหมาย ; f = คิดที่พิกเซลใหญ่กว่า f เท่าแล้วแตกลง (เช่น อิงศูนย์กลางพิกเซลแม่ 100 ม.)"""

    def __init__(self, geom, grid, rule='center', f=1):
        from shapely import prepared  # noqa: F401
        self.geom, self.grid, self.rule, self.f = geom, grid, rule, int(f)

    def __call__(self, r0, c0, h, w):
        from rasterio.features import geometry_mask
        f = self.f
        assert r0 % f == 0 and c0 % f == 0
        hh, ww = math.ceil(h / f), math.ceil(w / f)
        m = geometry_mask([self.geom], out_shape=(hh, ww), transform=self.grid.tile_transform(r0, c0, f),
                          all_touched=self.rule == 'touch', invert=True)
        if f > 1:
            m = np.repeat(np.repeat(m, f, 0), f, 1)[:h, :w]
        return m


# ---------- พิมพ์พิกัดโพลิกอนเอง ----------
COORD_CRS = {
    'EPSG:4326': 'WGS 84 ลอง/ละติ (องศา)',
    'EPSG:32647': 'WGS 84 / UTM โซน 47N',
    'EPSG:32648': 'WGS 84 / UTM โซน 48N',
    'EPSG:24047': 'Indian 1975 / UTM โซน 47N (แผนที่ไทยรุ่นเก่า)',
    'EPSG:24048': 'Indian 1975 / UTM โซน 48N (แผนที่ไทยรุ่นเก่า)',
}
_DMS = re.compile(r"(-?\d+(?:\.\d+)?)\s*°\s*(?:(\d+(?:\.\d+)?)\s*['′’]\s*)?(?:(\d+(?:\.\d+)?)\s*(?:\"|″|”|'')\s*)?([NSEWnsew]?)")
_NUM = re.compile(r'-?\d+(?:\.\d+)?')


def _line_points(line):
    """บรรทัดหนึ่ง → [(a, b, axis_hint)] · axis_hint = 'xy'/'yx' เมื่อมีตัวอักษร N/S/E/W บอกแกน"""
    vals, axes = [], []
    if '°' in line:
        for m in _DMS.finditer(line):
            d, mi, s, h = m.groups()
            v = abs(float(d)) + float(mi or 0) / 60 + float(s or 0) / 3600
            v = -v if d.startswith('-') or h.upper() in ('S', 'W') else v
            vals.append(v)
            axes.append('x' if h.upper() in ('E', 'W') else 'y' if h.upper() in ('N', 'S') else '')
    else:
        for m in _NUM.finditer(line):
            vals.append(float(m.group()))
            nxt = line[m.end():m.end() + 2].strip()[:1].upper()
            axes.append('x' if nxt in ('E', 'W') else 'y' if nxt in ('N', 'S') else '')
            if nxt in ('S', 'W'):
                vals[-1] = -abs(vals[-1])
    if len(vals) == 3:                                     # x y z → ตัด z
        vals, axes = vals[:2], axes[:2]
    if len(vals) % 2:
        raise AoiError(f'บรรทัดนี้มีตัวเลข {len(vals)} ค่า (ต้องเป็นคู่): "{line.strip()[:60]}"')
    out = []
    for i in range(0, len(vals), 2):
        hint = 'xy' if axes[i] == 'x' or axes[i + 1] == 'y' else 'yx' if axes[i] == 'y' or axes[i + 1] == 'x' else ''
        out.append((vals[i], vals[i + 1], hint))
    return out


def parse_coords(text, order='auto', crs='auto'):
    """ข้อความพิกัด → dict(geojson ใน EPSG:4326, พื้นที่, จำนวนจุด, สิ่งที่ตรวจพบ, คำเตือน)
    รองรับ: GeoJSON · WKT (MULTI)POLYGON · ตัวเลขบรรทัดละจุด หรือหลายคู่ต่อบรรทัด · องศา-ลิปดา-ฟิลิปดา · UTM 47/48
    หลายรูป: เว้นบรรทัดว่างคั่น · ปิดรูปให้เอง · ไม่แก้รูปที่ผิดแบบเงียบๆ (บอกปัญหาให้เห็น)"""
    from pyproj import Geod, Transformer
    from shapely import make_valid, wkt as swkt
    from shapely.geometry import MultiPolygon, Polygon, mapping, shape
    from shapely.ops import transform as stransform, unary_union
    from shapely.validation import explain_validity
    t = (text or '').strip()
    if not t:
        raise AoiError('ยังไม่ได้ใส่พิกัด')
    warns, info = [], {}
    if t[0] in '{[' and 'type' in t:
        try:
            gj = json.loads(t)
        except ValueError as e:
            raise AoiError(f'GeoJSON อ่านไม่ได้: {e}')
        feats = gj['features'] if gj.get('type') == 'FeatureCollection' else [gj if gj.get('type') == 'Feature' else {'geometry': gj}]
        polys = [shape(f['geometry']) for f in feats]
        info['format'] = 'GeoJSON'
        rings_xy = None
    elif re.match(r'(?i)^\s*(multi)?polygon\s*\(', t):
        try:
            polys = [swkt.loads(t)]
        except Exception as e:
            raise AoiError(f'WKT อ่านไม่ได้: {e}')
        info['format'] = 'WKT'
        rings_xy = None
    else:
        blocks = [b for b in re.split(r'\n\s*\n', t) if b.strip()]
        rings_xy = []
        for b in blocks:
            pts = [p for ln in b.splitlines() if ln.strip() and _NUM.search(ln) for p in _line_points(ln)]
            if pts:
                rings_xy.append(pts)
        if not rings_xy:
            raise AoiError('ไม่พบตัวเลขพิกัด')
        info['format'] = f'ตัวเลข {sum(len(r) for r in rings_xy)} จุด' + (f' · {len(rings_xy)} รูป' if len(rings_xy) > 1 else '')
        polys = None
    # ---- ระบบพิกัด + ลำดับแกน ----
    if rings_xy is not None:
        allv = [v for r in rings_xy for p in r for v in p[:2]]
        projected = max(abs(v) for v in allv) > 360
        hints = {p[2] for r in rings_xy for p in r if p[2]}
        if crs == 'auto':
            crs = 'EPSG:32647' if projected else 'EPSG:4326'
            if projected:
                warns.append('ตัวเลขใหญ่ → เดาว่าเป็น UTM โซน 47N (ภาคตะวันออกของไทยเลยลองจิจูด 102° อาจเป็นโซน 48N) — ตรวจตำแหน่งบนแผนที่')
        swap = False
        if order == 'yx':
            swap = True
        elif order == 'auto':
            if hints == {'yx'}:
                swap = True
            elif crs == 'EPSG:4326' and not hints:
                ok_xy = all(abs(p[0]) <= 180 and abs(p[1]) <= 90 for r in rings_xy for p in r)
                ok_yx = all(abs(p[1]) <= 180 and abs(p[0]) <= 90 for r in rings_xy for p in r)
                th_xy = all(95 <= p[0] <= 107 and 4 <= p[1] <= 22 for r in rings_xy for p in r)
                th_yx = all(95 <= p[1] <= 107 and 4 <= p[0] <= 22 for r in rings_xy for p in r)
                if (ok_yx and not ok_xy) or (th_yx and not th_xy):
                    swap = True
                elif ok_xy and ok_yx and not th_xy:
                    warns.append('ลำดับแกนไม่ชัด (ทั้งสองแบบเป็นพิกัดที่เป็นไปได้) — ใช้ ลองจิจูด, ละติจูด · ถ้ารูปไปผิดที่ให้เลือก "ละติ, ลอง"')
        geo = crs == 'EPSG:4326'
        info['order'] = (('ละติจูด, ลองจิจูด (สลับให้แล้ว)' if geo else 'Northing, Easting (สลับให้แล้ว)') if swap
                         else ('ลองจิจูด, ละติจูด' if geo else 'Easting, Northing'))
        polys = []
        for r in rings_xy:
            xy = [(p[1], p[0]) if swap else (p[0], p[1]) for p in r]
            if len(xy) >= 2 and xy[0] == xy[-1]:
                xy = xy[:-1]
            else:
                info['closed'] = 'ปิดรูปให้อัตโนมัติ (จุดสุดท้ายต่อกลับจุดแรก)'
            if len(set(xy)) < 3:
                raise AoiError(f'รูปหนึ่งมีจุดไม่ซ้ำกันแค่ {len(set(xy))} จุด — ต้องอย่างน้อย 3 จุด')
            polys.append(Polygon(xy))
    else:
        if crs == 'auto':
            b = unary_union(polys).bounds
            crs = 'EPSG:32647' if max(abs(v) for v in b) > 360 else 'EPSG:4326'
    if crs not in COORD_CRS:
        raise AoiError(f'ไม่รู้จักระบบพิกัด {crs}')
    info['crs'] = COORD_CRS[crs]
    geom = unary_union(polys) if len(polys) > 1 else polys[0]
    if geom.geom_type not in ('Polygon', 'MultiPolygon'):
        raise AoiError(f'ต้องเป็นโพลิกอน (ได้ {geom.geom_type})')
    if crs != 'EPSG:4326':
        tr = Transformer.from_crs(crs, 'EPSG:4326', always_xy=True)
        geom = stransform(tr.transform, geom)
    x0, y0, x1, y1 = geom.bounds
    if x0 < -180 or x1 > 180 or y0 < -90 or y1 > 90:
        raise AoiError(f'พิกัดเกินขอบเขตโลก ({x0:.3f}, {y0:.3f}, {x1:.3f}, {y1:.3f}) — ตรวจระบบพิกัด/ลำดับแกน')
    if not geom.is_valid:
        why = explain_validity(geom)
        fixed = make_valid(geom)
        fixed = unary_union([g for g in getattr(fixed, 'geoms', [fixed]) if g.geom_type in ('Polygon', 'MultiPolygon')])
        warns.append(f'รูปไม่ถูกต้อง: {why} — แก้ให้แล้ว (เส้นตัดกันเองมักเกิดจากลำดับจุดสลับ ตรวจรูปบนแผนที่ก่อนบันทึก)')
        geom = fixed
    if geom.is_empty or geom.area == 0:
        raise AoiError('รูปไม่มีพื้นที่ (จุดเรียงเป็นเส้นตรง?)')
    area = abs(Geod(ellps='WGS84').geometry_area_perimeter(geom)[0]) / 1e6
    if not (95 <= geom.centroid.x <= 107 and 4 <= geom.centroid.y <= 22):
        warns.append(f'รูปอยู่นอกประเทศไทย (กึ่งกลาง {geom.centroid.y:.3f}°N, {geom.centroid.x:.3f}°E) — ถ้าไม่ตั้งใจ ให้ตรวจลำดับแกน/ระบบพิกัด')
    npts = sum(len(p.exterior.coords) - 1 for p in getattr(geom, 'geoms', [geom]))
    return dict(geojson=mapping(geom), area_km2=round(area, 4), points=npts, parts=len(getattr(geom, 'geoms', [geom])),
                bounds=[round(v, 6) for v in geom.bounds], info=info, warnings=warns, crs=crs)
