# -*- coding: utf-8 -*-
"""ผู้ให้บริการ Claude Code (1.1.0): สะพาน MCP + ด่านของ /api/ai/cc_tool — ไม่ต้องติดตั้ง/ล็อกอิน Claude Code

1) app/ai_mcp.py คุยโปรโตคอล MCP (stdio JSON-RPC) ถูก: initialize · tools/list · tools/call ส่งต่อไปตัวประมวลผลพร้อมโทเคน
   · ข้อความที่ไม่ใช่ object ไม่ทำให้สะพานล้ม · method ที่ไม่รู้จัก → error -32601
2) ตัวประมวลผลที่รันอยู่: /api/ai/cc_tool ปฏิเสธโทเคนผิด และปฏิเสธคำขอที่มาจากหน้าเว็บ (มี Origin) แม้มีหัวโทเคน
3) ai_cc.chat ส่ง transcript ถูกรูปแบบ (ข้อความล่าสุดอยู่ท้าย)

    python tests/api/test_ai_cc.py
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from common import ENGINE, Results, session, wait_engine  # noqa: E402

R = Results()

# ---------- 1) สะพาน MCP กับตัวประมวลผลจำลอง ----------
seen = []


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        seen.append((self.headers.get('X-Ainu-CC'), b))
        body = json.dumps(dict(result=json.dumps({'echo': b['args']}), is_error=False)).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(body)


srv = ThreadingHTTPServer(('127.0.0.1', 0), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
specs = [dict(name='list_datasets', description='รายการชุดข้อมูล', parameters=dict(type='object', properties={}, required=[]))]
with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as f:
    json.dump(specs, f, ensure_ascii=False)
env = dict(os.environ, AINU_CC_URL=f'http://127.0.0.1:{srv.server_port}/api/ai/cc_tool', AINU_CC_TOKEN='tok123',
           AINU_CC_SPECS=f.name, PYTHONIOENCODING='utf-8')
msgs = [
    dict(jsonrpc='2.0', id=1, method='initialize', params=dict(protocolVersion='2025-06-18')),
    dict(jsonrpc='2.0', method='notifications/initialized'),
    'not-an-object',
    dict(jsonrpc='2.0', id=2, method='tools/list'),
    dict(jsonrpc='2.0', id=3, method='tools/call', params=dict(name='list_datasets', arguments=dict(q='ป่า'))),
    dict(jsonrpc='2.0', id=4, method='nope'),
]
p = subprocess.run([sys.executable, str(ROOT / 'app' / 'ai_mcp.py')], input='\n'.join(json.dumps(m, ensure_ascii=False) for m in msgs) + '\n',
                   capture_output=True, text=True, encoding='utf-8', env=env, timeout=60)
os.unlink(f.name)
out = {j['id']: j for j in (json.loads(l) for l in p.stdout.splitlines() if l.strip())}
R.check('initialize ตอบ protocolVersion + capabilities.tools', out.get(1, {}).get('result', {}).get('capabilities', {}).get('tools') is not None)
R.check('notification ไม่ถูกตอบ · ข้อความไม่ใช่ object ไม่ทำให้ล้ม', set(out) == {1, 2, 3, 4}, p.stderr[-300:])
R.check('tools/list มีเครื่องมือของแอป', [t['name'] for t in out[2]['result']['tools']] == ['list_datasets'])
txt = out[3]['result']['content'][0]['text']
R.check('tools/call ส่งต่อพร้อมโทเคน + อาร์กิวเมนต์ภาษาไทย', seen and seen[0][0] == 'tok123' and json.loads(txt) == {'echo': {'q': 'ป่า'}}, txt)
R.check('method ที่ไม่รู้จัก → -32601', out[4].get('error', {}).get('code') == -32601)
srv.shutdown()

# ---------- 2) ด่านของตัวประมวลผลจริง ----------
wait_engine()
import requests  # noqa: E402
r = requests.post(ENGINE + '/api/ai/cc_tool', json=dict(name='list_datasets', args={}), headers={'X-Ainu-CC': 'wrong'})
R.check('ไม่มี Origin + โทเคนผิด → 403', r.status_code == 403, r.status_code)
r = requests.post(ENGINE + '/api/ai/cc_tool', json=dict(name='list_datasets', args={}),
                  headers={'X-Ainu-CC': 'x', 'Origin': 'https://evil.example'})
R.check('คำขอจากเว็บภายนอก → 403', r.status_code == 403, r.status_code)
st = session.get(ENGINE + '/api/ai').json()
R.check('ผู้ให้บริการ claude_code อยู่ในรายการ (ไม่ต้องใส่ key)',
        any(x['id'] == 'claude_code' and x['no_key'] for x in st['providers']))

# ---------- 3) transcript ----------
from app import ai_cc  # noqa: E402
t = ai_cc._transcript([dict(role='user', content='ก'), dict(role='assistant', content='ข'), dict(role='user', content='ค')])
R.check('transcript: ข้อความล่าสุดอยู่ท้ายพร้อมป้าย', t.rstrip().endswith('ค') and '[ผู้ช่วย]\nข' in t)
R.check('transcript: ข้อความเดียวส่งตรง', ai_cc._transcript([dict(role='user', content='สวัสดี')]) == 'สวัสดี')

sys.exit(R.done())
