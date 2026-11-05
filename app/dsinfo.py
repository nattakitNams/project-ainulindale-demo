# -*- coding: utf-8 -*-
"""อ่านรายละเอียดชุดข้อมูล (metadata) — raster ด้วย rasterio, vector ด้วย pyogrio"""
import hashlib
import os
import re
import string
from pathlib import Path

import rasterio
from rasterio.warp import transform_bounds

from . import gridmath as gm
from .config import DIRS

RASTER_EXT = {'.tif', '.tiff', '.vrt', '.img', '.jp2', '.asc'}
VECTOR_EXT = {'.gpkg', '.shp', '.geojson', '.json', '.zip', '.fgb'}
SHP_SIDE = ('.shx', '.dbf', '.prj', '.cpg', '.qix', '.sbn', '.sbx', '.shp.xml')
COLAB_PREFIX = '/content/drive/MyDrive'


def kind_of(path):
    ext = Path(path).suffix.lower()
    if ext in RASTER_EXT:
        return 'raster'
    if ext in VECTOR_EXT:
        return 'vector'
    return None


def related_files(path):
    """ไฟล์ที่ต้องไปด้วยกัน (shapefile = .shp + .shx + .dbf + …)"""
    p = Path(path)
    out = [p]
    if p.suffix.lower() == '.shp':
        for s in SHP_SIDE:
            q = p.with_name(p.stem + s)
            if q.exists():
                out.append(q)
    for s in ('.aux.xml', '.ovr', '.msk'):
        q = p.with_name(p.name + s)
        if q.exists():
            out.append(q)
    return out


def fingerprint(path):
    """ขนาด + วันแก้ไข ของไฟล์หลักและไฟล์คู่ — ใช้ตรวจว่าไฟล์ย้าย/เปลี่ยน"""
    parts = []
    for f in related_files(path):
        try:
            st = f.stat()
        except OSError:
            return None
        parts.append(f'{f.name}:{st.st_size}:{int(st.st_mtime)}')
    return '|'.join(parts)


def total_size(path):
    return sum(f.stat().st_size for f in related_files(path) if f.exists())


def check_shapefile(path):
    p = Path(path)
    miss = [s for s in ('.shx', '.dbf') if not p.with_name(p.stem + s).exists()]
    warn = []
    if miss:
        raise ValueError(f'shapefile ไม่ครบ: ขาดไฟล์ {", ".join(p.stem + s for s in miss)} (ต้องอยู่โฟลเดอร์เดียวกับ .shp)')
    if not p.with_name(p.stem + '.prj').exists():
        warn.append('ไม่มีไฟล์ .prj → ไม่รู้ระบบพิกัด (CRS)')
    return warn


# ---------- VRT จาก Colab ----------
def find_mydrive():
    env = os.environ.get('AINU_MYDRIVE')
    if env:
        return env
    for L in string.ascii_uppercase[3:] + 'C':
        root = f'{L}:\\My Drive'
        if os.path.isdir(root):
            return root
    return None


def fix_vrt(path, key):
    """VRT ที่มี path แบบ Colab (/content/drive/MyDrive/…) → สำเนาใน cache/vrt ที่ชี้ไปที่ Drive ในเครื่อง
    (ไฟล์ต้นฉบับห้ามแก้) ; path relative แปลงเป็น absolute จากโฟลเดอร์เดิม"""
    if not str(path).lower().endswith('.vrt'):
        return str(path), []
    txt = Path(path).read_text(encoding='utf-8')
    if COLAB_PREFIX not in txt:
        return str(path), []
    root = find_mydrive()
    if not root:
        return str(path), ['VRT มี path ของ Colab แต่หาโฟลเดอร์ "My Drive" ในเครื่องไม่เจอ']
    fixed = txt.replace(COLAB_PREFIX, root.replace('\\', '/'))
    base = str(Path(path).parent).replace('\\', '/')
    fixed = re.sub(r'<SourceFilename relativeToVRT="1">([^<]+)</SourceFilename>',
                   lambda m: f'<SourceFilename relativeToVRT="0">{base}/{m.group(1)}</SourceFilename>', fixed)
    out = DIRS['cache'] / 'vrt' / f'{key}_{Path(path).name}'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(fixed, encoding='utf-8')
    return str(out), [f'VRT มี path ของ Colab → ใช้สำเนาที่แก้ path แล้ว: {out}']


def vrt_sources(path):
    """รายชื่อไฟล์ที่ VRT อ้าง (absolute)"""
    txt = Path(path).read_text(encoding='utf-8')
    base = Path(path).parent
    out = []
    for rel, f in re.findall(r'<SourceFilename relativeToVRT="(\d)"[^>]*>([^<]+)</SourceFilename>', txt):
        out.append(str(base / f) if rel == '1' else f)
    return out


# ---------- raster ----------
def crs_info(crs):
    if crs is None:
        return dict(crs=None, crs_key=None, crs_name='ไม่มี CRS', geographic=False)
    epsg = crs.to_epsg()
    key = f'EPSG:{epsg}' if epsg else 'WKT:' + hashlib.md5(crs.to_wkt().encode()).hexdigest()[:10]
    try:
        name = crs.to_dict().get('proj') or ''
        import pyproj
        name = pyproj.CRS.from_user_input(crs.to_wkt()).name
    except Exception:
        pass
    return dict(crs=crs.to_wkt(), crs_key=key, crs_name=f'{key} · {name}' if name else key, geographic=bool(crs.is_geographic))


def raster_meta(path, read_path=None):
    rp = read_path or path
    with rasterio.open(rp) as d:
        t = d.transform
        ci = crs_info(d.crs)
        geo = ci['geographic']
        rx, ry = abs(t.a), abs(t.e)
        fx = gm.exact_res(rx, geo)
        fy = gm.exact_res(ry, geo)
        b = d.bounds
        try:
            wb = transform_bounds(d.crs, 'EPSG:4326', *b) if d.crs else None
        except Exception:
            wb = None
        lat = (wb[1] + wb[3]) / 2 if wb else None
        m = dict(kind='raster', driver=d.driver, width=d.width, height=d.height, count=d.count,
                 dtypes=list(d.dtypes), nodata=d.nodata, transform=list(t)[:6], bounds=list(b),
                 bounds_wgs84=list(wb) if wb else None, center_lat=lat, res=[rx, ry],
                 res_exact=gm.frac_str(fx) if fx else None, res_exact_y=gm.frac_str(fy) if fy else None,
                 res_unit='arcsec' if geo else 'm', res_label=gm.res_label(fx, geo, lat) if fx else f'{rx:g}',
                 rotated=bool(t.b or t.d), overviews=d.overviews(1), block=list(d.block_shapes[0]),
                 compress=(d.compression.value if d.compression else None), pixels=d.width * d.height,
                 descriptions=list(d.descriptions), has_colormap=_has_cmap(d), **ci)
        m['square'] = fx == fy
    m['grid_family'] = gm.family_key(m)
    m['file_bytes'] = total_size(path)
    if str(path).lower().endswith('.vrt'):
        src = vrt_sources(rp)
        missing = [s for s in src[:2000] if not os.path.exists(s)]
        m['vrt'] = dict(sources=len(src), missing=len(missing), missing_sample=missing[:5])
        m['file_bytes'] = sum(os.path.getsize(s) for s in src if os.path.exists(s)) + os.path.getsize(path)
    return m


def _has_cmap(d):
    try:
        d.colormap(1)
        return True
    except Exception:
        return False


# ---------- vector: ภาษาไทยใน .dbf ----------
ENCODINGS = {'': 'อัตโนมัติ', 'UTF-8': 'UTF-8', 'cp874': 'ไทย TIS-620 / Windows-874', 'ISO-8859-1': 'Latin-1 (ISO-8859-1)'}


def _dbf_sample(dbf, nbytes=400_000):
    import struct
    with open(dbf, 'rb') as f:
        h = f.read(32)
        hlen, rlen = struct.unpack('<HH', h[8:12])
        fields, pos = [], 1
        while True:
            b = f.read(32)
            if not b or b[0] == 0x0D:
                break
            fields.append((b[:11].split(b'\0')[0].decode('ascii', 'replace'), chr(b[11]), pos, b[16]))
            pos += b[16]
        f.seek(hlen)
        data = f.read(min(nbytes, rlen * 2000))
    recs = [data[i:i + rlen] for i in range(0, len(data) - rlen + 1, rlen)]
    return fields, recs


def text_encoding(path):
    """shapefile: .cpg บอก encoding อะไร + ไบต์จริงเป็นภาษาไทย TIS-620 ไหม + ฟิลด์ที่มีแต่ '?' (ไทยเสียมาจากต้นทาง)
    คืน (encoding ที่ควรใช้ หรือ None = ให้ GDAL ตัดสิน, ข้อความเตือน)"""
    p = Path(path)
    if p.suffix.lower() != '.shp' or not p.with_suffix('.dbf').exists():
        return None, []
    cpg = p.with_suffix('.cpg')
    declared = cpg.read_text(errors='replace').strip() if cpg.exists() else ''
    warns, enc = [], None
    try:
        fields, recs = _dbf_sample(p.with_suffix('.dbf'))
    except Exception:
        return None, []
    tfields = [f for f in fields if f[1] == 'C']
    hi = sum(sum(1 for x in r if 0xA1 <= x <= 0xFB) for r in recs)
    if hi > 20 and 'UTF' not in declared.upper():
        try:
            txt = b''.join(recs).decode('cp874')
            if sum(1 for ch in txt if 'ก' <= ch <= '๛') > hi * 0.8:
                enc = 'cp874'
                warns.append(f'ไฟล์ .dbf เป็นภาษาไทย TIS-620 แต่ .cpg {"บอกว่า " + declared if declared else "ไม่มี"} → แอปอ่านเป็น TIS-620 ให้ (เปลี่ยนได้ที่ "การเข้ารหัสข้อความ")')
        except UnicodeDecodeError:
            pass
    broken = []
    for name, _, pos, ln in tfields:
        vals = [r[pos:pos + ln].strip(b' \0') for r in recs]
        vals = [v for v in vals if v]
        bad = sum(1 for v in vals if b'?' in v and set(v) <= set(b'?. '))
        if len(vals) >= 5 and bad >= 0.9 * len(vals):
            broken.append(name)
    if broken:
        warns.append(f'ฟิลด์ {", ".join(broken)} มีแต่ "?" — ตัวอักษรไทยเสียตั้งแต่ไฟล์ต้นทาง (ตอนสร้าง/ส่งออก) แอปกู้คืนไม่ได้ · '
                     'ใช้ฟิลด์รหัส (เช่น *_IDN) แทน หรือขอไฟล์ต้นฉบับใหม่ที่บันทึกเป็น UTF-8')
    return enc, warns


def read_vector(ds, **kw):
    """อ่าน vector ของชุดข้อมูล โดยใช้ encoding ที่ตั้งไว้/ตรวจพบ (ทุกจุดในแอปต้องอ่านผ่านฟังก์ชันนี้)"""
    import pyogrio
    enc = (ds.get('meta') or {}).get('encoding') or None
    return pyogrio.read_dataframe(ds['path'], layer=ds.get('layer'), encoding=enc, **kw)


# ---------- vector ----------
def vector_layers(path):
    import pyogrio
    return [l[0] for l in pyogrio.list_layers(path)]


def vector_meta(path, layer=None, encoding=None):
    import pyogrio
    enc_auto, enc_warns = text_encoding(path)
    info = pyogrio.read_info(path, layer=layer, encoding=encoding or enc_auto)
    from rasterio.crs import CRS
    crs = CRS.from_user_input(info['crs']) if info.get('crs') else None
    ci = crs_info(crs)
    b = info.get('total_bounds')
    wb = None
    if b is not None and crs is not None:
        try:
            wb = list(transform_bounds(crs, 'EPSG:4326', *b))
        except Exception:
            pass
    fields = [dict(name=n, type=str(t)) for n, t in zip(info['fields'], info['dtypes'])]
    return dict(kind='vector', driver=info.get('driver'), layer=layer, features=int(info['features']),
                geometry_type=info.get('geometry_type'), fields=fields, bounds=list(b) if b is not None else None,
                bounds_wgs84=wb, center_lat=(wb[1] + wb[3]) / 2 if wb else None,
                file_bytes=total_size(path), encoding=encoding or enc_auto, encoding_auto=enc_auto,
                encoding_warnings=enc_warns, encoding_checked=True, **ci)


# ---------- เดาประเภทค่า ----------
def guess_value_type(meta, name):
    """แอปเดาให้ แล้วผู้ใช้ต้องยืนยัน (ตั้งผิด = ผลผิดแต่ดูปกติ)"""
    n = name.lower()
    dt = meta['dtypes'][0]
    if meta.get('has_colormap'):
        return 'class', 'มีตารางสีในไฟล์ → น่าจะเป็นข้อมูลชั้น'
    if 'float' in dt:
        if re.search(r'pop|ppp|worldpop|ประชากร|count|_cn_', n):
            return 'count', 'ทศนิยม + ชื่อไฟล์เกี่ยวกับประชากร → น่าจะเป็นจำนวนนับต่อพิกเซล'
        if re.search(r'dens|ความหนาแน่น|per_?km', n):
            return 'density', 'ชื่อไฟล์บอกความหนาแน่น'
        return 'density', 'ทศนิยม → น่าจะเป็นค่าต่อเนื่อง (ความหนาแน่น/ความสูง/ดัชนี)'
    return 'class', 'จำนวนเต็ม → น่าจะเป็นข้อมูลชั้น/หมวดหมู่ หรือจำนวนครั้ง'
