# -*- coding: utf-8 -*-
"""พื้นที่ศึกษา (AOI): เลือกโพลิกอนจากชุดข้อมูลขอบเขต (จังหวัด/อำเภอ/ตำบล หรือชั้นใดก็ได้) หรือวาดเอง
เก็บเป็น GeoJSON (EPSG:4326) ใน workspace/aoi/ ; กติกาตัด: ศูนย์กลางพิกเซล (center) หรือ แตะ (touch)
ใช้กติกาเดียวกันทั้งตัดภาพและคิดสถิติ (ช่องที่อยู่นอกพื้นที่ = nodata)"""
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
    area = float(g.to_crs('ESRI:54009').area.iloc[0] / 1e6)        # Mollweide = พื้นที่เท่า
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


def create_from_geojson(name, gj):
    from shapely.geometry import shape
    from shapely.ops import unary_union
    feats = gj['features'] if gj.get('type') == 'FeatureCollection' else [gj if gj.get('type') == 'Feature' else {'geometry': gj}]
    geom = unary_union([shape(f['geometry']) for f in feats]).buffer(0)
    return _save(name, geom, dict(type='drawn'))


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
