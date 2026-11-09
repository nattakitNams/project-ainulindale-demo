# -*- coding: utf-8 -*-
"""ผู้ช่วย AI (ขั้นที่ 1: ตั้งค่า + ล็อกอินด้วย API key + แชต)

- ปิดไว้เป็นค่าเริ่มต้น · เปิดที่หน้า "ระบบ" → หน้าเว็บโชว์ช่องแชตลอยมุมขวาล่าง
- API key เก็บเข้ารหัสด้วย vault (DPAPI) ในเครื่องผู้ใช้ — หน้าเว็บไม่เคยเห็นค่า · ตัวประมวลผลคุยกับผู้ให้บริการแทน
- ค่าตั้ง (ไม่มี key) อยู่ที่ workspace/ai.json — แยกตาม workspace (ตัวประมวลผลทดสอบไม่ทับของจริง)
- ส่งให้ AI เฉพาะข้อความแชต + ข้อมูลอธิบายคลัง (ชื่อ/ประเภทค่า/ความละเอียด) — ไม่ส่งไฟล์ข้อมูล
"""
import json
import re

import requests

from . import db, vault
from .config import WORKSPACE

CFG_PATH = WORKSPACE / 'ai.json'
TIMEOUT = 120
PROVIDERS = {
    'anthropic': dict(label='Claude (Anthropic)', base='https://api.anthropic.com/v1', key_url='https://console.anthropic.com/settings/keys'),
    'openai': dict(label='OpenAI', base='https://api.openai.com/v1', key_url='https://platform.openai.com/api-keys'),
    'gemini': dict(label='Google Gemini', base='https://generativelanguage.googleapis.com/v1beta', key_url='https://aistudio.google.com/apikey'),
    'compat': dict(label='OpenAI-compatible (Ollama / OpenRouter / เซิร์ฟเวอร์หน่วยงาน)', base=None, key_url=None, key_optional=True),
}
# รุ่นที่ไม่ใช่แชต (OpenAI /models คืนทุกอย่าง)
_NOT_CHAT = re.compile(r'embed|whisper|tts|dall-e|moderation|image|audio|realtime|transcribe|search|babbage|davinci|computer-use', re.I)


class AiError(Exception):
    pass


# ---------- ค่าตั้ง ----------
def cfg():
    try:
        return json.loads(CFG_PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save(**kw):
    c = cfg()
    c.update(kw)
    CFG_PATH.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding='utf-8')
    return c


def _key(c=None):
    c = c or cfg()
    try:
        return vault.get(c.get('secret_id'))
    except Exception:                                # โทเคนถูกลบจากหน้า "ระบบ" / ถอดรหัสไม่ได้
        return None


def status():
    c = cfg()
    p = c.get('provider')
    connected = bool(p) and (bool(_key(c)) or (PROVIDERS.get(p, {}).get('key_optional') and bool(c.get('base_url'))))
    return dict(enabled=bool(c.get('enabled')), connected=connected, provider=p if connected else None,
                provider_label=PROVIDERS.get(p, {}).get('label') if connected else None,
                model=c.get('model') if connected else None, base_url=c.get('base_url') if connected else None,
                providers=[dict(id=k, label=v['label'], key_url=v['key_url'], key_optional=bool(v.get('key_optional'))) for k, v in PROVIDERS.items()])


# ---------- คุยกับผู้ให้บริการ ----------
def _base(p, base_url):
    if p == 'compat':
        b = (base_url or '').strip().rstrip('/')
        if not re.match(r'^https?://', b):
            raise AiError('ใส่ที่อยู่เซิร์ฟเวอร์ เช่น http://localhost:11434/v1 (Ollama) หรือ https://openrouter.ai/api/v1')
        return b
    return PROVIDERS[p]['base']


def _headers(p, key):
    if p == 'anthropic':
        return {'x-api-key': key, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'}
    if p == 'gemini':
        return {'x-goog-api-key': key, 'content-type': 'application/json'}
    return {'Authorization': f'Bearer {key}', 'content-type': 'application/json'} if key else {'content-type': 'application/json'}


def _req(method, url, p, key, **kw):
    try:
        r = requests.request(method, url, headers=_headers(p, key), timeout=TIMEOUT, **kw)
    except requests.RequestException as e:
        raise AiError(f'ติดต่อผู้ให้บริการไม่ได้ ({type(e).__name__})')
    if r.status_code in (401, 403):
        raise AiError('โทเคนไม่ถูกต้อง หรือไม่มีสิทธิ์ใช้รุ่นนี้')
    if r.status_code == 429:
        raise AiError('เกินโควตาหรืออัตราการใช้งานของบัญชี — รอสักครู่หรือตรวจยอดเครดิต')
    if not r.ok:
        try:
            j = r.json()
            msg = (j.get('error') or {}).get('message') if isinstance(j.get('error'), dict) else j.get('error') or j.get('message')
        except ValueError:
            msg = None
        raise AiError(f'ผู้ให้บริการตอบ {r.status_code}' + (f': {str(msg)[:300]}' if msg else ''))
    try:
        return r.json()
    except ValueError:
        raise AiError('ผู้ให้บริการตอบไม่ใช่ JSON — ตรวจที่อยู่เซิร์ฟเวอร์')


def list_models(p, key, base_url=None):
    b = _base(p, base_url)
    if p == 'anthropic':
        ids = [m['id'] for m in _req('GET', f'{b}/models', p, key, params=dict(limit=100)).get('data', [])]
    elif p == 'gemini':
        ms = _req('GET', f'{b}/models', p, key, params=dict(pageSize=200)).get('models', [])
        ids = [m['name'].split('/', 1)[-1] for m in ms if 'generateContent' in (m.get('supportedGenerationMethods') or [])]
    else:
        ids = [m['id'] for m in _req('GET', f'{b}/models', p, key).get('data', [])]
        if p == 'openai':
            ids = [i for i in ids if not _NOT_CHAT.search(i)]
    if not ids:
        raise AiError('เชื่อมต่อได้แต่ไม่พบรุ่นที่ใช้แชตได้')
    return ids


def default_model(p, ids):
    pref = dict(anthropic=['sonnet', 'opus', 'haiku'], openai=['gpt-5', 'gpt-4.1', 'gpt-4o'], gemini=['flash', 'pro']).get(p, [])
    for w in pref:
        hit = [i for i in ids if w in i and 'preview' not in i] or [i for i in ids if w in i]
        if hit:
            return sorted(hit, reverse=True)[0] if p == 'gemini' else hit[0]
    return ids[0]


def login(p, key, base_url=None):
    if p not in PROVIDERS:
        raise AiError('ไม่รู้จักผู้ให้บริการนี้')
    key = (key or '').strip()
    if not key and not PROVIDERS[p].get('key_optional'):
        raise AiError('ใส่ API key')
    ids = list_models(p, key, base_url)                 # ทดสอบ key ก่อนเก็บ
    old = cfg().get('secret_id')
    sid = vault.put(f'AI · {PROVIDERS[p]["label"].split(" (")[0]}', key) if key else None
    if old:
        vault.delete(old)
    save(provider=p, secret_id=sid, base_url=_base(p, base_url) if p == 'compat' else None, model=default_model(p, ids))
    return ids


def logout():
    c = cfg()
    if c.get('secret_id'):
        vault.delete(c['secret_id'])
    save(provider=None, secret_id=None, model=None, base_url=None)


def models():
    c = cfg()
    if not status()['connected']:
        raise AiError('ยังไม่ได้เชื่อมต่อ')
    return list_models(c['provider'], _key(c), c.get('base_url'))


# ---------- แชต ----------
SYSTEM = """คุณคือผู้ช่วยในแอป Ainulindalë — เครื่องมือไขว้ข้อมูลภูมิสารสนเทศสองชุดเป็นแผนที่ไบแวเรียต (bivariate) สำหรับข้อมูลใดก็ได้
ประมวลผลในเครื่องผู้ใช้ ความสามารถ: คลังข้อมูล (โฟลเดอร์/ถังขยะ), ยืนยันประเภทค่า (count = จำนวนนับ รวมแล้วผลรวมไม่หาย / density = ค่าต่อเนื่อง เฉลี่ยถ่วงพื้นที่ / class = ชั้น ใช้ majority),
ปรับความละเอียด, ตัดพื้นที่ศึกษา (มีพื้นที่ศึกษาพื้นฐาน "ประเทศไทย"), แปลงเวกเตอร์ ↔ ราสเตอร์ ↔ หกเหลี่ยม, ไบแวเรียต (กริดหรือหกเหลี่ยม, เกณฑ์เอง/ควอนไทล์/ช่วงเท่ากัน/DEGURBA),
เปรียบเทียบ 2 ช่วงเวลา, แผนที่ซ้อนชั้น, ตัวออกแบบรายงาน PDF, Data hub (รายชื่อแหล่งข้อมูลภายนอก)
ตอนนี้คุณยังสั่งงานในแอปเองไม่ได้ — แนะนำขั้นตอนเป็นข้อ ๆ ให้ผู้ใช้กดเอง ตอบสั้น ตรง ใช้ภาษาเดียวกับผู้ใช้ ถ้าไม่แน่ใจให้บอกตรง ๆ"""


def _context():
    """ข้อมูลอธิบายคลัง (ไม่ใช่ไฟล์ข้อมูล) ให้ AI ตอบตรงกับของที่ผู้ใช้มี"""
    ds = db.query("SELECT id, name, kind, role, value_type, meta FROM datasets WHERE trashed_at IS NULL ORDER BY id DESC LIMIT 80")
    aois = db.query('SELECT id, name, area_km2 FROM aoi WHERE trashed_at IS NULL ORDER BY id DESC LIMIT 30')
    rows = []
    for d in ds:
        m = d.get('meta') or {}
        extra = (m.get('res_label') or '').split(' (')[0] if d['kind'] == 'raster' else (m.get('type_label') or m.get('geometry_type') or '')
        rows.append(f"#{d['id']} {d['name']} · {d['kind']}/{d['role']}" + (f" · {d['value_type']}" if d['kind'] == 'raster' else '') + (f' · {extra}' if extra else ''))
    return ('คลังข้อมูลของผู้ใช้ (ชุดล่าสุด):\n' + '\n'.join(rows) if rows else 'คลังข้อมูลยังว่าง') \
        + ('\nพื้นที่ศึกษา: ' + ', '.join(f"{a['name']} ({a['area_km2']:,.0f} ตร.กม.)" for a in aois) if aois else '')


def chat(messages, page=None):
    c = cfg()
    if not c.get('enabled'):
        raise AiError('ผู้ช่วย AI ปิดอยู่ (เปิดที่หน้า "ระบบ")')
    if not status()['connected']:
        raise AiError('ยังไม่ได้เชื่อมต่อ')
    p, key, model = c['provider'], _key(c), c.get('model')
    msgs = [dict(role='assistant' if m.get('role') == 'assistant' else 'user', content=str(m.get('content') or '')[:8000])
            for m in (messages or [])[-30:] if m.get('content')]
    if not msgs or msgs[-1]['role'] != 'user':
        raise AiError('ไม่มีข้อความ')
    while msgs and msgs[0]['role'] != 'user':          # บางเจ้าบังคับให้เริ่มด้วย user
        msgs.pop(0)
    system = SYSTEM + '\n\n' + _context() + (f'\nผู้ใช้อยู่ที่หน้า: {page}' if page else '')
    b = _base(p, c.get('base_url'))
    if p == 'anthropic':
        j = _req('POST', f'{b}/messages', p, key, json=dict(model=model, max_tokens=2048, system=system, messages=msgs))
        text = ''.join(x.get('text', '') for x in j.get('content', []) if x.get('type') == 'text')
    elif p == 'gemini':
        j = _req('POST', f'{b}/models/{model}:generateContent', p, key, json=dict(
            systemInstruction=dict(parts=[dict(text=system)]),
            contents=[dict(role='model' if m['role'] == 'assistant' else 'user', parts=[dict(text=m['content'])]) for m in msgs]))
        cands = j.get('candidates') or []
        text = ''.join(x.get('text', '') for x in ((cands[0].get('content') or {}).get('parts') or [])) if cands else ''
    else:
        j = _req('POST', f'{b}/chat/completions', p, key, json=dict(model=model, messages=[dict(role='system', content=system)] + msgs))
        ch = j.get('choices') or []
        text = (ch[0].get('message') or {}).get('content') or '' if ch else ''
    if not text.strip():
        raise AiError('ผู้ให้บริการไม่ตอบข้อความ (อาจถูกตัวกรองเนื้อหา)')
    return dict(reply=text, model=model)
