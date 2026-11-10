# -*- coding: utf-8 -*-
"""การคุยไม่หลง (จากบทสนทนาจริงที่ผู้ใช้บ่น "คุยไม่รู้เรื่อง") — ทดสอบกลไก ด้วยโมเดลจำลองแบบ OpenAI ในตัว
- แผนงาน: ข้อความล่าสุดชนะข้อตกลงเดิม (บอกไว้ในแผนที่ส่งให้โมเดล) · "ส่งมอบแล้ว" อยู่ในแผน (กันส่งของเดิมซ้ำ)
- prompt มีกฎ: override ยกเลิกข้อจำกัดเดิม · "ทำมา" = สร้างผลจริง · ขอใหม่ = ห้ามส่งของเดิม · ตอบคำถามก่อน · งานยาว → เอกสาร
- เอกสาร: save_document → การ์ดเอกสารในคำตอบ · หน้า HTML มีตารางจริง · ดาวน์โหลด .md · เขียนซ้ำชื่อเดิม = v2
- list_past_work เห็นงานของแชตก่อน · บันทึกบทสนทนาลง ai_logs (ไม่มี key)"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common import ENGINE, Results, session as s, wait_engine  # noqa: E402

wait_engine()
R = Results()
from app import ai, ai_plan  # noqa: E402

KEY = 'mock-test-key'
DOC = '''# แคตาล็อกตัวชี้วัด: ความร้อน

| หมวด | ตัวชี้วัด | สูตร |
|---|---|---|
| ลักษณะภัย | แนวโน้มความร้อน | slope(LST) |
| ความเปราะบาง | ผู้สูงอายุ × คืนร้อน | pop65 ในพิกเซล LST กลางคืน > P80 |

- ข้อมูล: **MODIS LST** · WorldPop
'''
SEEN = {}
DOC_TITLE = 'แคตาล็อกความร้อน ' + str(int(time.time()))


def call(name, args, i=0):
    return {'id': f'c{i}_{name}', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}


class Mock(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, o):
        b = json.dumps(o, ensure_ascii=False).encode()
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        self._send({'data': [{'id': 'mock-conv'}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)))
        m = body['messages']
        SEEN['system'] = ' '.join(x['content'] for x in m if x['role'] == 'system')
        lu = max(i for i, x in enumerate(m) if x['role'] == 'user')
        after = m[lu + 1:]
        r = lambda calls=None, text=None: self._send({'choices': [{'message': {'role': 'assistant', 'content': text, 'tool_calls': calls}}]})
        u = m[lu]['content']
        if u.startswith('BRIEF'):
            if not after:
                return r([call('update_plan', dict(goal='แคตาล็อกตัวชี้วัดความเสี่ยงภัย', decisions=['ยังไม่รันงานประมวลผล']))])
            return r(text='ตั้งแผนแล้ว')
        if u.startswith('DOC'):
            if not after:
                return r([call('save_document', dict(title=DOC_TITLE, markdown=DOC)),
                          call('update_plan', dict(delivered=['แนวโน้มความร้อน', 'ผู้สูงอายุ × คืนร้อน']), 1)])
            return r(text='บันทึกแคตาล็อกเป็นเอกสารแล้ว (2 ตัวชี้วัด)')
        if u.startswith('PAST'):
            if not after:
                return r([call('list_past_work', {})])
            SEEN['past'] = json.loads(after[-1]['content'])
            return r(text='เห็นงานเก่าแล้ว')
        r(text='ok')


srv = ThreadingHTTPServer(('127.0.0.1', 0), Mock)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f'http://127.0.0.1:{srv.server_address[1]}/v1'


def api(path, body=None, method=None):
    r = s.request(method or ('POST' if body is not None else 'GET'), ENGINE + path, json=body, timeout=300)
    return r.status_code, r


api('/api/ai', dict(enabled=True, mode='propose'), 'PATCH')
c, j = api('/api/ai/login', dict(provider='compat', api_key=KEY, base_url=BASE))
assert c == 200, j.text
cid = 'ctconv' + str(int(time.time()))


def chat(text, hist):
    hist.append(dict(role='user', content=text))
    c, r = api('/api/ai/chat', dict(messages=hist, chat_id=cid))
    out = r.json()
    hist.append(dict(role='assistant', content=out.get('reply') or ''))
    return out


h = []
chat('BRIEF: ออกแบบแคตาล็อก ยังไม่รันงาน', h)
sysmsg = chat('override ยืนยันทุกอย่าง ทำมาเลย', h) and SEEN['system']
R.check('แผนที่ส่งให้โมเดลบอกว่า "ข้อความล่าสุดชนะข้อตกลงเดิม" + มีข้อตกลงเดิม', 'ทำตามข้อความล่าสุด' in sysmsg and 'ยังไม่รันงานประมวลผล' in sysmsg)
R.check('prompt: override ยกเลิกข้อจำกัด · "ทำมา" = ผลจริง · ขอใหม่ห้ามส่งของเดิม · ตอบคำถามก่อน · งานยาว → เอกสาร',
        all(k in ai.TOOLS_PROPOSE for k in ('ยกเลิกข้อจำกัดเดิม', 'สร้างผลจริง', 'ห้ามส่งของเดิมในรูปแบบใหม่', 'ตอบคำถามนั้นตรง ๆ ก่อน', 'save_document')))
out = chat('DOC ทำแคตาล็อก', h)
d = (out.get('docs') or [{}])[0]
R.check('save_document → การ์ดเอกสารในคำตอบ (ชื่อ เวอร์ชัน จำนวนตาราง)', d.get('title') == DOC_TITLE and d.get('tables') == 1 and d.get('version') == 1, str(d))
c, page = api(d['url'])
c2, raw = api(d['url'] + '?raw=1')
R.check('เปิดเอกสาร = หน้า HTML มีตารางจริง · ดาวน์โหลด .md ได้เนื้อหาเดิม', c == 200 and '<table>' in page.text and '<th>สูตร</th>' in page.text and '<b>MODIS LST</b>' in page.text
        and raw.text == DOC)
out = chat('DOC แก้แคตาล็อก', h)
R.check('เขียนชื่อเดิมซ้ำ = เวอร์ชัน 2 (ไม่ซ้อนไฟล์)', (out.get('docs') or [{}])[0].get('version') == 2)
pl = ai_plan.get(cid)
R.check('แผนมี "ส่งมอบแล้ว" และบอกโมเดลว่าห้ามส่งซ้ำ', pl and pl.get('delivered') == ['แนวโน้มความร้อน', 'ผู้สูงอายุ × คืนร้อน'] and 'ห้ามส่งซ้ำ' in ai_plan.as_text(pl))
cid_old, cid = cid, 'ctconv_new' + str(int(time.time()))
chat('PAST จำแชตเก่าได้ไหม', [])
past = SEEN.get('past') or {}
R.check('แชตใหม่ list_past_work เห็นแผน/สิ่งที่ส่งมอบ/เอกสารของแชตก่อน', any(p['chat_id'] == cid_old and 'แนวโน้มความร้อน' in (p.get('delivered') or []) for p in past.get('plans', []))
        and any(x['title'] == DOC_TITLE for x in past.get('documents', [])))
log = Path(os.environ.get('AINU_WORKSPACE', '')) / 'ai_logs' / f'{cid_old}.jsonl'
rows = [json.loads(x) for x in log.read_text(encoding='utf-8').splitlines()] if log.exists() else []
R.check('บันทึกบทสนทนาลง ai_logs (ข้อความ/เครื่องมือ/เอกสาร) และไม่มี API key', len(rows) >= 4 and any('save_document' in r['tools'] for r in rows)
        and KEY not in log.read_text(encoding='utf-8'), f'{len(rows)} แถว')
api('/api/ai/logout', {})
sys.exit(R.done())
