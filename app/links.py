# -*- coding: utf-8 -*-
"""เพิ่มแผนที่ด้วยลิงก์ (3.1–3.3)

ดูอย่างเดียว (ภาพ ไม่มีค่า): XYZ · WMTS (template) · WMS · ArcGIS MapServer (cache/dynamic) · ArcGIS ImageServer
ใช้วิเคราะห์ (ต้องดาวน์โหลดเข้า database ก่อน): ArcGIS FeatureServer / MapServer layer · WFS · GeoJSON · COG/GeoTIFF
ไทล์ทุกแบบผ่านพร็อกซีของแอป (/api/links/<id>/tile) → โทเคนไม่ถึงเบราว์เซอร์ · ไม่ติด CORS · แคชได้"""
import math
import re
import threading
import xml.etree.ElementTree as ET
from collections import OrderedDict
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests

from . import vault

UA = {'User-Agent': 'Ainulindale/0.3 (local GIS app)'}
TIMEOUT = 25
VIEW_TYPES = {'xyz', 'wmts', 'wms', 'arcgis_tile', 'arcgis_dynamic', 'arcgis_image'}
DATA_TYPES = {'arcgis_feature', 'wfs', 'geojson', 'cog'}
LABEL = dict(xyz='XYZ tiles', wmts='WMTS', wms='WMS', arcgis_tile='ArcGIS MapServer (cache)', arcgis_dynamic='ArcGIS MapServer',
             arcgis_image='ArcGIS ImageServer', arcgis_feature='ArcGIS Feature layer', wfs='WFS', geojson='GeoJSON', cog='COG / GeoTIFF')


class LinkError(Exception):
    pass


def _strip(url):
    """ตัด query ที่เป็นของ service ออก (เก็บ path หลัก)"""
    u = urlparse(url.strip())
    return urlunparse(u._replace(query='', fragment='')), {k.lower(): v[0] for k, v in parse_qs(u.query).items()}


def _get(url, params=None, token=None, stream=False):
    p = dict(params or {})
    if token:
        p['token'] = token
    r = requests.get(url, params=p, headers=UA, timeout=TIMEOUT, stream=stream)
    if r.status_code >= 400:
        raise LinkError(f'บริการตอบกลับ {r.status_code}: {r.text[:200]}')
    return r


def _json(url, params=None, token=None):
    r = _get(url, dict(params or {}, f='json'), token)
    try:
        j = r.json()
    except ValueError:
        raise LinkError('บริการไม่ได้ตอบเป็น JSON')
    if isinstance(j, dict) and j.get('error'):
        e = j['error']
        raise LinkError(f'ArcGIS error {e.get("code")}: {e.get("message")} (ต้องใช้โทเคน?)')
    return j


def _ns(tag):
    return tag.split('}', 1)[-1]


def _find_all(el, name):
    return [e for e in el.iter() if _ns(e.tag) == name]


def _text(el, name):
    for e in el:
        if _ns(e.tag) == name:
            return (e.text or '').strip()
    return ''


def inspect(url, token=None):
    """ตรวจลิงก์ → ชนิด + รายละเอียด (ชั้น, ขอบเขต, ฟิลด์ …)"""
    url = url.strip()
    low = url.lower()
    if '{z}' in low and '{x}' in low and '{y}' in low:
        return dict(type='xyz', url=url, title=urlparse(url).netloc)
    if '{tilematrix}' in low:
        return dict(type='wmts', url=url, title=urlparse(url).netloc,
                    note='ใช้ template แบบ REST · TileMatrixSet ต้องเป็น GoogleMapsCompatible / EPSG:3857')
    base, q = _strip(url)
    m = re.search(r'/(mapserver|featureserver|imageserver)(/(\d+))?/?$', base, re.I)
    if m:
        kind, lyr = m.group(1).lower(), m.group(3)
        root = base[:m.start()] + '/' + m.group(1)
        j = _json(base, token=token)
        if lyr is not None or kind == 'featureserver':
            if lyr is None:
                layers = [dict(id=l['id'], name=l['name'], geometry=l.get('geometryType')) for l in j.get('layers', [])]
                out = dict(type='arcgis_feature', url=root, title=j.get('serviceDescription') or root.rsplit('/', 2)[-2],
                           layers=layers, layer=layers[0]['id'] if layers else None, max_records=j.get('maxRecordCount'))
                if layers:                                   # ขอบเขต/ฟิลด์ของชั้นแรก (ระดับ service มักไม่มี extent ที่ใช้ได้)
                    out.update(layer_info(root, layers[0]['id'], token))
                return out
            if j.get('type') not in ('Feature Layer', 'Table'):
                raise LinkError(f'ชั้น {lyr} เป็น {j.get("type")} — ดาวน์โหลดได้เฉพาะ Feature Layer')
            return dict(type='arcgis_feature', url=root, layer=int(lyr), title=j.get('name'),
                        layers=[dict(id=int(lyr), name=j.get('name'), geometry=j.get('geometryType'))],
                        fields=[f['name'] for f in j.get('fields', [])], max_records=j.get('maxRecordCount'),
                        extent=j.get('extent'))
        if kind == 'imageserver':
            return dict(type='arcgis_image', url=root, title=j.get('name') or root, extent=j.get('extent'),
                        pixel=dict(x=j.get('pixelSizeX'), y=j.get('pixelSizeY')), bands=j.get('bandCount'))
        layers = [dict(id=l['id'], name=l['name']) for l in j.get('layers', [])]
        tiled = bool(j.get('singleFusedMapCache')) and (j.get('tileInfo', {}).get('spatialReference', {}).get('latestWkid') in (3857, 102100)
                                                        or j.get('tileInfo', {}).get('spatialReference', {}).get('wkid') in (3857, 102100))
        return dict(type='arcgis_tile' if tiled else 'arcgis_dynamic', url=root, title=j.get('documentInfo', {}).get('Title') or j.get('mapName') or root,
                    layers=layers, extent=j.get('fullExtent'), copyright=j.get('copyrightText'),
                    note='มีชั้นข้อมูลย่อย — ดาวน์โหลดเป็นข้อมูลได้ถ้าเป็น Feature Layer (ใส่ลิงก์ .../MapServer/<เลขชั้น>)' if layers else None)
    svc = q.get('service', '').lower() or ('wms' if 'wms' in low else 'wfs' if 'wfs' in low else '')
    if svc in ('wms', 'wfs'):
        r = _get(base, dict(service=svc.upper(), request='GetCapabilities'), token)
        try:
            root = ET.fromstring(r.content)
        except ET.ParseError:
            raise LinkError('อ่าน GetCapabilities ไม่ได้ (ไม่ใช่ XML)')
        if svc == 'wms':
            layers = [dict(id=_text(l, 'Name'), name=_text(l, 'Title') or _text(l, 'Name')) for l in _find_all(root, 'Layer') if _text(l, 'Name')]
            return dict(type='wms', url=base, title=_text(next(iter(_find_all(root, 'Service')), root), 'Title') or base,
                        layers=layers, layer=q.get('layers') or (layers[0]['id'] if layers else None), version=root.attrib.get('version', '1.3.0'))
        fts = [dict(id=_text(f, 'Name'), name=_text(f, 'Title') or _text(f, 'Name')) for f in _find_all(root, 'FeatureType') if _text(f, 'Name')]
        return dict(type='wfs', url=base, title=base, layers=fts, layer=q.get('typenames') or q.get('typename') or (fts[0]['id'] if fts else None),
                    version=root.attrib.get('version', '2.0.0'))
    if re.search(r'\.(tif|tiff)$', base, re.I):
        import rasterio
        try:
            with rasterio.open('/vsicurl/' + url) as d:
                info = dict(width=d.width, height=d.height, crs=str(d.crs), dtypes=list(d.dtypes), res=list(d.res),
                            overviews=d.overviews(1), tiled=d.profile.get('tiled'), bounds=list(d.bounds))
        except Exception as e:
            raise LinkError(f'เปิด GeoTIFF ทางเน็ตไม่ได้: {e}')
        return dict(type='cog', url=url, title=base.rsplit('/', 1)[-1], **info,
                    note=None if info['tiled'] and info['overviews'] else 'ไม่ใช่ COG เต็มรูปแบบ (ไม่มีไทล์/overview) — ตัดตามพื้นที่จะช้า')
    if re.search(r'\.(geo)?json$', base, re.I) or 'f=geojson' in low or 'outputformat=application%2fjson' in low:
        return dict(type='geojson', url=url, title=base.rsplit('/', 1)[-1])
    raise LinkError('ไม่รู้จักลิงก์ — รองรับ XYZ ({z}/{x}/{y}), WMTS template, WMS/WFS, ArcGIS MapServer/FeatureServer/ImageServer, GeoJSON, GeoTIFF/COG')


def layer_info(root, layer, token=None):
    """ขอบเขต (WGS84) + ฟิลด์ + จำนวนต่อครั้ง ของชั้น ArcGIS"""
    j = _json(f'{root}/{layer}', token=token)
    info = dict(extent=j.get('extent'), fields=[f['name'] for f in j.get('fields', [])],
                field_types={f['name']: f.get('type') for f in j.get('fields', [])},
                geometry=j.get('geometryType'), max_records=j.get('maxRecordCount'))
    info['bounds_wgs84'] = wgs_bounds(info)
    return info


# ---------- ดึง feature ทั้งหมด (ใช้ร่วม: ดาวน์โหลด / พื้นที่ศึกษา / ไบแวเรียตรายพื้นที่) ----------
def _sql_in(m, field, values):
    """where field IN (...) — ข้อความใส่ ' (escape '') ตัวเลขไม่ใส่"""
    ft = (m.get('field_types') or {}).get(field, '')
    num = ft in ('esriFieldTypeInteger', 'esriFieldTypeSmallInteger', 'esriFieldTypeDouble', 'esriFieldTypeSingle', 'esriFieldTypeOID')
    vals = [str(v) if num else "'" + str(v).replace("'", "''") + "'" for v in values]
    return f'{field} IN ({",".join(vals)})'


def fetch_features(m, layer=None, bbox=None, where=None, progress=None, log=None):
    """GeoJSON features ทั้งหมดของลิงก์ข้อมูล (EPSG:4326) ; ArcGIS ดึงด้วย objectIds ทีละ ≤1000 จนครบ"""
    t = m['type']
    token = vault.get(m.get('secret_id'))
    P = progress or (lambda f, msg=None: None)
    if t == 'arcgis_feature':
        layer = int(layer if layer is not None else (m.get('layer') or 0))
        q = f"{m['url']}/{layer}/query"
        base = dict(where=where or '1=1', f='json')
        if bbox:
            base.update(geometry=','.join(map(str, bbox)), geometryType='esriGeometryEnvelope', inSR=4326, spatialRel='esriSpatialRelIntersects')
        ids = sorted(_json(q, dict(base, returnIdsOnly='true'), token).get('objectIds') or [])
        if not ids:
            return []
        chunk = int(min(m.get('max_records') or 1000, 1000))
        if log:
            log(f'ArcGIS feature layer {layer}: {len(ids):,} feature · ดึงทีละ {chunk}')
        feats = []
        for i in range(0, len(ids), chunk):
            j = _get(q, dict(objectIds=','.join(map(str, ids[i:i + chunk])), outFields='*', outSR=4326, f='geojson'), token).json()
            if j.get('error'):
                raise LinkError(f'ArcGIS error: {j["error"].get("message")}')
            feats += j.get('features', [])
            P(min(0.9, (i + chunk) / len(ids) * 0.9), f'ดึงแล้ว {len(feats):,}/{len(ids):,} feature')
        return feats
    if t == 'wfs':
        layer = layer or m.get('layer')
        feats, start, page = [], 0, 1000
        for _ in range(500):
            prm = dict(service='WFS', request='GetFeature', version='2.0.0', typeNames=layer, outputFormat='application/json',
                       srsName='EPSG:4326', count=page, startIndex=start)
            if bbox:
                prm['bbox'] = ','.join(map(str, bbox)) + ',urn:ogc:def:crs:OGC:1.3:CRS84'
            j = _get(m['url'], prm, token).json()
            got = j.get('features', [])
            feats += got
            P(min(0.9, 0.05 + len(feats) / max(j.get('numberMatched') or len(feats) + page, 1) * 0.85), f'ดึงแล้ว {len(feats):,} feature')
            if len(got) < page:
                break
            start += page
        return feats
    if t == 'geojson':
        j = _get(m['url'], token=token).json()
        return j['features'] if j.get('type') == 'FeatureCollection' else [j]
    raise LinkError('ลิงก์ชนิดนี้ไม่มี feature')


def fetch_where_in(m, field, values, **kw):
    """feature ที่ field อยู่ในรายการ — ArcGIS ทำฝั่งบริการ (ทีละ 200 ค่า) · ชนิดอื่นดึงหมดแล้วกรอง"""
    if m['type'] == 'arcgis_feature':
        out = []
        values = list(values)
        for i in range(0, len(values), 200):
            out += fetch_features(m, where=_sql_in(m, field, values[i:i + 200]), **kw)
        return out
    want = {str(v) for v in values}
    return [f for f in fetch_features(m, **kw) if str((f.get('properties') or {}).get(field)) in want]


def extent_where_in(m, field, values):
    """กรอบ (WGS84) ของ feature ที่เลือก — ArcGIS ถามแค่ extent (เร็ว ไม่ดึงรูปร่าง)"""
    if m['type'] == 'arcgis_feature':
        e = _json(f"{m['url']}/{m.get('layer') or 0}/query",
                  dict(where=_sql_in(m, field, values), returnExtentOnly='true', outSR=4326), vault.get(m.get('secret_id'))).get('extent')
        if e and e.get('xmin') is not None and e.get('xmin') == e.get('xmin'):
            return [e['xmin'], e['ymin'], e['xmax'], e['ymax']]
    from shapely.geometry import shape
    fs = fetch_where_in(m, field, values)
    if not fs:
        return None
    bs = [shape(f['geometry']).bounds for f in fs if f.get('geometry')]
    return [min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs)] if bs else None


_dv = OrderedDict()


def distinct_values(ds, field, q='', limit=300):
    """ค่าไม่ซ้ำของฟิลด์ (เช่น ชื่อจังหวัด/อำเภอ/ตำบล) — แคชไว้ต่อ (ลิงก์, ชั้น, ฟิลด์)"""
    m = ds['meta']
    key = (ds['id'], m.get('layer'), field)
    if key not in _dv:
        vals = set()
        if m['type'] == 'arcgis_feature':
            token = vault.get(m.get('secret_id'))
            url = f"{m['url']}/{m.get('layer') or 0}/query"
            off, page = 0, int(m.get('max_records') or 1000)
            for _ in range(100):
                j = _json(url, dict(where='1=1', outFields=field, returnDistinctValues='true', returnGeometry='false',
                                    orderByFields=field, resultOffset=off, resultRecordCount=page), token)
                fs = j.get('features', [])
                vals |= {str(f['attributes'].get(field)) for f in fs if f['attributes'].get(field) is not None}
                if len(fs) < page and not j.get('exceededTransferLimit'):
                    break
                off += page
        else:
            vals = {str((f.get('properties') or {}).get(field)) for f in fetch_features(m) if (f.get('properties') or {}).get(field) is not None}
        _dv[key] = sorted(vals)
        while len(_dv) > 30:
            _dv.popitem(last=False)
    vals = _dv[key]
    if q:
        vals = [v for v in vals if q.lower() in v.lower()]
    return vals[:limit], len(vals)


# ---------- พรีวิว feature ของลิงก์ข้อมูล (เฉพาะกรอบที่มอง) ----------
_fc = OrderedDict()


def features(ds, bbox, z, limit=2000):
    """GeoJSON ของ feature ในกรอบ (WGS84) — ย่อรูปตามระดับซูม ; คืน (geojson dict, ถูกตัดไหม)"""
    m = ds['meta']
    t = m['type']
    token = vault.get(m.get('secret_id'))
    tol = 360 / (256 * 2 ** z) * 0.8                  # องศาต่อพิกเซลจอ
    if t == 'arcgis_feature':
        r = _get(f"{m['url']}/{m.get('layer') or 0}/query",
                 dict(where='1=1', geometry=','.join(f'{v:.6f}' for v in bbox), geometryType='esriGeometryEnvelope', inSR=4326,
                      spatialRel='esriSpatialRelIntersects', outSR=4326, outFields='*', f='geojson', resultRecordCount=limit,
                      maxAllowableOffset=tol, returnGeometry='true'), token)
        g = r.json()
        if g.get('error'):
            raise LinkError(f'ArcGIS error: {g["error"].get("message")}')
        return g, len(g.get('features', [])) >= limit or bool(g.get('exceededTransferLimit') or g.get('properties', {}).get('exceededTransferLimit'))
    if t == 'wfs':
        g = _get(m['url'], dict(service='WFS', request='GetFeature', version='2.0.0', typeNames=m.get('layer'), outputFormat='application/json',
                                srsName='EPSG:4326', count=limit, bbox=','.join(map(str, bbox)) + ',urn:ogc:def:crs:OGC:1.3:CRS84'), token).json()
        return g, len(g.get('features', [])) >= limit
    if t == 'geojson':
        if ds['id'] not in _fc:
            _fc[ds['id']] = _get(m['url'], token=token).json()
            while len(_fc) > 5:
                _fc.popitem(last=False)
        g = _fc[ds['id']]
        fs = g.get('features', [])
        return dict(type='FeatureCollection', features=fs[:limit]), len(fs) > limit
    raise LinkError('ลิงก์ชนิดนี้ไม่มี feature')


# ---------- พร็อกซีไทล์ ----------
def tile_bbox3857(z, x, y):
    R = 20037508.342789244
    s = 2 * R / 2 ** z
    return (-R + x * s, R - (y + 1) * s, -R + (x + 1) * s, R - y * s)


_tc, _lock = OrderedDict(), threading.Lock()


def tile(ds, z, x, y):
    m = ds['meta']
    t = m['type']
    token = vault.get(m.get('secret_id'))
    key = (ds['id'], m.get('layer'), json_key(m.get('layers_on')), z, x, y)
    with _lock:
        if key in _tc:
            _tc.move_to_end(key)
            return _tc[key]
    bb = ','.join(f'{v:.3f}' for v in tile_bbox3857(z, x, y))
    if t in ('xyz', 'wmts'):
        u = m['url']
        for a, b in (('{z}', z), ('{x}', x), ('{y}', y), ('{-y}', 2 ** z - 1 - y), ('{TileMatrix}', z), ('{TileCol}', x), ('{TileRow}', y)):
            u = re.sub(re.escape(a), str(b), u, flags=re.I)
        u = u.replace('{s}', 'abc'[(x + y) % 3])
        r = _get(u, token=token)
    elif t == 'arcgis_tile':
        r = _get(f"{m['url']}/tile/{z}/{y}/{x}", token=token)
    elif t == 'arcgis_dynamic':
        p = dict(bbox=bb, bboxSR=3857, imageSR=3857, size='256,256', format='png32', transparent='true', f='image', dpi=96)
        if m.get('layers_on'):
            p['layers'] = 'show:' + ','.join(str(i) for i in m['layers_on'])
        r = _get(f"{m['url']}/export", p, token)
    elif t == 'arcgis_image':
        r = _get(f"{m['url']}/exportImage", dict(bbox=bb, bboxSR=3857, imageSR=3857, size='256,256', format='png32', f='image'), token)
    elif t == 'wms':
        v = m.get('version', '1.3.0')
        p = dict(service='WMS', request='GetMap', version=v, layers=m.get('layer') or '', styles='', format='image/png', transparent='true',
                 width=256, height=256, bbox=bb, **({'crs': 'EPSG:3857'} if v.startswith('1.3') else {'srs': 'EPSG:3857'}))
        r = _get(m['url'], p, token)
    else:
        raise LinkError('ชนิดนี้เป็นข้อมูล (ต้องดาวน์โหลดก่อน) ไม่ใช่ไทล์ภาพ')
    ct = r.headers.get('Content-Type', 'image/png')
    if not ct.startswith('image'):
        raise LinkError(f'บริการไม่ได้ส่งภาพ: {r.text[:200]}')
    out = (r.content, ct)
    with _lock:
        _tc[key] = out
        while len(_tc) > 1500:
            _tc.popitem(last=False)
    return out


def json_key(v):
    return tuple(v) if isinstance(v, list) else v


def wgs_bounds(info):
    """ขอบเขตเป็น WGS84 จาก extent ของ ArcGIS (ถ้ามี)"""
    e = info.get('extent')
    if not e or 'xmin' not in e:
        return None
    sr = e.get('spatialReference', {})
    wk = sr.get('latestWkid') or sr.get('wkid')
    try:
        from rasterio.warp import transform_bounds
        return list(transform_bounds(f'EPSG:{3857 if wk == 102100 else wk}', 'EPSG:4326', e['xmin'], e['ymin'], e['xmax'], e['ymax']))
    except Exception:
        return None
