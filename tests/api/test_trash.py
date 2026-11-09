# ทดสอบถังขยะผ่าน API จริง (workspace ทดสอบ)
import time
from pathlib import Path

import requests
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, ENGINE, NTL, VECTORS, need, session, wait_engine  # noqa: E402


B = ENGINE
s = session
wait_engine()
ok = []


def api(path, body=None, method=None):
    r = s.request(method or ('POST' if body is not None else 'GET'), B + path, json=body, timeout=120)
    j = r.json()
    assert r.ok, f'{path}: {j}'
    return j


def check(name, cond, extra=''):
    ok.append(bool(cond))
    print(('✔' if cond else '✘'), name, extra)


ds = api('/api/datasets')
mp = [d for d in ds if d.get('role') == 'map'][-1]
ext = [d for d in ds if d['name'] == 'wp_bkk'][-1]
base = [d for d in ds if d['name'] == 'L05_Tambon'][-1]
mp_files = Path(api(f'/api/datasets/{mp["id"]}')['path'])
ext_path = Path(ext['path'])
n0 = api('/api/trash')['count']

# 1) ย้ายเข้าถัง → หายจากรายการ ไฟล์ยังอยู่
for d in (mp, ext, base):
    api(f'/api/datasets/{d["id"]}', method='DELETE')
ids = {d['id'] for d in api('/api/datasets')}
check('ย้ายเข้าถัง → หายจากคลัง', not ({mp['id'], ext['id'], base['id']} & ids))
check('ไฟล์ยังอยู่ระหว่างอยู่ในถัง', mp_files.exists() and ext_path.exists())
tr = api('/api/trash')
check('ถังขยะนับถูก', tr['count'] == n0 + 3, tr['count'])
desc = {it['id']: it['purge'] for it in tr['items'] if it['kind'] == 'dataset'}
check('แผนที่ผลลัพธ์ → จะลบไฟล์ใน workspace', desc[mp['id']]['action'] == 'delete', desc[mp['id']]['note'])
check('ไฟล์ต้นฉบับนอก workspace → ไม่ลบไฟล์', desc[ext['id']]['action'] == 'unlink', desc[ext['id']]['note'])
check('ลิงก์ → ไม่มีไฟล์', desc[base['id']]['action'] == 'unlink')
check('ข้อมูลพื้นฐานในถัง → ไม่นับว่ามีอยู่', not [i for i in api('/api/basedata')['items'] if i['name'] == 'L05_Tambon'][0]['present'])

# 2) กู้คืน
api(f'/api/trash/dataset/{mp["id"]}/restore', {})
api(f'/api/trash/dataset/{base["id"]}/restore', {})
ids = {d['id'] for d in api('/api/datasets')}
check('กู้คืน → กลับมาในคลัง', mp['id'] in ids and base['id'] in ids)
check('กู้คืนข้อมูลพื้นฐาน → present', [i for i in api('/api/basedata')['items'] if i['name'] == 'L05_Tambon'][0]['present'])

# 3) ลบถาวร
api(f'/api/datasets/{mp["id"]}', method='DELETE')
r = api(f'/api/trash/dataset/{mp["id"]}', method='DELETE')
check('ลบถาวรแผนที่ → ไฟล์หาย', not mp_files.exists() and not mp_files.parent.exists(), f"freed {r.get('freed'):,} B")
r = api(f'/api/trash/dataset/{ext["id"]}', method='DELETE')
check('ลบถาวรไฟล์นอก workspace → ไฟล์ต้นฉบับยังอยู่', ext_path.exists(), str(ext_path))

# 4) พื้นที่ศึกษา
a = api('/api/aoi', dict(name='ทดสอบถังขยะ', coords='100.45 13.70\n100.60 13.70\n100.60 13.82'))
aid = a['id']
ap = Path(a['aoi']['path'])
api(f'/api/aoi/{aid}', method='DELETE')
check('AOI → ถังขยะ ไฟล์ยังอยู่', aid not in {x['id'] for x in api('/api/aoi')} and ap.exists())
api(f'/api/trash/aoi/{aid}/restore', {})
check('AOI กู้คืน', aid in {x['id'] for x in api('/api/aoi')})
api(f'/api/aoi/{aid}', method='DELETE')
r = api('/api/trash', method='DELETE')
check('ล้างถังขยะ', api('/api/trash')['count'] == 0 and not ap.exists(), f"{r['removed']} รายการ")
check('ข้อมูลอื่นยังครบ', len(api('/api/datasets')) >= 3)
print(f'\nผล: ผ่าน {sum(ok)}/{len(ok)}')
sys.exit(0 if all(ok) else 1)
