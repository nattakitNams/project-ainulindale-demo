# -*- coding: utf-8 -*-
"""โฟลเดอร์ในคลังข้อมูล (ซ้อนกันได้หลายชั้น) — จัดหมวดในแอปเท่านั้น ไม่ย้ายไฟล์จริงบนดิสก์

- ชุดข้อมูล (รวมลิงก์) อยู่ได้ 1 โฟลเดอร์ (folder_id) · NULL = ราก
- ลบโฟลเดอร์ = ของข้างใน (ชุดข้อมูล + โฟลเดอร์ย่อย) ย้ายขึ้นไปโฟลเดอร์แม่ — ไม่มีข้อมูลหาย
- ผลลัพธ์จากงาน → เข้าโฟลเดอร์เดียวกับชุดข้อมูลต้นทางชุดแรก
"""
from . import db


class FolderError(Exception):
    pass


def all_():
    return db.query('SELECT * FROM folders ORDER BY name COLLATE NOCASE')


def get(fid):
    f = db.get('folders', int(fid)) if fid is not None else None
    if fid is not None and f is None:
        raise FolderError('ไม่พบโฟลเดอร์')
    return f


def _check_name(name, parent_id, skip=None):
    name = (name or '').strip()
    if not name:
        raise FolderError('ตั้งชื่อโฟลเดอร์ก่อน')
    if len(name) > 120:
        raise FolderError('ชื่อโฟลเดอร์ยาวเกิน 120 ตัวอักษร')
    for f in all_():
        if f['parent_id'] == parent_id and f['id'] != skip and f['name'].casefold() == name.casefold():
            raise FolderError(f'มีโฟลเดอร์ชื่อ "{name}" อยู่แล้วในที่นี้')
    return name


def create(name, parent_id=None):
    parent_id = int(parent_id) if parent_id else None
    get(parent_id)
    name = _check_name(name, parent_id)
    return db.insert('folders', name=name, parent_id=parent_id, created_at=db.now())


def _descendants(fid):
    kids = {fid}
    rows = all_()
    grew = True
    while grew:
        grew = False
        for f in rows:
            if f['parent_id'] in kids and f['id'] not in kids:
                kids.add(f['id'])
                grew = True
    return kids


def update(fid, name=None, parent_id=...):
    f = get(fid)
    upd = {}
    new_parent = f['parent_id']
    if parent_id is not ...:
        new_parent = int(parent_id) if parent_id else None
        get(new_parent)
        if new_parent is not None and new_parent in _descendants(f['id']):
            raise FolderError('ย้ายโฟลเดอร์เข้าไปในตัวเอง/โฟลเดอร์ย่อยของตัวเองไม่ได้')
        upd['parent_id'] = new_parent
    if name is not None or 'parent_id' in upd:
        upd['name'] = _check_name(name if name is not None else f['name'], new_parent, skip=f['id'])
    if upd:
        db.update('folders', f['id'], **upd)
    return db.get('folders', f['id'])


def delete(fid):
    """ลบโฟลเดอร์ — ของข้างในย้ายขึ้นไปโฟลเดอร์แม่ (ชื่อซ้ำกับโฟลเดอร์ที่แม่มีอยู่แล้ว → ต่อท้ายชื่อ)"""
    f = get(fid)
    parent = f['parent_id']
    names = {x['name'].casefold() for x in all_() if x['parent_id'] == parent and x['id'] != f['id']}
    moved_f = 0
    for k in [x for x in all_() if x['parent_id'] == f['id']]:
        n, i = k['name'], 2
        while n.casefold() in names:
            n, i = f'{k["name"]} ({i})', i + 1
        names.add(n.casefold())
        db.update('folders', k['id'], parent_id=parent, name=n)
        moved_f += 1
    with db.connect() as c:
        moved_d = c.execute('UPDATE datasets SET folder_id=? WHERE folder_id=?', (parent, f['id'])).rowcount
        c.execute('DELETE FROM folders WHERE id=?', (f['id'],))
    return dict(moved_datasets=moved_d, moved_folders=moved_f, to=parent)


def move(dataset_ids=(), folder_ids=(), to=None):
    to = int(to) if to else None
    get(to)
    n = 0
    for i in dataset_ids or []:
        if db.get('datasets', int(i)):
            db.update('datasets', int(i), folder_id=to)
            n += 1
    for i in folder_ids or []:
        update(int(i), parent_id=to)
        n += 1
    return n


def assign(dataset_ids, folder_id):
    """ชุดที่เพิ่งเพิ่ม → โฟลเดอร์ที่ผู้ใช้เปิดอยู่ (ไม่มี/หาไม่เจอ → ราก)"""
    if not folder_id:
        return
    try:
        get(int(folder_id))
    except (FolderError, ValueError):
        return
    for i in dataset_ids:
        db.update('datasets', int(i), folder_id=int(folder_id))


def input_folder(params):
    """โฟลเดอร์ของชุดข้อมูลต้นทางชุดแรกของงาน (ผลลัพธ์เข้าโฟลเดอร์เดียวกัน)"""
    p = params or {}
    if p.get('folder_id'):                                   # งานระบุโฟลเดอร์ผลลัพธ์เอง (เช่น ผู้ช่วยจัดเป็น <งาน>/output)
        f = db.get('folders', int(p['folder_id']))
        if f:
            return f['id']
    cands = [p.get('dataset_id')] + list(p.get('dataset_ids') or []) + [(p.get(a) or {}).get('dataset_id') for a in ('x', 'y', 'base')] \
        + [p.get('a_id'), p.get('link_id'), p.get('zones_dataset_id')]
    for c in cands:
        if c:
            d = db.get('datasets', int(c))
            if d and d.get('folder_id'):
                return d['folder_id']
    return None
