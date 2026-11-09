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
        if provider == 'openai-pro':                       # รุ่นที่ใช้ได้เฉพาะ Responses API: chat/completions ตอบ 404 → สลับไป /responses
            if url.endswith('/chat/completions'):
                raise ai.AiError('ผู้ให้บริการตอบ 404 — This is not a chat model and thus not supported in the v1/chat/completions endpoint. Did you mean to use v1/completions?')
            assert url.endswith('/responses') and body['instructions'] and body['tools'][0]['type'] == 'function' and 'name' in body['tools'][0]
            if not any(i.get('type') == 'function_call_output' for i in body['input']):
                return {'output': [{'type': 'reasoning', 'id': 'rs1', 'summary': []},
                                   {'type': 'function_call', 'id': 'fc1', 'call_id': 'call1', 'name': 'list_study_areas', 'arguments': '{}'}]}
            fo = [i for i in body['input'] if i.get('type') == 'function_call_output'][0]
            assert fo['call_id'] == 'call1' and 'ประเทศไทย' in fo['output'] and any(i.get('type') == 'reasoning' for i in body['input'])
            return {'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'มีพื้นที่ศึกษาประเทศไทย'}]}]}
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
ai.save = lambda **kw: None                                 # ไม่เขียน ai.json ของ workspace ทดสอบ
for prov in ('anthropic', 'gemini', 'openai', 'openai-pro'):
    ai.cfg = lambda prov=prov: dict(enabled=True, provider=prov.split('-')[0], model='m', mode='propose', secret_id='x')
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
