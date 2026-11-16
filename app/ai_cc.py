# -*- coding: utf-8 -*-
"""ผู้ให้บริการ "Claude Code" — ใช้บัญชี Claude (Pro/Max) ที่ล็อกอินไว้ในเครื่อง แทน API key

- ตัวประมวลผลเรียก `claude -p` (Claude Code CLI) ต่อหนึ่งรอบแชต · ใช้โควตาของแพ็กเกจผู้ใช้ ไม่มีค่า API เพิ่ม
- ปิดเครื่องมือในตัวของ Claude Code ทั้งหมด (--tools "") — แตะไฟล์/รันคำสั่งบนเครื่องไม่ได้
- เครื่องมือเดียวที่มี = เครื่องมือของแอป (ai_tools ชุดเดิม) ผ่าน MCP server เล็ก ๆ (ai_mcp.py)
  ที่ส่งต่อกลับมาที่ /api/ai/cc_tool ด้วยโทเคนใช้ครั้งเดียวต่อรอบ → ด่าน/ข้อเสนอ/การยืนยันเหมือนผู้ให้บริการอื่นทุกอย่าง
- ไม่ส่ง ANTHROPIC_API_KEY ต่อให้ CLI (ถ้ามีในเครื่อง) — กันไม่ให้สลับไปใช้ API แบบเสียเงินโดยไม่รู้ตัว
"""
import glob
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from .config import PORT, ROOT, WORKSPACE

MODELS = ['sonnet', 'opus', 'haiku']                  # alias ของ Claude Code → รุ่นล่าสุดของแต่ละตระกูลเสมอ
TIMEOUT = 1800                 # รอบเดียวอาจมีหลายรอบเครื่องมือ (ค้น hub / ประเมินงาน) — เผื่อให้พอ
_SESSIONS, _lock = {}, threading.Lock()


class CcError(Exception):
    pass


def find_cli():
    """หา claude.exe: ตั้งเองที่ AINU_CLAUDE_EXE > PATH > ตัวติดตั้งแบบ native > ตัวที่มากับแอป Claude Desktop (รุ่นใหม่สุด)"""
    env = os.environ.get('AINU_CLAUDE_EXE')
    if env and Path(env).is_file():
        return env
    w = shutil.which('claude')
    if w:
        return w
    home = Path.home()
    for p in (home / '.local' / 'bin' / 'claude.exe', home / '.local' / 'bin' / 'claude'):
        if p.is_file():
            return str(p)
    appdata = os.environ.get('APPDATA') or str(home / 'AppData' / 'Roaming')
    local = os.environ.get('LOCALAPPDATA') or str(home / 'AppData' / 'Local')
    tail = ('claude-code', '*', '*', 'claude.exe')
    hits = glob.glob(os.path.join(appdata, 'Claude', *tail))
    # Claude Desktop แบบ Microsoft Store (MSIX): AppData ของแอปถูกเก็บจริงใน Packages\…\LocalCache — โปรเซสนอกแอปมองไม่เห็นที่ path ปกติ
    hits += glob.glob(os.path.join(local, 'Packages', 'Claude_*', 'LocalCache', 'Roaming', 'Claude', *tail))
    if hits:
        return max(hits, key=os.path.getmtime)
    raise CcError('ไม่พบ Claude Code ในเครื่องนี้ — ติดตั้งแอป Claude Desktop หรือ Claude Code CLI แล้วล็อกอิน '
                  '(หรือตั้ง AINU_CLAUDE_EXE เป็น path ของ claude.exe)')


def _env():
    e = dict(os.environ)
    for k in ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_USE_BEDROCK', 'CLAUDE_CODE_USE_VERTEX'):
        e.pop(k, None)
    e['PYTHONIOENCODING'] = 'utf-8'
    return e


def _run(args, stdin=None, timeout=60):
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    try:
        return subprocess.run([find_cli(), *args], input=stdin, capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=timeout, env=_env(), cwd=str(_workdir()), creationflags=flags)
    except subprocess.TimeoutExpired:
        raise CcError(f'Claude Code ไม่ตอบภายใน {timeout} วินาที')
    except OSError as e:
        raise CcError(f'เปิด Claude Code ไม่ได้ ({e})')


def _workdir():
    d = WORKSPACE / 'cache' / 'claude_code'               # โฟลเดอร์ว่าง — ไม่มี CLAUDE.md/ค่าตั้งโปรเจกต์ให้ CLI หยิบไปใช้
    d.mkdir(parents=True, exist_ok=True)
    return d


def auth_status():
    r = _run(['auth', 'status'])
    try:
        j = json.loads(r.stdout)
    except ValueError:
        raise CcError('อ่านสถานะล็อกอินของ Claude Code ไม่ได้: ' + (r.stderr or r.stdout)[:300])
    if not j.get('loggedIn'):
        raise CcError('Claude Code ยังไม่ได้ล็อกอิน — เปิดแอป Claude แล้วล็อกอิน หรือรัน "claude auth login"')
    if j.get('authMethod') != 'claude.ai':
        raise CcError(f'Claude Code ล็อกอินแบบ {j.get("authMethod")} (ไม่ใช่บัญชี claude.ai) — จะคิดเงินแบบ API แทนโควตาแพ็กเกจ')
    return j


def models():
    auth_status()
    return list(MODELS)


# ---------- เครื่องมือ: MCP server (โปรเซสลูกของ CLI) → /api/ai/cc_tool ----------
def call(token, name, args):
    with _lock:
        s = _SESSIONS.get(token)
    if not s:
        return None
    return s['call_tool'](name, args)


def _transcript(msgs):
    if len(msgs) == 1:
        return msgs[0]['content']
    parts = ['ประวัติบทสนทนาในแอป (ใหม่สุดอยู่ท้าย):']
    for m in msgs[:-1]:
        parts.append(('[ผู้ใช้]\n' if m['role'] == 'user' else '[ผู้ช่วย]\n') + m['content'])
    parts.append('[ข้อความล่าสุดของผู้ใช้ — ตอบข้อความนี้]\n' + msgs[-1]['content'])
    return '\n\n'.join(parts)


def chat(model, system, msgs, specs, call_tool):
    """หนึ่งรอบแชต → (ข้อความตอบ, usage) · CLI วนเรียกเครื่องมือเองจนจบ"""
    token = secrets.token_urlsafe(24)
    wd = _workdir()
    spec_path, sys_path, mcp_path = (wd / f'{token[:12]}_{n}' for n in ('specs.json', 'system.txt', 'mcp.json'))
    spec_path.write_text(json.dumps(specs, ensure_ascii=False), encoding='utf-8')
    sys_path.write_text(system + '\n\nเครื่องมือของแอปอยู่ในชื่อ mcp__ainu__<ชื่อเครื่องมือ> (เช่น mcp__ainu__list_datasets) — '
                        'คุณไม่มีเครื่องมืออื่น (อ่าน/เขียนไฟล์ รันคำสั่ง เปิดเว็บ ไม่ได้)', encoding='utf-8')
    mcp_path.write_text(json.dumps(dict(mcpServers=dict(ainu=dict(
        type='stdio', command=sys.executable, args=[str(ROOT / 'app' / 'ai_mcp.py')],
        env=dict(AINU_CC_URL=f'http://127.0.0.1:{PORT}/api/ai/cc_tool', AINU_CC_TOKEN=token, AINU_CC_SPECS=str(spec_path),
                 PYTHONNOUSERSITE='1', PYTHONIOENCODING='utf-8', PYTHONUTF8='1'))))), encoding='utf-8')
    with _lock:
        _SESSIONS[token] = dict(call_tool=call_tool)
    try:
        r = _run(['-p', '--output-format', 'json', '--model', model or 'sonnet',
                  '--system-prompt-file', str(sys_path),
                  '--tools', '',                                   # ปิดเครื่องมือในตัวทั้งหมด
                  '--mcp-config', str(mcp_path), '--strict-mcp-config',
                  '--allowedTools', 'mcp__ainu',
                  '--setting-sources', 'project',                 # ข้าม hooks/ค่าตั้งส่วนตัวของผู้ใช้ (โฟลเดอร์งานว่าง)
                  '--no-session-persistence'],
                 stdin=_transcript(msgs), timeout=TIMEOUT)
    finally:
        with _lock:
            _SESSIONS.pop(token, None)
        for p in (spec_path, sys_path, mcp_path):
            try:
                p.unlink()
            except OSError:
                pass
    try:
        j = json.loads(r.stdout)
    except ValueError:
        msg = (r.stderr or r.stdout or '').strip()
        raise CcError('Claude Code ทำงานไม่สำเร็จ' + (f' — {msg[:400]}' if msg else f' (exit {r.returncode})'))
    if j.get('is_error'):
        t = str(j.get('result') or j.get('subtype') or '')
        if 'login' in t.lower():
            t += ' — ล็อกอินใหม่ในแอป Claude หรือรัน "claude auth login"'
        elif 'limit' in t.lower():
            t += ' — ใช้ครบโควตาของแพ็กเกจแล้ว รอรอบรีเซ็ต'
        raise CcError('Claude Code: ' + t[:400])
    u = j.get('usage') or {}
    usage = dict(calls=j.get('num_turns') or 1,
                 input=(u.get('input_tokens') or 0) + (u.get('cache_read_input_tokens') or 0) + (u.get('cache_creation_input_tokens') or 0),
                 cached=u.get('cache_read_input_tokens') or 0, output=u.get('output_tokens') or 0)
    return str(j.get('result') or '').strip(), usage
