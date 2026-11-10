# -*- coding: utf-8 -*-
"""ภาพดาวเทียมจาก Microsoft Planetary Computer (STAC) — ค้นภาพตามพื้นที่/ช่วงวันที่/เมฆ แล้วให้เซิร์ฟเวอร์ทำภาพรวม (mosaic) ส่งมาเฉพาะผลลัพธ์

ทำไมเร็ว (แนวคิดจาก Project Palantir + วัดจริง):
- ไฟล์ต้นทางเป็น COG บน Azure (ยุโรป) — ดึงเองจากไทยได้ ~0.09 MB/s ต่อการเชื่อมต่อ: ภาพ Sentinel-2 1 แผ่นที่ ~80 ม. ใช้ 41 วินาที, SAR 214 วินาที
- บริการ Data API ของ PC ทำ mosaic + เลือกพิกเซล (median / first ตามเมฆน้อยสุด) + อ่าน overview ฝั่งเซิร์ฟเวอร์ → ส่งไทล์ผลลัพธ์ 512×512 มา (~2 วินาที/ไทล์)
  ดึงหลายไทล์พร้อมกัน (16 การเชื่อมต่อ) · ใช้กริดไทล์ WGS1984Quad → ขนาดพิกเซล 180°/(512·2^z) เป็นเศษส่วนฐานสองแท้ ต่อกับเครื่องคำนวณเดิมได้
- ไม่ต้องมีบัญชี/โทเคน (Data API ลงชื่อ SAS ให้ฝั่งเซิร์ฟเวอร์)

ข้อจำกัดที่รู้: Sentinel-2 L2A ตั้งแต่ 25 ม.ค. 2565 (baseline 04.00) ค่ามี offset +1000 — ผลรวมช่วงคร่อมวันนั้นปนกันได้ (เตือนในการประเมิน)
"""
import math
import time
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.windows import Window

from . import db, export
from .engine import EngineError
from .ops import overview_factors, register_output

STAC = 'https://planetarycomputer.microsoft.com/api/stac/v1'
DATA = 'https://planetarycomputer.microsoft.com/api/data/v1'
HOME = 'https://planetarycomputer.microsoft.com/dataset/'
UA = {'User-Agent': 'Ainulindale (bivariate studio; github.com/nattakitNams/project-ainulindale-demo)'}
THREADS = 16
MAX_TILES = 12000

# คลังคอลเลกชันที่คัดไว้ (ชื่อแบนด์ = ชื่อ asset ใน STAC) · kind: optical / sar / index / dem / class
COLLECTIONS = [
    dict(id='sentinel-2-l2a', name='Sentinel-2 L2A (ภาพสี/อินฟราเรด 10–20 ม.)', kind='optical', years='2015–ปัจจุบัน', revisit='~5 วัน', native_m=10,
         cloud=True, vt='density', pick='median', default=['B04', 'B08'],
         bands=dict(B02='น้ำเงิน (Blue) 10 ม.', B03='เขียว (Green) 10 ม.', B04='แดง (Red) 10 ม.', B05='Red edge 1 · 20 ม.', B06='Red edge 2 · 20 ม.',
                    B07='Red edge 3 · 20 ม.', B08='อินฟราเรดใกล้ (NIR) 10 ม.', B8A='NIR แคบ · 20 ม.', B11='SWIR 1 · 20 ม.', B12='SWIR 2 · 20 ม.',
                    SCL='ชั้นจำแนกฉาก (เมฆ/เงา/น้ำ) · 20 ม.'),
         note='ค่าสะท้อน ×10000 (uint16) · ภาพตั้งแต่ 25 ม.ค. 2565 บวก 1000 · NDVI = (B08−B04)/(B08+B04)', license='Copernicus (เปิด)'),
    dict(id='landsat-c2-l2', name='Landsat 8/9 C2 L2 (30 ม. + ความร้อน)', kind='optical', years='1982–ปัจจุบัน (Landsat 4–9)', revisit='~8 วัน (8+9)', native_m=30,
         cloud=True, vt='density', pick='median', default=['red', 'nir08'],
         bands=dict(blue='น้ำเงิน', green='เขียว', red='แดง', nir08='อินฟราเรดใกล้ (NIR)', swir16='SWIR 1', swir22='SWIR 2', lwir11='ความร้อน (อุณหภูมิพื้นผิว) — Landsat 8/9',
                    qa_pixel='คุณภาพพิกเซล (เมฆ)'),
         note='ค่าสะท้อน = DN × 0.0000275 − 0.2 · อุณหภูมิ (K) = DN × 0.00341802 + 149', license='USGS (สาธารณะ)'),
    dict(id='sentinel-1-rtc', name='Sentinel-1 RTC (เรดาร์ SAR 10 ม. ทะลุเมฆ)', kind='sar', years='2014–ปัจจุบัน', revisit='~12 วัน', native_m=10,
         cloud=False, vt='density', pick='median', default=['vv', 'vh'],
         bands=dict(vv='VV (ความขรุขระพื้นผิว, น้ำนิ่ง = ต่ำมาก)', vh='VH (พืชพรรณ/ปริมาตร)'),
         note='ค่า backscatter แบบเส้นตรง (gamma0) · dB = 10·log10(ค่า) · น้ำท่วม: VV dB < ราว −18', license='Copernicus (เปิด) · แก้ภูมิประเทศโดย Catalyst'),
    dict(id='alos-palsar-mosaic', name='ALOS PALSAR รายปี (เรดาร์ L-band 25 ม.)', kind='sar', years='2015–2021', revisit='รายปี', native_m=25,
         cloud=False, vt='density', pick='first', default=['HH', 'HV'],
         bands=dict(HH='HH', HV='HV (ป่า/ชีวมวล)'), note='L-band ทะลุเรือนยอดได้ดีกว่า C-band (Sentinel-1) · DN ต้องแปลงเป็น dB', license='JAXA'),
    dict(id='modis-13Q1-061', name='MODIS NDVI/EVI 16 วัน (250 ม.)', kind='index', years='2000–ปัจจุบัน', revisit='16 วัน', native_m=250,
         cloud=False, vt='density', pick='median', default=['250m_16_days_NDVI'],
         bands={'250m_16_days_NDVI': 'NDVI ×10000', '250m_16_days_EVI': 'EVI ×10000'}, note='ค่า ÷ 10000 = ดัชนีจริง', license='NASA (สาธารณะ)'),
    dict(id='cop-dem-glo-30', name='Copernicus DEM 30 ม. (ความสูงภูมิประเทศ)', kind='dem', years='2011–2015 (ชุดเดียว)', revisit='—', native_m=30,
         cloud=False, vt='density', pick='first', default=['data'], bands=dict(data='ความสูง (ม.)'), note='', license='Copernicus DEM'),
    dict(id='esa-worldcover', name='ESA WorldCover 10 ม. (การใช้ที่ดิน 11 ชั้น)', kind='class', years='2020, 2021', revisit='รายปี', native_m=10,
         cloud=False, vt='class', pick='first', default=['map'], bands=dict(map='รหัสชั้น (10 ป่าไม้ … 80 น้ำ)'), note='', license='CC-BY-4.0'),
    dict(id='io-lulc-annual-v02', name='Esri/Impact Observatory LULC 10 ม. รายปี (9 ชั้น)', kind='class', years='2017–2023', revisit='รายปี', native_m=10,
         cloud=False, vt='class', pick='first', default=['data'], bands=dict(data='รหัสชั้น (1 น้ำ … 11 ทุ่งหญ้า)'), note='', license='CC-BY-4.0'),
    dict(id='jrc-gsw', name='JRC Global Surface Water (ความถี่น้ำ 1984–2021)', kind='index', years='1984–2021 (สรุป)', revisit='—', native_m=30,
         cloud=False, vt='density', pick='first', default=['occurrence'],
         bands=dict(occurrence='% ของเวลาที่มีน้ำ', seasonality='จำนวนเดือนที่มีน้ำ', recurrence='% การกลับมาของน้ำ', change='การเปลี่ยนแปลง',
                    transitions='ประเภทการเปลี่ยน', extent='เคยมีน้ำ (1/0)'), note='', license='Copernicus/JRC (เปิด)'),
]
BY_ID = {c['id']: c for c in COLLECTIONS}


def zoom_options():
    """ความละเอียด = ระดับไทล์ (พิกเซล 180°/(512·2^z))"""
    out = []
    for z in range(5, 13):
        res = 180 / 512 / 2 ** z
        out.append(dict(zoom=z, arcsec=res * 3600, m=round(res * 111320), label=f'≈ {round(res * 111320):,} ม.'))
    return out


def _req(method, url, tries=4, **kw):
    kw.setdefault('timeout', 120)
    kw.setdefault('headers', UA)
    for i in range(tries):
        try:
            r = requests.request(method, url, **kw)
            if r.status_code in (429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(float(r.headers.get('Retry-After') or 2 * (i + 1)))
                continue
            return r
        except requests.RequestException:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def _coll(cid):
    c = BY_ID.get(cid)
    if not c:
        raise EngineError(f'ไม่รู้จักคอลเลกชัน "{cid}" — มี: {", ".join(BY_ID)}')
    return c


def _datetime(p):
    s, e = (p.get('date_from') or '').strip(), (p.get('date_to') or '').strip()
    if not s and not e:
        return None
    return f'{s or ".."}/{e or ".."}'


def _query(p, bbox, c):
    q = dict(collections=[c['id']], bbox=bbox)
    dt = _datetime(p)
    if dt:
        q['datetime'] = dt
    if c['cloud'] and p.get('cloud_max') not in (None, ''):
        q['filter-lang'] = 'cql2-json'
        q['filter'] = {'op': '<=', 'args': [{'property': 'eo:cloud_cover'}, float(p['cloud_max'])]}
        q['sortby'] = [{'field': 'eo:cloud_cover', 'direction': 'asc'}]
    return q


def search(p, bbox, limit=500):
    """ภาพที่ตรงเงื่อนไข: จำนวน ช่วงวันที่ เมฆ (STAC search ทีละหน้า)"""
    c = _coll(p['collection'])
    q = _query(p, bbox, c)
    body = {k: v for k, v in q.items()}
    body['limit'] = 200
    body.pop('sortby', None)
    feats, url = [], STAC + '/search'
    while url and len(feats) < limit:
        r = _req('POST', url, json=body)
        if r.status_code != 200:
            raise EngineError(f'ค้นภาพไม่สำเร็จ ({r.status_code}): {r.text[:200]}')
        j = r.json()
        feats += j.get('features', [])
        nxt = [l for l in j.get('links', []) if l.get('rel') == 'next']
        if not nxt:
            break
        url, body = nxt[0]['href'], nxt[0].get('body') or body
    dates = sorted(f['properties'].get('datetime') or f['properties'].get('start_datetime') or '' for f in feats)
    clouds = [f['properties'].get('eo:cloud_cover') for f in feats if f['properties'].get('eo:cloud_cover') is not None]
    return dict(collection=c['id'], n=len(feats), more=len(feats) >= limit, first=dates[0][:10] if dates else None, last=dates[-1][:10] if dates else None,
                dates=sorted({d[:10] for d in dates})[-60:],
                cloud=dict(min=min(clouds), median=float(np.median(clouds)), max=max(clouds)) if clouds else None)


def _aoi(p):
    from . import aoi as aoimod
    if not p.get('aoi_id'):
        raise EngineError('เลือกพื้นที่ (พื้นที่ศึกษา) — ภาพดาวเทียมดึงตามพื้นที่เท่านั้น')
    a = aoimod.get(int(p['aoi_id']))
    g = aoimod.geom_in(int(p['aoi_id']), 'EPSG:4326')
    return a, g


def _tiles(geom, z):
    """ไทล์ WGS1984Quad (512 px @2x) ที่แตะพื้นที่"""
    from shapely.geometry import box
    from shapely.prepared import prep
    size = 180 / 2 ** z                                 # องศาต่อไทล์ (ระดับ z: 2^(z+1) × 2^z ไทล์)
    x0, y0, x1, y1 = geom.bounds
    pg = prep(geom)
    out = []
    for ty in range(int((90 - y1) // size), int((90 - y0) // size) + 1):
        for tx in range(int((x0 + 180) // size), int((x1 + 180) // size) + 1):
            b = box(-180 + tx * size, 90 - (ty + 1) * size, -180 + (tx + 1) * size, 90 - ty * size)
            if pg.intersects(b):
                out.append((tx, ty, pg.contains(b)))
    return out, size


def _check(p):
    c = _coll(p.get('collection'))
    bands = p.get('bands') or c['default']
    bad = [b for b in bands if b not in c['bands']]
    if bad:
        raise EngineError(f'{c["id"]} ไม่มีแบนด์ {", ".join(bad)} — มี: {", ".join(c["bands"])}')
    if not 1 <= len(bands) <= 8:
        raise EngineError('เลือก 1–8 แบนด์')
    z = int(p.get('zoom') or 9)
    if not 5 <= z <= 12:
        raise EngineError('ความละเอียด (zoom) ต้องอยู่ระหว่าง 5 (≈ 1.2 กม.) ถึง 12 (≈ 10 ม.)')
    if p.get('pick', c['pick']) not in ('median', 'first', 'mean', 'highest', 'lowest'):
        raise EngineError('วิธีรวมภาพต้องเป็น median / first / mean / highest / lowest')
    return c, bands, z


def estimate(p):
    c, bands, z = _check(p)
    a, g = _aoi(p)
    tiles, size = _tiles(g, z)
    res = Fraction(10125, 1024 * 2 ** (z - 7))
    warns = []
    if len(tiles) > MAX_TILES:
        raise EngineError(f'{len(tiles):,} ไทล์ มากเกิน (≤ {MAX_TILES:,}) — ลดความละเอียด หรือเลือกพื้นที่เล็กลง')
    sec = len(tiles) * 2.5 / THREADS * max(1, len(bands) / 2)
    if z - 1 >= 0 and 180 / 512 / 2 ** z * 111320 < c['native_m'] * 0.9:
        warns.append(f'ละเอียดกว่าข้อมูลต้นทาง ({c["native_m"]} ม.) — ไม่ได้รายละเอียดเพิ่ม แต่ไฟล์ใหญ่ขึ้น')
    if c['id'] == 'sentinel-2-l2a' and (p.get('date_from') or '') < '2022-01-25' < (p.get('date_to') or '9999'):
        warns.append('ช่วงวันที่คร่อม 25 ม.ค. 2565 — Sentinel-2 ภาพหลังวันนั้นค่าบวก 1000 (baseline 04.00) ผลรวมจะปนกัน · ถ้าคำนวณดัชนีควรแยกช่วง')
    W = round((g.bounds[2] - g.bounds[0]) / (size / 512))
    H = round((g.bounds[3] - g.bounds[1]) / (size / 512))
    from . import gridmath as gm
    return dict(grid=dict(res_label=gm.res_label(res, True), width=W, height=H), aoi=a['name'], tiles=len(tiles), seconds=round(sec),
                bands=bands, collection=c['id'], warnings=warns + [f'ประมาณ {len(tiles):,} ไทล์ · ~{max(1, round(sec / 60))} นาที (ขึ้นกับความเร็วเน็ต)'])


def op_satellite(job, P, log):
    from rasterio.features import geometry_mask
    p = job['params']
    c, bands, z = _check(p)
    a, g = _aoi(p)
    tiles, size = _tiles(g, z)
    if len(tiles) > MAX_TILES:
        raise EngineError(f'{len(tiles):,} ไทล์ มากเกิน')
    bbox = list(g.bounds)
    pick = p.get('pick') or c['pick']
    P(0.01, 'ค้นภาพ…')
    found = search(p, bbox, limit=1000)
    if not found['n']:
        raise EngineError('ไม่พบภาพที่ตรงเงื่อนไข (ช่วงวันที่/เมฆ/พื้นที่) — ขยายช่วงวันที่ หรือเพิ่มเกณฑ์เมฆ')
    log(f'{c["name"]} · {found["n"]:,}{"+" if found["more"] else ""} ภาพ ({"ตัวอย่าง " if found["more"] else ""}{found["first"]} – {found["last"]}) · แบนด์ {", ".join(bands)} · รวมแบบ {pick} · {len(tiles):,} ไทล์')
    r = _req('POST', DATA + '/mosaic/register', json=_query(p, bbox, c))
    if r.status_code != 200:
        raise EngineError(f'สร้าง mosaic ไม่สำเร็จ ({r.status_code}): {r.text[:200]}')
    sid = r.json()['id']
    px = size / 512
    tx0, ty0 = min(t[0] for t in tiles), min(t[1] for t in tiles)
    tx1, ty1 = max(t[0] for t in tiles), max(t[1] for t in tiles)
    W, H = (tx1 - tx0 + 1) * 512, (ty1 - ty0 + 1) * 512
    ox, oy = -180 + tx0 * size, 90 - ty0 * size
    tr = from_origin(ox, oy, px, px)
    # ตัดกรอบผลลัพธ์ให้พอดีพื้นที่ (ไม่ต้องเก็บส่วนว่างนอกกรอบ)
    c0, r0 = max(0, int((bbox[0] - ox) / px)), max(0, int((oy - bbox[3]) / px))
    c1, r1 = min(W, math.ceil((bbox[2] - ox) / px)), min(H, math.ceil((oy - bbox[1]) / px))
    OW, OH = c1 - c0, r1 - r0
    otr = from_origin(ox + c0 * px, oy - r0 * px, px, px)
    params = dict(collection=c['id'], assets=bands, pixel_selection=pick)
    if c['id'] == 'esa-worldcover' or c['kind'] == 'class':
        params['resampling'] = 'nearest'

    def fetch(t):
        tx, ty, inside = t
        for i in range(4):
            rr = _req('GET', f'{DATA}/mosaic/{sid}/tiles/WGS1984Quad/{z}/{tx}/{ty}@2x.tif', params=params, timeout=180)
            if rr.status_code == 200:
                with rasterio.MemoryFile(rr.content) as mf, mf.open() as d:
                    arr = d.read()
                return t, arr
            if rr.status_code in (204, 404):             # ไม่มีภาพในไทล์นี้
                return t, None
            time.sleep(2 * (i + 1))
        raise EngineError(f'ดึงไทล์ {tx},{ty} ไม่สำเร็จ ({rr.status_code}): {rr.text[:150]}')

    out_dir = Path(job['out_dir'])
    outp = out_dir / f'{export.slug(p.get("name") or c["id"] + "_" + "_".join(bands), 60)}.tif'
    ds = None
    got = empty = 0
    acc = [dict(n=0, s=0.0, mn=math.inf, mx=-math.inf) for _ in bands]
    t0 = time.time()
    with ThreadPoolExecutor(THREADS) as ex:
        for k, (t, arr) in enumerate(ex.map(fetch, tiles)):
            if arr is not None:
                data, alpha = arr[:len(bands)], arr[-1] if arr.shape[0] > len(bands) else None
                if ds is None:
                    dt = data.dtype.name
                    nod = 0 if np.issubdtype(data.dtype, np.integer) else -9999.0
                    ds = rasterio.open(outp, 'w', driver='GTiff', width=OW, height=OH, count=len(bands), dtype=dt, crs='EPSG:4326', transform=otr,
                                       nodata=nod, tiled=True, blockxsize=512, blockysize=512, compress='deflate', BIGTIFF='IF_SAFER', SPARSE_OK='TRUE')
                    for i, b in enumerate(bands):
                        ds.set_band_description(i + 1, f'{b} — {c["bands"][b]}')
                tx, ty, inside = t
                ok = alpha > 0 if alpha is not None else np.ones(data.shape[1:], bool)
                if not np.issubdtype(data.dtype, np.integer):
                    ok &= np.isfinite(data).all(0)
                if not inside:
                    ttr = from_origin(-180 + tx * size, 90 - ty * size, px, px)
                    ok &= geometry_mask([g], out_shape=ok.shape, transform=ttr, invert=True)
                # ตำแหน่งไทล์ในไฟล์ผลลัพธ์ (ตัดส่วนที่เกินกรอบ)
                R, C = (ty - ty0) * 512 - r0, (tx - tx0) * 512 - c0
                rs, cs = max(0, -R), max(0, -C)
                re, ce = min(512, OH - R), min(512, OW - C)
                if re > rs and ce > cs and ok[rs:re, cs:ce].any():
                    blk = np.where(ok[None, rs:re, cs:ce], data[:, rs:re, cs:ce], ds.nodata).astype(ds.dtypes[0])
                    ds.write(blk, window=Window(C + cs, R + rs, ce - cs, re - rs))
                    m = ok[rs:re, cs:ce]
                    for i in range(len(bands)):
                        v = data[i, rs:re, cs:ce][m].astype('float64')
                        acc[i]['n'] += v.size
                        acc[i]['s'] += float(v.sum())
                        acc[i]['mn'], acc[i]['mx'] = min(acc[i]['mn'], float(v.min())), max(acc[i]['mx'], float(v.max()))
                    got += 1
                else:
                    empty += 1
            else:
                empty += 1
            el = time.time() - t0
            P(0.03 + 0.87 * (k + 1) / len(tiles), f'ไทล์ {k + 1:,}/{len(tiles):,} · มีภาพ {got:,} · {el / (k + 1) * THREADS:,.1f} วิ/ไทล์')
    if ds is None or not acc[0]['n']:
        raise EngineError('ไม่มีข้อมูลในพื้นที่ (ไทล์ว่างทั้งหมด) — ลองช่วงวันที่ยาวขึ้น หรือเกณฑ์เมฆสูงขึ้น')
    ds.close()
    P(0.92, 'สร้าง overview…')
    with rasterio.open(outp, 'r+') as d:
        fac = overview_factors(d.width, d.height)
        if fac:
            d.build_overviews(fac, Resampling.mode if c['vt'] == 'class' else Resampling.average)
    stats = {b: dict(valid_pixels=x['n'], min=x['mn'], max=x['mx'], mean=x['s'] / x['n'] if x['n'] else None) for b, x in zip(bands, acc)}
    summary = dict(collection=c['id'], name=c['name'], images=found['n'], images_more=found['more'], first=found['first'], last=found['last'], cloud=found['cloud'],
                   tiles=len(tiles), tiles_with_data=got, width=OW, height=OH, bands=stats, aoi=dict(id=a['id'], name=a['name']), license=c['license'],
                   source=HOME + c['id'], seconds=round(time.time() - t0))
    export.write_lineage(out_dir, 'satellite', [], dict(p, bands=bands, pick=pick, mosaic_search=found), [outp], summary,
                         [f'ไทล์ไม่มีภาพ {empty:,} จาก {len(tiles):,}'] if empty else [])
    did = register_output(outp, p.get('name') or f'{c["name"].split(" (")[0]} {", ".join(bands)} · {found["first"]}–{found["last"]} · {a["name"]}',
                          c['vt'], job['id'], 'input')
    meta = db.get('datasets', did)['meta']
    meta['satellite'] = dict(collection=c['id'], bands=bands, band_meaning={b: c['bands'][b] for b in bands}, first=found['first'], last=found['last'],
                             images=found['n'], pick=pick, note=c['note'], license=c['license'], source=HOME + c['id'], purpose=p.get('purpose'))
    db.update('datasets', did, meta=meta, value_type_confirmed=1)
    log(f'เสร็จ: {OW:,} × {OH:,} พิกเซล · ไทล์มีภาพ {got:,}/{len(tiles):,} · {time.time() - t0:,.0f} วินาที')
    return dict(output=str(outp), dataset_id=did, summary=summary)


OPS_SAT = dict(satellite=op_satellite)
