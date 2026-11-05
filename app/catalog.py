# -*- coding: utf-8 -*-
"""เพิ่ม / แก้ / ลบ ชุดข้อมูลในทะเบียน"""
import os
import shutil
from pathlib import Path

from . import db, dsinfo, export
from .config import DIRS


class CatalogError(Exception):
    pass


def _norm(p):
    return str(Path(os.path.expandvars(os.path.expanduser(str(p).strip().strip('"')))).resolve())


def add_path(path, copy=False, name=None):
    """เพิ่มไฟล์จาก path → คืนรายการ id (GeoPackage หลายชั้น = หลายชุด) + คำเตือน"""
    path = _norm(path)
    if not os.path.exists(path):
        raise CatalogError(f'ไม่พบไฟล์: {path}')
    if os.path.isdir(path):
        raise CatalogError('เลือกได้เฉพาะไฟล์ (ไม่ใช่โฟลเดอร์) — shapefile ให้เลือกไฟล์ .shp')
    kind = dsinfo.kind_of(path)
    if kind is None:
        raise CatalogError(f'ยังไม่รองรับนามสกุล {Path(path).suffix} '
                           f'(raster: {", ".join(sorted(dsinfo.RASTER_EXT))} · vector: {", ".join(sorted(dsinfo.VECTOR_EXT))})')
    warns = []
    if path.lower().endswith('.shp'):
        warns += dsinfo.check_shapefile(path)
    src_path = path
    if copy:
        if path.lower().endswith('.vrt'):
            warns.append('VRT อ้างไฟล์อื่นจำนวนมาก — V1 ไม่ก๊อป VRT เข้า database ใช้แบบอ้าง path แทน')
            copy = False
        else:
            path = copy_in(path)
    layers = [None]
    if kind == 'vector':
        try:
            ls = dsinfo.vector_layers(path)
        except Exception as e:
            raise CatalogError(f'เปิดไฟล์ vector ไม่ได้: {e}')
        if len(ls) > 1:
            layers = ls
    ids = []
    for layer in layers:
        nm = name or Path(src_path).stem
        if layer and len(layers) > 1:
            nm = f'{nm} · {layer}'
        ids.append(_insert(path, src_path, copy, kind, layer, nm, warns))
    return ids, warns


def _insert(path, src_path, copied, kind, layer, name, warns, role='input', job_id=None, value_type=None):
    read_path, w2 = (path, [])
    tmp_key = f'{abs(hash(path)) % 10**8}'
    if kind == 'raster':
        read_path, w2 = dsinfo.fix_vrt(path, tmp_key)
        try:
            meta = dsinfo.raster_meta(path, read_path)
        except Exception as e:
            raise CatalogError(f'เปิดไฟล์ raster ไม่ได้: {e}')
        if meta.get('vrt', {}).get('missing'):
            w2.append(f"VRT อ้างไฟล์ที่หาไม่เจอ {meta['vrt']['missing']:,} ไฟล์ เช่น {meta['vrt']['missing_sample'][:2]}")
        if meta.get('rotated'):
            w2.append('raster หมุน (rotated) — V1 ไม่รองรับการคำนวณ')
        vt_guess, why = dsinfo.guess_value_type(meta, name)
        meta['value_type_guess'] = dict(value_type=vt_guess, reason=why)
    else:
        try:
            meta = dsinfo.vector_meta(path, layer)
        except Exception as e:
            raise CatalogError(f'อ่าน vector ไม่ได้: {e}')
        vt_guess = None
    meta['warnings'] = warns + w2 + meta.pop('encoding_warnings', [])
    did = db.insert('datasets', name=name, path=path, source_path=src_path, read_path=read_path, copied=int(bool(copied)),
                    kind=kind, format=Path(path).suffix.lower().lstrip('.'), layer=layer,
                    fingerprint=dsinfo.fingerprint(path), meta=meta,
                    value_type=value_type or vt_guess, value_type_confirmed=int(value_type is not None),
                    role=role, job_id=job_id, added_at=db.now(), status='ok')
    return did


def register_derived(path, name, value_type, job_id, role, kind='raster'):
    return _insert(str(path), str(path), False, kind, None, name, [], role=role, job_id=job_id, value_type=value_type)


def relink(ds, new_path):
    """ไฟล์ย้าย → ชี้ path ใหม่ (ต้องชนิดเดียวกัน) ; อ่าน metadata ใหม่ + เตือนถ้ากริดเปลี่ยน"""
    new_path = _norm(new_path)
    if not os.path.isfile(new_path):
        raise CatalogError(f'ไม่พบไฟล์: {new_path}')
    if dsinfo.kind_of(new_path) != ds['kind']:
        raise CatalogError('ไฟล์ใหม่ต้องเป็นชนิดเดียวกัน (raster/vector)')
    warns = []
    if ds['kind'] == 'raster':
        rp, w = dsinfo.fix_vrt(new_path, f'{ds["id"]}')
        warns += w
        meta = dsinfo.raster_meta(new_path, rp)
        old = ds['meta']
        for k, lbl in (('width', 'ความกว้าง'), ('height', 'ความสูง'), ('res_exact', 'ความละเอียด'), ('crs_key', 'CRS')):
            if old.get(k) != meta.get(k):
                warns.append(f'{lbl} เปลี่ยนจาก {old.get(k)} เป็น {meta.get(k)}')
        meta['value_type_guess'] = old.get('value_type_guess')
    else:
        rp = new_path
        meta = dsinfo.vector_meta(new_path, ds.get('layer'), ds['meta'].get('encoding') if ds['meta'].get('encoding') != ds['meta'].get('encoding_auto') else None)
        warns += meta.pop('encoding_warnings', [])
    meta['warnings'] = warns
    db.update('datasets', ds['id'], path=new_path, read_path=rp, fingerprint=dsinfo.fingerprint(new_path), meta=meta,
              status='ok', stats=None, preview_key=None)
    return warns


def changed_inputs(lineage):
    """ผลลัพธ์ที่ต้นทางเปลี่ยนหลังสร้าง (fingerprint ไม่ตรง) → ควรรันใหม่"""
    out = []
    for i in (lineage or {}).get('inputs', []):
        p = i.get('path')
        if p and os.path.exists(p):
            if i.get('fingerprint') and dsinfo.fingerprint(p) != i['fingerprint']:
                out.append(f'{i.get("name")}: ไฟล์เปลี่ยนหลังสร้างผลนี้')
        elif p:
            out.append(f'{i.get("name")}: ไม่พบไฟล์ต้นทาง')
    return out


def copy_in(path):
    """ก๊อปไฟล์ (และไฟล์คู่) เข้า workspace/database/<ชื่อ>/"""
    p = Path(path)
    dest = DIRS['database'] / f'{db.now().replace(":", "").replace("-", "")}_{export.slug(p.stem)}'
    dest.mkdir(parents=True, exist_ok=False)
    for f in dsinfo.related_files(path):
        shutil.copy2(f, dest / f.name)
    return str(dest / p.name)


def check_status(ds):
    """ไฟล์ยังอยู่ไหม / เปลี่ยนไปไหม (fingerprint)"""
    if ds['kind'] == 'link':
        return 'ok'
    if not os.path.exists(ds['path']):
        st = 'missing'
    else:
        fp = dsinfo.fingerprint(ds['path'])
        st = 'ok' if fp == ds['fingerprint'] else 'changed'
    if st != ds.get('status'):
        db.update('datasets', ds['id'], status=st)
        ds['status'] = st
    return st


def list_datasets():
    out = db.query('SELECT * FROM datasets ORDER BY id')
    for d in out:
        check_status(d)
    return out
