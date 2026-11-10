# -*- coding: utf-8 -*-
"""เอกสารที่ผู้ช่วยเขียน (แคตาล็อก ตาราง ระเบียบวิธี ร่างรายงาน) — เก็บเป็นไฟล์แทนการเทข้อความยาวในแชต

ปัญหาที่แก้: คำตอบยาวหลายตาราง × 10 แถว ทำให้ผู้ใช้หลงในแชต และของที่ได้ไม่ถูกเก็บเป็นชิ้นงาน
→ ผู้ช่วย save_document (markdown) → workspace/ai_docs/ · แชตแสดงสรุปสั้น + การ์ดเปิด/ดาวน์โหลด · เปิดเป็นหน้า HTML อ่านง่าย (ตารางจริง)
· เขียนชื่อเดิมซ้ำ = เวอร์ชันใหม่ของเอกสารเดิม (ไม่ซ้อนไฟล์)"""
import html
import json
import re
from datetime import datetime

from .config import WORKSPACE

DIR = WORKSPACE / 'ai_docs'


def _slug(t):
    s = re.sub(r'[^0-9A-Za-zก-๙]+', '_', t or 'doc').strip('_')
    return (s or 'doc')[:60]


def save(title, markdown, chat_id=None):
    if not (markdown or '').strip():
        raise ValueError('เนื้อหาว่าง')
    DIR.mkdir(parents=True, exist_ok=True)
    name = _slug(title) + '.md'
    p = DIR / name
    ver = 1
    meta_p = DIR / (name + '.json')
    if meta_p.exists():
        try:
            ver = json.loads(meta_p.read_text(encoding='utf-8')).get('version', 0) + 1
        except ValueError:
            pass
    p.write_text(markdown, encoding='utf-8')
    meta = dict(title=title, file=name, version=ver, chat_id=chat_id, updated_at=datetime.now().isoformat(timespec='seconds'),
                lines=markdown.count('\n') + 1, tables=len(re.findall(r'^\|.*\|\s*$\n^\|[-:| ]+\|\s*$', markdown, re.M)))
    meta_p.write_text(json.dumps(meta, ensure_ascii=False), encoding='utf-8')
    return meta


def all_():
    if not DIR.exists():
        return []
    out = []
    for m in DIR.glob('*.md.json'):
        try:
            out.append(json.loads(m.read_text(encoding='utf-8')))
        except ValueError:
            pass
    return sorted(out, key=lambda x: x.get('updated_at') or '', reverse=True)


def path(name):
    p = DIR / name
    if p.suffix != '.md' or p.parent != DIR or not p.exists():
        raise FileNotFoundError(name)
    return p


def _inline(s):
    s = html.escape(s)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    s = re.sub(r'\[([^\]]+)\]\((https?://[^)\s]+)\)', r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    return s


def to_html(md, title):
    """markdown อย่างง่าย (หัวข้อ ตาราง รายการ ย่อหน้า ตัวหนา โค้ด) → หน้า HTML พิมพ์ได้ — ไม่รัน HTML จากเนื้อหา"""
    L, out, i = md.replace('\r', '').split('\n'), [], 0
    while i < len(L):
        ln = L[i]
        if re.match(r'^\s*\|.*\|\s*$', ln) and i + 1 < len(L) and re.match(r'^\s*\|[-:| ]+\|\s*$', L[i + 1]):
            cells = lambda r: [c.strip() for c in r.strip().strip('|').split('|')]
            out.append('<table><thead><tr>' + ''.join(f'<th>{_inline(c)}</th>' for c in cells(ln)) + '</tr></thead><tbody>')
            i += 2
            while i < len(L) and re.match(r'^\s*\|.*\|\s*$', L[i]):
                out.append('<tr>' + ''.join(f'<td>{_inline(c)}</td>' for c in cells(L[i])) + '</tr>')
                i += 1
            out.append('</tbody></table>')
            continue
        m = re.match(r'^(#{1,4})\s+(.*)', ln)
        if m:
            out.append(f'<h{len(m.group(1))}>{_inline(m.group(2))}</h{len(m.group(1))}>')
        elif re.match(r'^\s*[-*]\s+', ln):
            items = []
            while i < len(L) and re.match(r'^\s*[-*]\s+', L[i]):
                items.append(f'<li>{_inline(re.sub(r"^\s*[-*]\s+", "", L[i]))}</li>')
                i += 1
            out.append('<ul>' + ''.join(items) + '</ul>')
            continue
        elif re.match(r'^\s*\d+[.)]\s+', ln):
            items = []
            while i < len(L) and re.match(r'^\s*\d+[.)]\s+', L[i]):
                items.append(f'<li>{_inline(re.sub(r"^\s*\d+[.)]\s+", "", L[i]))}</li>')
                i += 1
            out.append('<ol>' + ''.join(items) + '</ol>')
            continue
        elif ln.strip() in ('---', '***'):
            out.append('<hr>')
        elif ln.strip():
            out.append(f'<p>{_inline(ln)}</p>')
        i += 1
    css = ('body{font-family:Sarabun,"Noto Sans Thai",Tahoma,sans-serif;max-width:1100px;margin:24px auto;padding:0 16px;color:#1d2330;line-height:1.6}'
           'table{border-collapse:collapse;width:100%;margin:10px 0;font-size:14px}th,td{border:1px solid #cfd5e3;padding:6px 8px;vertical-align:top}'
           'th{background:#eef1f8;text-align:left}h1{font-size:24px}h2{font-size:20px;margin-top:28px}code{background:#f2f3f7;padding:1px 4px;border-radius:4px}'
           '@media print{body{margin:0}}')
    return (f'<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{html.escape(title)}</title><style>{css}</style></head><body>{"".join(out)}</body></html>')
