# -*- coding: utf-8 -*-
"""สูตรงาน (recipe) — ผู้ช่วยตัวเก่งออกแบบครั้งเดียว แอปรันเองทุกขั้นโดยไม่ใช้ LLM

ทำไม: งานหลายขั้น (ดึง LST 2 ปี → แนวโน้ม → ไบแวเรียตกับประชากร → สถิติ) เดิมต้องคุยกับโมเดลทุกขั้น
แต่ละรอบส่ง prompt ~15,000 โทเคน + ประวัติ → สูตรงานเหลือ: ออกแบบ 1 รอบ + สรุปผล 1 รอบ
ขั้นตอน: {"id":"s1","title":"…","kind":"satellite|download|calc|trend|change|bivariate|resample|rasterize|hex|hexbiv|vgrid|mosaic|vmerge|stats","params":{…}}
- อ้างผลของขั้นก่อนหน้าด้วยสตริง "$s1" ตรงไหนก็ได้ใน params (แทนด้วย #id ชุดผลลัพธ์ของขั้นนั้น)
- "target_res": "auto" = ความละเอียดของชุดข้อมูลต้นทางที่หยาบที่สุด (กันความแม่นยำเทียม)
- download: {"hub_key","file_url","name","value_type","aoi_id"} (ไฟล์ต้องอยู่ในรายการนำเข้าได้ของ Data hub)
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
KINDS = JOB_KINDS | {'download', 'stats'}
RAW_KINDS = {'satellite', 'download'}                          # ข้อมูลดิบ → โฟลเดอร์ raw · ที่เหลือ → output
_lock = threading.Lock()
_CANCEL = set()
REF = re.compile(r'^\$(s[\w-]{0,20})$')


class RecipeError(Exception):
    pass


def _path(rid):
    return DIR / f'{re.sub(r"[^A-Za-z0-9_-]", "", rid)}.json'


def get(rid):
    p = _path(rid)
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None


def _save(r):
    DIR.mkdir(parents=True, exist_ok=True)
    with _lock:
        _path(r['id']).write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding='utf-8')


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
    if not isinstance(steps, list) or not 1 <= len(steps) <= 20:
        raise RecipeError('สูตรงานต้องมี 1–20 ขั้น')
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
        bad = _refs(s['params'], set()) - set(seen)
        if bad:
            raise RecipeError(f'ขั้น {sid} อ้าง {", ".join("$" + b for b in sorted(bad))} ซึ่งไม่ใช่ขั้นก่อนหน้า')
        if s['kind'] == 'download':
            for k in ('hub_key', 'file_url', 'value_type'):
                if not s['params'].get(k):
                    raise RecipeError(f'ขั้น {sid} (download) ต้องมี {k}')
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
            return outs[m.group(1)]
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
            p = _resolve(s['params'], outs)
            if s['kind'] in JOB_KINDS:
                if p.get('target_res') == 'auto':
                    p['target_res'] = _auto_res(call, s['kind'], p)
                if s['kind'] in ('bivariate', 'hexbiv'):                 # ค่าเริ่มเดียวกับข้อเสนอปกติ (พาเลท/สี/กติกา)
                    from .ai_tools import _params
                    p = _params(s['kind'], p)
                fid = r.get('raw_folder_id') if s['kind'] in RAW_KINDS else r.get('output_folder_id')
                if fid and not p.get('folder_id'):
                    p['folder_id'] = fid
                p.setdefault('purpose', r.get('purpose'))
                p['requested_by'] = dict(r.get('requested_by') or {}, recipe=rid, step=s['id'])
                res = call('POST', '/api/jobs', dict(kind=s['kind'], params=p))
                if not isinstance(res, dict) or not res.get('job'):
                    raise RecipeError((res or {}).get('error') if isinstance(res, dict) else 'สร้างงานไม่สำเร็จ')
                s['job_id'] = res['job']
            elif s['kind'] == 'download':
                res = hub_import(p['hub_key'], p['file_url'], p.get('name'), p.get('aoi_id'), p.get('value_type'), r.get('purpose'),
                                 dict(r.get('requested_by') or {}, recipe=rid, step=s['id']), p.get('folder_id') or r.get('raw_folder_id'))
                s['job_id'] = res['job_id']
            if s['job_id']:
                _save(r)
                j = _wait_job(call, s['job_id'], rid)
                if j['status'] != 'done':
                    raise RecipeError(j.get('error') or f'งาน {j["status"]}')
                did = (j.get('result') or {}).get('dataset_id')
                if not did:
                    raise RecipeError('งานเสร็จแต่ไม่มีชุดผลลัพธ์')
                s['output'] = outs[s['id']] = int(did)
                call('GET', f'/api/datasets/{did}')                  # เปิดดู = สั่งเตรียมสถิติ/พรีวิว (ใช้ตรวจผลขั้นถัดไป)
                if s['kind'] == 'download' and p.get('value_type'):
                    call('PATCH', f'/api/datasets/{did}', dict(value_type=p['value_type'], value_type_confirmed=True))
                try:
                    rv = review(did)
                    s['review'] = dict(problems=[f'{c["item"]}: {c["detail"]}' for c in rv.get('problems') or []][:6])
                except Exception as e:                            # ตรวจไม่ได้ไม่ใช่ความผิดของงาน
                    s['review'] = dict(problems=[], note=f'ตรวจผลไม่ได้: {e}'[:200])
            elif s['kind'] == 'stats':
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


def summary_text(r):
    """สรุปผลส่งกลับแชต (ให้ผู้ช่วยตัวเก่งอ่านครั้งเดียว)"""
    L = [f'สูตรงาน "{r["title"]}" {dict(done="เสร็จ", failed="หยุดเพราะมีขั้นล้มเหลว", cancelled="ยกเลิก", interrupted="ถูกขัดจังหวะ (ตัวประมวลผลถูกปิด)").get(r["status"], r["status"])}']
    for s in r['steps']:
        line = f'- {s["id"]} {s["title"]} [{s["kind"]}]: {s["status"]}' + (f' → ชุด #{s["output"]}' if s.get('output') else '') + (f' · ผิดพลาด: {s["error"]}' if s.get('error') else '')
        rv = s.get('review') or {}
        if rv.get('problems'):
            line += ' · ตรวจพบ: ' + '; '.join(rv['problems'])
        if rv.get('stats'):
            line += ' · ' + ', '.join(f'{k}={v:.3g}' for k, v in rv['stats'].items() if isinstance(v, (int, float)))
        L.append(line)
    return '\n'.join(L)
