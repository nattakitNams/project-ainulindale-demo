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


def seed(force=False):
    """เพิ่มชุดที่ยังไม่มี · force=True = คืนชุดที่ผู้ใช้เคยลบด้วย"""
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
        STATUS['state'] = 'done'
        return STATUS
    finally:
        _lock.release()


def seed_background():
    threading.Thread(target=seed, daemon=True, name='basedata').start()
