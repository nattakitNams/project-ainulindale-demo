# -*- coding: utf-8 -*-
"""ตาราง attribute ของชุดเวกเตอร์ (รวมหกเหลี่ยมและแผนที่ไบแวเรียตแบบเวกเตอร์) สำหรับหน้าคลังข้อมูล

- อ่าน attribute ทั้งชั้นครั้งเดียว (ไม่อ่านรูป) เก็บในหน่วยความจำ LRU ตาม fingerprint + encoding
  → ค้นหา / เรียง / แบ่งหน้า เร็วโดยไม่อ่านไฟล์ซ้ำ ; ดัชนีของตาราง = FID ของ OGR (ใช้ดึงรูปทีละ feature)
- ชั้นที่ feature เกิน BIG (หลายล้าน) → อ่านทีละหน้าจากไฟล์ (skip/max_features) ค้นหา/เรียงไม่ได้ (กันหน่วยความจำเต็ม)
- รูปของ feature เดียว → WGS84 + ลดจุดตามขนาดกรอบ (แสดงผลเท่านั้น)"""
import math
import threading
from collections import OrderedDict

import numpy as np

from .dsinfo import read_vector

BIG = 1_500_000
_cache, _lock = OrderedDict(), threading.Lock()


def _key(ds):
    return (ds['id'], ds.get('fingerprint'), (ds.get('meta') or {}).get('encoding'))


_loading = {}                                               # key → Event ระหว่างอ่านทั้งชั้น (กันอ่านซ้ำพร้อมกัน)


def cached(ds):
    with _lock:
        return _cache.get(_key(ds))


def frame(ds):
    """DataFrame ของ attribute (index = FID) — หน่วยความจำ (LRU 4 ชั้น) → แคชดิสก์ → อ่านไฟล์ใน process แยก
    อ่านใน process แยกเพราะ OGR ถือ GIL ตลอดการอ่าน DBF ใหญ่ (y2011.shp 71,035 แถว ~18 วินาที):
    อ่านในเธรดเดียวกับเว็บ → คำขออื่นทั้งหมด (หน้าถัดไป ไทล์แผนที่) ค้างรอเกือบ 16 วินาที (วัดจริง)"""
    k = _key(ds)
    with _lock:
        if k in _cache:
            _cache.move_to_end(k)
            return _cache[k]
        ev = _loading.get(k)
        mine = ev is None
        if mine:
            ev = _loading[k] = threading.Event()
    if not mine:
        ev.wait()
        with _lock:
            if k in _cache:
                return _cache[k]
    try:
        df = _disk_load(ds)
        if df is None:
            _build_in_process(ds)
            df = _disk_load(ds)
        if df is None:                                       # process แยกล้มเหลว → อ่านตรง (ช้ากว่าแต่ได้ผล)
            df = read_vector(ds, read_geometry=False, fid_as_index=True)
            _disk_save(ds, df)
        with _lock:
            _cache[k] = df
            while len(_cache) > 4:
                _cache.popitem(last=False)
        return df
    finally:
        with _lock:
            _loading.pop(k, None)
        ev.set()


def _build_in_process(ds):
    """python -m app.attrtable <id> → เขียนแคชดิสก์ (เธรดที่รอ process ไม่ถือ GIL)"""
    import os
    import subprocess
    import sys
    from .config import ROOT
    try:
        subprocess.run([sys.executable, '-m', 'app.attrtable', str(ds['id'])], cwd=str(ROOT), timeout=1800,
                       creationflags=0x08000000 if os.name == 'nt' else 0, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print('[ตาราง attribute] process แยกล้มเหลว:', e)


def _disk_path(ds):
    """แคชบนดิสก์: อ่าน DBF ใหญ่ครั้งแรกช้า (y2011.shp 71,035 แถว ~18 วินาที เพราะ OGR แปลงข้อความทีละช่อง)
    ครั้งต่อไป (รวมหลังปิดตัวประมวลผล) โหลดจาก pickle ในไม่กี่สิบมิลลิวินาที · ชื่อไฟล์ผูก fingerprint + encoding"""
    import hashlib
    from .config import DIRS
    h = hashlib.sha1(repr(_key(ds)).encode()).hexdigest()[:16]
    return DIRS['cache'] / 'attr' / f'ds{ds["id"]}_{h}.pkl'


def _disk_load(ds):
    import pandas as pd
    p = _disk_path(ds)
    if not p.exists():
        return None
    try:
        return pd.read_pickle(p)
    except Exception:
        return None


def _disk_save(ds, df):
    p = _disk_path(ds)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        for old in p.parent.glob(f'ds{ds["id"]}_*.pkl'):        # รุ่นเก่าของชุดเดียวกัน (ไฟล์/encoding เปลี่ยน) ลบทิ้ง
            if old != p:
                old.unlink(missing_ok=True)
        tmp = p.with_suffix('.tmp')
        df.to_pickle(tmp)
        tmp.replace(p)
    except Exception as e:
        print('[ตาราง attribute] บันทึกแคชไม่ได้:', e)


def warm(ds):
    """เริ่มอ่านทั้งชั้นเบื้องหลัง (ไฟล์ใหญ่บน Google Drive อาจใช้หลายวินาที) — หน้าแรกไม่ต้องรอ"""
    k = _key(ds)
    with _lock:
        if k in _cache or k in _loading:
            return
    threading.Thread(target=lambda: _safe(frame, ds), daemon=True).start()


def _safe(fn, *a):
    try:
        fn(*a)
    except Exception as e:
        print('[ตาราง attribute]', e)


def _cell(v):
    if v is None:
        return None
    if isinstance(v, (float, np.floating)):
        return None if math.isnan(v) else (int(v) if float(v).is_integer() and abs(v) < 1e15 else float(v))
    if isinstance(v, (np.bool_, bool)):                     # ก่อน int — bool เป็นคลาสย่อยของ int
        return bool(v)
    if isinstance(v, (int, np.integer)):                     # int ของ Python (iterrows ของหน้าแรก) ด้วย — เดิมกลายเป็นข้อความ
        return int(v)
    return str(v)


def _fields(ds, df=None):
    m = ds.get('meta') or {}
    if m.get('fields'):
        return [dict(name=f['name'], type=f.get('type', '')) for f in m['fields']]
    return [dict(name=c, type=str(df[c].dtype)) for c in df.columns] if df is not None else []


def table(ds, offset=0, limit=50, q='', field='', sort='', desc=False, fid=None):
    """หนึ่งหน้าของตาราง → dict(fields, rows=[[fid, ค่า…]], total, matched, searchable)"""
    m = ds.get('meta') or {}
    total = int(m.get('features') or 0)
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    big = total > BIG
    if (big and not fid) or (cached(ds) is None and not q and not sort and fid in (None, '')):
        # อ่านเฉพาะหน้านี้จากไฟล์ (เร็ว) · ชั้นไม่ใหญ่เกิน → อ่านทั้งชั้นเบื้องหลังไว้ค้นหา/เรียง
        df = read_vector(ds, read_geometry=False, fid_as_index=True, skip_features=offset, max_features=limit)
        if not big:
            warm(ds)                                         # หลังอ่านหน้าแรกเสร็จ — ไม่ให้แย่งกันตอนเริ่ม
        flds = [f for f in _fields(ds, df) if f['name'] in df.columns]
        return dict(fields=flds, rows=[[int(i)] + [_cell(r.get(f['name'])) for f in flds] for i, r in df.iterrows()],
                    total=total, matched=total, offset=offset, searchable=not big, warming=not big,
                    note=f'ชั้นนี้มี {total:,} feature — ค้นหา/เรียงไม่ได้ เลื่อนดูทีละหน้าเท่านั้น' if big else None)
    df = frame(ds)
    flds = _fields(ds, df)
    total = len(df)
    sub = df
    if fid not in (None, ''):
        sub = df.loc[df.index == int(fid)]
    elif q:
        ql = str(q).lower()
        cols = [field] if field in df.columns else list(df.columns)
        hit = np.zeros(len(df), bool)
        for c in cols:
            hit |= df[c].astype(str).str.lower().str.contains(ql, regex=False, na=False).to_numpy()
        sub = df[hit]
    if sort in sub.columns:
        sub = sub.sort_values(sort, ascending=not desc, na_position='last', kind='stable')
    page = sub.iloc[offset:offset + limit]
    rows = [[int(i)] + [_cell(v) for v in r] for i, r in zip(page.index, page[[f['name'] for f in flds if f['name'] in page.columns]].itertuples(index=False))]
    return dict(fields=[f for f in flds if f['name'] in df.columns], rows=rows, total=total, matched=int(len(sub)),
                offset=offset, searchable=True)


def field_stats(ds, field):
    """สถิติ + กราฟของฟิลด์: ตัวเลข → ฮิสโทแกรม (log ถ้าเบ้มาก) · ข้อความ → ค่าที่พบบ่อย 15 อันดับ"""
    m = ds.get('meta') or {}
    if int(m.get('features') or 0) > BIG:
        df = read_vector(ds, read_geometry=False, columns=[field], max_features=BIG)
        note = f'คิดจาก {BIG:,} feature แรก'
    else:
        df, note = frame(ds), None
    if field not in df.columns:
        raise KeyError(field)
    s = df[field]
    n, nulls = int(len(s)), int(s.isna().sum())
    num = s.dtype.kind in 'iuf'
    if num:
        v = s.dropna().to_numpy('float64')
        v = v[np.isfinite(v)]
        out = dict(field=field, kind='number', n=n, nulls=nulls, note=note, distinct=int(np.unique(v).size) if v.size else 0)
        if not v.size:
            return out
        out.update(min=float(v.min()), max=float(v.max()), mean=float(v.mean()), median=float(np.median(v)), sum=float(v.sum()))
        out['hist'] = hist(v)
        if out['distinct'] <= 20:                           # ตัวเลขไม่กี่ค่า (รหัสไบแวเรียต, ชั้น) → นับรายค่าด้วย
            u, c = np.unique(v, return_counts=True)
            out['top'] = [dict(value=_cell(a), count=int(b)) for a, b in zip(u, c)]
        return out
    vc = s.dropna().astype(str).value_counts()
    return dict(field=field, kind='text', n=n, nulls=nulls, note=note, distinct=int(len(vc)),
                top=[dict(value=k, count=int(c)) for k, c in vc.head(15).items()])


def hist(v, bins=30):
    """ฮิสโทแกรมรูปแบบเดียวกับ /api/classes-preview (app/histo.py: เชิงเส้น / log / symlog)"""
    from . import histo
    return histo.hist(v, bins)


def feature(ds, fid):
    """รูปของ feature เดียว (WGS84, ลดจุดเพื่อแสดงผล) + กรอบ + attribute"""
    import shapely
    from shapely.geometry import mapping
    try:
        df = read_vector(ds, fids=[int(fid)], fid_as_index=True)
    except Exception:                                       # FID เกินช่วง → OGR โยน error ดิบ
        raise KeyError(fid)
    if not len(df):
        raise KeyError(fid)
    if df.crs is not None and df.crs.to_epsg() != 4326:
        df = df.to_crs(4326)
    g = df.geometry.iloc[0]
    if g is None or g.is_empty:
        return dict(fid=int(fid), geojson=None, bbox=None, attrs={k: _cell(v) for k, v in df.iloc[0].items() if k != 'geometry'})
    b = g.bounds
    tol = max(b[2] - b[0], b[3] - b[1]) / 3000                # ~3,000 จุดตามด้านยาว พอสำหรับไฮไลต์
    if shapely.get_num_coordinates(g) > 20000:
        g = shapely.simplify(g, tol, preserve_topology=False)
    return dict(fid=int(fid), geojson=mapping(g), bbox=list(b),
                attrs={k: _cell(v) for k, v in df.iloc[0].items() if k != 'geometry'})


if __name__ == '__main__':                                  # process แยก: อ่านทั้งชั้นแล้วเขียนแคชดิสก์
    import sys
    from . import db
    _d = db.get('datasets', int(sys.argv[1]))
    if _d:
        _disk_save(_d, read_vector(_d, read_geometry=False, fid_as_index=True))
