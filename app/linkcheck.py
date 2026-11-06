# -*- coding: utf-8 -*-
"""ตรวจลิงก์ของ Data hub จากเครื่องผู้ใช้ (หน้าเว็บตรวจข้ามโดเมนเองไม่ได้เพราะ CORS)

กันใช้เป็นช่องยิงเข้าเครือข่ายภายใน: รับเฉพาะ http/https · ทุกปลายทาง (รวมทุกขั้นที่ redirect) ต้องเป็น IP สาธารณะ
อ่านแค่ส่วนหัว (HEAD → ถ้าเว็บไม่รับค่อย GET แบบไม่โหลดเนื้อหา)
"""
import concurrent.futures as cf
import ipaddress
import socket
import time
from urllib.parse import urljoin, urlparse

import requests

UA = {'User-Agent': 'Ainulindale-DataHub-linkcheck/1.0 (+https://github.com/nattakitNams/project-ainulindale-demo)'}
MAX_URLS = 40
TIMEOUT = 12


class Blocked(Exception):
    pass


def _public(host):
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise Blocked('หาโดเมนไม่เจอ (DNS)')
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split('%')[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise Blocked('ปลายทางเป็นเครือข่ายภายใน — ไม่ตรวจ')


def _hop(s, method, url):
    u = urlparse(url)
    if u.scheme not in ('http', 'https') or not u.hostname:
        raise Blocked('รับเฉพาะลิงก์ http/https')
    _public(u.hostname)
    return s.request(method, url, timeout=TIMEOUT, allow_redirects=False, stream=True)


def check(url):
    t0 = time.time()
    out = dict(url=url)
    s = requests.Session()
    s.headers.update(UA)
    try:
        for method in ('HEAD', 'GET'):
            cur, hops = url, 0
            while True:
                try:
                    r = _hop(s, method, cur)
                except Blocked as e:
                    if hops:                                # ต้นทางส่งต่อ (redirect) ไปที่อยู่ภายใน เช่น http://localhost/… = เว็บต้นทางตั้งค่าผิด
                        raise Blocked(f'เว็บต้นทางส่งต่อไปที่อยู่ภายใน ({cur[:80]}) — ลิงก์น่าจะผิด (ลองเติม / ท้ายลิงก์)')
                    raise
                r.close()
                if r.is_redirect and hops < 6:
                    cur = urljoin(cur, r.headers.get('Location', ''))
                    hops += 1
                    continue
                break
            if method == 'HEAD' and r.status_code in (400, 403, 404, 405, 406, 429, 500, 501, 503):
                continue                                    # หลายเว็บไม่รับ HEAD → ลอง GET (อ่านแค่ส่วนหัว)
            break
        code = r.status_code
        out.update(status=code, final=cur if cur != url else None,
                   state='ok' if code < 400 else 'warn' if code in (401, 403, 429) else 'bad',
                   note={401: 'ต้องล็อกอิน', 403: 'เว็บปฏิเสธโปรแกรมตรวจ (เปิดด้วยเบราว์เซอร์อาจได้)', 429: 'เว็บจำกัดจำนวนครั้ง ลองใหม่ภายหลัง',
                         404: 'ไม่พบหน้า (ลิงก์อาจย้าย)'}.get(code))
    except Blocked as e:
        out.update(state='bad', status=None, note=str(e))
    except requests.Timeout:
        out.update(state='bad', status=None, note=f'ไม่ตอบใน {TIMEOUT} วินาที')
    except requests.RequestException as e:
        out.update(state='bad', status=None, note=f'เชื่อมต่อไม่ได้ ({type(e).__name__})')
    out['ms'] = int((time.time() - t0) * 1000)
    return out


def check_many(urls):
    urls = [u for u in dict.fromkeys(urls or []) if isinstance(u, str)][:MAX_URLS]
    with cf.ThreadPoolExecutor(8) as ex:
        return list(ex.map(check, urls))
