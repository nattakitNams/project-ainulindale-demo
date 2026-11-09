# -*- coding: utf-8 -*-
"""ตรวจรูปแบบ tool calling ของ Anthropic / Gemini / OpenAI โดยไม่ต้องมี key — แทน ai._req ด้วยคำตอบสคริปต์ตามรูปแบบจริงของแต่ละเจ้า
    set AINU_WORKSPACE=<workspace ทดสอบ> & set AINU_PORT=41299 & python -m tests.check_ai_formats"""
import json

from app import ai, server  # noqa: F401  (server ตั้ง ai_tools.CLIENT ให้)

SENT = []


def fake(provider):
    step = {'n': 0}

    def _req(method, url, p, key, **kw):
        body = kw.get('json') or {}
        SENT.append((provider, url, body))
        if method == 'GET':
            return {}
        n = step['n']; step['n'] += 1
        if provider == 'anthropic':
            assert body['tools'][0]['input_schema']['type'] == 'object'
            if n == 0:
                return {'content': [{'type': 'text', 'text': 'ขอดูคลังก่อน'},
                                    {'type': 'tool_use', 'id': 'tu1', 'name': 'list_study_areas', 'input': {}}], 'stop_reason': 'tool_use'}
            tr = body['messages'][-1]['content'][0]
            assert tr['type'] == 'tool_result' and tr['tool_use_id'] == 'tu1' and 'ประเทศไทย' in tr['content']
            assert body['messages'][-2]['role'] == 'assistant'
            return {'content': [{'type': 'text', 'text': 'มีพื้นที่ศึกษาประเทศไทย'}], 'stop_reason': 'end_turn'}
        if provider == 'gemini':
            decl = body['tools'][0]['functionDeclarations']
            assert all('parameters' not in d or d['parameters']['properties'] for d in decl)   # Gemini ไม่รับ object ว่าง
            if n == 0:
                return {'candidates': [{'content': {'role': 'model', 'parts': [{'functionCall': {'name': 'list_study_areas', 'args': {}}}]}}]}
            fr = body['contents'][-1]['parts'][0]['functionResponse']
            assert fr['name'] == 'list_study_areas' and 'ประเทศไทย' in fr['response']['result']
            return {'candidates': [{'content': {'parts': [{'text': 'มีพื้นที่ศึกษาประเทศไทย'}]}}]}
        if n == 0:
            return {'choices': [{'message': {'role': 'assistant', 'content': None, 'tool_calls': [
                {'id': 'c1', 'type': 'function', 'function': {'name': 'list_study_areas', 'arguments': '{}'}}]}}]}
        t = body['messages'][-1]
        assert t['role'] == 'tool' and t['tool_call_id'] == 'c1' and 'ประเทศไทย' in t['content']
        return {'choices': [{'message': {'role': 'assistant', 'content': 'มีพื้นที่ศึกษาประเทศไทย'}}]}
    return _req


ok = True
for prov in ('anthropic', 'gemini', 'openai'):
    ai.cfg = lambda prov=prov: dict(enabled=True, provider=prov, model='m', mode='propose', secret_id='x')
    ai._key = lambda c=None: 'k'
    ai.status = lambda: dict(connected=True)
    ai._req = fake(prov)
    try:
        r = ai.chat([dict(role='user', content='มีพื้นที่ศึกษาอะไรบ้าง')])
        good = 'ประเทศไทย' in r['reply'] and [u['tool'] for u in r['used']] == ['list_study_areas']
    except AssertionError as e:
        good, r = False, dict(reply=f'assert: {e}')
    ok &= good
    print('✔' if good else '✘', prov, '→', r['reply'].replace('\n', ' / ')[:80])
print('\nผล:', 'ผ่าน' if ok else 'ล้ม')
raise SystemExit(0 if ok else 1)
