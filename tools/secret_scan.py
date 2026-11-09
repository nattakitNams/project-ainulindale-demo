# สแกนความลับก่อนขึ้น GitHub — แสดงเฉพาะ "เจอ/ไม่เจอ" และตำแหน่ง ไม่พิมพ์ค่าความลับ
#     python tools/secret_scan.py   (รันก่อน commit ทุกครั้ง)
import base64
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ไฟล์ที่ .gitignore จะกันไว้ (ตรวจแยก)
IGNORED = re.compile(r'(^|\\)(workspace|dist|python|__pycache__|tools\\cache)(\\|$)|engine_token\.txt$|settings\.json$|\.installed\.json$|\.zip$|\.env$|\.pyc$')
files = [p for p in ROOT.rglob('*') if p.is_file()]
pub = [p for p in files if not IGNORED.search(str(p.relative_to(ROOT)))]
print(f'ไฟล์ทั้งหมด {len(files)} · จะขึ้น GitHub {len(pub)} · ถูกกันไว้ {len(files) - len(pub)}')

# 1) ค่าความลับจริงในเครื่อง
real = {}
tok = ROOT / 'engine_token.txt'
if tok.exists():
    real['engine_token (โทเคนจับคู่)'] = tok.read_text(encoding='utf-8').strip()
from app import vault  # noqa: E402
vault.PATH = ROOT / 'workspace' / 'secrets.json'
for e in vault.listing():
    try:
        real[f'vault:{e["name"]}'] = vault.get(e['id'])
    except Exception as ex:
        print('ถอดรหัส vault ไม่ได้', e['name'], ex)
for k, v in list(real.items()):
    if v and len(v) >= 8:
        real[k + ' (base64)'] = base64.b64encode(v.encode()).decode()
print(f'\n[1] ค่าความลับจริงที่ตรวจ: {len([k for k in real if "base64" not in k])} รายการ ({", ".join(k for k in real if "base64" not in k)})')

# 2) รูปแบบคีย์ที่รู้จัก
PAT = {
    'GitHub token': r'gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,}',
    'AWS key': r'AKIA[0-9A-Z]{16}',
    'Google API key': r'AIza[0-9A-Za-z_\-]{35}',
    'OpenAI/Anthropic key': r'sk-(?:ant-)?[A-Za-z0-9_\-]{20,}',
    'Slack token': r'xox[abprs]-[A-Za-z0-9\-]{10,}',
    'Private key': r'-----BEGIN [A-Z ]*PRIVATE KEY-----',
    'JWT': r'eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}',
    'URL มี token/key': r'[?&](?:token|access_token|api_?key|key|sig|signature|password)=[A-Za-z0-9_\-.%]{8,}',
    'กำหนดค่าความลับในโค้ด': r'''(?i)\b(?:api[_-]?key|apikey|secret|client[_-]?secret|password|passwd|access[_-]?token|auth[_-]?token|bearer)\b\s*[:=]\s*['"][A-Za-z0-9_\-./+=]{12,}['"]''',
    'Authorization header ค่าจริง': r'(?i)authorization["\']?\s*[:=]\s*["\'](?:bearer|basic|token)\s+[A-Za-z0-9_\-.=+/]{12,}',
}
# 3) ข้อมูลภายใน
INTERNAL = {
    'อีเมล': r'[A-Za-z0-9._%+\-]+@(?!users\.noreply\.github\.com)[A-Za-z0-9.\-]+\.[a-z]{2,}',
    'path ส่วนตัว (C:\\Users\\…)': r'C:\\\\?Users\\\\?[A-Za-z]',
    'path ข้อมูล (My Drive)': r'My Drive',
}
# รูปแบบเฉพาะเครื่อง/องค์กร (ชื่อเครื่อง, โฟลเดอร์ส่วนตัว ฯลฯ) → ใส่ใน tools/secret_scan.local.txt บรรทัดละ regex (ไฟล์นี้ไม่ขึ้น GitHub)
_local = Path(__file__).with_name('secret_scan.local.txt')
if _local.exists():
    for i, line in enumerate(_local.read_text(encoding='utf-8').splitlines()):
        if line.strip() and not line.startswith('#'):
            INTERNAL[f'รูปแบบเฉพาะเครื่อง #{i + 1}'] = line.strip()


def entropy(s):
    from collections import Counter
    c = Counter(s)
    return -sum(n / len(s) * math.log2(n / len(s)) for n in c.values())


hits, internal, env_like = [], {}, []
for p in pub:
    rel = str(p.relative_to(ROOT))
    if p.suffix.lower() in ('.png', '.jpg', '.ico', '.zip', '.db'):
        continue
    try:
        t = p.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        t = p.read_text(encoding='latin-1')
    t_noimg = re.sub(r'data:image/[a-z]+;base64,[A-Za-z0-9+/=]+', '', t)
    for name, v in real.items():
        if v and v in t:
            hits.append((rel, 'ค่าความลับจริง: ' + name))
    for name, rx in PAT.items():
        for m in re.finditer(rx, t_noimg):
            ln = t_noimg[:m.start()].count('\n') + 1
            hits.append((rel, f'{name} (บรรทัด {ln}): {m.group(0)[:12]}…'))
    # สตริงยาวที่สุ่มสูง (อาจเป็นคีย์) ในเครื่องหมายคำพูด
    for m in re.finditer(r'''["']([A-Za-z0-9_\-+/=]{32,})["']''', t_noimg):
        s = m.group(1)
        if entropy(s) > 4.3 and not re.fullmatch(r'[a-f0-9]+', s):
            ln = t_noimg[:m.start()].count('\n') + 1
            hits.append((rel, f'สตริงสุ่มยาว (บรรทัด {ln}) {s[:8]}… — ตรวจด้วยตา'))
    for name, rx in INTERNAL.items():
        n = len(re.findall(rx, t))
        if n:
            internal.setdefault(rel, []).append(f'{name}×{n}')
    if re.search(r'(?im)^\s*[A-Z][A-Z0-9_]{2,}\s*=\s*\S+', t) and p.suffix in ('', '.env', '.ini', '.cfg', '.txt'):
        env_like.append(rel)

print('\n[2] ความลับ / คีย์ ในไฟล์ที่จะขึ้น GitHub:')
print('   ไม่พบ ✔' if not hits else '\n'.join(f'   ✘ {f}: {w}' for f, w in hits))
print('\n[3] ไฟล์ลักษณะ .env / ค่าตั้งลับ:', env_like or 'ไม่พบ ✔')
print('\n[4] ข้อมูลภายใน (ไม่ใช่ความลับ แต่ควรตัดสินใจก่อนเปิดสาธารณะ):')
for f, w in sorted(internal.items()):
    print(f'   • {f}: {", ".join(w)}')
print('\n[5] ไฟล์ที่ถูกกันไว้ (ห้ามขึ้น):')
for p in sorted(set(str(p.relative_to(ROOT)).split('\\')[0] for p in files if IGNORED.search(str(p.relative_to(ROOT))))):
    print('   -', p)
