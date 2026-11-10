# -*- coding: utf-8 -*-
"""สร้าง Data hub (web/hub/) จากแคตตาล็อกรายชื่อดาต้าเซ็ต — ไม่เก็บไฟล์ข้อมูล เก็บแค่ "ใครมีอะไร อยู่ที่ไหน"

คำอธิบายของแต่ละชุด **ไม่เขียนเอง** — ดึงจากต้นทางพร้อมบอกที่มา:
  พอร์ทัลข้อมูลเปิด (CKAN: GISTDA, กรมพัฒนาที่ดิน, data.go.th, HDX) → แตกเป็นรายชุด + คำอธิบายที่ผู้ให้ข้อมูลเขียนในพอร์ทัล + รายการไฟล์
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
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import quote, urlencode

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
KW_RULES_TH = [
    ('pop', r'ประชากร|ครัวเรือน|ชุมชน|หมู่บ้าน|อาคาร|สิ่งปลูกสร้าง|เมือง|แสงไฟ|ผังเมือง'),
    ('lulc', r'การใช้ที่ดิน|สิ่งปกคลุม|ใช้ประโยชน์ที่ดิน'),
    ('forest', r'ป่า|ไม้|ชีวภาพ|สัตว์|อุทยาน|เขตรักษาพันธุ์|ป่าชายเลน|พื้นที่คุ้มครอง'),
    ('agri', r'เกษตร|ข้าว|นาข้าว|พืช|อ้อย|มันสำปะหลัง|ยางพารา|ปาล์ม|เพาะปลูก|ชลประทาน|ผลผลิต'),
    ('water', r'น้ำ|ลุ่มน้ำ|แม่น้ำ|อ่างเก็บ|เขื่อน|แหล่งน้ำ|บาดาล|คลอง'),
    ('climate', r'ฝน|อุณหภูมิ|ภูมิอากาศ|อากาศ|ลม|พายุ|ความชื้น'),
    ('atmos', r'ฝุ่น|pm ?2\.?5|คุณภาพอากาศ|มลพิษ|หมอกควัน'),
    ('elev', r'ความสูง|ระดับความสูง|ภูมิประเทศ|เส้นชั้นความสูง|ความลาดชัน'),
    ('soil', r'ดิน|ธรณี|แร่|หิน'),
    ('ocean', r'ทะเล|ชายฝั่ง|ปะการัง|กัดเซาะ|ประมง|หญ้าทะเล'),
    ('hazard', r'ภัย|ไฟป่า|จุดความร้อน|น้ำท่วม|อุทกภัย|ภัยแล้ง|แผ่นดินไหว|ดินถล่ม|เผา|พื้นที่เสี่ยง'),
    ('imagery', r'ภาพถ่าย|ดาวเทียม|ไทยโชต|ภาพจาก'),
    ('base', r'ขอบเขต|จังหวัด|อำเภอ|ตำบล|เทศบาล|ถนน|ทาง|สถานที่|ตั้ง|แผนที่ฐาน|โครงข่าย|สาธารณูปโภค|ไฟฟ้า|สถานี'),
    ('socio', r'สถิติ|เศรษฐกิจ|รายได้|ความยากจน|สุขภาพ|การศึกษา|โรงเรียน|โรงพยาบาล|ท่องเที่ยว|แรงงาน'),
]
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


def variables_of(stac):
    """ตัวแปร/แบนด์ของชุด (ให้ผู้ช่วยรู้ว่าชุดนี้มีอะไร หน่วยอะไร ต้องคูณสเกลไหม) — จาก eo:bands / gee:schema / item_assets"""
    s, out = stac.get('summaries') or {}, []
    for b in s.get('eo:bands') or []:
        if not isinstance(b, dict) or not b.get('name'):
            continue
        v = dict(name=b['name'], desc=(b.get('description') or '')[:160], unit=b.get('gee:units') or b.get('unit'),
                 scale=b.get('gee:scale'), offset=b.get('gee:offset'), gsd=(b.get('gsd') or [None])[0] if isinstance(b.get('gsd'), list) else b.get('gsd'))
        cls = b.get('gee:classes') or b.get('classification:classes')
        if cls:
            v['classes'] = '; '.join(f'{c.get("value")}={(c.get("description") or c.get("name") or "")[:40]}' for c in cls[:25])
        out.append(v)
    for b in s.get('gee:schema') or []:
        if isinstance(b, dict) and b.get('name'):
            out.append(dict(name=b['name'], desc=(b.get('description') or '')[:160], unit=b.get('units'), type=b.get('type'), field=True))
    for k, a in (stac.get('item_assets') or {}).items():
        if not isinstance(a, dict) or 'data' not in (a.get('roles') or []):
            continue
        rb = (a.get('raster:bands') or [{}])[0] if a.get('raster:bands') else {}
        eb = (a.get('eo:bands') or [{}])[0] if a.get('eo:bands') else {}
        out.append(dict(name=k, desc=(a.get('description') or a.get('title') or eb.get('description') or '')[:160], unit=rb.get('unit'),
                        scale=rb.get('scale'), offset=rb.get('offset'), dtype=rb.get('data_type'), nodata=rb.get('nodata'),
                        gsd=rb.get('spatial_resolution') or a.get('gsd')))
    return [{k: x for k, x in v.items() if x not in (None, '', [])} for v in out[:60]]


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
    for t, pat in KW_RULES + KW_RULES_TH:
        if t not in out and re.search(pat, low):
            out.append(t)
    return out or ['base']


# ---------- พอร์ทัลข้อมูลเปิด (CKAN) → รายชุด ----------
CKAN_VEC = {'shp', 'shapefile', 'geojson', 'kml', 'kmz', 'gpkg', 'geopackage', 'wfs', 'gml', 'gdb', 'file geodatabase'}
CKAN_RAS = {'geotiff', 'tiff', 'tif', 'tms', 'xyz', 'cog', 'netcdf', 'hdf', 'img'}
CKAN_SVC = {'wms', 'wmts', 'map', 'esri rest', 'arcgis geoservices rest api', 'api', 'url', 'html'}


def ckan_type(fmts):
    f = {x.strip().lower().lstrip('.') for x in fmts if x}
    if f & CKAN_VEC:
        return 'vector'
    if f & CKAN_RAS:
        return 'raster'
    if f & CKAN_SVC and not f & {'csv', 'xlsx', 'xls', 'json'}:
        return 'service'
    return 'table'


def ckan_lic(lid, title):
    s = f'{lid or ""} {title or ""}'.lower()
    if 'nc' in re.findall(r'\bnc\b|non-?commercial', s) or 'non-commercial' in s or '-nc' in s:
        return 'nc'
    if re.search(r'cc-?by|cc0|cc-?zero|odc|pddl|odbl|other-open|open data|open-data|public domain|ogl', s):
        return 'open'
    return 'check'


SECRET_PARAM = re.compile(r'([?&](?:token|key|api_?key|apikey|access_?token|auth|sig|signature|secret|password|pass|client_secret)=)([^&#\s"\'<>)\]]*)', re.I)


def redact(s):
    """คีย์/โทเคนที่ผู้ให้ข้อมูลฝังไว้ในลิงก์หรือคำอธิบาย → แทนด้วย {YOUR_API_KEY} (ไม่เผยแพร่ซ้ำ ใช้คีย์ของตัวเองแทน)"""
    if not s:
        return s, False
    out = SECRET_PARAM.sub(lambda m: m.group(1) + ('{YOUR_API_KEY}' if m.group(2) else ''), s)
    return out, out != s and bool(SECRET_PARAM.search(s) and any(g for _, g in SECRET_PARAM.findall(s)))


def ckan_harvest(portal, fetch):
    base, fq = portal['base'].rstrip('/'), portal.get('fq')
    out, start = [], 0
    while True:
        q = dict(rows=500, start=start, sort='name asc')
        if fq:
            q['fq'] = fq
        g = fetch.get(f'{base}/api/3/action/package_search?{urlencode(q)}', 'json')
        res = ((g.get('body') or {}).get('result') or {})
        rows = res.get('results') or []
        out += rows
        start += len(rows)
        if not rows or start >= (res.get('count') or 0):
            break
    recs = []
    for r in out:
        if r.get('private') or r.get('state', 'active') != 'active':
            continue
        org = (r.get('organization') or {}).get('title') or (r.get('organization') or {}).get('name') or ''
        resources = []
        for x in (r.get('resources') or []):
            if not (x.get('url') or '').startswith(('http://', 'https://')):
                continue
            u, hid = redact(x['url'])
            resources.append(dict(name=(x.get('name') or x.get('description') or '').strip()[:120] or None, format=(x.get('format') or '').strip() or None,
                                  url=u, **({'key': True} if hid or '{YOUR' in u.upper() or '[YOUR' in u.upper() else {})))
        tags = [x.get('display_name') or x.get('name') for x in (r.get('tags') or []) if x]
        page = f'{base}/dataset/{r["name"]}'
        notes = redact((r.get('notes') or '').strip())[0]
        rec = dict(src='ckan', platform=portal['name'], id=r['name'], title=r.get('title') or r['name'], provider=org, og=[org] if org else [],
                   type=ckan_type([x['format'] for x in resources if x['format']]), type_raw=', '.join(sorted({x['format'] for x in resources if x['format']}))[:120] or None,
                   license=r.get('license_title') or r.get('license_id'), lic=ckan_lic(r.get('license_id'), r.get('license_title')),
                   url=page, meta_url=f'{base}/api/3/action/package_show?id={r["name"]}', keywords=tags[:20], cats_src=[],
                   updated=(r.get('metadata_modified') or '')[:10] or None, resources=resources[:60], n_res=len(resources),
                   cover='thailand', source_page=redact(r.get('url'))[0] if (r.get('url') or '').startswith('http') else None)
        rec['desc'] = dict(text=notes, fmt='md', source=f'คำอธิบายที่ผู้ให้ข้อมูลเขียนใน {portal["name"]}', source_url=page,
                           license_note='ข้อความโดยผู้ให้ข้อมูล') if notes else None
        recs.append(rec)
    print(f'  {portal["name"]}: {len(recs):,} ชุด')
    return recs


def zenodo_harvest(z, fetch):
    """ชุดข้อมูลบน Zenodo (เวอร์ชันล่าสุดของ record) → รายการพร้อมไฟล์ดาวน์โหลดตรงทีละไฟล์ (เช่น ทีละปี)
    คำอธิบาย = ที่ผู้เผยแพร่เขียนใน Zenodo (ไม่เขียนเอง) · ไฟล์ /content รองรับอ่านบางส่วน (range) → ตัดเฉพาะพื้นที่ศึกษาได้"""
    g = fetch.get(f'https://zenodo.org/api/records/{z["record"]}/versions/latest', 'json')
    body = g.get('body') or {}
    md = body.get('metadata') or {}
    if not md:
        print(f'  Zenodo {z["record"]}: ดึงไม่ได้ ({g.get("status")})')
        return []
    pat = re.compile(z.get('files') or r'\.(tif|tiff)$', re.I)
    files = sorted([f for f in body.get('files') or [] if pat.search(f['key'])], key=lambda f: f['key'])
    resources = [dict(name=f['key'], format='GeoTIFF' if re.search(r'\.tiff?$', f['key'], re.I) else f['key'].rsplit('.', 1)[-1].upper(),
                      url=f['links']['self'], size=f.get('size')) for f in files]
    text = html.unescape(re.sub(r'<[^>]+>', ' ', md.get('description') or ''))
    text = re.sub(r'[ \t]+', ' ', re.sub(r'\s*\n\s*', '\n', text)).strip()
    creators = [c.get('name') for c in md.get('creators') or [] if c.get('name')]
    lic = (md.get('license') or {}).get('id') or ''
    page = body.get('links', {}).get('self_html') or f'https://zenodo.org/records/{body.get("id")}'
    rec = dict(src='ckan', platform='Zenodo', id=str(body.get('id')), title=md.get('title') or z['record'], provider=', '.join(creators[:3]),
               og=creators[:3], type='raster', type_raw='GeoTIFF', license=lic, lic='open' if lic.lower().startswith(('cc-by', 'cc0', 'odbl')) else 'check',
               url=page, meta_url=f'https://zenodo.org/api/records/{body.get("id")}', keywords=[str(k) for k in md.get('keywords') or []][:20],
               cats_src=z.get('cats') or [], updated=md.get('publication_date'), resources=resources[:80], n_res=len(resources),
               cover=z.get('cover') or 'global', source_page=page, citation=f'DOI {body.get("doi")}' if body.get('doi') else None)
    rec['desc'] = dict(text=text[:6000], fmt='text', source='คำอธิบายที่ผู้เผยแพร่เขียนใน Zenodo', source_url=page,
                       license_note='ข้อความโดยผู้เผยแพร่') if text else None
    print(f'  Zenodo {z["record"]} → {body.get("id")} {md.get("version") or ""}: {len(resources)} ไฟล์')
    return [rec]


def _orgs(rec):
    """หน่วยงานของชุด (ใช้กรอง): STAC = ผู้ผลิต/ผู้ให้สิทธิ์ (ไม่นับผู้โฮสต์) · อื่น = ช่องผู้ผลิตในแคตตาล็อก"""
    names = [p['name'] for p in (rec.get('providers') or []) if p.get('name') and set(p.get('roles') or []) - {'host'}]
    if not names and rec.get('provider'):
        names = [rec['provider']]
    return [re.sub(r'\s+', ' ', n).strip() for n in dict.fromkeys(names) if n and n.strip()][:6]


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

    stats = dict(pc=0, gee=0, wiki=0, site=0, none=0, ckan=0)
    portals = cur.get('ckan', [])
    replaced = {pt['replaces']: pt for pt in portals if pt.get('replaces')}
    ck_count, seen, mirrored = {}, {}, 0
    for pt in portals:                                    # ลำดับใน hub_curated = พอร์ทัลของหน่วยงานก่อน data.go.th (ที่ดึงสำเนาไป)
        for rec in ckan_harvest(pt, fetch):
            dk = (re.sub(r'\s+', ' ', rec['title']).strip().lower(), rec['provider'])
            first = seen.get(dk)
            if first is not None and first['platform'] != pt['name']:
                first.setdefault('mirrors', []).append(dict(platform=pt['name'], url=rec['url']))     # ชุดเดียวกันในพอร์ทัลอื่น → ลิงก์เสริม
                mirrored += 1
                continue
            seen.setdefault(dk, rec)
            ck_count[pt['name']] = ck_count.get(pt['name'], 0) + 1
            if rec['desc']:
                stats['ckan'] += 1
            text = ' '.join([rec['title'], rec['provider'], ' '.join(rec['keywords']), rec['id']])
            rec['themes'] = themes_for([], text)
            rec['key'] = re.sub(r'[^0-9a-zก-๙:._-]+', '-', ('ckan:' + pt['base'].split('//')[1].split('.')[0] + ':' + rec['id']).lower()).strip('-')
            recs.append(rec)
    print(f'  ชุดซ้ำข้ามพอร์ทัล (เก็บพอร์ทัลของหน่วยงาน + ลิงก์สำเนา): {mirrored}')
    for z in cur.get('zenodo', []):                      # ชุดเผยแพร่บน Zenodo ที่ดาวน์โหลดตรงได้ (เช่น night light รายปี)
        for rec in zenodo_harvest(z, fetch):
            text = ' '.join([rec['title'], rec['provider'], ' '.join(rec['keywords'])])
            rec['themes'] = themes_for(rec['cats_src'], text)
            rec['key'] = f'zenodo:{z["record"]}'
            recs.append(rec)
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
                rec['variables'] = variables_of(stac)
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
            if name in replaced:                          # พอร์ทัลที่แตกเป็นรายชุดแล้ว → แสดงเป็นแพลตฟอร์ม
                pt = replaced[name]
                rec.update(type='platform', platform=pt['name'], src='platform',
                           note=f'แตกเป็น {ck_count.get(pt["name"], 0):,} ชุดในรายการ' + (f' ({pt["note"]})' if pt.get('note') else '') + ' — เลือกแหล่งนี้ในตัวกรองเพื่อดูทั้งหมด')
                kind = 'platform'
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
        rec['og'] = _orgs(rec)
        rec['desc'] = desc
        rec['key'] = (kind + ':' + (rec['id'] or rec['title'])).lower()
        rec['key'] = re.sub(r'[^0-9a-zก-๙:._-]+', '-', rec['key']).strip('-')
        recs.append(rec)
    return recs, stats


IMPORT_PAT = re.compile(r'\.(tif|tiff)(/content)?(\?|$)|\.(geo)?json(\?|$)', re.I)                     # แอปนำเข้า/ตัดพื้นที่เองได้
FILE_PAT = re.compile(r'\.(tif|tiff|zip|gpkg|geojson|json|csv|xlsx?|nc|h5|kmz?|shp|parquet|7z)(/content)?(\?|$)', re.I)  # ลิงก์ไฟล์ตรง (กดแล้วโหลด)
YEAR_PAT = re.compile(r'(?<!\d)(19[5-9]\d|20[0-4]\d)(?:0101)?(?!\d)')


def knowledge(r):
    """ความรู้สรุปต่อชุด (ให้ผู้ช่วย AI/ตัวกรองใช้): ช่วงปี · จำนวนไฟล์ที่แอปนำเข้าได้ · จำนวนลิงก์ไฟล์ตรง"""
    res = [x for x in (r.get('resources') or []) if not x.get('key')]
    yrs = sorted({int(m.group(1)) for x in res for m in [YEAR_PAT.search((x.get('name') or '') + ' ' + (x.get('url') or '').rsplit('/', 1)[-1])] if m})
    for k in ('start', 'end'):                               # STAC (GEE/PC): ช่วงเวลาของ collection
        if r.get(k) and r[k][:4].isdigit():
            yrs.append(int(r[k][:4]))
    yrs = sorted(set(yrs))
    fy = sorted({int(m.group(1)) for x in res for m in [YEAR_PAT.search((x.get('name') or '') + ' ' + (x.get('url') or '').rsplit('/', 1)[-1])] if m})
    return dict(y=[yrs[0], yrs[-1]] if yrs else None, yl=fy if 1 < len(fy) <= 80 else None, nv=len(r.get('variables') or []) or None, ni=sum(bool(IMPORT_PAT.search(x.get('url') or '')) for x in res) or None,
                nf=sum(bool(FILE_PAT.search(x.get('url') or '')) for x in res) or None)


def write(recs, stats):
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob('desc_*.json'):
        f.unlink()
    fix = json.loads(CURATED.read_text(encoding='utf-8')).get('url_fix', {})
    for r in recs:                                       # ชื่อจากต้นทางบางชุดมี HTML entity (เช่น 0.05&deg;)
        r['title'] = html.unescape(r['title'] or '')
        r['url'] = fix.get(r['url'], r['url'])
    order = {'other': 0, 'ckan': 1, 'platform': 2, 'pc': 3, 'gee': 4}
    recs.sort(key=lambda r: (order[r['src']], (r['title'] or '').lower()))
    index, shards = [], {}
    for i, r in enumerate(recs):
        sh = i // SHARD
        shards.setdefault(sh, {})[r['key']] = dict(desc=r.get('desc'), citation=r.get('citation'), terms=r.get('terms'),
                                                     providers=r.get('providers'), keywords=r.get('keywords'), resources=r.get('resources'),
                                                     source_page=r.get('source_page'), mirrors=r.get('mirrors'), variables=r.get('variables'))
        has = bool(r.get('desc') and r['desc'].get('text'))
        kn = knowledge(r)
        index.append({k: v for k, v in dict(**kn,
            k=r['key'], t=r['title'], id=r.get('id'), p=r['platform'], s=r['src'], pr=r.get('provider'), ty=r['type'], tr=r.get('type_raw'),
            th=r['themes'], a=r.get('start'), b=r.get('end'), l=r.get('license'), lc=r['lic'], u=r['url'], m=r.get('meta_url'),
            bb=r.get('bbox'), cv=r['cover'], g=r.get('gsd'), cd=r.get('cadence'), dp=r.get('deprecated') or None, sh=sh, d=has or None,
            sd=r.get('short'), n=r.get('note'), kw=(r.get('keywords') or [])[:8] or None, og=r.get('og') or None, up=r.get('updated'),
            nr=r.get('n_res'), ds=(r.get('desc') or {}).get('source')).items() if v not in (None, [], '')})
    for sh, d in shards.items():
        (OUT / f'desc_{sh:02d}.json').write_text(json.dumps(d, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    meta = dict(built=date.today().isoformat(), count=len(recs), stats=stats,
                themes=[dict(k=k, th=t, en=e) for k, t, e in THEMES], types=TYPE_LABEL,
                platforms=sorted(Counter(r['platform'] for r in recs).items(), key=lambda x: -x[1]),
                orgs=sorted(Counter(o for r in recs for o in (r.get('og') or [])).items(), key=lambda x: (-x[1], x[0])),
                credits=[
                    'รายชื่อ collection: Planetary-Computer-Catalog และ Earth-Engine-Catalog (giswqs บน GitHub)',
                    'คำอธิบาย Planetary Computer: STAC API ของ Microsoft · Earth Engine: แคตตาล็อก STAC ของ Google (earthengine-catalog)',
                    'พอร์ทัลข้อมูลเปิด (GISTDA, กรมพัฒนาที่ดิน, data.go.th, HDX): รายชื่อ คำอธิบาย และไฟล์จาก CKAN API ของแต่ละพอร์ทัล',
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
