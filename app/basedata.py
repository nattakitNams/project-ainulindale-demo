# -*- coding: utf-8 -*-
"""ข้อมูลพื้นฐานที่ติดมากับทุกเครื่อง: ขอบเขตการปกครองจาก GISTDA (ArcGIS Feature layer)

- เพิ่มอัตโนมัติตอนเปิดตัวประมวลผล (เธรดเบื้องหลัง ไม่ทำให้เปิดช้า) · ออฟไลน์/เซิร์ฟเวอร์ล่ม → ลองใหม่ครั้งหน้า
- ผู้ใช้ลบชุดไหน → จำไว้ใน settings.json (basedata_removed) ไม่เพิ่มกลับเอง · กด "เพิ่มข้อมูลพื้นฐานกลับ" ได้
- เป็นลิงก์ ไม่ดาวน์โหลดทั้งชุด: ดึงเฉพาะส่วนที่ใช้ผ่านพร็อกซีของแอปเหมือนลิงก์ที่ผู้ใช้เพิ่มเอง
"""
import threading

from . import db, links
from .config import load_settings, save_settings

BASE = [
    ('L05_Province', 'http://gistdaportal.gistda.or.th/arcgis/rest/services/Hosted/L05_Province_2559/FeatureServer', 'ขอบเขตจังหวัด (GISTDA 2559)'),
    ('L05_Amphoe', 'http://gistdaportal.gistda.or.th/arcgis/rest/services/Hosted/L05_Amphoe_2559/FeatureServer', 'ขอบเขตอำเภอ (GISTDA 2559)'),
    ('L05_Tambon', 'http://gistdaportal.gistda.or.th/arcgis/rest/services/Hosted/L05_Tambon_2559/FeatureServer', 'ขอบเขตตำบล (GISTDA 2559)'),
    ('L05_Munisan', 'https://gistdaportal.gistda.or.th/arcgis/rest/services/Hosted/L05_Munisan_DPT_50K/FeatureServer', 'ขอบเขตเทศบาล (กรมโยธาฯ 1:50,000)'),
]
URLS = {u for _, u, _ in BASE}
# พื้นที่ศึกษาพื้นฐาน: (key, ชื่อ, ชั้นพื้นฐานที่ใช้สร้าง, คำอธิบาย) — สร้างครั้งเดียวจากลิงก์ GISTDA แล้วเก็บเป็นไฟล์ใน workspace/aoi
BASE_AOI = [('thailand', 'ประเทศไทย', 'L05_Province', 'รวมขอบเขต 77 จังหวัด (GISTDA 2559)')]
STATUS = dict(state='idle', added=[], failed=[])
_lock = threading.Lock()


def _norm(u):
    return (u or '').rstrip('/').lower().replace('https://', 'http://')


def _existing():
    return {_norm(r['path']) for r in db.query("SELECT path FROM datasets WHERE kind='link'")}


def is_base(url):
    return _norm(url) in {_norm(u) for u in URLS}


def mark_removed(url):
    """ผู้ใช้ลบชุดข้อมูลพื้นฐาน → ไม่เพิ่มกลับเองอีก"""
    if is_base(url):
        rm = set(load_settings().get('basedata_removed') or [])
        rm.add(_norm(url))
        save_settings(basedata_removed=sorted(rm))


def unmark_removed(url):
    """กู้คืนจากถังขยะ → เลิกจำว่าผู้ใช้ลบ"""
    rm = set(load_settings().get('basedata_removed') or [])
    if _norm(url) in rm:
        rm.discard(_norm(url))
        save_settings(basedata_removed=sorted(rm))


def aoi_removed(a):
    """ผู้ใช้ลบพื้นที่ศึกษาพื้นฐานถาวร → ไม่สร้างกลับเอง"""
    key = (a.get('source') or {}).get('base') if isinstance(a.get('source'), dict) else None
    if key:
        rm = set(load_settings().get('basedata_removed') or [])
        rm.add('aoi:' + key)
        save_settings(basedata_removed=sorted(rm))


def _seed_aoi(removed, force):
    import geopandas as gpd
    from . import aoi
    have = {}
    for a in db.query('SELECT id, source, trashed_at FROM aoi'):
        s = a.get('source')
        if isinstance(s, dict) and s.get('base'):
            have[s['base']] = a
    for key, name, link_name, desc in BASE_AOI:
        if key in have:
            if force and have[key]['trashed_at']:
                db.update('aoi', have[key]['id'], trashed_at=None)
                STATUS['added'].append(name)
            continue
        if 'aoi:' + key in removed:
            continue
        url = next(u for n, u, _ in BASE if n == link_name)
        try:
            info = links.inspect(url)
            info['layer'] = 0
            info.update(links.layer_info(url, 0))
            feats = links.fetch_features(info)
            g = gpd.GeoDataFrame.from_features(feats, crs='EPSG:4326')
            geom = g.geometry.make_valid().union_all()
            if geom.geom_type == 'GeometryCollection':
                from shapely.geometry import MultiPolygon
                geom = MultiPolygon([p for x in geom.geoms for p in (x.geoms if hasattr(x, 'geoms') else [x]) if p.geom_type == 'Polygon'])
            aoi._save(name, geom, dict(type='base', base=key, description=desc, url=url, features=len(feats),
                                       fetched_at=db.now()))
            STATUS['added'].append(name)
        except Exception as e:                              # ออฟไลน์ → ลองใหม่ครั้งหน้า
            STATUS['failed'].append(f'{name}: {e}')


def seed(force=False):
    """เพิ่มชุดที่ยังไม่มี (+ พื้นที่ศึกษาพื้นฐาน) · force=True = คืนชุดที่ผู้ใช้เคยลบด้วย"""
    if not _lock.acquire(blocking=False):
        return STATUS
    try:
        STATUS.update(state='running', added=[], failed=[])
        if force:
            save_settings(basedata_removed=[])
            for r in db.query("SELECT id, path FROM datasets WHERE kind='link' AND trashed_at IS NOT NULL"):
                if is_base(r['path']):                       # อยู่ในถังขยะ → กู้คืนแทนการเพิ่มซ้ำ
                    db.update('datasets', r['id'], trashed_at=None)
                    STATUS['added'].append(r['path'])
        removed = set(load_settings().get('basedata_removed') or [])
        have = _existing()
        for name, url, desc in BASE:
            if _norm(url) in have or _norm(url) in removed:
                continue
            try:
                info = links.inspect(url)
                info['layer'] = 0
                info.update(links.layer_info(url, 0))
                meta = {k: v for k, v in info.items() if k != 'token'}
                meta.update(kind='link', secret_id=None, type_label=links.LABEL.get(info['type']), view=False,
                            bounds_wgs84=info.get('bounds_wgs84') or links.wgs_bounds(info), added_from=url,
                            builtin=True, description=desc)
                meta.setdefault('warnings', [])
                db.insert('datasets', name=name, path=url, source_path=url, read_path=url, copied=0, kind='link',
                          format=info['type'], meta=meta, role='input', added_at=db.now(), status='ok', fingerprint=None)
                STATUS['added'].append(name)
            except Exception as e:                          # ออฟไลน์ / บริการล่ม → ลองใหม่ครั้งหน้า
                STATUS['failed'].append(f'{name}: {e}')
        _seed_aoi(removed, force)
        STATUS['state'] = 'done'
        return STATUS
    finally:
        _lock.release()


def seed_background():
    threading.Thread(target=seed, daemon=True, name='basedata').start()
