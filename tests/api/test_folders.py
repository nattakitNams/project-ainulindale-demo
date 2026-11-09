# ทดสอบโฟลเดอร์ในคลังข้อมูลผ่าน API จริง
import time

import requests
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, ENGINE, NTL, VECTORS, need, session, wait_engine  # noqa: E402


B = ENGINE
wait_engine()
s = session
for _ in range(30):
    try:
        s.get(B + '/api/engine/hello', timeout=2)
        break
    except requests.RequestException:
        time.sleep(1)
ok = []


def api(path, body=None, method=None):
    r = s.request(method or ('POST' if body is not None else 'GET'), B + path, json=body, timeout=600)
    return r.status_code, r.json()


def check(name, cond, extra=''):
    ok.append(bool(cond))
    print(('✔' if cond else '✘'), name, extra)


def ds(i):
    return api(f'/api/datasets/{i}')[1]


c, a = api('/api/folders', dict(name='น้ำท่วม 2567'))
A = a['id']
c, b = api('/api/folders', dict(name='ภาคกลาง', parent_id=A))
Bf = b['id']
check('สร้างโฟลเดอร์ + โฟลเดอร์ย่อย', A and Bf and b['folder']['parent_id'] == A)
c, e = api('/api/folders', dict(name='น้ำท่วม 2567'))
check('ชื่อซ้ำในที่เดียวกัน → ปฏิเสธ', c == 400, e.get('error'))
c, e = api(f'/api/folders/{A}', dict(parent_id=Bf), 'PATCH')
check('ย้ายโฟลเดอร์เข้าลูกตัวเอง → ปฏิเสธ', c == 400, e.get('error'))

all_ = api('/api/datasets')[1]
wp = [d for d in all_ if d['name'] == 'wp_bkk'][-1]
lu = [d for d in all_ if d['name'] == 'LU_CMI_2553'][-1]
api('/api/folders/move', dict(dataset_ids=[wp['id']], to=Bf))
api('/api/folders/move', dict(dataset_ids=[lu['id']], to=A))
check('ย้ายชุดข้อมูลเข้าโฟลเดอร์', ds(wp['id'])['folder_id'] == Bf and ds(lu['id'])['folder_id'] == A)

# ผลลัพธ์จากงานเข้าโฟลเดอร์เดียวกับต้นทาง
opts = api(f'/api/res-options?ids={wp["id"]}')[1]['options']
coarse = [o for o in opts if o['px'] < max(x['px'] for x in opts if x['is_source'])][0]['value']
c, j = api('/api/jobs', dict(kind='resample', params=dict(dataset_id=wp['id'], target_res=coarse)))
for _ in range(120):
    jj = api(f'/api/jobs/{j["job"]}')[1]
    jj = jj.get('job', jj)
    if jj['status'] in ('done', 'failed'):
        break
    time.sleep(1)
out = jj['result']['dataset_id'] if jj['status'] == 'done' else None
check('ผลลัพธ์งานเข้าโฟลเดอร์เดียวกับต้นทาง', out and ds(out)['folder_id'] == Bf, f'งาน {jj["status"]}')

# เพิ่มไฟล์ตอนอยู่ในโฟลเดอร์
p = str(need(DATA, 'AINU_TEST_DATA') / 'vnl_edge.tif')
c, r = api('/api/datasets', dict(paths=[p], folder_id=A))
nid = (r.get('added') or [None])[0]
check('เพิ่มไฟล์ใหม่เข้าโฟลเดอร์ที่เปิดอยู่', nid and ds(nid)['folder_id'] == A, str(r.get('errors') or ''))

# แก้ชื่อ + ลบโฟลเดอร์แม่ → ลูกและชุดข้อมูลย้ายขึ้นราก ไม่หาย
c, f = api(f'/api/folders/{Bf}', dict(name='ภาคกลาง (กทม.)'), 'PATCH')
check('แก้ชื่อโฟลเดอร์', f['folder']['name'] == 'ภาคกลาง (กทม.)')
c, d = api(f'/api/folders/{A}', method='DELETE')
fol = api('/api/folders')[1]['folders']
check('ลบโฟลเดอร์ → ของข้างในย้ายขึ้นแม่ (ราก) ไม่หาย',
      ds(lu['id'])['folder_id'] is None and ds(nid)['folder_id'] is None and [x for x in fol if x['id'] == Bf][0]['parent_id'] is None and ds(wp['id'])['folder_id'] == Bf,
      str(d))
# เก็บกวาด: ย้ายทุกอย่างกลับราก ลบโฟลเดอร์ทดสอบ
api('/api/folders/move', dict(dataset_ids=[wp['id'], out], to=None))
api(f'/api/folders/{Bf}', method='DELETE')
if nid:
    api(f'/api/datasets/{nid}', method='DELETE')
if out:
    api(f'/api/datasets/{out}', method='DELETE')
print(f'\nผล: ผ่าน {sum(ok)}/{len(ok)}')
sys.exit(0 if all(ok) else 1)
