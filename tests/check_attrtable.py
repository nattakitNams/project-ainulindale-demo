# -*- coding: utf-8 -*-
"""ตรวจตาราง attribute (app/attrtable.py) — ไม่ต้องเปิดตัวประมวลผล ใช้ GeoPackage ที่สร้างชั่วคราว

    python -m tests.check_attrtable

ครอบคลุม (1.0.43): หน้าแรกอ่านเฉพาะหน้า · ค้นหา/เรียง/ดึงด้วย FID จากแคช · สถิติฟิลด์ตัวเลข/ข้อความ
· รูป feature เดียวแปลงเป็น WGS84 · FID ที่ไม่มี → KeyError (ไม่ใช่ error ดิบของ OGR) · ชั้นใหญ่เกิน BIG → ค้นหาไม่ได้"""
import tempfile
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

from app import attrtable as A

FAIL = []


def check(name, cond, detail=''):
    print(('ok   ' if cond else 'FAIL ') + name + (f'  [{detail}]' if detail else ''))
    if not cond:
        FAIL.append(name)


# ไม่ใช้ process แยก/แคชดิสก์ของ workspace จริง → อ่านตรงใน process นี้
A._build_in_process = lambda ds: None
A._disk_load = lambda ds: None
A._disk_save = lambda ds, df: None

tmp = Path(tempfile.mkdtemp())
names = ['Bangkok', 'Sing Buri', 'Nonthaburi', 'Chiang Mai', 'Phuket', 'Singapore-ish']
g = gpd.GeoDataFrame(dict(name=names, code=[10, 17, 12, 50, 83, 99], pop=[5.5e6, 2.1e5, 1.2e6, 1.8e6, 4.2e5, None]),
                     geometry=[box(100 + i * 0.1, 13 + i * 0.1, 100.05 + i * 0.1, 13.05 + i * 0.1) for i in range(6)],
                     crs=4326).to_crs(32647)
p = tmp / 't.gpkg'
g.to_file(p, layer='t')
fields = [dict(name='name', type='str'), dict(name='code', type='int64'), dict(name='pop', type='float64')]
ds = dict(id=99001, path=str(p), layer='t', fingerprint='x', meta=dict(features=6, fields=fields))

r = A.table(ds, limit=4)
check('หน้าแรกอ่านเฉพาะหน้า (ยังไม่มีแคช)', len(r['rows']) == 4 and r['total'] == 6 and r.get('warming'), r['rows'][0])
check('หน้าแรก: เลขจำนวนเต็มเป็นตัวเลข ไม่ใช่ข้อความ', r['rows'][0][2] == 10 and isinstance(r['rows'][0][2], int), r['rows'][0])
fid0 = r['rows'][0][0]
A.frame(ds)                                                   # รอให้อ่านทั้งชั้นเสร็จ (warm อาจกำลังอ่านอยู่)
r = A.table(ds, q='sing')
check('ค้นหาไม่สนตัวพิมพ์ใหญ่-เล็ก', sorted(x[1] for x in r['rows']) == ['Sing Buri', 'Singapore-ish'] and r['matched'] == 2)
r = A.table(ds, q='sing', field='code')
check('ค้นหาเฉพาะฟิลด์', r['matched'] == 0)
r = A.table(ds, sort='code', desc=True, limit=2)
check('เรียงมากไปน้อย', [x[2] for x in r['rows']] == [99, 83])
r = A.table(ds, sort='pop')
check('ค่าว่างอยู่ท้ายเมื่อเรียง', r['rows'][-1][3] is None)
r = A.table(ds, fid=fid0)
check('ดึงแถวเดียวด้วย FID', r['matched'] == 1 and r['rows'][0][0] == fid0)

s = A.field_stats(ds, 'code')
check('สถิติฟิลด์ตัวเลข', s['kind'] == 'number' and s['min'] == 10 and s['max'] == 99 and len(s['top']) == 6)
s = A.field_stats(ds, 'pop')
check('นับค่าว่าง', s['nulls'] == 1 and s['n'] == 6)
s = A.field_stats(ds, 'name')
check('ฟิลด์ข้อความ = นับรายค่า', s['kind'] == 'text' and s['distinct'] == 6)
try:
    A.field_stats(ds, 'nope'); check('ฟิลด์ที่ไม่มี → KeyError', False)
except KeyError:
    check('ฟิลด์ที่ไม่มี → KeyError', True)

f = A.feature(ds, fid0)
b = f['bbox']
check('รูป feature แปลงกลับเป็น WGS84', abs(b[0] - 100) < 1e-6 and abs(b[1] - 13) < 1e-6 and f['geojson']['type'] == 'Polygon', b)
try:
    A.feature(ds, 999999); check('FID ที่ไม่มี → KeyError', False)
except KeyError:
    check('FID ที่ไม่มี → KeyError', True)

h = A.hist([0] * 50 + [1] * 300 + [2] * 100 + [5000, 8000, 12000, 30000, 90000] * 3)
check('ฮิสโทแกรมเบ้มาก → log + นับศูนย์แยก', h['log'] and h['zeros'] == 50)

old = A.BIG
A.BIG = 3                                                     # จำลองชั้นใหญ่
big = dict(ds, id=99002, meta=dict(features=6, fields=fields))
r = A.table(big, offset=2, limit=2)
check('ชั้นใหญ่: อ่านทีละหน้า ค้นหาไม่ได้', len(r['rows']) == 2 and not r['searchable'] and r['note'])
A.BIG = old

print('\nผ่านทั้งหมด' if not FAIL else f'\nไม่ผ่าน {len(FAIL)} ข้อ: {FAIL}')
raise SystemExit(1 if FAIL else 0)
