# -*- coding: utf-8 -*-
"""ไล่เก็บรายการไฟล์รายปีของ Data hub ล่วงหน้า → web/hub/files_extra.json

ชุดที่ต้นทางลงทะเบียนเป็น ZIP ก้อนใหญ่ แต่เซิร์ฟเวอร์เปิดรายชื่อโฟลเดอร์ (เช่น WorldPop):
ใช้ app.hub_browse เดินโฟลเดอร์ข้าง ZIP → ได้ GeoTIFF แยกรายปี/รายตัวแปร ให้หน้าเว็บโชว์ลิงก์ได้ทันที
โดยไม่ต้องกด "ดูไฟล์" ทีละชุด (ผลถูกแคช 7 วันโดย hub_browse — รันซ้ำได้ เร็วขึ้นเรื่อย ๆ)

รัน:  python\\python.exe tools\\build_files_extra.py        (ในโฟลเดอร์แอป · ต้องต่อเน็ต)
"""
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import hub_browse                                   # noqa: E402
from app.config import ensure_workspace                      # noqa: E402

DL = re.compile(r'\.(tif|tiff)(/content)?(\?|$)|\.(geo)?json(\?|$)', re.I)
ZIP = re.compile(r'\.zip(\?|$)', re.I)
YEAR = re.compile(r'(?<!\d)(19[5-9]\d|20[0-4]\d)(?:0101)?(?!\d)')
HUB = ROOT / 'web' / 'hub'
OUT = HUB / 'files_extra.json'
MAX_ZIP_PER_ITEM = 24            # เท่ากติกาของ _hub_files ใน ai_tools
MAX_FILES_PER_ITEM = 1500


def _year(name):
    m = YEAR.search(name or '')
    return int(m.group(1)) if m else None


def load_hub():
    idx = json.loads((HUB / 'index.json').read_text(encoding='utf-8'))
    desc = {}
    for i in range(32):
        p = HUB / f'desc_{i:02d}.json'
        if not p.exists():
            break
        desc.update(json.loads(p.read_text(encoding='utf-8')))
    return idx, desc


def candidates(idx, desc):
    """ชุดที่มี ZIP แต่ไฟล์ raster ตรง < 5 — โฟลเดอร์ข้าง ZIP อาจมีไฟล์แยก"""
    out = []
    for it in idx['items']:
        rs = (desc.get(it['k']) or {}).get('resources') or []
        urls = [r.get('url') or '' for r in rs if not r.get('key')]
        tifs = [u for u in urls if DL.search(u)]
        zips = [r for r in rs if ZIP.search(r.get('url') or '') and not r.get('key')]
        if zips and len(tifs) < 5:
            out.append((it['k'], zips, set(tifs)))
    return out


def crawl_one(key, zips, have):
    pick = zips[:MAX_ZIP_PER_ITEM]
    try:
        got = hub_browse.expand([z['url'] for z in pick])
    except Exception as e:
        return key, None, f'{type(e).__name__}: {e}'
    files, seen = [], set(have)
    for z in pick:
        zy = _year(z.get('name') or z['url'])
        for f in got.get(z['url']) or []:
            if f['url'] in seen:
                continue
            seen.add(f['url'])
            files.append(dict(name=f['name'], url=f['url'], year=_year(f['name']) or zy,
                              size_mb=f.get('size_mb'), from_zip=z.get('name')))
            if len(files) >= MAX_FILES_PER_ITEM:
                return key, files, 'ตัดที่เพดานไฟล์ต่อชุด'
    return key, files, None


BUDGET_S = int(os.environ.get('AINU_BUILD_BUDGET_S', 18 * 60))   # เพดานเวลารวม — ครบแล้วเขียนเท่าที่ได้ (แหล่งที่ค้างถูกข้าม · แคช 7 วันทำให้รันรอบหน้าเก็บต่อได้)


def write_out(cands, items, skipped=0):
    total = sum(len(v) for v in items.values())
    out = dict(meta=dict(built=time.strftime('%Y-%m-%d'), sources_checked=len(cands), sources_with_files=len(items),
                         files=total, skipped=skipped,
                         note='ไฟล์แยกจากโฟลเดอร์ต้นทางข้าง ZIP (hub_browse) — สร้างด้วย tools/build_files_extra.py'),
               items=items)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    return total


def main():
    ensure_workspace()                                       # hub_browse ใช้แคชใน workspace/cache
    idx, desc = load_hub()
    cands = candidates(idx, desc)
    print(f'เข้าข่ายไล่จากโฟลเดอร์ข้าง ZIP: {len(cands)} ชุด · เพดานเวลา {BUDGET_S // 60} นาที')
    items, notes, t0 = {}, {}, time.time()
    done = 0
    ex = ThreadPoolExecutor(max_workers=8)
    futs = {ex.submit(crawl_one, k, z, h): k for k, z, h in cands}
    try:
        for fu in as_completed(futs, timeout=BUDGET_S):
            key, files, note = fu.result()
            done += 1
            if files:
                items[key] = files
            if note:
                notes[key] = note
            if files or done % 25 == 0:
                print(f'[{done}/{len(cands)}] {key}: {len(files or [])} ไฟล์' + (f' · {note}' if note else ''), flush=True)
            if done % 20 == 0:
                write_out(cands, items, len(cands) - done)   # เขียนเป็นระยะ — โดนตัดกลางทางก็ยังมีผล
    except TimeoutError:
        left = [k for fu, k in futs.items() if not fu.done()]
        print(f'ครบเพดานเวลา — ข้าม {len(left)} ชุดที่ยังไม่ตอบ: {left[:6]}', flush=True)
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    total = write_out(cands, items, len(cands) - done)
    print(f'\nเก็บได้ {len(items)} ชุด · {total:,} ไฟล์ → {OUT} ({OUT.stat().st_size / 1e6:.2f} MB) · ใช้เวลา {time.time() - t0:,.0f} วินาที')
    if notes:
        print('หมายเหตุ:', json.dumps(notes, ensure_ascii=False)[:600])


if __name__ == '__main__':
    main()
