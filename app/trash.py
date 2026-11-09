# -*- coding: utf-8 -*-
"""ถังขยะ: ลบ = ย้ายเข้าถัง (ซ่อนจากทุกหน้า กู้คืนได้) · ลบในถัง = ลบถาวร

ลบถาวรแล้วไฟล์หายจริงเฉพาะไฟล์ที่แอปเก็บไว้ใน workspace (สำเนาที่ก๊อปเข้า/อัปโหลด, ผลลัพธ์ของงาน, พื้นที่ศึกษา)
ไฟล์ต้นฉบับของผู้ใช้ที่อยู่นอก workspace (เช่น Downloads, Drive) ไม่ถูกแตะ — แค่เอาออกจากทะเบียน
"""
import shutil
from pathlib import Path

from . import basedata, db, dsinfo
from .config import DIRS

OWNED = ('database', 'derived', 'maps', 'aoi')       # โฟลเดอร์ใน workspace ที่แอปเป็นเจ้าของไฟล์


def _owned(p):
    """path อยู่ในโฟลเดอร์ที่แอปสร้างเอง → ลบได้ ; คืนโฟลเดอร์ระดับบนสุดที่ครอบอยู่ หรือ None"""
    try:
        p = Path(p).resolve()
    except OSError:
        return None
    for k in OWNED:
        root = DIRS[k].resolve()
        if root in p.parents:
            return root
    return None


def _size(p):
    p = Path(p)
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob('*') if f.is_file()) if p.is_dir() else 0


def _ds_files(d):
    """ไฟล์ของชุดข้อมูลที่จะลบถาวร: (โฟลเดอร์ทั้งก้อน หรือ None, รายการไฟล์)"""
    if d['kind'] == 'link':
        return None, []
    paths = {d['path'], d.get('read_path') or d['path']}
    files = set()
    for p in paths:
        if not p or not _owned(p):
            continue
        try:
            files.update(Path(f) for f in dsinfo.related_files(p))
        except Exception:
            files.add(Path(p))
        stem = Path(p).with_suffix('')
        for extra in (Path(p).with_suffix('.qml'), Path(str(p) + '.aux.xml'), Path(str(p) + '.ovr'), Path(f'{stem}_legend.png')):
            files.add(extra)
    files = {f for f in files if f.exists() and _owned(f)}
    if not files:
        return None, []
    # โฟลเดอร์ของงาน/สำเนา (ระดับแรกใต้ database/derived/maps) ที่ไม่มีชุดข้อมูลอื่นใช้ → ลบทั้งโฟลเดอร์ (lineage, csv, legend ฯลฯ)
    f0 = next(iter(files)).resolve()
    root = _owned(f0)
    top = root / f0.relative_to(root).parts[0] if len(f0.relative_to(root).parts) > 1 else None
    if top is not None:
        others = [o for o in db.query('SELECT id, path, read_path FROM datasets WHERE id != ?', (d['id'],))
                  if any(q and (top in Path(q).resolve().parents) for q in (o['path'], o['read_path']))]
        if not others:
            return top, sorted(files)
    return None, sorted(files)


def _preview_cache(d):
    out = []
    if d.get('preview_path'):
        out.append(Path(d['preview_path']))
    sp = (d.get('stats') or {}).get('sample_path')
    if sp:
        out.append(Path(sp))
    return [p for p in out if p.exists() and DIRS['cache'].resolve() in p.resolve().parents]


def describe(d):
    """ลบถาวรแล้วจะเกิดอะไรกับไฟล์ — ให้หน้าเว็บบอกก่อนกด"""
    if d['kind'] == 'link':
        return dict(action='unlink', note='ลิงก์ — เอาออกจากทะเบียน (ไม่มีไฟล์ในเครื่อง)', bytes=0)
    top, files = _ds_files(d)
    if top is not None:
        return dict(action='delete', note='ลบไฟล์ใน workspace (ทั้งโฟลเดอร์ผลลัพธ์)', bytes=_size(top), path=str(top))
    if files:
        return dict(action='delete', note=f'ลบ {len(files)} ไฟล์ใน workspace', bytes=sum(f.stat().st_size for f in files), path=str(files[0]))
    return dict(action='unlink', note='ไฟล์ต้นฉบับอยู่นอก workspace — ไม่ลบไฟล์ แค่เอาออกจากทะเบียน', bytes=0, path=d['path'])


def move_dataset(d):
    db.update('datasets', d['id'], trashed_at=db.now())
    if d['kind'] == 'link':
        basedata.mark_removed(d['path'])                     # ข้อมูลพื้นฐานที่ผู้ใช้ลบ → ไม่เพิ่มกลับเอง


def restore_dataset(d):
    db.update('datasets', d['id'], trashed_at=None)
    if d['kind'] == 'link' and basedata.is_base(d['path']):
        basedata.unmark_removed(d['path'])


def purge_dataset(d):
    from . import tiles
    info = describe(d)
    top, files = _ds_files(d)
    for p in {d.get('read_path'), d['path'], d.get('preview_path')} - {None}:
        tiles.drop_pool(p)
    freed = 0
    if top is not None:
        freed = _size(top)
        shutil.rmtree(top, ignore_errors=True)
    else:
        for f in files:
            try:
                freed += f.stat().st_size
                f.unlink()
            except OSError:
                pass
    for f in _preview_cache(d):
        try:
            freed += f.stat().st_size
            f.unlink()
        except OSError:
            pass
    db.delete('datasets', d['id'])
    return dict(info, freed=freed)


def purge_aoi(a):
    freed = 0
    p = Path(a['path']) if a.get('path') else None
    if p and p.exists() and _owned(p):
        freed = p.stat().st_size
        p.unlink()
    db.delete('aoi', a['id'])
    basedata.aoi_removed(a)                     # พื้นที่ศึกษาพื้นฐาน (เช่น ประเทศไทย) → ไม่สร้างกลับเอง
    return dict(freed=freed)


def items():
    ds = db.query('SELECT * FROM datasets WHERE trashed_at IS NOT NULL ORDER BY trashed_at DESC')
    aois = db.query('SELECT * FROM aoi WHERE trashed_at IS NOT NULL ORDER BY trashed_at DESC')
    out = [dict(kind='dataset', id=d['id'], name=d['name'], type=d['kind'], role=d.get('role'), trashed_at=d['trashed_at'], purge=describe(d))
           for d in ds]
    out += [dict(kind='aoi', id=a['id'], name=a['name'], type='aoi', trashed_at=a['trashed_at'],
                 purge=dict(action='delete', note='ลบไฟล์ขอบเขตพื้นที่ศึกษาใน workspace', bytes=_size(a['path']) if a.get('path') else 0))
            for a in aois]
    out.sort(key=lambda x: x['trashed_at'], reverse=True)
    return out


def count():
    return sum(db.query(f'SELECT COUNT(*) AS n FROM {t} WHERE trashed_at IS NOT NULL')[0]['n'] for t in ('datasets', 'aoi'))
