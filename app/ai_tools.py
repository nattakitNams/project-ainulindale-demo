# -*- coding: utf-8 -*-
"""เครื่องมือที่ผู้ช่วย AI เรียกได้ (ขั้นที่ 2)

หลักการ
- เรียกผ่าน API ของตัวประมวลผลเอง (test_client, same-origin) → ใช้ด่านตรวจ/validate_job ชุดเดียวกับที่ผู้ใช้กดเองทุกประการ
- ระดับ read  : ทำทันที (อ่านคลัง / ประเมินงาน / ค้น Data hub / สถานะงาน)
- ระดับ action: ไม่ทำทันที → สร้าง "ข้อเสนอ" ใช้ได้ครั้งเดียว ผูกกับค่าที่ตั้งชุดนั้น · รันเมื่อผู้ใช้กดยืนยันในแชตเท่านั้น
- ไม่มีเครื่องมือ ลบ/ถังขยะ/โทเคน/ค่าตั้งระบบ/path ไฟล์ — AI ทำสิ่งเหล่านี้ไม่ได้เลย
- ทุกงานที่รันจากข้อเสนอ: บันทึก `requested_by` ใน params (ลง lineage) ว่าสั่งโดยผู้ช่วย AI รุ่นใด ยืนยันเมื่อไร
"""
import json
import re
import secrets
import threading
import time

from . import db, palettes
from .config import PORT, STATIC

CLIENT = None                    # server ตั้งให้: lambda: app.test_client()
JOB_KINDS = ('bivariate', 'resample', 'rasterize', 'hex', 'hexbiv', 'vgrid', 'change', 'download', 'calc', 'trend', 'mosaic', 'vmerge', 'satellite')
PROPOSAL_TTL = 30 * 60
_PROPOSALS, _lock = {}, threading.Lock()


class ToolError(Exception):
    pass


def _call(method, path, body=None, params=None):
    c = CLIENT()
    o = f'http://127.0.0.1:{PORT}'
    r = c.open(path, method=method, json=body, query_string=params, base_url=o, headers={'Origin': o})
    try:
        j = r.get_json(silent=True)
    except Exception:
        j = None
    if r.status_code >= 400:
        raise ToolError((j or {}).get('error') or f'HTTP {r.status_code}')
    return j


# ---------- read ----------
def _folders():
    fs = (_call('GET', '/api/folders') or {}).get('folders', [])
    by = {f['id']: f for f in fs}

    def path(fid):
        out = []
        while fid in by:
            out.insert(0, by[fid]['name'])
            fid = by[fid].get('parent_id')
        return ' / '.join(out)
    return fs, path


def t_list_datasets(query=None, kind=None, role=None, limit=60):
    ds = _call('GET', '/api/datasets')
    _, fpath = _folders()
    q = (query or '').lower().strip()
    out = []
    for d in ds:
        if kind and d['kind'] != kind or role and d.get('role') != role:
            continue
        if q and q not in d['name'].lower() and q not in fpath(d.get('folder_id')).lower() and f"#{d['id']}" != q:
            continue
        m = d.get('meta') or {}
        r = dict(id=d['id'], name=d['name'], kind=d['kind'], role=d.get('role'), folder=fpath(d.get('folder_id')) or None)
        if d['kind'] == 'raster':
            r.update(value_type=d.get('value_type'), value_type_confirmed=bool(d.get('value_type_confirmed')),
                     res=(m.get('res_label') or '').split(' (')[0], crs=m.get('crs_key') or m.get('crs_name'))
        elif d['kind'] == 'vector':
            r.update(geometry=m.get('geometry_type'), features=m.get('features'), fields=[f['name'] for f in (m.get('fields') or [])][:40])
            if m.get('hex'):
                r['hex_km'] = m['hex'].get('d_km')
        else:
            r.update(link_type=m.get('type_label'), builtin=bool(m.get('builtin')), downloadable=not m.get('view'))
        out.append(r)
    return dict(total=len(out), datasets=out[:int(limit or 60)])


def t_get_dataset(dataset_id):
    d = _call('GET', f'/api/datasets/{int(dataset_id)}')
    m, st = d.get('meta') or {}, d.get('stats') or {}
    r = dict(id=d['id'], name=d['name'], kind=d['kind'], role=d.get('role'), format=d.get('format'), status=d.get('status'))
    if d['kind'] == 'raster':
        g = m.get('value_type_guess') or {}
        r.update(value_type=d.get('value_type'), value_type_confirmed=bool(d.get('value_type_confirmed')),
                 value_type_guess=dict(type=g.get('type'), reason=g.get('reason')) if g else None,
                 res=m.get('res_label'), res_exact=m.get('res_exact'), crs=m.get('crs_name'), geographic=m.get('geographic'),
                 size=[m.get('width'), m.get('height')], bounds_wgs84=m.get('bounds_wgs84'), nodata=m.get('nodata'),
                 nodata_as=d.get('nodata_as'), exclude_values=d.get('exclude_values'), bands=m.get('count'),
                 stats={k: st.get(k) for k in ('valid', 'nodata', 'min', 'max', 'mean', 'sum') if k in st} or None)
    elif d['kind'] == 'vector':
        r.update(geometry=m.get('geometry_type'), features=m.get('features'), crs=m.get('crs_name'), bounds_wgs84=m.get('bounds_wgs84'),
                 fields=[dict(name=f['name'], type=f.get('type')) for f in (m.get('fields') or [])], hex=m.get('hex'))
    else:
        r.update(link_type=m.get('type_label'), url=d.get('path'), downloadable=not m.get('view'), description=m.get('description'))
    if d.get('lineage'):
        lp = d['lineage'].get('params') or {}
        r['made_by'] = dict(kind=d['lineage'].get('kind'), params={k: lp[k] for k in list(lp)[:20] if k != 'colors'})
    from . import knowledge
    r['knowledge_topics'] = knowledge.match(' '.join([d['name'], str((m.get('satellite') or {}).get('collection') or ''), str(m.get('hub_key') or '')]))
    return r


def t_list_study_areas():
    return [dict(id=a['id'], name=a['name'], area_km2=round(a['area_km2'] or 0, 1), builtin=bool(a.get('builtin')))
            for a in _call('GET', '/api/aoi')]


def t_resolution_options(dataset_ids):
    ids = ','.join(str(int(i)) for i in dataset_ids)
    r = _call('GET', '/api/res-options', params=dict(ids=ids))
    return [dict(value=o['value'], label=o['label'], pixels=o.get('px'), same_as_source=bool(o.get('is_source'))) for o in r['options']]


def t_preview_classes(dataset_id, method='quantile', n=3, metric='value', breaks=None):
    cfg = dict(method=method, n=int(n), metric=metric, breaks=breaks or [])
    r = _call('POST', '/api/classes-preview', dict(dataset_id=int(dataset_id), cfg=cfg))
    return {k: r.get(k) for k in ('breaks', 'pixel_share', 'value_share', 'n', 'note')}


def t_estimate_job(kind, params_json):
    p = _params(kind, params_json)
    r = _call('POST', '/api/estimate', dict(kind=kind, params=p))
    if not r.get('ok'):
        return dict(ok=False, error=r.get('error'))
    g = r.get('grid') or {}
    return dict(ok=True, resolution=g.get('res_label'), size=[g.get('width'), g.get('height')], aoi=r.get('aoi'), warnings=r.get('warnings') or [])


def t_job_status(job_id):
    for j in _call('GET', '/api/jobs'):
        if j['id'] == int(job_id):
            res = j.get('result') or {}
            out = res.get('dataset_id') if isinstance(res, dict) else None
            r = dict(id=j['id'], title=j['title'], status=j['status'], progress=j.get('progress'), message=j.get('message'),
                     error=j.get('error'), output_dataset_id=out)
            if out and j['status'] == 'done':                   # เปิดดูชุดผลลัพธ์ = สั่งเตรียมข้อมูล (สถิติ/พรีวิว) ถ้ายังไม่ทำ
                try:
                    d = _call('GET', f'/api/datasets/{out}')
                    r.update(output_name=d['name'], output_value_type=d.get('value_type'), output_value_type_confirmed=bool(d.get('value_type_confirmed')))
                except ToolError:
                    pass
            return r
    raise ToolError(f'ไม่พบงาน #{job_id}')


def t_list_jobs(limit=10):
    return [dict(id=j['id'], kind=j['kind'], title=j['title'], status=j['status'], progress=j.get('progress'))
            for j in _call('GET', '/api/jobs')[:int(limit or 10)]]


def t_get_dataset_profile(dataset_id):
    """ประวัติชุดข้อมูล: ไฟล์อะไร รูปแบบ มาจากไหน ชุดต้นทาง (พ่อแม่) ค่าที่ตั้ง ชุดที่ทำต่อ (ลูก) โน้ต"""
    return _call('GET', f'/api/datasets/{int(dataset_id)}/profile')


def t_write_dataset_note(dataset_id, text):
    """โน้ตของผู้ช่วย AI ในประวัติชุดข้อมูล (ไม่แตะข้อมูล/ไฟล์ — ติดป้ายว่าเขียนโดย AI ผู้ใช้แก้/ลบได้)"""
    d = db.get('datasets', int(dataset_id))
    if d is None or d.get('trashed_at'):
        raise ToolError(f'ไม่พบชุดข้อมูล #{dataset_id}')
    t = str(text or '').strip()[:2000]
    if not t:
        raise ToolError('โน้ตว่าง')
    db.update('datasets', d['id'], meta=dict(d['meta'], note_ai=dict(text=t, model=CURRENT_MODEL.get('m'), at=db.now())))
    return dict(ok=True, dataset_id=d['id'])


CURRENT_MODEL = {}                                          # ai.chat ตั้งชื่อรุ่นไว้ให้โน้ตของ AI ระบุได้ว่าใครเขียน
_HUB = None
_DESC = {}
DL_PAT = re.compile(r'\.(tif|tiff)(/content)?(\?|$)|\.(geo)?json(\?|$)', re.I)     # ไฟล์ที่แอปดาวน์โหลด/ตัดพื้นที่เองได้


_HUB_META = {}


def _hub():
    global _HUB
    if _HUB is None:
        ix = json.loads((STATIC / 'hub' / 'index.json').read_text(encoding='utf-8'))
        _HUB = ix['items']
        _HUB_META.update(ix.get('meta') or {})
    return _HUB


COVER_TH = dict(thailand='ประเทศไทย', asean='อาเซียน/ภูมิภาค', asia='เอเชีย', global_='ทั่วโลก', partial='บางส่วน', unknown='ไม่ทราบ')
LIC_TH = dict(open='เปิด (ใช้/เผยแพร่ได้ อ้างอิงแหล่ง)', nc='ห้ามใช้เชิงพาณิชย์', check='ต้องตรวจเงื่อนไขเอง', restricted='มีข้อจำกัด')


def _data_card(it, d, dl, direct, res):
    """บัตรข้อมูลมาตรฐานของชุดใน Data hub — แยกหมวด/ตัวแปร/เวลา/พื้นที่/การเข้าถึง ให้ผู้ช่วยอ่านแล้วตอบผู้ใช้ได้ละเอียดและถูก"""
    import datetime
    from . import hub_access, knowledge, ops_sat
    _hub()
    th = {t['k']: t['th'] for t in _HUB_META.get('themes') or []}
    lv, why = hub_access.access(it, set(ops_sat.BY_ID))
    cid = (it.get('id') or '') if it.get('s') == 'pc' else ''
    sat = next((c for c in ops_sat.COLLECTIONS if c['id'].lower() == cid.lower()), None)
    how = ('ดึงเข้าแอปได้ทันที: งาน satellite collection="' + sat['id'] + '"') if sat else \
        (f'นำเข้าคลังได้ {len(dl)} ไฟล์ (propose_download_data)' if dl else
         f'GEE: ee.ImageCollection/Image("{it.get("id")}") — ต้องมีบัญชี ส่งออกเอง' if it.get('s') == 'gee' else
         f'ลิงก์ไฟล์ตรง {len(direct)} ไฟล์ (แอปนำเข้ารูปแบบนี้เองไม่ได้)' if direct else 'ดาวน์โหลดเองจากหน้าเว็บต้นทาง')
    vars_ = d.get('variables') or []
    start, end = it.get('a'), it.get('b')
    by_year = {}
    for r in dl:
        if r.get('year'):
            by_year.setdefault(r['year'], []).append(r['name'])
    return dict(
        what=dict(title=it.get('t'), short=it.get('sd'), categories=[th.get(k, k) for k in it.get('th') or []], data_type=it.get('tr') or it.get('ty'),
                  knowledge_topics=knowledge.match(' '.join([it.get('t') or '', it.get('k') or '', str(it.get('id') or ''), ' '.join(it.get('kw') or [])]))),
        variables=dict(count=len(vars_), items=vars_[:40],
                       note='ตัวแปร/แบนด์จาก metadata ต้นทาง: unit = หน่วย · scale/offset = ค่าจริง = DN × scale + offset · classes = รหัสชั้น' if vars_ else 'ต้นทางไม่ระบุตัวแปร — ดูคำอธิบาย/ไฟล์'),
        time=dict(start=start, end=end or (('ต่อเนื่องถึงปัจจุบัน (' + str(datetime.date.today().year) + ')') if start else None), cadence=it.get('cd'),
                  years_range=it.get('y'), years_with_files=sorted(by_year) or it.get('yl'), files_by_year={str(k): v for k, v in sorted(by_year.items())} or None,
                  updated=it.get('up')),
        space=dict(coverage=COVER_TH.get('global_' if it.get('cv') == 'global' else it.get('cv'), it.get('cv')), bbox=it.get('bb'),
                   resolution_m=it.get('g'), note='resolution_m = gsd จาก metadata (ความละเอียดตามชื่อ)' if it.get('g') else None),
        access=dict(level=lv, detail=why, how_to_get=how, satellite_collection=sat['id'] if sat else None, gee_id=it.get('id') if it.get('s') == 'gee' else None),
        source=dict(provider=it.get('pr'), organisations=it.get('og'), platform=it.get('p'), page=it.get('u'), metadata=it.get('m'),
                    license=it.get('l'), license_class=LIC_TH.get(it.get('lc'), it.get('lc')), citation=d.get('citation'),
                    deprecated=bool(it.get('dp')), description_source=(d.get('desc') or {}).get('source')),
        files=dict(importable=len(dl), direct_links=len(direct), other=len(res) - len(dl) - len(direct)))


def _hub_desc(it):
    sh = it.get('sh', 0)
    if sh not in _DESC:
        _DESC[sh] = json.loads((STATIC / 'hub' / f'desc_{sh:02d}.json').read_text(encoding='utf-8'))
    return _DESC[sh].get(it['k']) or {}


def _year(name):
    m = re.search(r'(?<!\d)(19[5-9]\d|20[0-4]\d)(?:0101)?(?!\d)', name or '')
    return int(m.group(1)) if m else None


def t_get_hub_item(key):
    """รายละเอียดชุดใน Data hub: คำอธิบายจากต้นทาง + ไฟล์ที่ดาวน์โหลดเข้าคลังได้ (พร้อมปี) — ใช้เลือกปี/ไฟล์ก่อนเสนอดาวน์โหลด"""
    it = next((x for x in _hub() if x['k'] == key), None)
    if it is None:
        raise ToolError(f'ไม่พบ {key} ใน Data hub — ใช้ key จาก search_data_hub')
    d = _hub_desc(it)
    res = []
    for r in d.get('resources') or []:
        u = r.get('url') or ''
        ok = bool(DL_PAT.search(u)) and not r.get('key')
        res.append(dict(name=r.get('name'), format=r.get('format'), year=_year(r.get('name') or u), url=u, size_mb=round(r['size'] / 1e6, 1) if r.get('size') else None,
                        downloadable=ok))
    dl = [r for r in res if r['downloadable']]
    direct = [dict(name=r['name'], year=r['year'], format=r['format'], url=r['url']) for r in res
              if not r['downloadable'] and re.search(r'\.(zip|gpkg|csv|xlsx?|nc|h5|kmz?|shp|parquet|7z)(/content)?(\?|$)', r['url'] or '', re.I)]
    note = None
    if not dl:
        note = {'gee': 'อยู่บน Google Earth Engine — แอปดาวน์โหลดเองไม่ได้ (ต้องใช้บัญชี GEE ส่งออกเป็น GeoTIFF แล้วเพิ่มเข้าคลัง)',
                'pc': 'อยู่บน Planetary Computer — ถ้าไม่อยู่ในเครื่องมือภาพดาวเทียม แอปดาวน์โหลดเองไม่ได้'}.get(it.get('s'), 'ไม่มีไฟล์ที่แอปดาวน์โหลดเองได้ — เปิดลิงก์ต้นทางเพื่อดาวน์โหลดเองแล้วเพิ่มเข้าคลัง')
    desc = ((d.get('desc') or {}).get('text') or '')
    card = _data_card(it, d, dl, direct, res)
    if card['access']['satellite_collection']:
        note = f'ดึงด้วยเครื่องมือภาพดาวเทียมได้ทันที (งาน satellite collection="{card["access"]["satellite_collection"]}") ไม่ต้องดาวน์โหลดไฟล์'
    return dict(key=it['k'], title=it.get('t'), card=card, platform=it.get('p'), provider=it.get('pr'), coverage=it.get('cv'), license=it.get('l') or it.get('lc'),
                url=it.get('u'), description=desc[:1500] + ('…' if len(desc) > 1500 else ''), description_source=(d.get('desc') or {}).get('source'),
                years_available=sorted({r['year'] for r in dl if r['year']}) or it.get('y'),
                downloadable_files=dl[:60], direct_links_app_cannot_import=direct[:40], other_files=len(res) - len(dl) - len(direct),
                gee_id=it.get('id') if it.get('s') == 'gee' else None, note=note)


STOP = {'thailand', 'thai', 'ไทย', 'ประเทศไทย', 'raster', 'data', 'dataset', 'datasets', 'map', 'maps', 'annual', 'global', 'the', 'of', 'and',
        'for', 'in', 'grid', 'gridded', 'file', 'files', 'tif', 'geotiff', 'layer', 'ข้อมูล', 'แผนที่', 'รายปี', '-', '/', 'change', 'index'}
# คำพ้อง: ผู้ช่วยมักค้นด้วยคำที่ต่างจากชื่อชุด (PM2.5 ↔ air pollution, built-up ↔ GHSL ...) — ขยายคำค้นให้เอง
SYN = {
    'pm2.5': ['pm25', 'pm 2.5', 'particulate', 'air pollution', 'air quality', 'aerosol', 'pm'], 'pm25': ['pm2.5', 'particulate', 'air pollution', 'air quality'],
    'pm': ['pm2.5', 'particulate', 'air quality'], 'air': ['air quality', 'air pollution', 'pm2.5', 'aerosol'], 'pollution': ['air quality', 'pm2.5', 'no2'],
    'built-up': ['built', 'ghsl', 'settlement', 'urban', 'impervious', 'building'], 'built': ['ghsl', 'settlement', 'urban', 'impervious', 'building'],
    'urban': ['built', 'ghsl', 'settlement', 'city', 'impervious'], 'settlement': ['ghsl', 'built', 'urban'], 'impervious': ['built', 'urban', 'ghsl'],
    'lst': ['land surface temperature', 'temperature', 'thermal', 'modis lst'], 'heat': ['land surface temperature', 'temperature', 'thermal', 'lst'],
    'temperature': ['lst', 'thermal', 'climate'], 'thermal': ['lst', 'temperature'],
    'flood': ['inundation', 'surface water', 'flooding', 'water'], 'recurrence': ['occurrence', 'frequency'], 'inundation': ['flood', 'surface water'],
    'drought': ['spi', 'spei', 'soil moisture', 'precipitation', 'dryness'], 'rainfall': ['precipitation', 'chirps', 'rain'], 'rain': ['precipitation', 'rainfall'],
    'population': ['worldpop', 'people', 'pop'], 'night': ['nighttime lights', 'viirs', 'dmsp'], 'nighttime': ['night', 'viirs', 'lights'], 'lights': ['nighttime', 'viirs'],
    'ndvi': ['vegetation', 'evi', 'greenness'], 'vegetation': ['ndvi', 'evi', 'forest'], 'green': ['ndvi', 'vegetation', 'tree cover'],
    'roads': ['road', 'openstreetmap', 'osm', 'transport'], 'road': ['roads', 'openstreetmap', 'osm'], 'health': ['hospital', 'health facilities', 'clinic'],
    'hospital': ['health', 'health facilities'], 'mangrove': ['mangroves', 'coastal', 'wetland'], 'wetland': ['wetlands', 'mangrove'], 'dem': ['elevation', 'srtm', 'terrain'],
    'elevation': ['dem', 'srtm', 'terrain'], 'landcover': ['land cover', 'lulc', 'worldcover'], 'cropland': ['agriculture', 'crop', 'farmland'],
    'น้ำท่วม': ['flood', 'inundation'], 'ประชากร': ['population', 'worldpop'], 'อุณหภูมิ': ['temperature', 'lst'], 'ฝุ่น': ['pm2.5', 'air quality'],
}
# ชุดที่ดึงได้ทันทีด้วยเครื่องมือภาพดาวเทียม (ไม่ต้องหาไฟล์) — คำค้น → คอลเลกชัน
SAT_HINT = {
    'modis-11A2-061': ['lst', 'land surface temperature', 'heat', 'temperature', 'thermal', 'อุณหภูมิ', 'ความร้อน'],
    'landsat-c2-l2': ['landsat', 'thermal', 'lst', 'heat', 'temperature', 'ndvi', 'ndwi', 'ndbi'],
    'sentinel-2-l2a': ['sentinel-2', 'ndvi', 'ndwi', 'ndbi', 'vegetation', 'imagery', 'optical', 'reflectance', 'ภาพถ่ายดาวเทียม'],
    'sentinel-1-rtc': ['sar', 'radar', 'sentinel-1', 'flood', 'inundation', 'water', 'น้ำท่วม', 'เรดาร์'],
    'alos-palsar-mosaic': ['palsar', 'l-band', 'sar', 'forest', 'biomass'],
    'modis-13Q1-061': ['ndvi', 'evi', 'vegetation', 'greenness', 'modis'],
    'cop-dem-glo-30': ['dem', 'elevation', 'terrain', 'slope', 'srtm', 'coastal', 'ความสูง'],
    'esa-worldcover': ['land cover', 'landcover', 'worldcover', 'built', 'built-up', 'urban', 'cropland', 'wetland', 'mangrove', 'การใช้ที่ดิน'],
    'io-lulc-annual-v02': ['land cover', 'lulc', 'built', 'built-up', 'urban', 'urban expansion', 'cropland', 'การใช้ที่ดิน'],
    'jrc-gsw': ['flood', 'recurrence', 'inundation', 'surface water', 'water', 'occurrence', 'น้ำท่วม', 'แหล่งน้ำ'],
}


def _terms(query):
    q = (query or '').lower().replace(',', ' ').replace(';', ' ')
    words = [w.strip('()[]"\'') for w in q.split() if w.strip('()[]"\'')]
    words = [w for w in words if w not in STOP] or words
    phrases = [q] if len(words) > 1 else []
    return words, phrases


def t_search_data_hub(query, limit=12):
    """ค้นแหล่งข้อมูลภายนอกใน Data hub — ไม่ต้องตรงทุกคำ (ให้คะแนนตามคำที่เจอ + คำพ้อง) · ดันชุดที่นำเข้าได้/ครอบไทยขึ้นก่อน
    + บอกชุดที่ดึงได้ทันทีด้วยเครื่องมือภาพดาวเทียม (satellite_tool)"""
    from . import hub_access, ops_sat
    sat = set(ops_sat.BY_ID)
    words, phrases = _terms(query)
    exp = {w: SYN.get(w, []) for w in words}
    scored = []
    for it in _hub():
        title = (it.get('t') or '').lower()
        hay = ' '.join([title, it.get('pr', ''), it.get('k', ''), it.get('tr', ''), str(it.get('id') or ''), ' '.join(it.get('kw') or []), ' '.join(it.get('th') or [])]).lower()
        sc, hit = 0.0, 0
        for w in words:
            if w in hay:
                sc += 3 if w in title else 1
                hit += 1
            elif any(x in hay for x in exp[w]):
                sc += 0.8
                hit += 1
        sc += sum(4 for ph in phrases if ph in hay)
        if not hit:
            continue
        sc *= hit / len(words)                               # ครบหลายคำได้คะแนนมากกว่า แต่ไม่บังคับครบ
        lv, why = hub_access.access(it, sat)
        sc += (2 if it.get('cv') == 'thailand' else 0) + (3 if lv == 'app' else 1 if lv == 'open' else 0)
        scored.append((sc, it, lv, why))
    scored.sort(key=lambda x: -x[0])
    res = [dict(key=it['k'], title=it.get('t'), provider=it.get('pr'), platform=it.get('p'), type=it.get('tr'), coverage=it.get('cv'),
                license=it.get('lc'), years=it.get('y'), files_app_can_import=it.get('ni') or 0, direct_download_links=it.get('nf') or 0,
                access=dict(level=lv, detail=why), page=it.get('u'), gee_id=it.get('id') if it.get('s') == 'gee' else None,
                n_variables=it.get('nv'), resolution_m=it.get('g'), cadence=it.get('cd'), start=it.get('a'), end=it.get('b'), years_with_files=it.get('yl'),
                satellite_collection=it['k'].split(':', 1)[1] if it.get('s') == 'pc' and it['k'].split(':', 1)[1] in sat else None)
           for _, it, lv, why in scored[:int(limit or 12)]]
    q = (query or '').lower()
    tool = [dict(collection=c['id'], name=c['name'], years=c['years'], bands=list(c['bands']), how='งาน satellite (ดึงได้ทันที ไม่ต้องมีบัญชี)')
            for c in ops_sat.COLLECTIONS if any(h in q for h in SAT_HINT.get(c['id'], [])) or any(h in words or h in q for w in words for h in SYN.get(w, []) if h in SAT_HINT.get(c['id'], []))]
    return dict(results=res, satellite_tool=tool,
                tip='ไม่เจอ → ลองคำสั้น 1–2 คำ (อังกฤษ) หลายรอบ เช่น "ghsl", "pm2.5", "air quality", "lst" · ดู satellite_tool ก่อนบอกผู้ใช้ว่าต้องไป GEE' if not res else None)


def t_list_folders():
    """โฟลเดอร์ในคลัง (id, ชื่อ, path)"""
    fs = _call('GET', '/api/folders')['folders']
    by = {f['id']: f for f in fs}

    def path(f):
        out = [f['name']]
        while f.get('parent_id') and f['parent_id'] in by:
            f = by[f['parent_id']]
            out.insert(0, f['name'])
        return '/'.join(out)
    return [dict(id=f['id'], path=path(f), parent_id=f.get('parent_id')) for f in fs]


def t_propose_create_folders(paths, purpose=None):
    """เสนอสร้างโฟลเดอร์ (หลายชั้นได้ เช่น "Urban_Heat_TH/raw_data") — ผู้ใช้ยืนยันครั้งเดียว"""
    ps = [str(x).strip().strip('/') for x in (paths or []) if str(x).strip().strip('/')]
    if not ps or len(ps) > 20:
        raise ToolError('ใส่ path 1–20 รายการ เช่น ["งานA/raw_data", "งานA/output"]')
    exist = {f['path'] for f in t_list_folders()}
    new = [x for x in ps if x not in exist]
    return _propose('create_folders', 'สร้างโฟลเดอร์: ' + ', '.join(ps), dict(paths=ps, new=new, purpose=purpose))


def t_propose_move_to_folder(dataset_ids, folder_id):
    """เสนอย้ายชุดข้อมูลเข้าโฟลเดอร์"""
    ids = [int(i) for i in dataset_ids or []]
    if not ids:
        raise ToolError('เลือกชุดข้อมูลอย่างน้อย 1 ชุด')
    f = next((x for x in t_list_folders() if x['id'] == int(folder_id)), None)
    if not f:
        raise ToolError(f'ไม่พบโฟลเดอร์ #{folder_id} (ดู list_folders)')
    names = [_call('GET', f'/api/datasets/{i}')['name'] for i in ids]
    return _propose('move_folder', f'ย้าย {len(ids)} ชุดเข้า {f["path"]}', dict(dataset_ids=ids, folder_id=f['id'], folder=f['path'], names=names))


def _ensure_folders(paths):
    """สร้างโฟลเดอร์ตาม path (ข้ามที่มีอยู่แล้ว) → {path: id}"""
    out = {}
    for path in paths:
        parent = None
        acc = []
        for part in path.split('/'):
            acc.append(part)
            key = '/'.join(acc)
            cur = {f['path']: f['id'] for f in t_list_folders()}
            if key in cur:
                parent = cur[key]
            else:
                r = _call('POST', '/api/folders', dict(name=part, parent_id=parent))
                parent = r.get('id') or (r.get('folder') or {}).get('id')
        out[path] = parent
    return out


def t_analyze_bivariate(dataset_id, force=False):
    """สถิติความสัมพันธ์ของแผนที่ไบแวเรียต (ค่าชุดเดียวกับแผนที่) — คืนตัวเลขหลัก + การตีความ + คำเตือน"""
    r = _call('POST', f'/api/datasets/{int(dataset_id)}/bivstats', dict(force=bool(force)))
    if isinstance(r, dict) and r.get('error'):
        raise ToolError(r['error'])
    c = r['correlation']
    return dict(map=r['name'], x=r['x'], y=r['y'], resolution=r['resolution'], aoi=r.get('aoi'), n=r['sample']['n'],
                pearson_r=c['pearson_r'], pearson_ci95=c['pearson_ci95'], spearman_rho=c['spearman_rho'], log_pearson_r=c['log_pearson_r'],
                ols=c['ols'], n_effective=c['n_effective'], p_adjusted=c['p_adjusted'], moran=r['spatial'],
                cramers_v=r['crosstab']['cramers_v'], obs_exp=r['crosstab']['obs_exp'], anova=r['by_x_class']['anova'], kruskal=r['by_x_class']['kruskal'],
                y_by_x_class=r['by_x_class']['classes'], interpretation=r['interpretation'], warnings=r['warnings'],
                charts=[f'/api/datasets/{int(dataset_id)}/bivstats/{v}' for v in r['charts'].values()])


def t_get_data_knowledge(topics=None, query=None):
    """ความรู้ชนิดข้อมูล: วัดอะไร หน่วย การแปลงค่า (สูตรพร้อมใช้) ช่วงค่าปกติ เหมาะ/ไม่เหมาะ ข้อควรระวัง ความน่าเชื่อถือ + หลักการวิเคราะห์"""
    from . import knowledge
    return knowledge.get(topics, query)


def t_save_document(title, markdown):
    """บันทึกงานเขียนยาว (แคตาล็อก ตาราง ระเบียบวิธี ร่างรายงาน) เป็นเอกสาร — ชื่อเดิม = เวอร์ชันใหม่"""
    from . import ai_docs
    try:
        m = ai_docs.save(title, markdown, CURRENT_CHAT.get('id'))
    except ValueError as e:
        raise ToolError(str(e))
    return dict(ok=True, document=dict(title=m['title'], file=m['file'], version=m['version'], lines=m['lines'], tables=m['tables'],
                                       url=f'/api/ai/docs/{m["file"]}'),
                hint='ในแชตตอบแค่สรุปสั้น (≤ 8 บรรทัด) ว่าเอกสารมีอะไร/เปลี่ยนอะไร — ผู้ใช้เปิดเอกสารจากการ์ดได้')


def t_list_past_work(limit=8):
    """งานในบทสนทนาก่อน ๆ: แผนงาน (เป้าหมาย ข้อตกลง ขั้นตอน สิ่งที่ส่งมอบ) + เอกสารที่เขียนไว้ + โน้ตชุดข้อมูลล่าสุด"""
    from . import ai_docs, ai_plan
    plans = [dict(chat_id=p['chat_id'], current=p['chat_id'] == CURRENT_CHAT.get('id'), updated_at=p.get('updated_at'), goal=p.get('goal'),
                  purpose=p.get('purpose'), decisions=p.get('decisions'), delivered=p.get('delivered'),
                  steps=[f'[{s["status"]}] {s["title"]}' + (f' → #{",#".join(map(str, s["outputs"]))}' if s.get('outputs') else '') for s in p.get('steps') or []],
                  blockers=p.get('blockers')) for p in ai_plan.all_()[:int(limit or 8)]]
    docs = [dict(title=d['title'], file=d['file'], version=d['version'], updated_at=d['updated_at'], url=f'/api/ai/docs/{d["file"]}') for d in ai_docs.all_()[:20]]
    return dict(plans=plans, documents=docs, note='ประวัติข้อความแชตเก่าเก็บในเบราว์เซอร์ ผู้ช่วยไม่เห็น — แต่เห็นแผนงาน/เอกสาร/โน้ตเหล่านี้')


# ---------- แผนงานของบทสนทนา ----------
CURRENT_CHAT = {'id': None}


def t_update_plan(goal=None, purpose=None, audience=None, steps_json=None, decisions=None, blockers=None, folder_id=None, delivered=None):
    """เขียน/อัปเดตแผนงานของบทสนทนานี้ (เก็บถาวร แสดงให้ผู้ใช้เห็น) — ส่งเฉพาะช่องที่เปลี่ยน"""
    import json as _json
    from . import ai_plan
    steps = None
    if steps_json is not None:
        try:
            steps = _json.loads(steps_json) if isinstance(steps_json, str) else steps_json
        except ValueError:
            raise ToolError('steps_json ต้องเป็น JSON: [{"title":"…","status":"todo|doing|done|blocked|skipped","outputs":[69],"note":"…"}]')
    if not CURRENT_CHAT['id']:
        raise ToolError('บทสนทนานี้ไม่มีรหัส (หน้าเว็บรุ่นเก่า) — รีเฟรชหน้าเว็บ')
    plan = ai_plan.update(CURRENT_CHAT['id'], goal=goal, purpose=purpose, audience=audience, steps=steps, decisions=decisions, blockers=blockers, folder_id=folder_id,
                          delivered=delivered)
    return dict(ok=True, plan=plan)


# ---------- action → ข้อเสนอ ----------
def _params(kind, params_json):
    if kind not in JOB_KINDS:
        raise ToolError(f'ชนิดงานต้องเป็นหนึ่งใน {", ".join(JOB_KINDS)}')
    try:
        p = json.loads(params_json) if isinstance(params_json, str) else dict(params_json or {})
    except ValueError:
        raise ToolError('params_json ไม่ใช่ JSON ที่ถูกต้อง')
    if kind in ('bivariate', 'hexbiv'):                      # สีไม่ได้ระบุ → พาเลทตามชื่อ (ค่าเริ่ม bluered) ขยายตามจำนวนคลาส
        nx, ny = int((p.get('x') or {}).get('n', 3)), int((p.get('y') or {}).get('n', 3))
        if not p.get('colors') or len(p['colors']) != nx * ny:
            pal = palettes.BY_ID.get(p.get('palette') or palettes.DEFAULT_PALETTE, palettes.BY_ID[palettes.DEFAULT_PALETTE])
            p['colors'] = palettes.interpolate(pal['colors'], nx, ny)
            p['palette'] = 'b:' + pal['id']
        p.setdefault('highlight', [])
        p.setdefault('tie', 'high')
        p.setdefault('count_down_valid', 'positive')
    return p


def _propose(action, title, args, check=None):
    pid = secrets.token_hex(8)
    est = None
    if check:
        try:
            est = check()
        except Exception as e:                              # ประเมินไม่ได้ (เช่น ยังไม่ได้ยืนยันประเภทค่าในข้อเสนอเดียวกัน) → ตรวจอีกครั้งตอนรัน
            est = dict(ok=False, error=str(e))
    with _lock:
        now = time.time()
        for k in [k for k, v in _PROPOSALS.items() if now - v['t'] > PROPOSAL_TTL]:
            _PROPOSALS.pop(k, None)
        _PROPOSALS[pid] = dict(id=pid, action=action, title=title, args=args, estimate=est, t=now)
    return dict(proposal_id=pid, status='รอผู้ใช้กดยืนยันในแชต — ยังไม่ได้รัน', title=title, estimate=est)


def t_propose_set_value_type(dataset_id, value_type):
    if value_type not in ('count', 'density', 'class'):
        raise ToolError('value_type ต้องเป็น count / density / class')
    d = _call('GET', f'/api/datasets/{int(dataset_id)}')
    if d['kind'] != 'raster':
        raise ToolError('ตั้งประเภทค่าได้เฉพาะราสเตอร์')
    return _propose('set_value_type', f'ตั้งประเภทค่า #{d["id"]} {d["name"]} → {value_type}', dict(dataset_id=d['id'], value_type=value_type),
                    lambda: dict(ok=True, current=d.get('value_type'), confirmed=bool(d.get('value_type_confirmed'))))


def _res_ids(kind, p):
    """ชุดข้อมูลที่กำหนดตัวเลือกความละเอียดของงานนี้ (งานที่ใช้ target_res จากรายการ)"""
    if kind == 'bivariate':
        return [(p.get(a) or {}).get('dataset_id') for a in ('x', 'y')]
    if kind == 'resample':
        return [p.get('dataset_id')]
    if kind == 'change':
        return [p.get('a_id'), p.get('b_id')]
    if kind == 'vgrid':
        return list(p.get('dataset_ids') or [])
    if kind == 'rasterize' and p.get('grid') == 'ref':
        return [p.get('ref_dataset_id')]
    return []


def t_propose_run_job(kind, params_json, title=None, purpose=None):
    p = _params(kind, params_json)
    if purpose:                                             # วัตถุประสงค์ → ลง lineage ของผลลัพธ์ (รายงานดึงไปใช้ได้)
        p['purpose'] = str(purpose)[:500]
    t = title or (p.get('name') and f'{kind}: {p["name"]}') or kind
    ids = [i for i in _res_ids(kind, p) if i]
    res_opts = None
    if ids:                                                 # การ์ดให้ผู้ใช้เปลี่ยนความละเอียดเองได้ก่อนยืนยัน
        try:
            res_opts = t_resolution_options(ids)
        except Exception:
            res_opts = None

    def check():
        r = _call('POST', '/api/estimate', dict(kind=kind, params=p))
        if not r.get('ok'):
            return dict(ok=False, error=r.get('error'))
        g = r.get('grid') or {}
        return dict(ok=True, resolution=g.get('res_label'), size=[g.get('width'), g.get('height')], aoi=r.get('aoi'), warnings=r.get('warnings') or [])
    out = _propose('run_job', t, dict(kind=kind, params=p), check)
    info = _info(p)
    with _lock:
        _PROPOSALS[out['proposal_id']].update(res_options=res_opts, info=info)
    return out


def _info(p):
    """ชื่อ/ประเภทค่าของชุดข้อมูล + ชื่อพื้นที่ศึกษาที่อ้างใน params — ให้การ์ดแสดงค่าที่ตั้งเป็นภาษาคน (ไม่ใช่ JSON)"""
    ids = set()
    for k, v in p.items():
        if k in ('dataset_id', 'ref_dataset_id', 'extent_dataset_id', 'a_id', 'b_id', 'link_id') and v:
            ids.add(int(v))
        elif k == 'dataset_ids':
            ids |= {int(i) for i in v or []}
        elif k in ('x', 'y') and isinstance(v, dict) and v.get('dataset_id'):
            ids.add(int(v['dataset_id']))
    ds = {}
    for i in ids:
        try:
            d = _call('GET', f'/api/datasets/{i}')
            ds[str(i)] = dict(name=d['name'], kind=d['kind'], value_type=d.get('value_type') if d['kind'] == 'raster' else None)
        except ToolError:
            ds[str(i)] = dict(name='(ไม่พบ)', kind=None, value_type=None)
    aois = {str(a['id']): a['name'] for a in t_list_study_areas()} if (p.get('aoi_id') or p.get('extent_aoi_id')) else {}
    return dict(datasets=ds, aois=aois)


def t_propose_create_study_area(name, source_dataset_id, field, values):
    d = _call('GET', f'/api/datasets/{int(source_dataset_id)}')
    body = dict(name=name, field=field, values=[str(v) for v in values or []])
    body['link_id' if d['kind'] == 'link' else 'dataset_id'] = d['id']
    return _propose('create_aoi', f'สร้างพื้นที่ศึกษา "{name}" จาก {d["name"]} ({field} = {", ".join(map(str, values[:5]))}{"…" if len(values) > 5 else ""})', body)


_POOL = None


def _inspect_quick(url, limit=25):
    """อ่านหัวไฟล์ทางเน็ตแต่ไม่เกิน limit วินาที (เซิร์ฟเวอร์ช้า เช่น Zenodo บางช่วง ทยอยส่งข้อมูลจน timeout ของ GDAL ไม่ทำงาน) → None ถ้าไม่ทัน"""
    global _POOL
    import concurrent.futures as cf
    from . import links
    if _POOL is None:
        _POOL = cf.ThreadPoolExecutor(4, thread_name_prefix='ai-inspect')
    fut = _POOL.submit(links.inspect, url)
    try:
        return fut.result(timeout=limit)
    except cf.TimeoutError:
        return None


def t_propose_download_data(hub_key, file_url, name, purpose, aoi_id=None, value_type=None, folder_id=None):
    """ดาวน์โหลดไฟล์จาก Data hub เข้าคลัง (ตัดตามกรอบพื้นที่ศึกษา) — รับเฉพาะ URL ที่อยู่ในรายการไฟล์ของชุดนั้นใน Data hub
    (AI ส่ง URL อื่นไม่ได้: กันดึงไฟล์จากที่ที่ไม่รู้จัก / คำสั่งแฝงในข้อมูล)"""
    from . import links
    item = t_get_hub_item(hub_key)
    f = next((x for x in item['downloadable_files'] if x['url'] == file_url), None)
    if f is None:
        raise ToolError('URL นี้ไม่อยู่ในรายการไฟล์ที่ดาวน์โหลดได้ของชุดนี้ — เลือกจาก get_hub_item.downloadable_files')
    if value_type not in (None, 'count', 'density', 'class'):
        raise ToolError('value_type ต้องเป็น count / density / class')
    aoi_name = None
    if aoi_id:
        aoi_name = next((a['name'] for a in t_list_study_areas() if a['id'] == int(aoi_id)), None)
        if aoi_name is None:
            raise ToolError(f'ไม่พบพื้นที่ศึกษา #{aoi_id}')
    args = dict(hub_key=hub_key, title=item['title'], file=f, name=str(name)[:120], aoi_id=int(aoi_id) if aoi_id else None,
                aoi_name=aoi_name, value_type=value_type, purpose=str(purpose)[:500], license=item.get('license'), source=item.get('url'),
                folder_id=int(folder_id) if folder_id else None)

    def check():
        info = _inspect_quick(file_url)                     # อ่านหัวไฟล์ทางเน็ต (ไม่โหลดทั้งไฟล์) · เซิร์ฟเวอร์ไม่รองรับ range → แค่ขนาดไฟล์
        if info is None:
            return dict(ok=False, error='เซิร์ฟเวอร์ตอบช้า อ่านหัวไฟล์ไม่ทันใน 25 วินาที — ยังดาวน์โหลดได้ (งานเบื้องหลังรอนานกว่านี้)')
        return dict(ok=True, type=info.get('type'), crs=info.get('crs'), size=[info.get('width'), info.get('height')],
                    res=info.get('res'), note=info.get('note'), range=info.get('range', True),
                    file_mb=round(info['file_bytes'] / 1e6, 1) if info.get('file_bytes') else None)
    t = f'ดาวน์โหลด "{name}" ← {f["name"]}' + (f' · ตัดตาม {aoi_name}' if aoi_name else ' · ทั้งไฟล์')
    return _propose('download', t, args, check)


def start_hub_import(hub_key, url, name, aoi_id=None, value_type=None, purpose=None, requested_by=None, folder_id=None):
    """นำเข้าไฟล์จาก Data hub (ใช้ร่วม: ผู้ช่วย AI หลังผู้ใช้ยืนยัน · ปุ่ม "นำเข้าคลัง" ในหน้า Data hub)
    URL ต้องเป็นไฟล์ที่นำเข้าได้ของชุดนั้นใน Data hub เท่านั้น → เพิ่มลิงก์ → งานดาวน์โหลด (ตัดกรอบพื้นที่ศึกษา) → ชุดใหม่ในคลัง"""
    from . import links
    item = t_get_hub_item(hub_key)
    f = next((x for x in item['downloadable_files'] if x['url'] == url), None)
    if f is None:
        raise ToolError('ไฟล์นี้ไม่อยู่ในรายการไฟล์ที่นำเข้าได้ของชุดนี้ใน Data hub')
    if value_type not in (None, 'count', 'density', 'class'):
        raise ToolError('value_type ต้องเป็น count / density / class')
    try:
        info = _inspect_quick(url)
    except links.LinkError:
        info = None
    if info is None:                                         # หัวไฟล์อ่านไม่ทัน (เซิร์ฟเวอร์ช้า) → ให้งานดาวน์โหลดลองเองด้วยเวลารอที่นานกว่า
        info = dict(type='cog' if re.search(r'\.tiff?(/content)?(\?|$)', url, re.I) else 'geojson', url=url, title=f['name'])
    nm = (name or re.sub(r'\.(tiff?|geo)?json$|\.tiff?$', '', f['name'], flags=re.I))[:120]
    lid = _call('POST', '/api/links', dict(info=info, name=f'{item["title"][:80]} · {f["name"]}'))['id']
    jp = dict(link_id=lid, aoi_id=int(aoi_id) if aoi_id else None, name=nm, value_type=value_type, purpose=purpose, hub_key=hub_key,
              folder_id=int(folder_id) if folder_id else None,
              requested_by=requested_by or dict(by='user', at=db.now()))
    r = _call('POST', '/api/jobs', dict(kind='download', params=jp))
    return dict(ok=True, job_id=r['job'], link_id=lid, message=f'เริ่มนำเข้า "{nm}" (งาน #{r["job"]}) — เสร็จแล้วจะเข้าคลังข้อมูล')


REPORT_TEMPLATES = {'gov_l': 'ราชการ A4 แนวนอน', 'gov_p': 'ราชการ A4 แนวตั้ง', 'ocha': 'สากลงานมนุษยธรรม (OCHA)',
                    'journal': 'ภาพประกอบบทความวิชาการ', 'poster_a3': 'โปสเตอร์ A3 แนวตั้ง', 'dashboard': 'Dashboard / อินโฟกราฟิก A4'}


def t_propose_create_report(dataset_ids, template='gov_l', title='', subtitle='', org='', author='', note='', caption='', map_no='', extent_aoi_id=None, purpose=''):
    """รายงานจัดหน้าอยู่ในเบราว์เซอร์ (ตัวออกแบบรายงาน) → ยืนยันแล้วหน้าเว็บเปิดตัวออกแบบพร้อมค่าที่ตั้งนี้ ผู้ใช้กดส่งออก PDF เอง"""
    if template not in REPORT_TEMPLATES:
        raise ToolError(f'template ต้องเป็นหนึ่งใน {", ".join(REPORT_TEMPLATES)}')
    names = []
    for i in dataset_ids or []:
        d = _call('GET', f'/api/datasets/{int(i)}')
        names.append(f'#{d["id"]} {d["name"]}')
    if not names:
        raise ToolError('เลือกชุดข้อมูลอย่างน้อย 1 ชุด (ปกติคือแผนที่ไบแวเรียตที่สร้างแล้ว)')
    if extent_aoi_id:
        t_ids = [a['id'] for a in t_list_study_areas()]
        if int(extent_aoi_id) not in t_ids:
            raise ToolError(f'ไม่พบพื้นที่ศึกษา #{extent_aoi_id}')
    if purpose and not note:                                # วัตถุประสงค์ขึ้นเป็นหมายเหตุของรายงาน (แก้ได้ในตัวออกแบบ)
        note = f'วัตถุประสงค์: {purpose}'
    spec = dict(dataset_ids=[int(i) for i in dataset_ids], template=template, extent_aoi_id=int(extent_aoi_id) if extent_aoi_id else None, purpose=str(purpose)[:500] or None,
                meta={k: str(v)[:300] for k, v in dict(title=title, subtitle=subtitle, org=org, author=author, note=note, caption=caption, map_no=map_no).items() if v})
    return _propose('create_report', f'รายงาน "{title or names[0]}" · {REPORT_TEMPLATES[template]} · ' + ', '.join(names[:4]), spec,
                    lambda: dict(ok=True, template=REPORT_TEMPLATES[template], layers=names))


def proposals_public(ids):
    with _lock:
        return [dict(id=p['id'], action=p['action'], title=p['title'], estimate=p['estimate'], res_options=p.get('res_options'), info=p.get('info'),
                     args=p['args'] if p['action'] != 'run_job' else dict(kind=p['args']['kind'], params={k: v for k, v in p['args']['params'].items() if k != 'colors'}))
                for p in (_PROPOSALS.get(i) for i in ids) if p]


def execute(pid, model=None, params=None):
    """ผู้ใช้กดยืนยัน → รันข้อเสนอ (ครั้งเดียว) · params = ค่าที่ผู้ใช้แก้ในการ์ดเอง (เฉพาะงาน) — ตรวจซ้ำด้วย validate_job ตอนสร้างงาน"""
    with _lock:
        p = _PROPOSALS.pop(pid, None)
    if not p:
        raise ToolError('ข้อเสนอนี้หมดอายุหรือถูกใช้ไปแล้ว — ให้ผู้ช่วยเสนอใหม่')
    a = p['args']
    if p['action'] == 'create_report':
        return dict(ok=True, report=a, message='เปิดตัวออกแบบรายงานพร้อมค่าที่ตั้งแล้ว — ตรวจแล้วกด "ส่งออก" เพื่อได้ PDF')
    if p['action'] == 'download':                            # เพิ่มลิงก์เข้าคลัง → งานดาวน์โหลด (ตัดกรอบพื้นที่ศึกษา) → ชุดข้อมูลใหม่ในคลัง
        vt = a.get('value_type')
        if isinstance(params, dict) and 'value_type' in params and params['value_type'] in ('count', 'density', 'class', None):
            vt = params['value_type']                          # ผู้ใช้เลือกประเภทค่าในการ์ดเอง
        return start_hub_import(a['hub_key'], a['file']['url'], a['name'], a.get('aoi_id'), vt, a.get('purpose'),
                                dict(by='ai_assistant', model=model, confirmed_at=db.now()), a.get('folder_id'))
    if p['action'] == 'run_job' and isinstance(params, dict):
        a = dict(a, params=_params(a['kind'], params))
        p['user_edited'] = True
    if p['action'] == 'set_value_type':
        _call('PATCH', f'/api/datasets/{a["dataset_id"]}', dict(value_type=a['value_type'], value_type_confirmed=True))
        return dict(ok=True, message=f'ตั้งประเภทค่า #{a["dataset_id"]} เป็น {a["value_type"]} แล้ว')
    if p['action'] == 'create_folders':
        ids = _ensure_folders(a['paths'])
        return dict(ok=True, folders=ids, message='สร้างโฟลเดอร์แล้ว: ' + ', '.join(f'{k} (#{v})' for k, v in ids.items()))
    if p['action'] == 'move_folder':
        _call('POST', '/api/folders/move', dict(dataset_ids=a['dataset_ids'], folder_ids=[], to=a['folder_id']))
        return dict(ok=True, message=f'ย้าย {len(a["dataset_ids"])} ชุดเข้า {a["folder"]} (#{a["folder_id"]}) แล้ว')
    if p['action'] == 'create_aoi':
        r = _call('POST', '/api/aoi', a)
        aid = r.get('id') or (r.get('aoi') or {}).get('id')
        return dict(ok=True, aoi_id=aid, message=f'สร้างพื้นที่ศึกษา #{aid} "{a["name"]}" แล้ว')
    params = dict(a['params'], requested_by=dict(by='ai_assistant', model=model, confirmed_at=db.now(), edited_by_user=bool(p.get('user_edited'))))
    r = _call('POST', '/api/jobs', dict(kind=a['kind'], params=params))
    return dict(ok=True, job_id=r['job'], message=f'เริ่มงาน #{r["job"]} แล้ว')


def reject(pid):
    with _lock:
        _PROPOSALS.pop(pid, None)



# ---------- ภาพดาวเทียม (Planetary Computer) ----------
def t_satellite_catalog():
    """คอลเลกชันภาพดาวเทียมที่ดึงได้ (ไม่ต้องมีบัญชี) + แบนด์ + ช่วงปี + ความละเอียด (zoom)"""
    from . import ops_sat
    return dict(collections=[dict(id=c['id'], name=c['name'], kind=c['kind'], years=c['years'], revisit=c['revisit'], native_m=c['native_m'],
                                  cloud_filter=c['cloud'], default_bands=c['default'], bands=c['bands'], note=c['note'], license=c['license'])
                             for c in ops_sat.COLLECTIONS],
                zoom_options=ops_sat.zoom_options(), auth='ไม่ต้องมีบัญชี/โทเคน')


def t_search_satellite(collection, aoi_id, date_from=None, date_to=None, cloud_max=None):
    r = _call('POST', '/api/satellite/search', dict(collection=collection, aoi_id=aoi_id, date_from=date_from, date_to=date_to, cloud_max=cloud_max))
    if isinstance(r, dict) and r.get('error'):
        raise ToolError(r['error'])
    return r


# ---------- ประเมินผลงานตัวเอง ----------
def t_review_output(dataset_id, expectation=None):
    """ตรวจผลลัพธ์: ครอบพื้นที่ครบไหม ค่าสมเหตุสมผลไหม มีคำเตือนจากงานไหม → ข้อสังเกต + สิ่งที่ควรแก้"""
    import math
    d = _call('GET', f'/api/datasets/{int(dataset_id)}')
    prof = _call('GET', f'/api/datasets/{int(dataset_id)}/profile')
    m, st = d.get('meta') or {}, d.get('stats') or {}
    mb = prof.get('made_by') or {}
    raw = mb.get('raw') or {}
    summ, params = raw.get('summary') or mb.get('summary') or {}, raw.get('params') or {}
    checks = []

    def ck(ok, item, detail=''):
        checks.append(dict(ok=bool(ok), item=item, detail=detail))
    if d['kind'] == 'raster':
        if not st:
            ck(False, 'สถิติ', 'ยังคำนวณสถิติไม่เสร็จ — รอสักครู่แล้วตรวจใหม่')
        else:
            lo, hi, valid = st.get('min'), st.get('max'), st.get('valid') or 0
            tot = (m.get('width') or 0) * (m.get('height') or 0)
            ck(valid > 0, 'มีข้อมูล', f'{valid:,} พิกเซลมีค่า จาก {tot:,} ({valid / tot:.0%} ของกรอบ)' if tot else '')
            ck(lo is not None and hi is not None and hi > lo, 'ค่าไม่คงที่', f'ช่วงค่า {lo} – {hi}')
            aid = params.get('aoi_id')
            if aid and m.get('geographic') and m.get('transform') and valid:
                a = next((x for x in t_list_study_areas() if x['id'] == int(aid)), None)
                b = m.get('bounds') or [0, 0, 0, 0]
                r = abs(m['transform'][0])
                km2 = valid * (r * 111.32) ** 2 * math.cos(math.radians((b[1] + b[3]) / 2))
                if a and a.get('area_km2'):
                    cov = km2 / a['area_km2']
                    ck(cov > 0.9, 'ครอบพื้นที่ศึกษา', f'มีค่า ≈ {km2:,.0f} ตร.กม. = {cov:.0%} ของ "{a["name"]}" ({a["area_km2"]:,.0f} ตร.กม.)'
                       + ('' if cov > 0.9 else ' — ขาดบางส่วน (ภาพไม่ครบ/เมฆ/ข้อมูลไม่ทับกัน)'))
            n = (d.get('name') or '').lower() + ' ' + str(params.get('expr') or '')
            if lo is not None and hi is not None and (any(k in n for k in ('ndvi', 'ndwi', 'ndbi', 'evi')) or ('(' in n and '-' in n and '+' in n and '/' in n)):
                good = lo >= -1.0001 and hi <= 1.0001
                ck(good, 'ช่วงดัชนี −1…1', f'{lo} – {hi}' + ('' if good else ' — เกินช่วง: แบนด์อาจผิดลำดับ/ยังไม่แปลงสเกล/มี offset'))
            if d.get('value_type') == 'count' and st.get('sum') is not None:
                ck(True, 'ผลรวม', f'{st["sum"]:,.0f}')
    if m.get('satellite') or mb.get('operation') == 'satellite':
        tw, tt = summ.get('tiles_with_data'), summ.get('tiles')
        if tt:
            ck(tw == tt, 'ไทล์มีภาพครบ', f'{tw}/{tt}' + ('' if tw == tt else ' — ส่วนที่ไม่มีภาพ: ขยายช่วงวันที่หรือเพิ่มเกณฑ์เมฆ'))
        cl = summ.get('cloud') or {}
        if cl:
            ck((cl.get('median') or 0) <= 30, 'เมฆ', f'ภาพที่ใช้ เมฆ {cl.get("min", 0):.0f}–{cl.get("max", 0):.0f}% (มัธยฐาน {cl.get("median", 0):.0f}%)')
        if summ.get('first'):
            ck(True, 'ช่วงภาพ', f'{summ.get("images")}{"+ (นับถึงขีดจำกัด)" if summ.get("images_more") else ""} ภาพ {summ.get("first")} – {summ.get("last")}')
        for b, x in (summ.get('bands') or {}).items():
            ck(x.get('valid_pixels', 0) > 0, f'แบนด์ {b}', f'{x.get("min")} – {x.get("max")} (เฉลี่ย {x.get("mean"):.4g})' if x.get('mean') is not None else 'ว่าง')
        if summ.get('collection') == 'sentinel-2-l2a' and (summ.get('first') or '') < '2022-01-25' < (summ.get('last') or ''):
            ck(False, 'Sentinel-2 offset', 'ภาพคร่อม 25 ม.ค. 2565 — ค่าหลังวันนั้นบวก 1000 ปนกัน')
    for w in mb.get('warnings') or []:
        ck(False, 'คำเตือนจากงาน', w)
    return dict(dataset=dict(id=d['id'], name=d['name'], kind=d['kind'], value_type=d.get('value_type')), expectation=expectation,
                purpose=params.get('purpose'), checks=checks, problems=[c for c in checks if not c['ok']],
                made_by=dict(operation=mb.get('operation'), settings=mb.get('settings')))

# ---------- ทะเบียนเครื่องมือ (schema เรียบง่าย ใช้ได้ทั้ง Anthropic / OpenAI / Gemini) ----------
S, I, N, B = dict(type='string'), dict(type='integer'), dict(type='number'), dict(type='boolean')
TOOLS = [
    ('list_datasets', 'read', t_list_datasets, 'รายการชุดข้อมูลในคลัง (กรองด้วยคำค้น/ชนิด/บทบาทได้) — ใช้ก่อนอ้าง #id ทุกครั้ง',
     dict(query=S, kind=dict(type='string', enum=['raster', 'vector', 'link']), role=dict(type='string', enum=['input', 'derived', 'map'])), []),
    ('get_dataset', 'read', t_get_dataset, 'รายละเอียดชุดข้อมูล: ประเภทค่า (ยืนยันแล้วหรือยัง + ที่แอปเดา), ความละเอียด, CRS, ขอบเขต, สถิติ, ฟิลด์', dict(dataset_id=I), ['dataset_id']),
    ('list_study_areas', 'read', t_list_study_areas, 'รายการพื้นที่ศึกษา (builtin = พื้นฐาน เช่น ประเทศไทย)', {}, []),
    ('resolution_options', 'read', t_resolution_options, 'ตัวเลือกความละเอียดผลลัพธ์ที่ใช้ได้กับชุดข้อมูลเหล่านี้ (ค่า value ใช้ใส่ target_res)',
     dict(dataset_ids=dict(type='array', items=I)), ['dataset_ids']),
    ('preview_classes', 'read', t_preview_classes, 'พรีวิวเกณฑ์แบ่งคลาสของชุดข้อมูล (สัดส่วนพิกเซล/ค่าในแต่ละคลาส)',
     dict(dataset_id=I, method=dict(type='string', enum=['breaks', 'quantile', 'equal']), n=I, metric=dict(type='string', enum=['density', 'per_pixel', 'value']),
          breaks=dict(type='array', items=N)), ['dataset_id']),
    ('estimate_job', 'read', t_estimate_job, 'ตรวจค่าที่ตั้ง + ประเมินขนาดงานโดยไม่รัน (ใช้ก่อนเสนองาน)', dict(kind=dict(type='string', enum=list(JOB_KINDS)), params_json=S), ['kind', 'params_json']),
    ('get_dataset_profile', 'read', t_get_dataset_profile, 'ประวัติชุดข้อมูล: ไฟล์อะไร รูปแบบ มาจากไหน ชุดต้นทาง (พ่อแม่) ค่าที่ตั้ง ชุดที่ทำต่อ (ลูก) โน้ต — ใช้ตอบคำถามที่มาของข้อมูล', dict(dataset_id=I), ['dataset_id']),
    ('write_dataset_note', 'note', t_write_dataset_note,
     'เขียนโน้ตสั้น ๆ ในประวัติชุดข้อมูล (2–5 ประโยค): เป็นข้อมูลอะไร หน่วย/ความหมายของค่า แหล่ง ปี วัตถุประสงค์ ข้อควรระวัง — ใช้หลังดาวน์โหลดหรือสร้างชุดใหม่เสร็จ (ไม่ต้องยืนยัน ไม่แตะข้อมูล)',
     dict(dataset_id=I, text=S), ['dataset_id', 'text']),
    ('job_status', 'read', t_job_status, 'สถานะงาน + ชุดข้อมูลผลลัพธ์เมื่อเสร็จ', dict(job_id=I), ['job_id']),
    ('list_jobs', 'read', t_list_jobs, 'งานล่าสุด', dict(limit=I), []),
    ('search_data_hub', 'read', t_search_data_hub, 'ค้นแหล่งข้อมูลภายนอกใน Data hub (GEE, Planetary Computer, พอร์ทัลไทย, Zenodo ฯลฯ) — คำอังกฤษสั้น 1–2 คำต่อครั้ง ค้นหลายรอบ เช่น "population", "ghsl", "pm2.5" · ผลมี satellite_tool = ชุดที่ดึงได้ทันทีด้วยงาน satellite', dict(query=S, limit=I), ['query']),
    ('get_hub_item', 'read', t_get_hub_item, 'บัตรข้อมูลของชุดใน Data hub (card): หมวด · ตัวแปร/แบนด์ (หน่วย scale offset รหัสชั้น) · ช่วงเวลา/ความถี่/ปีที่มีไฟล์ · ความละเอียด/ขอบเขต · ต้องมีบัญชีไหม/วิธีได้มา · ผู้ผลิต/สัญญาอนุญาต/การอ้างอิง + ไฟล์ที่นำเข้าได้ (url ใช้กับ propose_download_data)', dict(key=S), ['key']),
    ('satellite_catalog', 'read', t_satellite_catalog, 'ภาพดาวเทียมที่ดึงได้ทันที (Planetary Computer, ไม่ต้องมีบัญชี): Sentinel-2, Landsat, SAR (Sentinel-1, ALOS PALSAR), MODIS NDVI, DEM, การใช้ที่ดิน, น้ำผิวดิน — แบนด์/ช่วงปี/ความละเอียด', {}, []),
    ('search_satellite', 'read', t_search_satellite, 'ค้นภาพดาวเทียมในพื้นที่+ช่วงวันที่ (+เมฆสูงสุด %) → จำนวนภาพ วันที่ เมฆ — ใช้ก่อนเสนองาน satellite',
     dict(collection=S, aoi_id=I, date_from=S, date_to=S, cloud_max=N), ['collection', 'aoi_id']),
    ('review_output', 'read', t_review_output, 'ประเมินผลงานตัวเอง: ตรวจชุดผลลัพธ์ (ครอบพื้นที่ครบไหม ช่วงค่าสมเหตุสมผลไหม ภาพ/เมฆ คำเตือนของงาน) — เรียกทุกครั้งหลังงานเสร็จ ก่อนสรุปให้ผู้ใช้',
     dict(dataset_id=I, expectation=S), ['dataset_id']),
    ('update_plan', 'note', t_update_plan,
     'เขียน/อัปเดตแผนงานของบทสนทนา (ผู้ใช้เห็นเป็นแผงในแชต · ส่งกลับให้คุณทุกรอบ) — เรียกเมื่อเริ่มงานหลายขั้น และทุกครั้งที่ขั้นเปลี่ยนสถานะ/ได้ชุดใหม่/ผู้ใช้ตัดสินใจอะไร · ส่งเฉพาะช่องที่เปลี่ยน',
     dict(goal=S, purpose=S, audience=S, steps_json=dict(type='string', description='JSON array [{"title","status":"todo|doing|done|blocked|skipped","outputs":[ids],"note"}] — ส่งทั้งรายการ'),
          decisions=dict(type='array', items=S), blockers=dict(type='array', items=S), folder_id=I,
          delivered=dict(type='array', items=S, description='ทุกสิ่งที่ส่งมอบแล้ว (ชื่อตัวชี้วัด/เอกสาร/แผนที่) — ส่งทั้งรายการ')), []),
    ('save_document', 'note', t_save_document, 'บันทึกงานเขียนยาวเป็นเอกสาร (markdown: ตาราง แคตาล็อก ระเบียบวิธี ร่างรายงาน) — ใช้แทนการพิมพ์ยาวในแชตทุกครั้งที่เกิน ~25 บรรทัดหรือมีตารางใหญ่ · ชื่อเดิม = อัปเดตเวอร์ชัน',
     dict(title=S, markdown=S), ['title', 'markdown']),
    ('list_past_work', 'read', t_list_past_work, 'งานในบทสนทนาก่อน ๆ (แผนงาน ข้อตกลง สิ่งที่ส่งมอบ เอกสาร) — ใช้เมื่อผู้ใช้ถามถึงแชตเก่า/งานที่เคยทำ หรือเริ่มแชตใหม่ที่ต่อจากงานเดิม', dict(limit=I), []),
    ('get_data_knowledge', 'read', t_get_data_knowledge,
     'คลังความรู้ข้อมูล: ข้อมูลชนิดนี้วัดอะไร หน่วย การแปลงค่า/calibration (สูตรใช้กับ calc ได้ทันที) ช่วงค่าปกติ เหมาะ/ไม่เหมาะ ข้อควรระวัง ความน่าเชื่อถือ + หลักการ (ประเภทค่า MAUP เวลา ไบแวเรียต การเลือกแหล่ง) — topics ดูจาก knowledge_topics ของชุดข้อมูล หรือใส่ query เป็นชื่อชุด',
     dict(topics=dict(type='array', items=S), query=S), []),
    ('analyze_bivariate', 'read', t_analyze_bivariate,
     'สถิติความสัมพันธ์ของแผนที่ไบแวเรียต: Pearson/Spearman, OLS, ตารางไขว้ (χ², Cramér\'s V, obs/exp), ANOVA + Kruskal–Wallis ของ Y ตามชั้น X, Moran\'s I + p ที่ปรับการเกาะกลุ่ม + กราฟ — ใช้หลังไบแวเรียตเสร็จ หรือเมื่อผู้ใช้ถามว่าสองตัวแปรสัมพันธ์กันไหม',
     dict(dataset_id=I, force=B), ['dataset_id']),
    ('list_folders', 'read', t_list_folders, 'โฟลเดอร์ในคลัง (id + path)', {}, []),
    ('propose_create_folders', 'action', t_propose_create_folders, 'เสนอสร้างโฟลเดอร์หลายชั้นในครั้งเดียว เช่น ["งานA/raw_data","งานA/output"] (ผู้ใช้ยืนยัน) — ผลลัพธ์ของงานถัดไปใส่ "folder_id" ใน params เพื่อเข้าโฟลเดอร์นั้นอัตโนมัติ',
     dict(paths=dict(type='array', items=S), purpose=S), ['paths']),
    ('propose_move_to_folder', 'action', t_propose_move_to_folder, 'เสนอย้ายชุดข้อมูลที่มีอยู่เข้าโฟลเดอร์ (ผู้ใช้ยืนยัน)', dict(dataset_ids=dict(type='array', items=I), folder_id=I), ['dataset_ids', 'folder_id']),
    ('propose_set_value_type', 'action', t_propose_set_value_type, 'เสนอยืนยัน/เปลี่ยนประเภทค่าของราสเตอร์ (ผู้ใช้ต้องกดยืนยัน)',
     dict(dataset_id=I, value_type=dict(type='string', enum=['count', 'density', 'class'])), ['dataset_id', 'value_type']),
    ('propose_run_job', 'action', t_propose_run_job, 'เสนองานประมวลผล (ผู้ใช้ต้องกดยืนยัน) — params_json เป็น JSON ตามสเปกใน system prompt',
     dict(kind=dict(type='string', enum=list(JOB_KINDS)), params_json=S, title=S, purpose=S), ['kind', 'params_json', 'purpose']),
    ('propose_download_data', 'action', t_propose_download_data,
     'เสนอดาวน์โหลดไฟล์จาก Data hub เข้าคลัง ตัดตามกรอบพื้นที่ศึกษา (ผู้ใช้ต้องกดยืนยัน) — file_url ต้องมาจาก get_hub_item.downloadable_files · ใส่ value_type ถ้ารู้ความหมายแน่ชัด (เช่น WorldPop ppp = count, night light = density)',
     dict(hub_key=S, file_url=S, name=S, purpose=S, aoi_id=I, folder_id=I, value_type=dict(type='string', enum=['count', 'density', 'class'])), ['hub_key', 'file_url', 'name', 'purpose']),
    ('propose_create_report', 'action', t_propose_create_report,
     'เสนอทำรายงานแผนที่ (เปิดตัวออกแบบรายงานพร้อมเทมเพลต/ชั้นข้อมูล/ข้อความ ผู้ใช้กดยืนยันแล้วส่งออก PDF เอง) — dataset_ids ปกติคือแผนที่ไบแวเรียตที่ทำเสร็จแล้ว',
     dict(dataset_ids=dict(type='array', items=I), template=dict(type='string', enum=list(REPORT_TEMPLATES)), title=S, subtitle=S, org=S, author=S,
          note=S, caption=S, map_no=S, extent_aoi_id=I, purpose=S), ['dataset_ids', 'title', 'purpose']),
    ('propose_create_study_area', 'action', t_propose_create_study_area, 'เสนอสร้างพื้นที่ศึกษาจากชั้นขอบเขต (เลือกค่าของฟิลด์ เช่น ชื่อจังหวัด)',
     dict(name=S, source_dataset_id=I, field=S, values=dict(type='array', items=S)), ['name', 'source_dataset_id', 'field', 'values']),
]
BY_NAME = {t[0]: t for t in TOOLS}


def specs(mode):
    out = []
    for name, lvl, _, desc, props, req in TOOLS:
        if lvl != 'read' and mode != 'propose':             # อ่านอย่างเดียว → ไม่มีเครื่องมือเสนองาน/เขียนโน้ต
            continue
        out.append(dict(name=name, description=desc, parameters=dict(type='object', properties=props, required=req)))
    return out


def run(name, args, mode):
    t = BY_NAME.get(name)
    if not t or (t[1] != 'read' and mode != 'propose'):
        return dict(error=f'ไม่มีเครื่องมือ {name} (หรือปิดสิทธิ์เสนองานอยู่)')
    try:
        return t[2](**(args or {}))
    except TypeError as e:
        return dict(error=f'อาร์กิวเมนต์ไม่ถูกต้อง: {e}')
    except ToolError as e:
        return dict(error=str(e))
    except Exception as e:                                   # ไม่ให้ทั้งรอบแชตล้มเพราะเครื่องมือเดียว
        return dict(error=f'{type(e).__name__}: {e}')
