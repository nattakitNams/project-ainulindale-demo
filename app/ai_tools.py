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
import secrets
import threading
import time

from . import db, palettes
from .config import PORT, STATIC

CLIENT = None                    # server ตั้งให้: lambda: app.test_client()
JOB_KINDS = ('bivariate', 'resample', 'rasterize', 'hex', 'hexbiv', 'vgrid', 'change', 'download')
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
            return dict(id=j['id'], title=j['title'], status=j['status'], progress=j.get('progress'), message=j.get('message'),
                        error=j.get('error'), output_dataset_id=res.get('dataset_id') if isinstance(res, dict) else None)
    raise ToolError(f'ไม่พบงาน #{job_id}')


def t_list_jobs(limit=10):
    return [dict(id=j['id'], kind=j['kind'], title=j['title'], status=j['status'], progress=j.get('progress'))
            for j in _call('GET', '/api/jobs')[:int(limit or 10)]]


_HUB = None


def t_search_data_hub(query, limit=12):
    """ค้นรายชื่อแหล่งข้อมูลภายนอกใน Data hub (ชื่อ/ผู้ให้บริการ/คำสำคัญ)"""
    global _HUB
    if _HUB is None:
        _HUB = json.loads((STATIC / 'hub' / 'index.json').read_text(encoding='utf-8'))['items']
    words = [w for w in (query or '').lower().split() if w]
    scored = []
    for it in _HUB:
        hay = ' '.join([it.get('t', ''), it.get('pr', ''), it.get('k', ''), it.get('tr', ''), ' '.join(it.get('kw') or []), ' '.join(it.get('th') or [])]).lower()
        s = sum(hay.count(w) for w in words)
        if s and all(w in hay for w in words[:3]):
            scored.append((s + (3 if it.get('cv') == 'thailand' else 0), it))
    scored.sort(key=lambda x: -x[0])
    return [dict(key=it['k'], title=it.get('t'), provider=it.get('pr'), platform=it.get('p'), type=it.get('tr'), coverage=it.get('cv'),
                 license=it.get('lc'), url=it.get('u')) for _, it in scored[:int(limit or 12)]]


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
    if p['action'] == 'run_job' and isinstance(params, dict):
        a = dict(a, params=_params(a['kind'], params))
        p['user_edited'] = True
    if p['action'] == 'set_value_type':
        _call('PATCH', f'/api/datasets/{a["dataset_id"]}', dict(value_type=a['value_type'], value_type_confirmed=True))
        return dict(ok=True, message=f'ตั้งประเภทค่า #{a["dataset_id"]} เป็น {a["value_type"]} แล้ว')
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
    ('job_status', 'read', t_job_status, 'สถานะงาน + ชุดข้อมูลผลลัพธ์เมื่อเสร็จ', dict(job_id=I), ['job_id']),
    ('list_jobs', 'read', t_list_jobs, 'งานล่าสุด', dict(limit=I), []),
    ('search_data_hub', 'read', t_search_data_hub, 'ค้นแหล่งข้อมูลภายนอกใน Data hub (GEE, Planetary Computer, พอร์ทัลไทย ฯลฯ)', dict(query=S, limit=I), ['query']),
    ('propose_set_value_type', 'action', t_propose_set_value_type, 'เสนอยืนยัน/เปลี่ยนประเภทค่าของราสเตอร์ (ผู้ใช้ต้องกดยืนยัน)',
     dict(dataset_id=I, value_type=dict(type='string', enum=['count', 'density', 'class'])), ['dataset_id', 'value_type']),
    ('propose_run_job', 'action', t_propose_run_job, 'เสนองานประมวลผล (ผู้ใช้ต้องกดยืนยัน) — params_json เป็น JSON ตามสเปกใน system prompt',
     dict(kind=dict(type='string', enum=list(JOB_KINDS)), params_json=S, title=S, purpose=S), ['kind', 'params_json', 'purpose']),
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
        if lvl == 'action' and mode != 'propose':
            continue
        out.append(dict(name=name, description=desc, parameters=dict(type='object', properties=props, required=req)))
    return out


def run(name, args, mode):
    t = BY_NAME.get(name)
    if not t or (t[1] == 'action' and mode != 'propose'):
        return dict(error=f'ไม่มีเครื่องมือ {name} (หรือปิดสิทธิ์เสนองานอยู่)')
    try:
        return t[2](**(args or {}))
    except TypeError as e:
        return dict(error=f'อาร์กิวเมนต์ไม่ถูกต้อง: {e}')
    except ToolError as e:
        return dict(error=str(e))
    except Exception as e:                                   # ไม่ให้ทั้งรอบแชตล้มเพราะเครื่องมือเดียว
        return dict(error=f'{type(e).__name__}: {e}')
