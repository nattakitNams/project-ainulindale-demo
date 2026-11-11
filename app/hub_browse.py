# -*- coding: utf-8 -*-
"""แตกไฟล์ย่อยจากโฟลเดอร์ต้นทางของ Data hub — ชุดที่ต้นทางลงทะเบียนไว้เป็น ZIP ก้อนใหญ่ แต่เซิร์ฟเวอร์เปิดรายชื่อโฟลเดอร์ (autoindex)

ตัวอย่างจริง: WorldPop "Age and Gender Structures (2015-2030)" บน HDX มีแค่ ZIP ปีละไฟล์ (100 ม. ~4.5 GB)
แต่ data.worldpop.org/…/2015/THA/v1/100m/constrained/ มี GeoTIFF แยกทุกช่วงอายุ/เพศ (tha_t_65_2015_…tif) ให้โหลดทีละไฟล์
→ ผู้ช่วยเลือกเฉพาะช่วงอายุที่ต้องการได้เอง ไม่ต้องโหลด ZIP ทั้งก้อน

ความปลอดภัย: เดินเฉพาะโฟลเดอร์ของ ZIP ที่อยู่ใน Data hub และโฟลเดอร์ลูก (ลึก ≤ 2 ชั้น) บนโฮสต์เดียวกัน · http(s) เท่านั้น
· จำกัดจำนวนหน้า/เวลา · แคชบนดิสก์ 7 วัน (รายชื่อไฟล์ ไม่ใช่ตัวไฟล์)"""
import hashlib
import json
import re
import threading
import time
from urllib.parse import urljoin, urlparse

from .config import DIRS

TTL = 7 * 86400
MAX_PAGES = 24
_mem, _lock = {}, threading.Lock()
TIF = re.compile(r'\.tiff?$', re.I)
HREF = re.compile(r'<a\s+[^>]*href="([^"?#][^"]*)"[^>]*>.*?</a>(.*)', re.I | re.S)
SIZE = re.compile(r'(?<![\d:.-])(\d+(?:\.\d+)?)\s*([KMG])\b', re.I)


def _cache_path(url):
    return DIRS['cache'] / 'hub_dirs' / (hashlib.sha1(url.encode()).hexdigest()[:20] + '.json')


def _rows(text):
    """แถวของหน้ารายชื่อ: แบบตาราง (<tr>) หรือแบบ <pre> (บรรทัดละไฟล์)"""
    if '<tr' in text.lower():
        return re.split('<tr[ >]', text, flags=re.I)
    return text.splitlines()


def listing(url, timeout=20):
    """รายชื่อในโฟลเดอร์ (autoindex ของ Apache/nginx) → [{name, url, dir, size_mb}] · ไม่ใช่หน้ารายชื่อ → []"""
    with _lock:
        hit = _mem.get(url)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    p = _cache_path(url)
    try:
        j = json.loads(p.read_text(encoding='utf-8'))
        if time.time() - j['t'] < TTL:
            with _lock:
                _mem[url] = (j['t'], j['items'])
            return j['items']
    except (OSError, ValueError, KeyError):
        pass
    import requests
    try:
        r = requests.get(url, timeout=timeout, headers={'User-Agent': 'Ainulindale/1 (hub browse)'})
    except requests.RequestException:
        return []
    if not r.ok or 'html' not in r.headers.get('content-type', ''):
        return []
    host = urlparse(url).netloc
    items, seen = [], set()
    for row in _rows(r.text):
        m = HREF.search(row)
        if not m:
            continue
        href, tail = m.group(1), re.sub(r'<[^>]+>', ' ', m.group(2))
        u = urljoin(url, href)
        if urlparse(u).netloc != host or not u.startswith(url) or u == url or u in seen:   # เฉพาะของในโฟลเดอร์นี้ (ไม่ขึ้นไปโฟลเดอร์แม่)
            continue
        seen.add(u)
        m = SIZE.search(tail or '')
        mb = None
        if m:
            mb = round(float(m.group(1)) * {'K': 1e-3, 'M': 1, 'G': 1e3}[m.group(2).upper()], 2)
        items.append(dict(name=u.rstrip('/').rsplit('/', 1)[-1], url=u, dir=u.endswith('/'), size_mb=mb))
    now = time.time()
    with _lock:
        _mem[url] = (now, items)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(dict(t=now, url=url, items=items), ensure_ascii=False), encoding='utf-8')
    except OSError:
        pass
    return items


def files_near(zip_url, depth=2):
    """GeoTIFF ในโฟลเดอร์เดียวกับ ZIP + โฟลเดอร์ลูก (ลึก ≤ depth) — ลำดับตามที่เซิร์ฟเวอร์แสดง"""
    if not re.match(r'^https?://', zip_url or ''):
        return []
    base = zip_url.rsplit('/', 1)[0] + '/'
    out, queue, pages = [], [(base, 0)], 0
    while queue and pages < MAX_PAGES:
        url, d = queue.pop(0)
        pages += 1
        for it in listing(url):
            if it['dir']:
                if d < depth:
                    queue.append((it['url'], d + 1))
            elif TIF.search(it['name']):
                out.append(dict(name=it['name'], url=it['url'], size_mb=it['size_mb'], folder=url))
    return out


def expand(zips, workers=6):
    """หลาย ZIP พร้อมกัน → {zip_url: [ไฟล์]} (เครือข่ายช้า → ขนาน · เคยดูแล้วมาจากแคช)"""
    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(min(workers, max(1, len(zips))), thread_name_prefix='hub-browse') as ex:
        return dict(zip(zips, ex.map(files_near, zips)))
