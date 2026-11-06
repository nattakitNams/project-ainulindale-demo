# -*- coding: utf-8 -*-
"""สร้าง Data hub (web/hub/) จากแคตตาล็อกรายชื่อดาต้าเซ็ต — ไม่เก็บไฟล์ข้อมูล เก็บแค่ "ใครมีอะไร อยู่ที่ไหน"

คำอธิบายของแต่ละชุด **ไม่เขียนเอง** — ดึงจากต้นทางพร้อมบอกที่มา:
  Planetary Computer → STAC API ของ Microsoft (description ทางการ)
  Earth Engine       → แคตตาล็อก STAC ของ Google (description + citation + terms of use)
  แหล่งอื่น/แพลตฟอร์ม → Wikipedia (REST summary, CC BY-SA) ถ้ามีบทความ ไม่มี → meta description ที่หน้าเว็บผู้ผลิตเขียนเอง

    python tools/build_hub.py --xlsx <catalog.xlsx>      # แปลงไฟล์แคตตาล็อกเป็น tools/hub_source.json แล้วสร้าง
    python tools/build_hub.py                            # สร้างใหม่จาก tools/hub_source.json (แคชคำตอบไว้ที่ --cache)
"""
import argparse
import concurrent.futures as cf
import hashlib
import html
import json
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'tools' / 'hub_source.json'
CURATED = ROOT / 'tools' / 'hub_curated.json'
OUT = ROOT / 'web' / 'hub'
UA = {'User-Agent': 'Ainulindale-DataHub-builder/1.0 (+https://github.com/nattakitNams/project-ainulindale-demo)'}
TH_BBOX = (97.3, 5.6, 105.7, 20.5)
SHARD = 100

# ---------- หมวดหมู่ (ชุดเดียวกันทุกแหล่ง · ชุดหนึ่งอยู่ได้หลายหมวด) ----------
THEMES = [
    ('pop', 'ประชากรและการตั้งถิ่นฐาน', 'Population & settlement'),
    ('lulc', 'การใช้ที่ดิน / สิ่งปกคลุมดิน', 'Land use / land cover'),
    ('forest', 'ป่าไม้ ระบบนิเวศ และความหลากหลายทางชีวภาพ', 'Forest, ecosystems & biodiversity'),
    ('agri', 'เกษตรและพืชพรรณ', 'Agriculture & vegetation'),
    ('water', 'น้ำและอุทกวิทยา', 'Water & hydrology'),
    ('climate', 'ภูมิอากาศและสภาพอากาศ', 'Climate & weather'),
    ('atmos', 'บรรยากาศและคุณภาพอากาศ', 'Atmosphere & air quality'),
    ('elev', 'ความสูงและภูมิประเทศ', 'Elevation & terrain'),
    ('soil', 'ดินและธรณี', 'Soil & geology'),
    ('ocean', 'ทะเลและชายฝั่ง', 'Ocean & coast'),
    ('cryo', 'น้ำแข็งและหิมะ', 'Snow & ice'),
    ('hazard', 'ภัยพิบัติและไฟ', 'Hazards & fire'),
    ('imagery', 'ภาพดาวเทียมและภาพถ่ายทางอากาศ', 'Satellite & aerial imagery'),
    ('base', 'ขอบเขต โครงสร้างพื้นฐาน และแผนที่ฐาน', 'Boundaries, infrastructure & basemaps'),
    ('socio', 'สังคม เศรษฐกิจ และสถิติ', 'Socio-economic & statistics'),
    ('hist', 'แผนที่และภาพเก่า', 'Historical maps & imagery'),
]
# หมวดในไฟล์แคตตาล็อก → หมวดใหม่
CAT_MAP = {
    'ประชากร': ['pop'], 'โครงสร้างพื้นฐาน/ประชากร': ['pop', 'base'], 'โครงสร้างพื้นฐาน/ขอบเขต': ['base'],
    'การใช้ที่ดิน/Land Cover': ['lulc'], 'Land Cover/ป่าไม้': ['lulc', 'forest'],
    'ป่าไม้/ชีวภาพ/ความหลากหลาย': ['forest'], 'ป่าไม้/ชีวมวล': ['forest'], 'ระบบนิเวศ': ['forest'],
    'เกษตร': ['agri'], 'ผลผลิตพืช': ['agri'], 'ดัชนีพืชพรรณ': ['agri'],
    'น้ำ': ['water'], 'น้ำผิวดิน/น้ำใต้ดิน': ['water'], 'ไอน้ำ': ['water'],
    'ภูมิอากาศ/อากาศ': ['climate'], 'ฝน': ['climate'], 'ภูมิอากาศ/ดิน/น้ำ': ['climate'],
    'บรรยากาศ': ['atmos'], 'ความสูง/ภูมิประเทศ': ['elev'], 'ความสูง': ['elev'], 'ดิน': ['soil'],
    'ทะเล/มหาสมุทร': ['ocean'], 'ทะเล': ['ocean'], 'น้ำแข็ง/หิมะ': ['cryo'], 'ไฟ': ['hazard'], 'ภัยพิบัติ': ['hazard'],
    'ภาพดาวเทียม': ['imagery'], 'ภาพดาวเทียม/ผลิตภัณฑ์จากดาวเทียม': ['imagery'], 'ภาพถ่ายทางอากาศ': ['imagery'],
    'ขอบเขตและข้อมูลพื้นฐาน': ['base'], 'ประวัติศาสตร์': ['hist'], 'ประเทศไทย': [], 'อื่น ๆ': [],
}
# คำในชื่อ/คีย์เวิร์ดจากต้นทาง → หมวดเพิ่ม (ช่วยให้ค้นเจอข้ามหมวด เช่น night light อยู่ทั้งภาพดาวเทียมและประชากร)
KW_RULES = [
    ('pop', r'\bpopulation|worldpop|settlement|built.?up|\bghsl|night.?(time)?.?light|\bviirs\b.*(night|dnb)|\bvnl\b|urban|building'),
    ('lulc', r'land.?cover|land.?use|\blulc\b|worldcover|dynamic world|impervious'),
    ('forest', r'forest|tree|mangrove|biomass|canopy|biodiversity|habitat|protected area|ecosystem|wetland'),
    ('agri', r'\bcrop|agricultur|\bndvi\b|\bevi\b|vegetation|phenolog|cropland|irrigat|\blai\b|\bfpar\b'),
    ('water', r'surface water|water occurrence|river|lake|reservoir|hydro|basin|groundwater|evapotrans|\bgrace\b|streamflow|runoff'),
    ('climate', r'climate|precipitation|rainfall|\bchirps\b|temperature|\bera5\b|reanalysis|weather|\bcmip\d?|\bgldas\b|\bnldas\b|wind'),
    ('atmos', r'aerosol|\bno2\b|ozone|\bso2\b|methane|\bco2\b|air quality|pm2\.?5|sentinel.?5p|tropomi|\bco\b column|atmospher'),
    ('elev', r'\bdem\b|elevation|terrain|topograph|\bsrtm\b|bathymetr|\bdsm\b|\bdtm\b|lidar|\b3dep\b|copernicus dem|\bnasadem\b|\bfabdem\b'),
    ('soil', r'\bsoil|geolog|lithol'),
    ('ocean', r'ocean|\bsea\b|marine|coral|\bsst\b|chlorophyll|coast|tide|reef'),
    ('cryo', r'snow|\bice\b|glacier|permafrost|sea ice'),
    ('hazard', r'\bfire|burn|flood|drought|earthquake|landslide|hazard|disaster|cyclone|hurricane'),
    ('imagery', r'landsat|sentinel.?[12]\b|sentinel-1|sentinel-2|\bmodis\b.*reflectance|surface reflectance|\bnaip\b|aerial|orthophoto|\bhls\b|planet|aster\b|\bsar\b|radar'),
    ('base', r'boundar|administrative|\broad|openstreetmap|\bosm\b|building footprint|infrastructure|overture|gadm|admin'),
    ('socio', r'poverty|economic|\bgdp\b|indicator|statistic|census|accessibility|travel time|health'),
    ('hist', r'histor|declassified|\bcorona\b|scanned map'),
]
TYPE_NORM = [
    ('timeseries', r'ชุดภาพหลายช่วงเวลา'), ('multidim', r'multidimensional|netcdf|zarr'), ('pointcloud', r'point cloud'),
    ('table', r'bigquery|^ตาราง|ฟีด'), ('service', r'^service'), ('scan', r'สแกน'),
    ('vector', r'^vector'), ('raster', r'^raster'),
]
TYPE_LABEL = {'raster': 'Raster', 'timeseries': 'Raster หลายช่วงเวลา', 'vector': 'Vector', 'table': 'ตาราง/API', 'multidim': 'หลายมิติ (NetCDF/Zarr)',
              'pointcloud': 'Point cloud', 'service': 'บริการแผนที่ (Service)', 'scan': 'ภาพ/แผนที่สแกน'}
OPEN = {'CC0-1.0', 'PDDL-1.0', 'CC-BY-4.0', 'CC-BY-SA-4.0', 'ODbL-1.0', 'OGL-Canada-2.0', 'CDLA-Permissive-1.0', 'CDLA-Sharing-1.0', 'etalab-2.0'}
NC = {'CC-BY-NC-4.0', 'CC-BY-NC-SA-4.0', 'proprietary_non_commercial'}


def norm_type(t):
    t = (t or '').strip().lower()
    for k, pat in TYPE_NORM:
        if re.search(pat, t, re.I):
            return k
    return 'raster' if 'raster' in t else 'vector' if 'vector' in t else 'table'


def lic_class(lic):
    if not lic:
        return 'check'
    if lic in OPEN:
        return 'open'
    if lic in NC:
        return 'nc'
    return 'check'          # proprietary / other = ต้องอ่านเงื่อนไขของผู้ผลิต (ไม่ได้แปลว่าปิด)


# ---------- แคตตาล็อกต้นทาง ----------
def from_xlsx(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True)
    out = {}
    for sh in ('Platforms', 'PC_Datasets', 'GEE_Datasets', 'Other_Sources'):
        rows = [r for r in wb[sh].iter_rows(values_only=True) if any(c is not None for c in r)]
        hdr = rows[0]
        out[sh] = [{h: (v.strip() if isinstance(v, str) else v) for h, v in zip(hdr, r)} for r in rows[1:]]
    SRC.write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding='utf-8')
    print(f'แปลง {path} → {SRC.relative_to(ROOT)}')
    return out


# ---------- ดึงคำอธิบายจากต้นทาง (แคชไว้ ดึงซ้ำไม่ต้องยิงใหม่) ----------
class Fetch:
    def __init__(self, cache):
        self.dir = Path(cache)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.s = requests.Session()
        self.s.headers.update(UA)

    def get(self, url, kind='json'):
        f = self.dir / (hashlib.sha1(url.encode()).hexdigest() + '.json')
        if f.exists():
            return json.loads(f.read_text(encoding='utf-8'))
        res = dict(url=url, status=None, body=None)
        for attempt in range(3):
            try:
                r = self.s.get(url, timeout=30)
                res['status'] = r.status_code
                if r.ok:
                    if kind == 'json':
                        res['body'] = r.json()
                    else:
                        r.encoding = r.encoding if r.encoding and r.encoding.lower() != 'iso-8859-1' else r.apparent_encoding
                        res['body'] = r.text[:400_000]
                break
            except (requests.RequestException, ValueError) as e:
                res['status'] = f'error: {type(e).__name__}'
                time.sleep(1.5 * (attempt + 1))
        f.write_text(json.dumps(res, ensure_ascii=False), encoding='utf-8')
        return res


def gee_stac_url(did):
    p = did.split('/')
    folder = p[1] if p[0] == 'projects' else p[0]          # ชุดของชุมชน projects/<ผู้ให้>/... อยู่ในโฟลเดอร์ของผู้ให้
    return f'https://storage.googleapis.com/earthengine-stac/catalog/{folder}/{did.replace("/", "_")}.json'


def pc_stac_url(did):
    return f'https://planetarycomputer.microsoft.com/api/stac/v1/collections/{did}'


def wiki_url(ref):
    lang, title = ref.split(':', 1)
    return lang, f'https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(" ", "_"), safe="")}'


def meta_description(page):
    """<meta name=description> / og:description ที่ผู้ผลิตเขียนเองในหน้าเว็บ"""
    for pat in (r'<meta[^>]+(?:name|property)=["\'](?:og:)?description["\'][^>]*content=["\']([^"\']{20,})["\']',
                r'<meta[^>]+content=["\']([^"\']{20,})["\'][^>]*(?:name|property)=["\'](?:og:)?description["\']'):
        m = re.search(pat, page, re.I)
        if m:
            s = html.unescape(m.group(1)).replace('‍', '').strip()
            title = re.search(r'<title[^>]*>([^<]*)</title>', page, re.I)
            if len(s) < 50 or (title and s.lower() in html.unescape(title.group(1)).lower()):
                return None                              # สั้นไป / ซ้ำชื่อเว็บ = ไม่ใช่คำอธิบาย
            return s
    return None


def _similar(a, b):
    """ชื่อในแคตตาล็อกกับชื่อบทความ Wikipedia เป็นเรื่องเดียวกันไหม (ไม่ใช่บทความของหน่วยงานแม่ที่ redirect ไป)"""
    wa = set(re.findall(r'[a-z0-9]{3,}|[ก-๙]{3,}', a.lower()))
    wb = set(re.findall(r'[a-z0-9]{3,}|[ก-๙]{3,}', b.lower()))
    ab = re.sub(r'[^A-Z]', '', b)
    return bool(wa & wb) or (len(ab) >= 3 and ab.lower() in a.lower().replace('-', ''))


def bbox_of(stac):
    try:
        b = stac['extent']['spatial']['bbox'][0]
        return [round(float(v), 3) for v in b[:2] + b[-3:-1]] if len(b) == 6 else [round(float(v), 3) for v in b]
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def covers(b):
    if not b:
        return None
    return 'global' if (b[2] - b[0]) >= 300 and (b[3] - b[1]) >= 120 else (
        'thailand' if b[0] <= TH_BBOX[2] and b[2] >= TH_BBOX[0] and b[1] <= TH_BBOX[3] and b[3] >= TH_BBOX[1] else 'other')


def gsd_of(stac):
    s = stac.get('summaries') or {}
    g = s.get('gsd')
    if isinstance(g, list) and g:
        try:
            v = sorted({float(x) for x in g})
            return v
        except (TypeError, ValueError):
            return None
    return None


def interval_of(stac):
    i = stac.get('gee:interval')
    if isinstance(i, dict) and i.get('interval'):
        u = {'day': 'วัน', 'month': 'เดือน', 'year': 'ปี', 'hour': 'ชั่วโมง', 'minute': 'นาที', 'week': 'สัปดาห์'}.get(i.get('unit'), i.get('unit'))
        return f'ทุก {i["interval"]} {u}'
    return None


def themes_for(cats, text):
    out = []
    for c in cats:
        for t in CAT_MAP.get(c, []):
            if t not in out:
                out.append(t)
    low = text.lower()
    for t, pat in KW_RULES:
        if t not in out and re.search(pat, low):
            out.append(t)
    return out or ['base']


def build(src, fetch):
    cur = json.loads(CURATED.read_text(encoding='utf-8'))
    recs = []
    jobs = []
    for r in src['PC_Datasets']:
        jobs.append(('pc', r, pc_stac_url(r['Dataset ID']), 'json'))
    for r in src['GEE_Datasets']:
        jobs.append(('gee', r, gee_stac_url(r['Dataset ID']), 'json'))
    for sh, kind in (('Other_Sources', 'other'), ('Platforms', 'platform')):
        for r in src[sh]:
            name = r.get('ชื่อดาต้าเซ็ต') or r.get('ชื่อ')
            ref = cur['wiki'].get(name)
            jobs.append((kind, r, wiki_url(ref)[1] if ref else r['ลิงก์'], 'json' if ref else 'html'))
    print(f'ดึงข้อมูลประกอบ {len(jobs):,} รายการ (แคช: {fetch.dir})')
    with cf.ThreadPoolExecutor(8) as ex:
        got = list(ex.map(lambda j: fetch.get(j[2], j[3]), jobs))
    # Wikipedia ไม่มีบทความ → ใช้ meta description ของหน้าเว็บผู้ผลิต
    for i, (kind, r, url, k) in enumerate(jobs):
        if k == 'json' and kind in ('other', 'platform') and not (got[i].get('body') or {}).get('extract'):
            jobs[i] = (kind, r, r['ลิงก์'], 'html')
            got[i] = fetch.get(r['ลิงก์'], 'html')

    stats = dict(pc=0, gee=0, wiki=0, site=0, none=0)
    for (kind, r, url, k), g in zip(jobs, got):
        body = g.get('body')
        rec = dict(platform={'pc': 'Microsoft Planetary Computer', 'gee': 'Google Earth Engine'}.get(kind, r.get('แพลตฟอร์ม') or ''),
                   src=kind)
        desc = None
        if kind in ('pc', 'gee'):
            did = r['Dataset ID']
            stac = body if isinstance(body, dict) else {}
            rec.update(id=did, title=r['ชื่อดาต้าเซ็ต'], provider=r.get('องค์กรผู้ผลิต/ผู้ให้บริการ') or '', type=norm_type(r.get('ประเภทข้อมูล')),
                       type_raw=r.get('ประเภทข้อมูล'), start=(r.get('เริ่ม') or '')[:10] or None, end=(r.get('สิ้นสุด') or '')[:10] or None,
                       license=r.get('License') or stac.get('license'), url=r['ลิงก์'], meta_url=url,
                       cats_src=[c.strip() for c in (r.get('หมวดหมู่') or '').split(',') if c.strip()])
            if stac:
                desc = dict(text=stac.get('description'), fmt='md', source='STAC ของ ' + ('Microsoft Planetary Computer' if kind == 'pc' else 'Google Earth Engine'),
                            source_url=url, license_note='ข้อมูลประกอบทางการที่ผู้ให้บริการเผยแพร่')
                rec['keywords'] = [str(x) for x in (stac.get('keywords') or [])][:20]
                rec['bbox'] = bbox_of(stac)
                rec['gsd'] = gsd_of(stac)
                rec['cadence'] = interval_of(stac)
                rec['providers'] = [dict(name=p.get('name'), url=p.get('url'), roles=p.get('roles')) for p in (stac.get('providers') or []) if p.get('name')][:6]
                rec['deprecated'] = stac.get('gee:status') == 'deprecated' or bool(re.search(r'deprecated|will be retired|has been retired', stac.get('description') or '', re.I))
                if stac.get('sci:citation'):
                    rec['citation'] = stac['sci:citation']
                if stac.get('gee:terms_of_use'):
                    rec['terms'] = stac['gee:terms_of_use']
                if kind == 'pc' and stac.get('msft:short_description'):
                    rec['short'] = stac['msft:short_description']
                stats[kind] += 1
            else:
                rec['meta_status'] = g.get('status')
                stats['none'] += 1
        else:
            name = r.get('ชื่อดาต้าเซ็ต') or r.get('ชื่อ')
            rec.update(id=None, title=name, provider=r.get('องค์กรผู้ผลิต') or r.get('องค์กรเจ้าของ') or '',
                       type='platform' if kind == 'platform' else norm_type(r.get('ประเภทข้อมูล')), type_raw=r.get('ประเภทข้อมูล') or r.get('ชนิด'),
                       license=None, url=r['ลิงก์'], cats_src=[r['หมวดหมู่']] if r.get('หมวดหมู่') else [],
                       platform=name if kind == 'platform' else 'แหล่งผู้ผลิตโดยตรง')
            if kind == 'platform':
                rec['note'] = r.get('สถานะในไฟล์นี้')
            cv = cur['cover'].get(name) or cur['cover'].get(r.get('หมวดหมู่') or '') or 'global'
            rec['cover'] = cv
            if k == 'json' and isinstance(body, dict) and body.get('extract'):
                lang = 'th' if url.startswith('https://th.') else 'en'
                page = (body.get('content_urls') or {}).get('desktop', {}).get('page') or url
                wt = body.get('title') or ''
                desc = dict(text=body['extract'], fmt='text', source=f'Wikipedia ({lang}) — {wt}', source_url=page,
                            license_note='CC BY-SA 4.0 · ข้อความจาก Wikipedia',
                            about=None if _similar(name, wt) or name in cur.get('wiki_direct', []) else f'บทความนี้เกี่ยวกับ "{wt}" (หน่วยงาน/โครงการ/อุปกรณ์ที่เกี่ยวข้อง) ไม่ใช่คำอธิบายของชุดข้อมูลโดยตรง')
                stats['wiki'] += 1
            elif k == 'html' and isinstance(body, str) and (md := meta_description(body)):
                desc = dict(text=md, fmt='text', source='คำอธิบายที่หน้าเว็บผู้ผลิต', source_url=r['ลิงก์'], license_note='ข้อความโดยเจ้าของเว็บไซต์')
                stats['site'] += 1
            else:
                stats['none'] += 1
        text = ' '.join([rec['title'] or '', rec.get('provider') or '', ' '.join(rec.get('keywords') or []), rec.get('id') or ''])
        rec['themes'] = themes_for(rec['cats_src'], text)
        if 'cover' not in rec:
            rec['cover'] = covers(rec.get('bbox')) or 'unknown'
        rec['lic'] = lic_class(rec.get('license')) if kind not in ('other', 'platform') else 'check'
        rec['desc'] = desc
        rec['key'] = (kind + ':' + (rec['id'] or rec['title'])).lower()
        rec['key'] = re.sub(r'[^0-9a-zก-๙:._-]+', '-', rec['key']).strip('-')
        recs.append(rec)
    return recs, stats


def write(recs, stats):
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob('desc_*.json'):
        f.unlink()
    for r in recs:                                       # ชื่อจากต้นทางบางชุดมี HTML entity (เช่น 0.05&deg;)
        r['title'] = html.unescape(r['title'] or '')
    order = {'other': 0, 'platform': 1, 'pc': 2, 'gee': 3}
    recs.sort(key=lambda r: (order[r['src']], (r['title'] or '').lower()))
    index, shards = [], {}
    for i, r in enumerate(recs):
        sh = i // SHARD
        shards.setdefault(sh, {})[r['key']] = dict(desc=r.get('desc'), citation=r.get('citation'), terms=r.get('terms'),
                                                     providers=r.get('providers'), keywords=r.get('keywords'))
        has = bool(r.get('desc') and r['desc'].get('text'))
        index.append({k: v for k, v in dict(
            k=r['key'], t=r['title'], id=r.get('id'), p=r['platform'], s=r['src'], pr=r.get('provider'), ty=r['type'], tr=r.get('type_raw'),
            th=r['themes'], a=r.get('start'), b=r.get('end'), l=r.get('license'), lc=r['lic'], u=r['url'], m=r.get('meta_url'),
            bb=r.get('bbox'), cv=r['cover'], g=r.get('gsd'), cd=r.get('cadence'), dp=r.get('deprecated') or None, sh=sh, d=has or None,
            sd=r.get('short'), n=r.get('note'), kw=(r.get('keywords') or [])[:8] or None).items() if v not in (None, [], '')})
    for sh, d in shards.items():
        (OUT / f'desc_{sh:02d}.json').write_text(json.dumps(d, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    meta = dict(built=date.today().isoformat(), count=len(recs), stats=stats,
                themes=[dict(k=k, th=t, en=e) for k, t, e in THEMES], types=TYPE_LABEL,
                platforms=sorted({r['platform'] for r in recs}),
                credits=[
                    'รายชื่อ collection: Planetary-Computer-Catalog และ Earth-Engine-Catalog (giswqs บน GitHub)',
                    'คำอธิบาย Planetary Computer: STAC API ของ Microsoft · Earth Engine: แคตตาล็อก STAC ของ Google (earthengine-catalog)',
                    'คำอธิบายจาก Wikipedia ใช้ภายใต้ CC BY-SA 4.0 — ลิงก์ไปบทความต้นฉบับอยู่ในแต่ละรายการ',
                    'ตรวจเงื่อนไขการใช้ (License / Terms of use) ของแต่ละชุดที่ต้นทางก่อนนำไปใช้หรือเผยแพร่ซ้ำ'])
    (OUT / 'index.json').write_text(json.dumps(dict(meta=meta, items=index), ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    sz = sum(f.stat().st_size for f in OUT.glob('*.json'))
    print(f'เขียน {len(recs):,} รายการ → {OUT.relative_to(ROOT)} ({sz / 1e6:.1f} MB) · คำอธิบาย: {stats}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--xlsx')
    ap.add_argument('--cache', default=str(ROOT / 'workspace' / 'cache' / 'hub_build'))
    a = ap.parse_args()
    src = from_xlsx(a.xlsx) if a.xlsx else json.loads(SRC.read_text(encoding='utf-8'))
    recs, stats = build(src, Fetch(a.cache))
    write(recs, stats)
