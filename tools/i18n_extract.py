# -*- coding: utf-8 -*-
"""ดึงข้อความภาษาไทยที่แสดงในหน้าเว็บ + ข้อความจากตัวประมวลผล → tools/i18n/th_fragments.txt (ไว้แปล)

ตัวแปลในหน้าเว็บ (web/i18n.js) แทนข้อความแบบ "ชิ้นย่อยที่ยาวสุดก่อน" ในทุกโหนดข้อความ
→ ชิ้นต้องตรงกับที่ปรากฏบนจอ: ตัดตามแท็ก HTML, ${...} ของ template และ {...} ของ f-string

    python tools/i18n_extract.py           # เขียนรายการชิ้นที่ยังไม่มีคำแปลใน web/i18n_en.js
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TH = re.compile(r'[฀-๿]')
WEB = ['web/app.js', 'web/ai.js', 'web/hub.js', 'web/report.js', 'web/config.js', 'web/setup.js', 'web/index.html']
PY = sorted((ROOT / 'app').glob('*.py'))
FRAG = re.compile(r"[^<>`'\"{}$\n|\\]*[฀-๿][^<>`'\"{}$\n|\\]*")


def clean(s):
    return s.strip().strip(':·—,;=+').strip()


def web_frags():
    out = set()
    for f in WEB:
        t = (ROOT / f).read_text(encoding='utf-8')
        t = re.sub(r'^\s*//.*$', '', t, flags=re.M)
        t = re.sub(r'(?<=[;,)}\]{\s])\s+//\s.*$', '', t, flags=re.M)      # คอมเมนต์ต่อท้ายบรรทัด (// ตามด้วยเว้นวรรค — ไม่ใช่ https://)
        t = re.sub(r'/\*.*?\*/', '', t, flags=re.S)
        t = re.sub(r'<!--.*?-->', '', t, flags=re.S)
        for m in FRAG.finditer(t):
            s = clean(m.group())
            if TH.search(s) and not s.startswith('#'):
                out.add(s)
    return out


def py_frags():
    """ข้อความในโค้ด Python ที่อาจขึ้นจอ (error/คำเตือน/ป้าย) — ใช้ AST: ข้าม docstring และคอมเมนต์"""
    import ast
    out = set()
    for f in PY:
        tree = ast.parse(f.read_text(encoding='utf-8'))
        docs = set()
        for n in ast.walk(tree):
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body \
                    and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], 'value', None), ast.Constant):
                docs.add(id(n.body[0].value))
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs and TH.search(n.value):
                for line in n.value.split('\n'):
                    for part in re.split(r'\{[^{}]*\}', line):
                        s = clean(part)
                        if TH.search(s):
                            out.add(s)
    return out


def known():
    p = ROOT / 'web' / 'i18n_en.js'
    if not p.exists():
        return {}
    t = p.read_text(encoding='utf-8')
    return json.loads(t[t.index('{'):t.rindex('}') + 1])


if __name__ == '__main__':
    k = known()
    w, py = web_frags(), py_frags()
    todo = sorted((w | py) - set(k), key=lambda s: (-len(s), s))
    d = ROOT / 'tools' / 'i18n'
    d.mkdir(exist_ok=True)
    (d / 'th_fragments.txt').write_text('\n'.join(todo), encoding='utf-8')
    print(f'web {len(w):,} · server {len(py):,} · มีคำแปลแล้ว {len(k):,} · ยังไม่แปล {len(todo):,} → tools/i18n/th_fragments.txt')
