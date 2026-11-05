# -*- coding: utf-8 -*-
"""ทะเบียนข้อมูล SQLite (workspace/catalog.db) — ชุดข้อมูล / งาน / พาเลท
ใช้ได้ทั้งจากเซิร์ฟเวอร์ (หลายเธรด) และ process งาน → เปิด connection ใหม่ทุกครั้ง + WAL"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    path TEXT NOT NULL,              -- path ที่ใช้งาน (ต้นฉบับ หรือสำเนาใน database/)
    source_path TEXT,                -- path ต้นฉบับตอนนำเข้า (กรณีก๊อป)
    read_path TEXT,                  -- path ที่ใช้อ่านจริง (เช่น VRT ที่แก้ path Colab แล้ว)
    copied INTEGER DEFAULT 0,
    kind TEXT NOT NULL,              -- raster / vector
    format TEXT,
    layer TEXT,                      -- ชั้นใน GeoPackage
    fingerprint TEXT,
    meta TEXT,                       -- JSON (ดู inspect.py)
    value_type TEXT,                 -- count / density / class (raster)
    value_type_confirmed INTEGER DEFAULT 0,
    nodata_as REAL,                  -- NULL = nodata คือ "ไม่มีข้อมูล" ; ตัวเลข = นับ nodata เป็นค่านี้
    band INTEGER DEFAULT 1,
    stats TEXT,                      -- JSON สถิติ/ฮิสโทแกรม (งาน prepare)
    preview_path TEXT,
    preview_key TEXT,
    status TEXT DEFAULT 'ok',        -- ok / missing / changed
    role TEXT DEFAULT 'input',       -- input / derived / map
    job_id INTEGER,                  -- งานที่สร้างชุดนี้ (derived / map)
    added_at TEXT
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,              -- prepare / resample / bivariate / copy
    title TEXT,
    status TEXT DEFAULT 'queued',    -- queued / running / cancelling / done / failed / cancelled
    params TEXT,
    progress REAL DEFAULT 0,
    message TEXT,
    out_dir TEXT,
    log_path TEXT,
    pid INTEGER,
    result TEXT,
    error TEXT,
    created_at TEXT, started_at TEXT, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS aoi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, source TEXT, path TEXT, bbox TEXT, area_km2 REAL, created_at TEXT
);
CREATE TABLE IF NOT EXISTS palettes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT, nx INTEGER, ny INTEGER, colors TEXT, created_at TEXT
);
"""

JSON_COLS = {'meta', 'stats', 'params', 'result', 'colors', 'source', 'bbox', 'style', 'exclude_values'}

# คอลัมน์ที่เพิ่มทีหลัง (ไฟล์ catalog.db เก่าไม่มี) → ALTER TABLE ตอนเปิดแอป
MIGRATE = {
    'datasets': [('style', 'TEXT'), ('exclude_values', 'TEXT')],
    'jobs': [('eta_s', 'REAL'), ('elapsed_s', 'REAL')],
}


def now():
    return datetime.now().isoformat(timespec='seconds')


@contextmanager
def connect():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        con.execute('PRAGMA journal_mode=WAL')
        yield con
        con.commit()
    finally:
        con.close()


def init():
    with connect() as c:
        c.executescript(SCHEMA)
        for table, cols in MIGRATE.items():
            have = {r[1] for r in c.execute(f'PRAGMA table_info({table})')}
            for name, typ in cols:
                if name not in have:
                    c.execute(f'ALTER TABLE {table} ADD COLUMN {name} {typ}')


def _row(r):
    if r is None:
        return None
    d = dict(r)
    for k in JSON_COLS & d.keys():
        if d[k]:
            try:
                d[k] = json.loads(d[k])
            except ValueError:
                pass
    return d


def _enc(v):
    return json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v


def insert(table, **kw):
    kw = {k: _enc(v) for k, v in kw.items()}
    with connect() as c:
        cur = c.execute(f'INSERT INTO {table} ({",".join(kw)}) VALUES ({",".join("?" * len(kw))})', list(kw.values()))
        return cur.lastrowid


def update(table, id_, **kw):
    if not kw:
        return
    kw = {k: _enc(v) for k, v in kw.items()}
    with connect() as c:
        c.execute(f'UPDATE {table} SET {",".join(f"{k}=?" for k in kw)} WHERE id=?', [*kw.values(), id_])


def get(table, id_):
    with connect() as c:
        return _row(c.execute(f'SELECT * FROM {table} WHERE id=?', (id_,)).fetchone())


def query(sql, args=()):
    with connect() as c:
        return [_row(r) for r in c.execute(sql, args).fetchall()]


def delete(table, id_):
    with connect() as c:
        c.execute(f'DELETE FROM {table} WHERE id=?', (id_,))
