# -*- coding: utf-8 -*-
"""เก็บโทเคน/รหัสของบริการแผนที่อย่างปลอดภัย (3.3)
Windows: เข้ารหัสด้วย DPAPI (CryptProtectData) — ถอดได้เฉพาะบัญชี Windows เดียวกันบนเครื่องนี้
ไฟล์ workspace/secrets.json เก็บเฉพาะข้อความที่เข้ารหัสแล้ว · ไม่ลง lineage / log / catalog"""
import base64
import ctypes
import json
import os
import secrets as _sec
from ctypes import wintypes

from .config import WORKSPACE

PATH = WORKSPACE / 'secrets.json'


class _BLOB(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]


def _blob(b):
    buf = ctypes.create_string_buffer(b, len(b))
    return _BLOB(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def _protect(data: bytes, encrypt=True) -> bytes:
    if os.name != 'nt':
        raise RuntimeError('ที่เก็บโทเคนแบบเข้ารหัสรองรับเฉพาะ Windows')
    fn = ctypes.windll.crypt32.CryptProtectData if encrypt else ctypes.windll.crypt32.CryptUnprotectData
    src, _keep = _blob(data)
    out = _BLOB()
    if not fn(ctypes.byref(src), None, None, None, None, 0x1, ctypes.byref(out)):   # CRYPTPROTECT_UI_FORBIDDEN
        raise RuntimeError('เข้ารหัส/ถอดรหัสโทเคนไม่ได้')
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def _load():
    try:
        return json.loads(PATH.read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        return {}


def _save(d):
    PATH.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding='utf-8')


def put(name, value):
    d = _load()
    sid = _sec.token_hex(6)
    d[sid] = dict(name=name, data=base64.b64encode(_protect(value.encode('utf-8'))).decode())
    _save(d)
    return sid


def get(sid):
    if not sid:
        return None
    e = _load().get(sid)
    return _protect(base64.b64decode(e['data']), False).decode('utf-8') if e else None


def listing():
    return [dict(id=k, name=v['name']) for k, v in _load().items()]


def delete(sid):
    d = _load()
    d.pop(sid, None)
    _save(d)
