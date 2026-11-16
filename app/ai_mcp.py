# -*- coding: utf-8 -*-
"""MCP server (stdio) ที่ Claude Code เปิดเป็นโปรเซสลูก — เปิดเครื่องมือของแอปให้ Claude ใช้

รันแบบสคริปต์เดี่ยว (ใช้แค่ stdlib) · ไม่ทำงานเอง: ทุก tools/call ส่งต่อไปที่ตัวประมวลผล (/api/ai/cc_tool)
พร้อมโทเคนของรอบแชตนั้น → ตัวประมวลผลเรียก ai_tools.run ชุดเดิม (ด่าน/ข้อเสนอ/ยืนยันเหมือนเดิม)
ค่าจาก env: AINU_CC_URL, AINU_CC_TOKEN, AINU_CC_SPECS (ไฟล์ JSON รายการเครื่องมือ)
"""
import json
import os
import sys
import urllib.error
import urllib.request

URL = os.environ['AINU_CC_URL']
TOKEN = os.environ['AINU_CC_TOKEN']
with open(os.environ['AINU_CC_SPECS'], encoding='utf-8') as f:
    SPECS = json.load(f)

stdin = sys.stdin.buffer
stdout = sys.stdout.buffer


def send(msg):
    stdout.write(json.dumps(msg, ensure_ascii=False).encode('utf-8') + b'\n')
    stdout.flush()


def call_app(name, args):
    req = urllib.request.Request(URL, data=json.dumps(dict(name=name, args=args or {}), ensure_ascii=False).encode('utf-8'),
                                 headers={'Content-Type': 'application/json', 'X-Ainu-CC': TOKEN}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            j = json.loads(r.read().decode('utf-8'))
        return j.get('result') or '', bool(j.get('is_error'))
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode('utf-8')).get('error')
        except Exception:
            msg = None
        return f'ตัวประมวลผลตอบ {e.code}' + (f': {msg}' if msg else ''), True
    except Exception as e:
        return f'ติดต่อตัวประมวลผลไม่ได้ ({type(e).__name__})', True


def handle(m):
    method, mid = m.get('method'), m.get('id')
    if mid is None:                                            # notification (เช่น notifications/initialized) — ไม่ต้องตอบ
        return
    if method == 'initialize':
        res = dict(protocolVersion=(m.get('params') or {}).get('protocolVersion') or '2025-06-18',
                   capabilities=dict(tools=dict(listChanged=False)), serverInfo=dict(name='ainu', version='1.0'))
    elif method == 'ping':
        res = {}
    elif method == 'tools/list':
        res = dict(tools=[dict(name=s['name'], description=s['description'], inputSchema=s['parameters']) for s in SPECS])
    elif method == 'tools/call':
        p = m.get('params') or {}
        text, err = call_app(p.get('name'), p.get('arguments'))
        res = dict(content=[dict(type='text', text=text)], isError=err)
    else:
        send(dict(jsonrpc='2.0', id=mid, error=dict(code=-32601, message=f'method not found: {method}')))
        return
    send(dict(jsonrpc='2.0', id=mid, result=res))


for line in stdin:
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line.decode('utf-8'))
    except ValueError:
        continue
    for one in (msg if isinstance(msg, list) else [msg]):
        if not isinstance(one, dict):
            continue
        try:
            handle(one)
        except Exception as e:
            if one.get('id') is not None:
                send(dict(jsonrpc='2.0', id=one['id'], error=dict(code=-32603, message=f'{type(e).__name__}: {e}')))
