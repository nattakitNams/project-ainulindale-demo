# -*- coding: utf-8 -*-
"""แผนงานของบทสนทนากับผู้ช่วย AI — เก็บถาวรต่อแชต (workspace/ai_plans/<chat_id>.json)

ปัญหาที่แก้: แชตยาว ๆ ผู้ช่วยลืมว่าตกลงอะไรไปแล้ว ถามวัตถุประสงค์ซ้ำ วนกลับไปไอเดียเก่า และผู้ใช้เองก็ไม่รู้ว่าทำถึงไหน
→ ผู้ช่วยเขียน/อัปเดตแผน (เป้าหมาย · วัตถุประสงค์ · ข้อตกลง · ขั้นตอน+สถานะ · ชุดที่ได้ · สิ่งที่ติด) ทุกครั้งที่มีความคืบหน้า
  แผนถูกส่งกลับเข้า system prompt ทุกรอบ และแสดงเป็นแผงในแชต"""
import json
import re

from . import db
from .config import WORKSPACE

DIR = WORKSPACE / 'ai_plans'
STATUS = ('todo', 'doing', 'done', 'blocked', 'skipped')
STATUS_TH = dict(todo='ยังไม่เริ่ม', doing='กำลังทำ', done='เสร็จ', blocked='ติด', skipped='ข้าม')


def _path(cid):
    cid = re.sub(r'[^A-Za-z0-9_-]', '', str(cid or ''))[:64]
    return DIR / f'{cid}.json' if cid else None


def get(cid):
    p = _path(cid)
    if not p or not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except ValueError:
        return None


def update(cid, **kw):
    """แก้เฉพาะช่องที่ส่งมา (None = คงเดิม)"""
    p = _path(cid)
    if not p:
        raise ValueError('ไม่มีรหัสบทสนทนา')
    cur = get(cid) or dict(goal='', purpose='', decisions=[], steps=[], blockers=[], folder_id=None)
    for k in ('goal', 'purpose', 'audience'):
        if kw.get(k) is not None:
            cur[k] = str(kw[k])[:500]
    if kw.get('decisions') is not None:
        cur['decisions'] = [str(x)[:200] for x in kw['decisions']][:20]
    if kw.get('delivered') is not None:
        cur['delivered'] = [str(x)[:160] for x in kw['delivered']][:40]
    if kw.get('blockers') is not None:
        cur['blockers'] = [str(x)[:300] for x in kw['blockers']][:10]
    if kw.get('folder_id') is not None:
        cur['folder_id'] = int(kw['folder_id']) if kw['folder_id'] else None
    if kw.get('steps') is not None:
        steps = []
        for s in kw['steps'][:30]:
            if isinstance(s, str):
                s = dict(title=s)
            st = s.get('status') if s.get('status') in STATUS else 'todo'
            steps.append(dict(title=str(s.get('title') or '')[:200], status=st, note=str(s.get('note') or '')[:300],
                              outputs=[int(i) for i in (s.get('outputs') or []) if str(i).isdigit()][:10]))
        cur['steps'] = steps
    cur['updated_at'] = db.now()
    DIR.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding='utf-8')
    return cur


def all_():
    """แผนของทุกบทสนทนา (ใหม่สุดก่อน) — ให้ผู้ช่วยตอบได้ว่าเคยทำอะไรไปแล้วในแชตก่อน ๆ"""
    if not DIR.exists():
        return []
    out = []
    for p in DIR.glob('*.json'):
        try:
            d = json.loads(p.read_text(encoding='utf-8'))
        except ValueError:
            continue
        out.append(dict(d, chat_id=p.stem))
    return sorted(out, key=lambda x: x.get('updated_at') or '', reverse=True)


def as_text(plan):
    if not plan:
        return 'แผนงานของบทสนทนานี้: ยังไม่มี (สร้างด้วย update_plan เมื่อผู้ใช้ให้ทำงานที่มีหลายขั้น)'
    L = ['แผนงานของบทสนทนานี้ — สิ่งที่ผู้ใช้ตอบแล้วห้ามถามซ้ำ · แต่ถ้าข้อความล่าสุดของผู้ใช้ขัดกับข้อตกลงใด ให้ทำตามข้อความล่าสุด แล้ว update_plan แก้ข้อตกลงนั้น:']
    if plan.get('goal'):
        L.append(f'เป้าหมาย: {plan["goal"]}')
    if plan.get('purpose'):
        L.append(f'วัตถุประสงค์: {plan["purpose"]}' + (f' · ผู้ใช้/ผู้ชม: {plan["audience"]}' if plan.get('audience') else ''))
    if plan.get('folder_id'):
        L.append(f'โฟลเดอร์งาน: #{plan["folder_id"]}')
    for d in plan.get('decisions') or []:
        L.append(f'ตกลงแล้ว: {d}')
    for i, s in enumerate(plan.get('steps') or [], 1):
        L.append(f'{i}. [{STATUS_TH.get(s["status"], s["status"])}] {s["title"]}' + (f' — {s["note"]}' if s.get('note') else '')
                 + (f' → ชุด {", ".join("#" + str(o) for o in s["outputs"])}' if s.get('outputs') else ''))
    for x in plan.get('delivered') or []:
        L.append(f'ส่งมอบแล้ว (ห้ามส่งซ้ำ/ห้ามแต่งชื่อใหม่ให้ของเดิม): {x}')
    for b in plan.get('blockers') or []:
        L.append(f'ติด: {b}')
    return '\n'.join(L)
