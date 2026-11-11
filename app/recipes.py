# -*- coding: utf-8 -*-
"""สูตรงาน (recipe) — ผู้ช่วยตัวเก่งออกแบบครั้งเดียว แอปรันเองทุกขั้นโดยไม่ใช้ LLM

ทำไม: งานหลายขั้น (ดึง LST 2 ปี → แนวโน้ม → ไบแวเรียตกับประชากร → สถิติ) เดิมต้องคุยกับโมเดลทุกขั้น
แต่ละรอบส่ง prompt ~15,000 โทเคน + ประวัติ → สูตรงานเหลือ: ออกแบบ 1 รอบ + สรุปผล 1 รอบ
ขั้นตอน: {"id":"s1","title":"…","kind":"satellite|download|calc|trend|change|bivariate|resample|rasterize|hex|hexbiv|vgrid|mosaic|vmerge|stats","params":{…}}
- อ้างผลของขั้นก่อนหน้าด้วยสตริง "$s1" ตรงไหนก็ได้ใน params (แทนด้วย #id ชุดผลลัพธ์ของขั้นนั้น)
- "target_res": "auto" = ความละเอียดของชุดข้อมูลต้นทางที่หยาบที่สุด (กันความแม่นยำเทียม)
- download: {"hub_key","file_url","name","value_type","aoi_id"} (ไฟล์ต้องอยู่ในรายการนำเข้าได้ของ Data hub)
  หลายไฟล์ต่อปี: {"hub_key","years":[2015,…],"match":["_t_60_","_t_65_"],"must":["1km"],"combine":"sum","name":"pop60plus_{year}",…}
  → ทุกปี: ดาวน์โหลดไฟล์ที่ชื่อตรง แล้วรวม (sum) เป็นชุดเดียวต่อปี · ผลขั้น = {ปี: #id} อ้างด้วย "$s1.2015"
- ขั้นงานใดก็ได้ใส่ "for_years":[…] หรือ "for_years":"$s1" → ทำซ้ำทุกปี แทน {year} ในทุกข้อความของ params ("$s1.{year}", "pct_{year}") · ผล = {ปี: #id}
- trend: "items":"$s3" (ผลรายปี) = ใช้ทุกปีเรียงให้เอง
- summary: {"dataset_ids":"$s3" | [#id…], "ratio_to":"$s2" (ไม่บังคับ)} = ผลรวม/ค่าเฉลี่ยของแต่ละชุด (+ % เทียบชุดคู่ปีเดียวกัน) ส่งกลับแชต
- stats: {"dataset_id":"$s4"} = สถิติความสัมพันธ์ของแผนที่ไบแวเรียต
ผู้ใช้ยืนยันครั้งเดียวทั้งสูตร · ขั้นพลาด = หยุด (ขั้นถัดไปที่พึ่งพาทำต่อไม่ได้) · ผลรวมส่งกลับแชตครั้งเดียวให้ผู้ช่วยสรุป"""
import copy
import json
import re
import secrets
import threading
import time

from . import db
from .config import WORKSPACE

DIR = WORKSPACE / 'recipes'
JOB_KINDS = {'satellite', 'calc', 'trend', 'change', 'bivariate', 'resample', 'rasterize', 'hex', 'hexbiv', 'vgrid', 'mosaic', 'vmerge'}
KINDS = JOB_KINDS | {'download', 'stats', 'summary'}
MAX_STEPS = 30
RAW_KINDS = {'satellite', 'download'}                          # ข้อมูลดิบ → โฟลเดอร์ raw · ที่เหลือ → output
_lock = threading.Lock()
_CANCEL = set()
REF = re.compile(r'^\$(s[\w-]{0,20})(?:\.(\w+))?$')                # $s1 · $s1.2015 (ผลรายปี)


class RecipeError(Exception):
    pass


def _path(rid):
    return DIR / f'{re.sub(r"[^A-Za-z0-9_-]", "", rid)}.json'


def get(rid):
    p = _path(rid)
    for i in range(20):                                       # อ่านชนจังหวะเขียน (Windows แทนที่ไฟล์ไม่ทันที) → ลองใหม่
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            time.sleep(0.05)
    raise RecipeError(f'อ่านสูตรงาน {rid} ไม่ได้')


def _save(r):
    """เขียนแบบอะตอม (ไฟล์ชั่วคราว → แทนที่) — หน้าเว็บอ่านสถานะทุก 2 วินาทีระหว่างที่สูตรกำลังเขียน
    (เดิม write_text ตรง ๆ → อ่านเจอไฟล์ว่างครึ่งทาง → 500 · 1.0.44 บันทึกถี่ขึ้น (รายปี) เลยเจอบ่อย)"""
    import os
    DIR.mkdir(parents=True, exist_ok=True)
    p = _path(r['id'])
    with _lock:
        tmp = p.with_suffix('.tmp')
        tmp.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding='utf-8')
        for i in range(20):
            try:
                os.replace(tmp, p)
                break
            except PermissionError:                           # ผู้อ่านเปิดไฟล์ค้างอยู่ (Windows)
                time.sleep(0.05)


def all_(limit=20):
    if not DIR.exists():
        return []
    out = []
    for p in DIR.glob('*.json'):
        try:
            out.append(json.loads(p.read_text(encoding='utf-8')))
        except ValueError:
            pass
    return sorted(out, key=lambda r: r.get('created_at') or '', reverse=True)[:limit]


def _refs(x, out):
    if isinstance(x, str):
        m = REF.match(x)
        if m:
            out.add(m.group(1))
    elif isinstance(x, dict):
        for v in x.values():
            _refs(v, out)
    elif isinstance(x, list):
        for v in x:
            _refs(v, out)
    return out


def validate(steps):
    """ตรวจโครงสร้าง (ไม่รัน): id ไม่ซ้ำ · ชนิดที่รองรับ · อ้างเฉพาะขั้นก่อนหน้า · download ต้องมี value_type"""
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        raise RecipeError(f'สูตรงานต้องมี 1–{MAX_STEPS} ขั้น (หลายปีใช้ for_years / download แบบ years+match แทนการแยกขั้นทีละปี)')
    seen = []
    for i, s in enumerate(steps):
        if not isinstance(s, dict):
            raise RecipeError(f'ขั้นที่ {i + 1} ต้องเป็น object')
        sid = str(s.get('id') or f's{i + 1}')
        if not re.match(r'^s[\w-]{0,20}$', sid) or sid in seen:
            raise RecipeError(f'ขั้นที่ {i + 1}: id ต้องขึ้นต้นด้วย s และไม่ซ้ำ (เช่น s1, s2)')
        s['id'] = sid
        if s.get('kind') not in KINDS:
            raise RecipeError(f'ขั้น {sid}: kind ต้องเป็นหนึ่งใน {", ".join(sorted(KINDS))}')
        if not isinstance(s.get('params'), dict):
            raise RecipeError(f'ขั้น {sid}: ต้องมี params')
        bad = (_refs(s['params'], set()) | _refs(s.get('for_years'), set())) - set(seen)
        if bad:
            raise RecipeError(f'ขั้น {sid} อ้าง {", ".join("$" + b for b in sorted(bad))} ซึ่งไม่ใช่ขั้นก่อนหน้า')
        if s['kind'] == 'download':
            for k in ('hub_key', 'value_type'):
                if not s['params'].get(k):
                    raise RecipeError(f'ขั้น {sid} (download) ต้องมี {k}')
            if not s['params'].get('file_url') and not s['params'].get('match'):
                raise RecipeError(f'ขั้น {sid} (download) ต้องมี file_url (ไฟล์เดียว) หรือ match (+ years) สำหรับหลายไฟล์')
        if s.get('for_years') is not None:
            fy = s['for_years']
            if s['kind'] not in JOB_KINDS:
                raise RecipeError(f'ขั้น {sid}: for_years ใช้กับขั้นงาน ({", ".join(sorted(JOB_KINDS))}) เท่านั้น')
            if not (isinstance(fy, str) and REF.match(fy)) and not (isinstance(fy, list) and fy and all(str(y).isdigit() for y in fy)):
                raise RecipeError(f'ขั้น {sid}: for_years ต้องเป็นรายการปี หรือ "$sN" (ผลรายปีของขั้นก่อน)')
        if s['kind'] == 'summary' and not s['params'].get('dataset_ids'):
            raise RecipeError(f'ขั้น {sid} (summary) ต้องมี dataset_ids')
        if s['kind'] == 'stats' and not s['params'].get('dataset_id'):
            raise RecipeError(f'ขั้น {sid} (stats) ต้องมี dataset_id ของแผนที่ไบแวเรียต')
        s['title'] = str(s.get('title') or s['kind'])[:120]
        seen.append(sid)
    return steps


def _resolve(x, outs):
    if isinstance(x, str):
        m = REF.match(x)
        if m:
            if m.group(1) not in outs:
                raise RecipeError(f'ขั้น {m.group(1)} ยังไม่มีผลลัพธ์')
            v = outs[m.group(1)]
            if m.group(2) is not None:
                if not isinstance(v, dict) or str(m.group(2)) not in {str(k) for k in v}:
                    raise RecipeError(f'{x}: ขั้น {m.group(1)} ไม่มีผลของ {m.group(2)}' + (f' (มี {", ".join(map(str, v))})' if isinstance(v, dict) else ''))
                return next(val for k, val in v.items() if str(k) == str(m.group(2)))
            return v
        return x
    if isinstance(x, dict):
        return {k: _resolve(v, outs) for k, v in x.items()}
    if isinstance(x, list):
        return [_resolve(v, outs) for v in x]
    return x


def _input_ids(kind, p):
    ids = []
    for k in ('dataset_id', 'a_id', 'b_id', 'ref_dataset_id'):
        if p.get(k):
            ids.append(p[k])
    ids += list(p.get('dataset_ids') or [])
    ids += [(p.get(a) or {}).get('dataset_id') for a in ('x', 'y')]
    ids += [v.get('dataset_id') for v in (p.get('vars') or {}).values() if isinstance(v, dict)]
    ids += [it.get('dataset_id') for it in p.get('items') or [] if isinstance(it, dict)]
    return [int(i) for i in ids if i]


def _auto_res(call, kind, p):
    """target_res "auto" → ความละเอียดต้นทางที่หยาบที่สุดในชุดที่ใช้ (จำนวนพิกเซลน้อยสุดในตัวเลือก is_source)"""
    ids = _input_ids(kind, p)
    if not ids:
        raise RecipeError('target_res "auto" ต้องมีชุดข้อมูลต้นทาง')
    opts = call('GET', f'/api/res-options?ids={",".join(map(str, ids))}').get('options') or []
    src = [o for o in opts if o.get('is_source')] or opts
    if not src:
        raise RecipeError('หาความละเอียดอัตโนมัติไม่ได้')
    return min(src, key=lambda o: o.get('px') or 0)['value']


def create(title, purpose, steps, chat_id=None, raw_folder_id=None, output_folder_id=None, requested_by=None):
    steps = validate(copy.deepcopy(steps))
    r = dict(id='r' + secrets.token_hex(5), title=str(title)[:160], purpose=str(purpose or '')[:500], chat_id=chat_id, status='queued',
             created_at=db.now(), raw_folder_id=raw_folder_id, output_folder_id=output_folder_id, requested_by=requested_by,
             steps=[dict(s, status='todo', job_id=None, output=None, error=None, review=None) for s in steps])
    _save(r)
    return r


def start(r, call, hub_import, review):
    threading.Thread(target=_run, args=(r['id'], call, hub_import, review), daemon=True, name=f'recipe-{r["id"]}').start()
    return r['id']


def cancel(rid):
    _CANCEL.add(rid)


def _wait_job(call, jid, rid, timeout=6 * 3600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = db.get('jobs', int(jid))
        if j and j['status'] in ('done', 'failed', 'cancelled'):
            return j
        if rid in _CANCEL:
            call('POST', f'/api/jobs/{jid}/cancel', {})
        time.sleep(2)
    raise RecipeError('งานใช้เวลานานเกินกำหนด')


def _sub_year(x, y):
    """แทน {year} ในทุกข้อความของ params"""
    if isinstance(x, str):
        return x.replace('{year}', str(y))
    if isinstance(x, dict):
        return {k: _sub_year(v, y) for k, v in x.items()}
    if isinstance(x, list):
        return [_sub_year(v, y) for v in x]
    return x


def _finish(call, review, s, did, value_type=None):
    """ชุดผลลัพธ์ใหม่: สั่งเตรียมสถิติ · ตั้งประเภทค่า (ดาวน์โหลด) · ตรวจผลอัตโนมัติ (สะสมปัญหาในขั้น)"""
    call('GET', f'/api/datasets/{did}')                        # เปิดดู = สั่งเตรียมสถิติ/พรีวิว (ใช้ตรวจผลขั้นถัดไป)
    if value_type:
        call('PATCH', f'/api/datasets/{did}', dict(value_type=value_type, value_type_confirmed=True))
    rv = s['review'] = s.get('review') or dict(problems=[])      # ขั้นถูกสร้างพร้อม review=None
    try:
        r = review(did)
        rv['problems'] = (rv.get('problems') or []) + [f'#{did} {c["item"]}: {c["detail"]}' for c in r.get('problems') or []][:6]
    except Exception as e:                                    # ตรวจไม่ได้ไม่ใช่ความผิดของงาน
        rv['note'] = f'ตรวจผลไม่ได้: {e}'[:200]


def _wait_did(call, s, jid, rid):
    s.setdefault('job_ids', []).append(jid)
    s['job_id'] = jid
    j = _wait_job(call, jid, rid)
    if j['status'] != 'done':
        raise RecipeError(j.get('error') or f'งาน {j["status"]}')
    did = (j.get('result') or {}).get('dataset_id')
    if not did:
        raise RecipeError('งานเสร็จแต่ไม่มีชุดผลลัพธ์')
    return int(did)


def _job(r, s, p, call, review, rid, kind=None):
    """ส่งงานหนึ่งงาน (ตรวจด่านเดียวกับผู้ใช้กดเอง) → รอเสร็จ → #id ผลลัพธ์"""
    kind = kind or s['kind']
    if isinstance(p.get('items'), dict):                      # trend "items":"$s3" → ทุกปีของผลรายปี
        p['items'] = [dict(dataset_id=v, year=int(k)) for k, v in sorted(p['items'].items(), key=lambda kv: int(kv[0]))]
    if p.get('target_res') == 'auto':
        p['target_res'] = _auto_res(call, kind, p)
    if kind in ('bivariate', 'hexbiv'):                       # ค่าเริ่มเดียวกับข้อเสนอปกติ (พาเลท/สี/กติกา)
        from .ai_tools import _params
        p = _params(kind, p)
    fid = r.get('raw_folder_id') if kind in RAW_KINDS else r.get('output_folder_id')
    if fid and not p.get('folder_id'):
        p['folder_id'] = fid
    p.setdefault('purpose', r.get('purpose'))
    p['requested_by'] = dict(r.get('requested_by') or {}, recipe=rid, step=s['id'])
    res = call('POST', '/api/jobs', dict(kind=kind, params=p))
    if not isinstance(res, dict) or not res.get('job'):
        raise RecipeError((res or {}).get('error') if isinstance(res, dict) else 'สร้างงานไม่สำเร็จ')
    _save(r)
    did = _wait_did(call, s, res['job'], rid)
    _finish(call, review, s, did)
    return did


def _submit_dl(r, s, p, hub_import, rid, url, name):
    res = hub_import(p['hub_key'], url, name, p.get('aoi_id'), p.get('value_type'), r.get('purpose'),
                     dict(r.get('requested_by') or {}, recipe=rid, step=s['id']), p.get('folder_id') or r.get('raw_folder_id'))
    return res['job_id']


def _download(r, s, p, call, hub_import, review, rid, url, name):
    jid = _submit_dl(r, s, p, hub_import, rid, url, name)
    _save(r)
    did = _wait_did(call, s, jid, rid)
    _finish(call, review, s, did, p.get('value_type'))
    return did


def _wait_years(r, s, p, call, review, rid, jobs, res):
    """download หลายไฟล์: รอทีละปี → ตั้งประเภทค่าไฟล์ย่อย → รวมเป็นชุดเดียวต่อปี (res[ปี] = #id)"""
    for y, (nm, jids) in jobs.items():
        ids = []
        for jid in jids:
            did = _wait_did(call, s, jid, rid)
            call('GET', f'/api/datasets/{did}')                   # ไฟล์ย่อย: เตรียมสถิติ + ประเภทค่า (ไม่ตรวจทีละไฟล์ — ตรวจผลรวมของปี)
            if p.get('value_type'):
                call('PATCH', f'/api/datasets/{did}', dict(value_type=p['value_type'], value_type_confirmed=True))
            ids.append(did)
        if len(ids) == 1:
            _finish(call, review, s, ids[0])
        res[int(y)] = _sum_ids(r, s, p, call, review, rid, ids, nm)
        s['output'] = res
        _save(r)


def _sum_ids(r, s, p, call, review, rid, ids, name):
    """รวมหลายชุด (กริดเดียวกันจากผลิตภัณฑ์เดียวกัน) ด้วยงาน calc — ทีละ ≤ 12 ตัวแปร"""
    while len(ids) > 1:
        part, rest = ids[:12], ids[12:]
        vars_ = {f'F{i + 1}': dict(dataset_id=d) for i, d in enumerate(part)}
        q = dict(expr=' + '.join(vars_), vars=vars_, target_res='auto', value_type=p.get('value_type') or 'count',
                 name=name if not rest else f'{name}_part', aoi_id=p.get('aoi_id'))
        ids = [_job(r, s, q, call, review, rid, kind='calc')] + rest
    return ids[0]


def _summary(call, p):
    """ผลรวม/ค่าเฉลี่ยของแต่ละชุด (+ % เทียบชุดคู่) — จากสถิติที่ระบบนับไว้ (ทุกพิกเซล)"""
    def norm(x):
        if isinstance(x, dict):
            return [(str(k), v) for k, v in sorted(x.items(), key=lambda kv: str(kv[0]))]
        if isinstance(x, list):
            return [(str(v), v) for v in x]
        return [(str(x), x)]

    def stat(did):
        for _ in range(150):                                      # สถิติของชุดที่ดาวน์โหลดเอง (prepare) อาจยังไม่เสร็จ
            d = call('GET', f'/api/datasets/{int(did)}')
            st = (d or {}).get('stats') or {}
            if st.get('sum') is not None or st.get('valid') is not None:
                return d, st
            time.sleep(2)
        raise RecipeError(f'ชุด #{did} ยังไม่มีสถิติ (งานเตรียมข้อมูลยังไม่เสร็จ)')
    ref = dict(norm(p['ratio_to'])) if p.get('ratio_to') else {}
    rows = []
    for k, did in norm(p['dataset_ids']):
        d, st = stat(did)
        row = dict(key=k, dataset_id=int(did), name=d.get('name'), sum=st.get('sum'), mean=st.get('mean'), min=st.get('min'), max=st.get('max'),
                   valid_pixels=st.get('valid'))
        if k in ref:
            _d2, st2 = stat(ref[k])
            row['ratio_to'] = int(ref[k])
            row['pct_of_ref'] = (100 * st['sum'] / st2['sum']) if st.get('sum') is not None and st2.get('sum') else None
        rows.append(row)
    return rows


def _run(rid, call, hub_import, review):
    r = get(rid)
    r['status'], r['started_at'] = 'running', db.now()
    _save(r)
    outs = {}
    for s in r['steps']:
        if rid in _CANCEL:
            s['status'] = 'skipped'
            continue
        s['status'], s['started_at'] = 'running', db.now()
        _save(r)
        try:
            fy = s.get('for_years')
            if fy is not None:                                      # ทำซ้ำทุกปี
                ys = _resolve(fy, outs)
                ys = list(ys.keys()) if isinstance(ys, dict) else list(ys)
                res = {}
                for y in sorted(ys, key=lambda v: int(v)):
                    if rid in _CANCEL:
                        raise RecipeError('ยกเลิก')
                    res[int(y)] = _job(r, s, _resolve(_sub_year(s['params'], y), outs), call, review, rid)
                    s['output'] = res
                    _save(r)
                outs[s['id']] = res
            elif s['kind'] in JOB_KINDS:
                s['output'] = outs[s['id']] = _job(r, s, _resolve(s['params'], outs), call, review, rid)
            elif s['kind'] == 'download':
                p = _resolve(s['params'], outs)
                if p.get('file_url'):
                    s['output'] = outs[s['id']] = _download(r, s, p, call, hub_import, review, rid, p['file_url'], p.get('name'))
                else:
                    from .ai_tools import hub_plan
                    plan = hub_plan(p['hub_key'], p.get('years'), p.get('match'), p.get('must'))
                    for y, files in plan.items():
                        if not files:
                            raise RecipeError(f'ปี {y}: ไม่พบไฟล์ที่ชื่อมี {p.get("match")}')
                        if len(files) > 1 and p.get('combine', 'sum') != 'sum':
                            raise RecipeError(f'ปี {y} มี {len(files)} ไฟล์ — ใส่ "combine":"sum" หรือ match ให้เหลือไฟล์เดียวต่อปี')
                    # ส่งงานดาวน์โหลดทุกไฟล์ทุกปีก่อน (คิวรันพร้อมกันได้ PAR_DOWNLOAD งาน) แล้วค่อยรอ/รวมทีละปี
                    jobs = {}
                    for y, files in plan.items():
                        nm = (p.get('name') or 'hub_{year}').replace('{year}', str(y))
                        jobs[y] = (nm, [_submit_dl(r, s, p, hub_import, rid, f['url'], f'{nm}_{i + 1}' if len(files) > 1 else nm) for i, f in enumerate(files)])
                    _save(r)
                    res = {}
                    try:
                        _wait_years(r, s, p, call, review, rid, jobs, res)
                    except Exception:                               # พัง/ยกเลิก → ยกเลิกงานดาวน์โหลดที่ยังรอคิวด้วย (ไม่ค้างโหลดต่อเงียบ ๆ)
                        for _nm, jids in jobs.values():
                            for jid in jids:
                                j = db.get('jobs', int(jid))
                                if j and j['status'] in ('queued', 'running'):
                                    call('POST', f'/api/jobs/{jid}/cancel', {})
                        raise
                    outs[s['id']] = res
            elif s['kind'] == 'summary':
                rows = _summary(call, _resolve(s['params'], outs))
                s['output'] = outs[s['id']] = {row['key']: row['dataset_id'] for row in rows}
                s['review'] = dict(table=rows, problems=[])
            elif s['kind'] == 'stats':
                p = _resolve(s['params'], outs)
                st = call('POST', f'/api/datasets/{int(p["dataset_id"])}/bivstats', dict(force=False))
                if not isinstance(st, dict) or st.get('error'):
                    raise RecipeError((st or {}).get('error') or 'คิดสถิติไม่สำเร็จ')
                c = st['correlation']
                s['output'] = outs[s['id']] = int(p['dataset_id'])
                s['review'] = dict(stats=dict(spearman_rho=c.get('spearman_rho'), pearson_r=c.get('pearson_r'), p_adjusted=c.get('p_adjusted'),
                                              cramers_v=st['crosstab'].get('cramers_v'), epsilon2=(st['by_x_class'].get('kruskal') or {}).get('epsilon2')),
                                   interpretation=st.get('interpretation'), problems=[])
            s['status'], s['finished_at'] = 'done', db.now()
        except Exception as e:
            s['status'], s['error'] = 'failed', str(e)[:500]
            _save(r)
            break
        _save(r)
    for s in r['steps']:
        if s['status'] in ('todo', 'running'):
            s['status'] = 'skipped'
    r['status'] = 'cancelled' if rid in _CANCEL else 'failed' if any(s['status'] == 'failed' for s in r['steps']) else 'done'
    r['finished_at'] = db.now()
    _CANCEL.discard(rid)
    _save(r)


def recover():
    """ตัวประมวลผลถูกปิดระหว่างรันสูตร → เธรดหายไปด้วย · ตั้งสถานะให้ชัด (ไม่ค้าง "กำลังรัน" ตลอดไป) — เรียกตอนเปิดเซิร์ฟเวอร์"""
    n = 0
    for r in all_(limit=200):
        if r.get('status') in ('queued', 'running'):
            for s in r['steps']:
                if s['status'] == 'running':
                    s['status'], s['error'] = 'failed', 'ตัวประมวลผลถูกปิดระหว่างรันขั้นนี้ — สั่งสูตรใหม่ (ขั้นที่เสร็จแล้วมีชุดผลลัพธ์อยู่แล้ว)'
                elif s['status'] == 'todo':
                    s['status'] = 'skipped'
            r['status'], r['finished_at'] = 'interrupted', db.now()
            _save(r)
            n += 1
    return n


def _num(v):
    return '–' if v is None else f'{v:,.0f}' if abs(v) >= 100 else f'{v:,.4g}'


def summary_text(r):
    """สรุปผลส่งกลับแชต (ให้ผู้ช่วยตัวเก่งอ่านครั้งเดียว)"""
    L = [f'สูตรงาน "{r["title"]}" {dict(done="เสร็จ", failed="หยุดเพราะมีขั้นล้มเหลว", cancelled="ยกเลิก", interrupted="ถูกขัดจังหวะ (ตัวประมวลผลถูกปิด)").get(r["status"], r["status"])}']
    for s in r['steps']:
        out = s.get('output')
        outs = (' → ' + ', '.join(f'{k}: #{v}' for k, v in out.items())) if isinstance(out, dict) else (f' → ชุด #{out}' if out else '')
        line = f'- {s["id"]} {s["title"]} [{s["kind"]}]: {s["status"]}' + outs + (f' · ผิดพลาด: {s["error"]}' if s.get('error') else '')
        rv = s.get('review') or {}
        if rv.get('problems'):
            line += ' · ตรวจพบ: ' + '; '.join(rv['problems'])
        for row in rv.get('table') or []:
            line += (f'\n    {row["key"]}: #{row["dataset_id"]} ผลรวม {_num(row.get("sum"))} · เฉลี่ย {_num(row.get("mean"))}'
                     + (f' · = {row["pct_of_ref"]:.2f}% ของ #{row["ratio_to"]}' if row.get('pct_of_ref') is not None else ''))
        if rv.get('stats'):
            line += ' · ' + ', '.join(f'{k}={v:.3g}' for k, v in rv['stats'].items() if isinstance(v, (int, float)))
        L.append(line)
    return '\n'.join(L)
