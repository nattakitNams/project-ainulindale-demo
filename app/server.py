# -*- coding: utf-8 -*-
"""เซิร์ฟเวอร์ Flask (รันในเครื่อง) — python -m app.server หรือ run.bat"""
import json
import os
import re
import subprocess
import sys
import warnings
from fractions import Fraction
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file, send_from_directory
from werkzeug.exceptions import HTTPException

from . import aoi as aoimod
from . import ai, basedata, catalog, db, dsinfo, engine, export, folders, jobs, links, ops, ops3, palettes, symbology, tiles, trash, vault
from . import gridmath as gm
from .config import APP_NAME, APP_VERSION, DIRS, PORT, ROOT, STATIC, WORKSPACE, ensure_workspace

warnings.filterwarnings('ignore')
app = Flask(__name__, static_folder=None)
app.json.ensure_ascii = False

# ---------------- v1: หน้าเว็บภายนอก ↔ ตัวประมวลผลในเครื่อง ----------------
# หน้าเว็บ (โฟลเดอร์ web/) วางบนโฮสต์ไหนก็ได้ แล้วเรียก API ที่ http://127.0.0.1:<PORT> ของเครื่องผู้ใช้
# ด่านป้องกัน: (1) Host ต้องเป็น localhost — กัน DNS rebinding
#              (2) Origin ต้องเป็นหน้าของตัวเอง หรืออยู่ใน engine.json → allowed_origins
#              (3) คำขอที่เปลี่ยนข้อมูล (ไม่ใช่ GET) จากเว็บภายนอกต้องมีโทเคนจับคู่ (X-Ainu-Token)
import hmac
import secrets as _secrets
import threading
import webbrowser

ENGINE_CFG_PATH = ROOT / 'engine.json'


def engine_cfg():
    try:
        return json.loads(ENGINE_CFG_PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def engine_token():
    p = ROOT / 'engine_token.txt'                          # ที่เดียวกับตัวช่วยติดตั้ง (คงเดิมแม้ย้าย workspace)
    if not p.exists():
        p.write_text(_secrets.token_urlsafe(24), encoding='utf-8')
    return p.read_text(encoding='utf-8').strip()


def _self_origin(o):
    return o in (f'http://127.0.0.1:{PORT}', f'http://localhost:{PORT}')


def _allowed_origin(o):
    return _self_origin(o) or o in (engine_cfg().get('allowed_origins') or [])


def _token_ok():
    return hmac.compare_digest(request.headers.get('X-Ainu-Token', ''), engine_token())


@app.before_request
def _guard():
    if request.host not in (f'127.0.0.1:{PORT}', f'localhost:{PORT}'):
        return jsonify(error='host not allowed'), 403
    o = request.headers.get('Origin')
    if o and not _allowed_origin(o):
        return jsonify(error=f'หน้าเว็บ {o} ไม่ได้รับอนุญาต — เพิ่มใน engine.json → allowed_origins'), 403
    if request.method == 'OPTIONS':                          # preflight ของ CORS / Private Network Access
        return Response(status=204)
    if request.method not in ('GET', 'HEAD') and request.path.startswith('/api/') and not _self_origin(o or '') and not _token_ok():
        return jsonify(error='ยังไม่ได้จับคู่กับตัวประมวลผลในเครื่อง (โทเคนไม่ถูกต้อง)', pair=True), 401


@app.after_request
def _cors(r):
    o = request.headers.get('Origin')
    if o and _allowed_origin(o):
        r.headers['Access-Control-Allow-Origin'] = o
        r.headers.add('Vary', 'Origin')
        r.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-Ainu-Token'
        r.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
        r.headers['Access-Control-Expose-Headers'] = 'X-Truncated, X-Count, X-Hidden, Content-Disposition'
        r.headers['Access-Control-Max-Age'] = '600'
        if request.headers.get('Access-Control-Request-Private-Network'):
            r.headers['Access-Control-Allow-Private-Network'] = 'true'    # Chrome/Edge: เว็บสาธารณะ → localhost
    return r


@app.route('/api/engine/hello')
def engine_hello():
    """หน้าเว็บใช้ตรวจว่าเจอตัวประมวลผลไหม และจับคู่แล้วหรือยัง (ไม่เปิดเผยข้อมูลอื่น)"""
    return jsonify(app=APP_NAME, version=APP_VERSION, engine=True, mode='engine', paired=_token_ok(),
                   machine=os.environ.get('COMPUTERNAME', ''), port=PORT)


class ApiError(Exception):
    pass


def ds_or_404(did):
    d = db.get('datasets', did)
    if d is None:
        raise ApiError(f'ไม่พบชุดข้อมูล #{did}')
    return d


def public(d):
    d = dict(d)
    d.pop('_cmap', None)
    return d


def prepare_if_needed(did):
    d = db.get('datasets', did)
    if d['kind'] != 'raster' or d.get('role') == 'map':
        return None                       # แผนที่ไบแวเรียตมีตารางสี + overview + สถิติใน lineage แล้ว
    F = ops.preview_factor(d['meta'])
    if d.get('stats') and d.get('preview_key') == ops.preview_key(d, F):
        return None
    pend = db.query("SELECT id FROM jobs WHERE kind='prepare' AND status IN ('queued','running') AND params LIKE ?",
                    (f'%"dataset_id": {did}}}%',))
    if pend:
        return pend[0]['id']
    return jobs.submit('prepare', dict(dataset_id=did), f'เตรียมข้อมูล: {d["name"]}')


# ---------------- หน้าเว็บ ----------------
@app.route('/')
def index():
    from flask import redirect
    return redirect('/ui/')


@app.route('/ui/')
def ui_index():
    """หน้าเว็บสำรองที่ตัวประมวลผลเสิร์ฟเอง (same-origin ไม่ต้องจับคู่) — ใช้ได้แม้ไม่มีอินเทอร์เน็ต"""
    html = (STATIC / 'index.html').read_text(encoding='utf-8').replace('<head>', '<head>\n<meta name="ainu-engine" content="same-origin">', 1)
    return Response(html, mimetype='text/html', headers={'Cache-Control': 'no-cache'})


@app.route('/ui/<path:p>')
def ui_file(p):
    r = send_from_directory(STATIC, p)
    r.headers['Cache-Control'] = 'no-cache'
    return r


@app.route('/static/<path:p>')
def static_file(p):
    r = send_from_directory(STATIC, p)
    r.headers['Cache-Control'] = 'no-cache'
    return r


@app.route('/api/state')
def state():
    return jsonify(app=APP_NAME, version=APP_VERSION, workspace=str(WORKSPACE), dirs={k: str(v) for k, v in DIRS.items()},
                   palettes=palettes.PALETTES, default_palette=palettes.DEFAULT_PALETTE,
                   raster_ext=sorted(dsinfo.RASTER_EXT), vector_ext=sorted(dsinfo.VECTOR_EXT),
                   ramps=symbology.RAMPS, categorical=sorted(symbology.CATEGORICAL))


# ---------------- ชุดข้อมูล ----------------
@app.route('/api/datasets')
def list_ds():
    return jsonify([public(d) for d in catalog.list_datasets()])


@app.route('/api/datasets', methods=['POST'])
def add_ds():
    b = request.get_json(force=True)
    paths = b.get('paths') or [b.get('path')]
    added, warns, errors = [], [], []
    for p in [p for p in paths if p]:
        try:
            ids, w = catalog.add_path(p, copy=bool(b.get('copy')), name=b.get('name') if len(paths) == 1 else None)
            added += ids
            warns += [f'{Path(p).name}: {x}' for x in w]
        except catalog.CatalogError as e:
            errors.append(f'{p}: {e}')
    folders.assign(added, b.get('folder_id'))
    for i in added:
        prepare_if_needed(i)
    return jsonify(added=added, warnings=warns, errors=errors)


# ---------------- โฟลเดอร์ในคลังข้อมูล ----------------
@app.errorhandler(folders.FolderError)
def folder_err(e):
    return jsonify(error=str(e)), 400


@app.errorhandler(ai.AiError)
def ai_err(e):
    return jsonify(error=str(e)), 400


def _ai_client():                                       # เครื่องมือของผู้ช่วย AI เรียก API ชุดเดียวกับหน้าเว็บ (ผ่านด่าน/validate เดิม)
    return app.test_client()


from . import ai_tools as _ai_tools  # noqa: E402
_ai_tools.CLIENT = _ai_client


# ---------- ผู้ช่วย AI (key อยู่ใน vault — ไม่ส่งกลับหน้าเว็บ) ----------
@app.route('/api/ai')
def ai_status():
    return jsonify(ai.status())


@app.route('/api/ai', methods=['PATCH'])
def ai_update():
    b = request.get_json(force=True)
    if 'enabled' in b:
        ai.save(enabled=bool(b['enabled']))
    if b.get('mode') in ('read', 'propose'):              # read = อ่านอย่างเดียว · propose = เสนองาน (ต้องยืนยันทุกครั้ง)
        ai.save(mode=b['mode'])
    if b.get('model'):
        if not ai.status()['connected']:
            raise ai.AiError('ยังไม่ได้เชื่อมต่อ')
        ai.save(model=str(b['model'])[:200])
    return jsonify(ai.status())


@app.route('/api/ai/login', methods=['POST'])
def ai_login():
    b = request.get_json(force=True)
    ids = ai.login(b.get('provider'), b.get('api_key'), b.get('base_url'))
    return jsonify(dict(ai.status(), models=ids))


@app.route('/api/ai/logout', methods=['POST'])
def ai_logout():
    ai.logout()
    return jsonify(ai.status())


@app.route('/api/ai/models', methods=['POST'])       # POST: GET ที่ไม่มี Origin ผ่านด่านได้ — ไม่ให้ใครกระตุ้นให้ใช้ key
def ai_models():
    return jsonify(models=ai.models(), model=ai.cfg().get('model'))


@app.route('/api/ai/chat', methods=['POST'])
def ai_chat():
    b = request.get_json(force=True)
    r = ai.chat(b.get('messages'), b.get('page'), b.get('chat_id'))
    from . import ai_plan
    r['plan'] = ai_plan.get(b.get('chat_id'))
    _ai_log(b, r)
    return jsonify(r)


def _ai_log(b, r):
    """บันทึกบทสนทนาลง workspace/ai_logs/<chat_id>.jsonl (ในเครื่องเท่านั้น — ไม่มี API key) ใช้ตรวจย้อนหลังว่าผู้ช่วยตอบอะไร/เรียกเครื่องมืออะไร"""
    import re as _re
    cid = _re.sub(r'[^A-Za-z0-9_-]', '', str(b.get('chat_id') or ''))[:64]
    if not cid:
        return
    try:
        msgs = b.get('messages') or []
        last = next((m for m in reversed(msgs) if m.get('role') in ('user', 'event')), {})
        d = WORKSPACE / 'ai_logs'
        d.mkdir(parents=True, exist_ok=True)
        with open(d / f'{cid}.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(dict(t=db.now(), model=ai.cfg().get('model'), user=str(last.get('content') or '')[:4000], reply=str(r.get('reply') or '')[:20000],
                                    tools=[u.get('tool') for u in r.get('used') or []], proposals=[p.get('action') for p in r.get('proposals') or []],
                                    docs=[x.get('file') for x in r.get('docs') or []], usage=r.get('usage')), ensure_ascii=False) + '\n')
    except Exception as e:                                   # บันทึกไม่ได้ ไม่ให้แชตล้ม
        print('[ai log]', e)


@app.route('/api/recipes')
def recipe_list():
    from . import recipes
    return jsonify(recipes=recipes.all_())


@app.route('/api/recipes/<rid>')
def recipe_get(rid):
    from . import recipes
    r = recipes.get(rid)
    if not r:
        raise ApiError('ไม่พบสูตรงาน')
    return jsonify(dict(r, summary=recipes.summary_text(r)))


@app.route('/api/recipes/<rid>/cancel', methods=['POST'])
def recipe_cancel(rid):
    from . import recipes
    recipes.cancel(rid)
    return jsonify(ok=True)


@app.route('/api/ai/docs')
def ai_docs_list():
    from . import ai_docs
    return jsonify(docs=ai_docs.all_())


@app.route('/api/ai/docs/<name>')
def ai_docs_get(name):
    from . import ai_docs
    try:
        p = ai_docs.path(name)
    except FileNotFoundError:
        raise ApiError('ไม่พบเอกสาร')
    md = p.read_text(encoding='utf-8')
    if request.args.get('raw'):
        return Response(md, mimetype='text/markdown; charset=utf-8', headers={'Content-Disposition': f'attachment; filename*=UTF-8\'\'{_q(name)}'})
    return Response(ai_docs.to_html(md, p.stem), mimetype='text/html; charset=utf-8')


def _q(s):
    from urllib.parse import quote
    return quote(s)


@app.route('/api/datasets/<int:did>/bivstats', methods=['POST'])
def ds_bivstats(did):
    from . import bivstats
    b = request.get_json(silent=True) or {}
    try:
        return jsonify(bivstats.compute(did, force=bool(b.get('force'))))
    except engine.EngineError as e:
        raise ApiError(str(e))


@app.route('/api/datasets/<int:did>/bivstats/<name>')
def ds_bivstats_file(did, name):
    from . import bivstats
    try:
        return send_file(bivstats.chart_path(did, name))
    except engine.EngineError as e:
        raise ApiError(str(e))


@app.route('/api/ai/plan')
def ai_plan_get():
    from . import ai_plan
    return jsonify(plan=ai_plan.get(request.args.get('chat')))


@app.route('/api/ai/confirm', methods=['POST'])         # ผู้ใช้กดยืนยันการ์ดข้อเสนอ → รัน (ข้อเสนอใช้ได้ครั้งเดียว)
def ai_confirm():
    from . import ai_tools
    b = request.get_json(force=True)
    try:
        return jsonify(ai_tools.execute(str(b.get('id')), ai.cfg().get('model'), b.get('params')))
    except ai_tools.ToolError as e:
        raise ApiError(str(e))


@app.route('/api/hub/browse')
def hub_browse():
    """ไฟล์ย่อยในโฟลเดอร์ต้นทางของชุดที่ลงไว้เป็น ZIP (เช่น WorldPop รายช่วงอายุ/เพศ) · ?key= &years=2015,2016 &match=_t_60_,_t_65_ &must=1km"""
    from . import ai_tools
    a = request.args
    ys = [int(y) for y in (a.get('years') or '').split(',') if y.strip().isdigit()] or None
    try:
        it, _d, _res, dl, _direct, browsed = ai_tools._hub_files(str(a.get('key')), ys, a.get('match') or None, a.get('must') or None)
    except ai_tools.ToolError as e:
        raise ApiError(str(e))
    files = [dict(name=f['name'], year=f.get('year'), url=f['url'], size_mb=f.get('size_mb')) for f in dl if f.get('from_zip')]
    return jsonify(files=files[:600], total=len(files), browsed=browsed, patterns=ai_tools._patterns([f for f in dl if f.get('from_zip')], 120))


@app.route('/api/hub/import', methods=['POST'])
def hub_import():
    """ปุ่ม "นำเข้าคลัง" ในหน้า Data hub — ไฟล์ต้องอยู่ในรายการนำเข้าได้ของชุดนั้น"""
    from . import ai_tools
    b = request.get_json(force=True)
    try:
        return jsonify(ai_tools.start_hub_import(str(b.get('hub_key')), str(b.get('url')), b.get('name'), b.get('aoi_id'), b.get('value_type') or None))
    except ai_tools.ToolError as e:
        raise ApiError(str(e))


@app.route('/api/ai/reject', methods=['POST'])
def ai_reject():
    from . import ai_tools
    ai_tools.reject(str(request.get_json(force=True).get('id')))
    return jsonify(ok=True)


@app.route('/api/folders')
def folder_list():
    return jsonify(folders=folders.all_())


@app.route('/api/folders', methods=['POST'])
def folder_create():
    b = request.get_json(force=True)
    fid = folders.create(b.get('name'), b.get('parent_id'))
    return jsonify(id=fid, folder=db.get('folders', fid))


@app.route('/api/folders/<int:fid>', methods=['PATCH'])
def folder_patch(fid):
    b = request.get_json(force=True)
    return jsonify(folder=folders.update(fid, name=b.get('name'), parent_id=b['parent_id'] if 'parent_id' in b else ...))


@app.route('/api/folders/<int:fid>', methods=['DELETE'])
def folder_delete(fid):
    return jsonify(ok=True, **folders.delete(fid))


@app.route('/api/folders/move', methods=['POST'])
def folder_move():
    b = request.get_json(force=True)
    return jsonify(ok=True, moved=folders.move(b.get('dataset_ids'), b.get('folder_ids'), b.get('to')))


@app.route('/api/upload', methods=['POST'])
def upload():
    """ลากไฟล์มาวาง: เบราว์เซอร์ไม่บอก path จริง → ต้องอัปโหลด = ก๊อปเข้า database เสมอ"""
    files = request.files.getlist('files')
    if not files:
        raise ApiError('ไม่มีไฟล์')
    dest = DIRS['database'] / f'{db.now().replace(":", "").replace("-", "")}_upload'
    dest.mkdir(parents=True, exist_ok=True)
    saved = []
    for f in files:
        name = Path(f.filename).name
        p = dest / name
        f.save(p)
        saved.append(p)
    mains = [p for p in saved if dsinfo.kind_of(p) and p.suffix.lower() not in ('.shx', '.dbf', '.prj', '.cpg')]
    added, warns, errors = [], [], []
    for p in mains:
        if p.suffix.lower() == '.vrt':
            errors.append(f'{p.name}: VRT อ้างไฟล์อื่น ลากมาวางไม่ได้ — ใช้ "เลือกไฟล์" หรือวาง path แทน')
            continue
        try:
            ids, w = catalog.add_path(p, copy=False)
            for i in ids:
                db.update('datasets', i, copied=1)
            added += ids
            warns += w
        except catalog.CatalogError as e:
            errors.append(f'{p.name}: {e}')
    folders.assign(added, request.form.get('folder_id'))
    for i in added:
        prepare_if_needed(i)
    return jsonify(added=added, warnings=warns, errors=errors, folder=str(dest))


@app.route('/api/browse', methods=['POST'])
def browse():
    """หน้าต่างเลือกไฟล์ของ Windows (เปิดใน process แยก — แอปรันในเครื่องจึงได้ path จริง)"""
    code = ("import tkinter as tk, json\nfrom tkinter import filedialog\nr=tk.Tk();r.withdraw();r.attributes('-topmost',True)\n"
            "p=filedialog.askopenfilenames(title='เลือกไฟล์ชุดข้อมูล',filetypes=[('ข้อมูลภูมิสารสนเทศ','*.tif *.tiff *.vrt *.img *.jp2 "
            "*.asc *.gpkg *.shp *.geojson *.json *.zip *.fgb'),('ทุกไฟล์','*.*')])\nprint(json.dumps(list(p)))")
    r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, encoding='utf-8', timeout=600)
    try:
        return jsonify(paths=json.loads(r.stdout.strip().splitlines()[-1]))
    except Exception:
        return jsonify(paths=[], error=r.stderr[-500:])


@app.route('/api/datasets/<int:did>/profile')
def ds_profile(did):
    """ประวัติชุดข้อมูล: ไฟล์อะไร รูปแบบสำคัญ มาจากไหน พ่อแม่/ลูก ค่าที่ตั้ง โน้ต"""
    from . import profile
    ds_or_404(did)
    return jsonify(profile.build(did))


@app.route('/api/datasets/<int:did>/profile.md')
def ds_profile_md(did):
    from urllib.parse import quote
    from . import profile
    p = profile.build(ds_or_404(did)['id'])
    name = export.slug(p['name'], 60) + '_ประวัติ.md'
    return Response(profile.as_markdown(p), mimetype='text/markdown; charset=utf-8',
                    headers={'Content-Disposition': f"attachment; filename*=UTF-8''{quote(name)}"})


@app.route('/api/datasets/<int:did>/note', methods=['POST'])
def ds_note(did):
    """โน้ตของผู้ใช้ (ว่าง = ลบ) · ลบโน้ตของ AI ได้ด้วย ai=false"""
    d = ds_or_404(did)
    b = request.get_json(force=True)
    m = dict(d['meta'])
    if 'text' in b:
        t = (b.get('text') or '').strip()[:5000]
        m['note_user'] = t or None
    if b.get('clear_ai'):
        m.pop('note_ai', None)
    db.update('datasets', did, meta=m)
    return jsonify(ok=True)


@app.route('/api/datasets/<int:did>')
def get_ds(did):
    d = ds_or_404(did)
    catalog.check_status(d)
    if d['status'] == 'ok':
        prepare_if_needed(did)            # งานเตรียมข้อมูลหายไป (เช่น ปิดแอประหว่างทำ) → สร้างใหม่
    d['jobs'] = db.query("SELECT id,kind,status,progress,message FROM jobs WHERE params LIKE ? ORDER BY id DESC LIMIT 5",
                         (f'%"dataset_id": {did}}}%',))
    if d.get('job_id'):
        j = db.get('jobs', d['job_id'])
        if j and j.get('out_dir'):
            lp = Path(j['out_dir']) / 'lineage.json'
            d['lineage'] = json.loads(lp.read_text(encoding='utf-8')) if lp.exists() else None
            d['out_dir'] = j['out_dir']
            d['source_changed'] = catalog.changed_inputs(d['lineage'])
            d['job_kind'] = j['kind']
    if d['kind'] == 'raster':
        d['res_options'] = res_options([d])
    if d['kind'] == 'vector' and not d['meta'].get('encoding_checked') and d['status'] == 'ok':
        enc, w = dsinfo.text_encoding(d['path'])          # ชุดข้อมูลที่เพิ่มก่อน v0.3.7 → ตรวจภาษาไทยครั้งเดียว
        m = d['meta']
        m.update(encoding=m.get('encoding') or enc, encoding_auto=enc, encoding_checked=True)
        m['warnings'] = (m.get('warnings') or []) + [x for x in w if x not in (m.get('warnings') or [])]
        db.update('datasets', did, meta=m)
    d['encodings'] = dsinfo.ENCODINGS
    return jsonify(public(d))


@app.route('/api/datasets/<int:did>', methods=['PATCH'])
def patch_ds(did):
    d = ds_or_404(did)
    b = request.get_json(force=True)
    upd = {}
    if 'name' in b:
        n = str(b['name']).strip()
        if not n:
            raise ApiError('ชื่อห้ามว่าง')
        upd['name'] = n
    if 'value_type' in b:
        if b['value_type'] not in ('count', 'density', 'class'):
            raise ApiError('ประเภทค่าต้องเป็น count / density / class')
        upd['value_type'] = b['value_type']
        upd['value_type_confirmed'] = 1
    if 'nodata_as' in b:
        v = b['nodata_as']
        upd['nodata_as'] = None if v in (None, '') else float(v)
    if 'exclude_values' in b:
        try:
            ev = [float(x) for x in str(b['exclude_values']).replace(' ', '').split(',') if x != '']
        except ValueError:
            raise ApiError('ค่าที่ไม่นับต้องเป็นตัวเลขคั่นด้วย ,')
        upd['exclude_values'] = ev or None
    if 'encoding' in b and d['kind'] == 'vector':
        enc = b['encoding'] or None
        if enc and enc not in dsinfo.ENCODINGS:
            raise ApiError('การเข้ารหัสไม่ถูกต้อง')
        m = d['meta']
        m['encoding'] = enc or m.get('encoding_auto')
        m['encoding_manual'] = bool(enc)
        upd['meta'] = m
    if 'band' in b:
        bd = int(b['band'])
        if not 1 <= bd <= d['meta'].get('count', 1):
            raise ApiError('แบนด์ไม่ถูกต้อง')
        upd['band'] = bd
    db.update('datasets', did, **upd)
    job = prepare_if_needed(did) if ('value_type' in upd or 'band' in upd) else None
    return jsonify(ok=True, prepare_job=job)


@app.route('/api/datasets/<int:did>', methods=['DELETE'])
def del_ds(did):
    """ลบ = ย้ายเข้าถังขยะ (กู้คืนได้) · ลบถาวรทำในถังขยะ"""
    d = ds_or_404(did)
    trash.move_dataset(d)
    return jsonify(ok=True, note=f'ย้าย "{d["name"]}" ไปถังขยะแล้ว — กู้คืนได้จากถังขยะ', trash=trash.count())


# ---------------- Data hub: ตรวจลิงก์ ----------------
@app.route('/api/hub/check', methods=['POST'])
def hub_check():
    from . import linkcheck
    urls = request.get_json(force=True).get('urls') or []
    return jsonify(results=linkcheck.check_many(urls), max=linkcheck.MAX_URLS)


# ---------------- ถังขยะ ----------------
@app.route('/api/trash')
def trash_list():
    return jsonify(items=trash.items(), count=trash.count())


def _trash_item(kind, iid):
    if kind == 'dataset':
        d = db.get('datasets', iid)
    elif kind == 'aoi':
        d = db.get('aoi', iid)
    else:
        raise ApiError('ไม่รู้จักชนิด')
    if not d or not d.get('trashed_at'):
        raise ApiError('ไม่พบในถังขยะ')
    return d


@app.route('/api/trash/<kind>/<int:iid>/restore', methods=['POST'])
def trash_restore(kind, iid):
    d = _trash_item(kind, iid)
    if kind == 'dataset':
        trash.restore_dataset(d)
    else:
        db.update('aoi', iid, trashed_at=None)
    return jsonify(ok=True, count=trash.count())


@app.route('/api/trash/<kind>/<int:iid>', methods=['DELETE'])
def trash_purge(kind, iid):
    d = _trash_item(kind, iid)
    r = trash.purge_dataset(d) if kind == 'dataset' else trash.purge_aoi(d)
    return jsonify(ok=True, count=trash.count(), **r)


@app.route('/api/trash', methods=['DELETE'])
def trash_empty():
    freed = n = 0
    for it in trash.items():
        d = _trash_item(it['kind'], it['id'])
        freed += (trash.purge_dataset(d) if it['kind'] == 'dataset' else trash.purge_aoi(d)).get('freed', 0)
        n += 1
    return jsonify(ok=True, removed=n, freed=freed, count=0)


@app.route('/api/datasets/<int:did>/prepare', methods=['POST'])
def re_prepare(did):
    d = ds_or_404(did)
    db.update('datasets', did, preview_key=None)
    return jsonify(job=prepare_if_needed(did))


@app.route('/api/datasets/<int:did>/tile/<int:z>/<int:x>/<int:y>.png')
def tile(did, z, x, y):
    d = ds_or_404(did)
    cols = None
    c = request.args.get('c')
    if c:
        cols = ['#' + s if s else None for s in c.split(',')]
    tok = request.args.get('st', '')
    st = _previews.get(tok)
    if st is not None:                       # ใช้อยู่ → ย้ายไปท้าย (ไม่โดนไล่ออกก่อน; ชั้นในแผนที่ซ้อนชั้นใช้ token ค้างไว้)
        _previews[tok] = _previews.pop(tok)
    clip = request.args.get('clip')
    try:
        data, cache = tiles.render(d, z, x, y, cols, st, int(clip) if clip and clip.isdigit() else None)
    except Exception as e:
        print(f'[ไทล์] #{did} {z}/{x}/{y}:', e)
        return Response(tiles.EMPTY, mimetype='image/png', headers={'Cache-Control': 'no-store'})
    return Response(data, mimetype='image/png', headers={'Cache-Control': 'no-store' if not cache else 'max-age=600'})


@app.route('/api/datasets/<int:did>/point')
def point(did):
    d = ds_or_404(did)
    lon, lat = float(request.args['lon']), float(request.args['lat'])
    z = int(request.args.get('z', 10))
    if d['kind'] == 'raster':
        return jsonify(kind='raster', lon=lon, lat=lat, **tiles.point_raster(d, lon, lat))
    return jsonify(kind='vector', lon=lon, lat=lat, features=tiles.point_vector(d, lon, lat, z))


@app.route('/api/datasets/<int:did>/features')
def feats(did):
    d = ds_or_404(did)
    bbox = [float(v) for v in request.args['bbox'].split(',')]
    z = int(request.args.get('z', 8))
    flds = [f for f in request.args.get('fields', '').split(',') if f]
    gj, trunc, n, hidden = tiles.features(d, bbox, z, int(request.args.get('limit', 4000)), flds)
    return Response(gj, mimetype='application/geo+json', headers={'X-Truncated': str(int(trunc)), 'X-Count': str(n), 'X-Hidden': str(hidden)})


@app.route('/api/datasets/<int:did>/table')
def ds_table(did):
    """ตาราง attribute หนึ่งหน้า: ค้นหา (q, field) · เรียง (sort, desc) · แบ่งหน้า (offset, limit) · fid = แถวเดียว"""
    from . import attrtable
    d = ds_or_404(did)
    if d['kind'] != 'vector':
        raise ApiError('ตาราง attribute มีเฉพาะชุดเวกเตอร์')
    a = request.args
    return jsonify(attrtable.table(d, a.get('offset', 0), a.get('limit', 50), a.get('q', ''), a.get('field', ''),
                                   a.get('sort', ''), a.get('desc') in ('1', 'true'), a.get('fid')))


@app.route('/api/datasets/<int:did>/field-stats')
def ds_field_stats(did):
    from . import attrtable
    d = ds_or_404(did)
    try:
        return jsonify(attrtable.field_stats(d, request.args['field']))
    except KeyError:
        raise ApiError('ไม่พบฟิลด์นี้')


@app.route('/api/datasets/<int:did>/feature/<int:fid>')
def ds_feature(did, fid):
    """รูป + attribute ของ feature เดียว (ไว้ซูม/ไฮไลต์จากตาราง)"""
    from . import attrtable
    try:
        return jsonify(attrtable.feature(ds_or_404(did), fid))
    except KeyError:
        raise ApiError('ไม่พบ feature นี้')


@app.route('/api/datasets/<int:did>/colors', methods=['POST'])
def set_colors(did):
    """แก้สีของแผนที่ไบแวเรียตที่สร้างแล้ว: เขียนตารางสีในไฟล์ + QML + legend ใหม่"""
    import rasterio
    d = ds_or_404(did)
    if d.get('role') != 'map':
        raise ApiError('แก้สีได้เฉพาะแผนที่ไบแวเรียต')
    cols = request.get_json(force=True)['colors']
    j = db.get('jobs', d['job_id'])
    p = j['params']
    out = Path(j['out_dir'])
    lin = json.loads((out / 'lineage.json').read_text(encoding='utf-8'))
    lp = lin['params']
    nx, ny = int(lp['x']['n']), int(lp['y']['n'])
    if len(cols) != nx * ny:
        raise ApiError(f'ต้องมี {nx * ny} สี')
    cmap = {0: (0, 0, 0, 0)}
    for i, c in enumerate(cols, 1):
        h = c.lstrip('#')
        cmap[i] = (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)
    tiles.drop_pool(d['path'])
    with rasterio.open(d['path'], 'r+') as ds:
        ds.write_colormap(1, cmap)
    base = Path(d['path']).stem
    xl, yl = export.class_labels(dict(lp['x'], breaks=lp['x']['resolved_breaks'])), export.class_labels(dict(lp['y'], breaks=lp['y']['resolved_breaks']))
    xname = lp['x'].get('label') or ''
    yname = lp['y'].get('label') or ''
    ents = [(c, cols[c - 1], f'{c}: {yname} {yl[(c - 1) // nx]} · {xname} {xl[(c - 1) % nx]}') for c in range(1, nx * ny + 1)]
    (out / f'{base}.qml').write_text(export.qml_paletted(ents), encoding='utf-8')
    export.legend_png(out / f'{base}_legend.png', nx, ny, cols, xname, yname, xl, yl, lp.get('highlight', []))
    lin.setdefault('palette_edits', []).append(dict(at=db.now(), colors=cols))
    (out / 'lineage.json').write_text(json.dumps(lin, ensure_ascii=False, indent=1), encoding='utf-8')
    upd = dict(fingerprint=dsinfo.fingerprint(d['path']), status='ok')
    if d.get('style') and d['style'].get('type') == 'paletted':      # สีในสไตล์ตามไฟล์ (คงค่าซ่อน/แสดงไว้)
        st = d['style']
        for e in st.get('entries', []):
            v = int(float(e['value']))
            if 1 <= v <= len(cols):
                e['color'] = cols[v - 1]
        upd['style'] = st
    db.update('datasets', did, **upd)
    return jsonify(ok=True)


# ---------------- สไตล์ (symbology แบบ QGIS) ----------------
_previews = {}          # token → สไตล์ชั่วคราว (พรีวิวก่อนบันทึก)


@app.route('/api/datasets/<int:did>/style')
def get_style(did):
    d = ds_or_404(did)
    return jsonify(style=tiles.style_of(d), saved=bool(d.get('style')))


@app.route('/api/datasets/<int:did>/style', methods=['POST'])
def save_style(did):
    """บันทึกสไตล์ (style=null → กลับเป็นค่าเริ่มต้น) ; ผลแปลงของแอปเขียน .qml คู่ไฟล์ให้ด้วย"""
    d = ds_or_404(did)
    st = request.get_json(force=True).get('style')
    db.update('datasets', did, style=symbology.jsonable(st) if st else None)
    d = ds_or_404(did)
    wrote = None
    if st and d['kind'] == 'raster' and d.get('role') == 'derived':
        p = Path(d['path']).with_suffix('.qml')
        p.write_text(symbology.qml(d, st), encoding='utf-8')
        wrote = str(p)
    return jsonify(ok=True, qml=wrote)


@app.route('/api/datasets/<int:did>/classify', methods=['POST'])
def classify(did):
    d = ds_or_404(did)
    try:
        return jsonify(style=symbology.jsonable(symbology.classify(d, request.get_json(force=True))))
    except ValueError as e:
        raise ApiError(str(e))


@app.route('/api/style-preview', methods=['POST'])
def style_preview():
    import hashlib
    b = request.get_json(force=True)
    tok = hashlib.sha1(json.dumps(b, sort_keys=True).encode()).hexdigest()[:12]
    _previews[tok] = b['style']
    while len(_previews) > 300:
        _previews.pop(next(iter(_previews)))
    return jsonify(token=tok)


@app.route('/api/datasets/<int:did>/style.qml')
def style_qml(did):
    d = ds_or_404(did)
    xml = symbology.qml(d, tiles.style_of(d))
    name = re.sub(r'[^\w.\-]', '_', Path(d['path']).stem) + '.qml'
    return Response(xml, mimetype='application/xml', headers={'Content-Disposition': f'attachment; filename="{name}"'})


# ---------------- ลิงก์ (3.1–3.3) ----------------
@app.route('/api/basedata', methods=['GET', 'POST'])
def basedata_api():
    """GET = รายการข้อมูลพื้นฐาน + สถานะ · POST = เพิ่มชุดที่ขาด (รวมที่ผู้ใช้เคยลบ)"""
    if request.method == 'POST':
        basedata.seed(force=True)
    have = {basedata._norm(r['path']) for r in db.query("SELECT path FROM datasets WHERE kind='link' AND trashed_at IS NULL")}
    return jsonify(items=[dict(name=n, url=u, description=d, present=basedata._norm(u) in have) for n, u, d in basedata.BASE],
                   status=basedata.STATUS)


@app.route('/api/links/inspect', methods=['POST'])
def link_inspect():
    b = request.get_json(force=True)
    try:
        info = links.inspect(b['url'], vault.get(b.get('secret_id')))
    except links.LinkError as e:
        raise ApiError(str(e))
    except Exception as e:
        raise ApiError(f'เชื่อมต่อไม่ได้: {e}')
    info['type_label'] = links.LABEL.get(info['type'])
    info['view'] = info['type'] in links.VIEW_TYPES
    return jsonify(info)


@app.route('/api/links', methods=['POST'])
def link_add():
    b = request.get_json(force=True)
    info = b['info']
    name = (b.get('name') or info.get('title') or 'ลิงก์').strip()
    meta = {k: v for k, v in info.items() if k != 'token'}
    meta.update(kind='link', secret_id=b.get('secret_id'), type_label=links.LABEL.get(info['type']), view=info['type'] in links.VIEW_TYPES,
                bounds_wgs84=info.get('bounds_wgs84') or links.wgs_bounds(info), added_from=info.get('url'))
    meta.setdefault('warnings', [])
    if info.get('note'):
        meta['warnings'].append(info['note'])
    did = db.insert('datasets', name=name, path=info['url'], source_path=info['url'], read_path=info['url'], copied=0, kind='link',
                    format=info['type'], meta=meta, role='input', added_at=db.now(), status='ok', fingerprint=None)
    folders.assign([did], b.get('folder_id'))
    return jsonify(id=did)


@app.route('/api/links/<int:did>/layer', methods=['POST'])
def link_layer(did):
    d = ds_or_404(did)
    b = request.get_json(force=True)
    m = d['meta']
    if 'layer' in b:
        m['layer'] = b['layer']
    if 'layers_on' in b:
        m['layers_on'] = b['layers_on'] or None
    if 'secret_id' in b:
        m['secret_id'] = b['secret_id'] or None
    db.update('datasets', did, meta=m)
    return jsonify(ok=True)


@app.route('/api/links/<int:did>/features')
def link_features(did):
    """พรีวิว feature จากลิงก์ข้อมูล (ArcGIS Feature layer / WFS / GeoJSON) เฉพาะกรอบที่มอง ผ่านพร็อกซีของแอป"""
    d = ds_or_404(did)
    bbox = [float(v) for v in request.args['bbox'].split(',')]
    try:
        g, trunc = links.features(d, bbox, int(request.args.get('z', 8)))
    except Exception as e:
        raise ApiError(f'ดึง feature ไม่ได้: {e}')
    return Response(json.dumps(g, ensure_ascii=False), mimetype='application/geo+json',
                    headers={'X-Truncated': str(int(trunc)), 'X-Count': str(len(g.get('features', [])))})


@app.route('/api/links/<int:did>/field-values')
def link_field_values(did):
    d = ds_or_404(did)
    try:
        vals, total = links.distinct_values(d, request.args['field'], request.args.get('q', ''), int(request.args.get('limit', 300)))
    except Exception as e:
        raise ApiError(f'อ่านค่าฟิลด์จากบริการไม่ได้: {e}')
    return jsonify(values=vals, total=total)


@app.route('/api/datasets/<int:did>/extent', methods=['POST'])
@app.route('/api/links/<int:did>/extent', methods=['POST'])
def feature_extent(did):
    """กรอบของพื้นที่ที่เลือก (ชื่อในฟิลด์) — หน้าพื้นที่ศึกษาใช้ซูมไปพื้นที่นั้น"""
    d = ds_or_404(did)
    b = request.get_json(force=True)
    vals = b.get('values') or []
    if not vals:
        return jsonify(bounds=None)
    try:
        bb = links.extent_where_in(d['meta'], b['field'], vals) if d['kind'] == 'link' else aoimod.extent_of(d, b['field'], vals)
    except Exception as e:
        raise ApiError(f'หาขอบเขตไม่ได้: {e}')
    return jsonify(bounds=bb)


@app.route('/api/links/<int:did>/refresh', methods=['POST'])
def link_refresh(did):
    """อ่านขอบเขต/ฟิลด์ของชั้นที่เลือกใหม่ (ลิงก์ที่เพิ่มก่อน v3.1 ไม่มีขอบเขต)"""
    d = ds_or_404(did)
    m = d['meta']
    if m['type'] == 'arcgis_feature':
        try:
            m.update(links.layer_info(m['url'], m.get('layer') or 0, vault.get(m.get('secret_id'))))
        except Exception as e:
            raise ApiError(f'อ่านข้อมูลชั้นไม่ได้: {e}')
    elif not m.get('bounds_wgs84'):
        m['bounds_wgs84'] = links.wgs_bounds(m)
    db.update('datasets', did, meta=m)
    return jsonify(bounds=m.get('bounds_wgs84'), fields=m.get('fields'))


@app.route('/api/links/<int:did>/tile/<int:z>/<int:x>/<int:y>.png')
def link_tile(did, z, x, y):
    d = ds_or_404(did)
    try:
        data, ct = links.tile(d, z, x, y)
    except Exception as e:
        print(f'[ลิงก์] #{did} {z}/{x}/{y}:', e)
        return Response(tiles.EMPTY, mimetype='image/png', headers={'Cache-Control': 'no-store'})
    return Response(data, mimetype=ct, headers={'Cache-Control': 'max-age=3600'})


@app.route('/api/secrets')
def secrets_list():
    return jsonify(vault.listing())


@app.route('/api/secrets', methods=['POST'])
def secrets_add():
    b = request.get_json(force=True)
    if not b.get('value'):
        raise ApiError('ใส่โทเคนก่อน')
    return jsonify(id=vault.put((b.get('name') or 'โทเคน').strip(), b['value'].strip()))


@app.route('/api/secrets/<sid>', methods=['DELETE'])
def secrets_del(sid):
    vault.delete(sid)
    return jsonify(ok=True)


# ---------------- รายงาน PDF (3.7) ----------------
@app.route('/api/datasets/<int:did>/report.pdf')
def report_pdf(did):
    from . import report
    d = ds_or_404(did)
    if d['kind'] == 'link':
        raise ApiError('ลิงก์ดูอย่างเดียวทำรายงานไม่ได้')
    data = report.make_pdf(d)
    name = re.sub(r'[^\w.\-]', '_', Path(d['path']).stem) + '_report.pdf'
    return Response(data, mimetype='application/pdf', headers={'Content-Disposition': f'inline; filename="{name}"'})


@app.route('/api/report/templates')
def report_templates():
    from . import layout
    return jsonify(templates=[[k, v['name']] for k, v in layout.TEMPLATES.items()],       # list — jsonify เรียงคีย์ dict ตามตัวอักษร
                   basemaps={k: v[1] for k, v in layout.BASEMAPS.items()})


# ---------------- จัดหน้าแบบแคนวาส (v0.5) ----------------
@app.route('/api/report/map', methods=['POST'])
def report_map():
    from . import canvas
    b = request.get_json(force=True)
    try:
        return jsonify(canvas.render_map(b.get('map') or {}, b['w'], b['h'], int(b.get('dpi') or 110), b.get('view')))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise ApiError(f'วาดแผนที่ไม่ได้: {e}')


@app.route('/api/report/view', methods=['POST'])
def report_view():
    """กรอบเริ่มต้นตามข้อมูล/พื้นที่ศึกษา (ปุ่ม "พอดีข้อมูล")"""
    from . import canvas
    b = request.get_json(force=True)
    return jsonify(view=canvas.auto_view(b.get('map') or {}, float(b['w']), float(b['h'])))


@app.route('/api/report/inset', methods=['POST'])
def report_inset():
    from . import canvas
    b = request.get_json(force=True)
    return jsonify(canvas.render_inset(b['ext'], b['w'], b['h'], int(b.get('dpi') or 110), b.get('basemap') or 'esri_light', b.get('zoom') or 1))


@app.route('/api/report/info', methods=['POST'])
def report_info():
    from . import canvas
    return jsonify(canvas.info(request.get_json(force=True).get('map') or {}))


@app.route('/api/report/img/<key>.png')
def report_img(key):
    from . import canvas
    if not re.fullmatch(r'[0-9a-f]{20}', key):
        raise ApiError('ไม่พบภาพ')
    r = send_from_directory(canvas.RDIR, f'{key}.png')
    r.headers['Cache-Control'] = 'max-age=86400'
    return r


@app.route('/api/report/export', methods=['POST'])
def report_export():
    from urllib.parse import quote
    from . import canvas
    b = request.get_json(force=True)
    doc, fmt = b['doc'], b.get('format', 'pdf')
    try:
        data = canvas.export(doc, fmt, b.get('dpi') or 200, request.host_url)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise ApiError(f'ส่งออกไม่ได้: {e}')
    name = export.slug((doc.get('meta') or {}).get('title') or 'map', 50) + ('.png' if fmt == 'png' else '.pdf')
    return Response(data, mimetype='image/png' if fmt == 'png' else 'application/pdf',
                    headers={'Content-Disposition': f"attachment; filename*=UTF-8''{quote(name)}", 'Cache-Control': 'no-store'})


@app.route('/report/print/<tok>')
def report_print(tok):
    from . import canvas
    doc = canvas.PRINTS.get(tok)
    if doc is None:
        return Response('expired', status=404)
    return Response(canvas.print_html(doc), mimetype='text/html')


@app.route('/api/report/render', methods=['POST'])
def report_render():
    """จัดหน้าแผนที่ตามแบบที่เลือก → PNG (พรีวิว/ส่งออก) หรือ PDF"""
    from . import layout
    b = request.get_json(force=True)
    spec = b.get('spec') or {}
    if not spec.get('layers'):
        raise ApiError('เลือกชั้นข้อมูลอย่างน้อย 1 ชั้น')
    fmt = 'png' if b.get('preview') else (spec.get('format') or 'pdf')
    try:
        data = layout.render(spec, fmt=fmt, preview=bool(b.get('preview')))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise ApiError(f'จัดหน้าไม่ได้: {e}')
    name = export.slug(spec.get('title') or 'map', 50) + ('.png' if fmt == 'png' else '.pdf')    # slug คงสระ/วรรณยุกต์ไทยไว้แล้ว
    from urllib.parse import quote
    return Response(data, mimetype='image/png' if fmt == 'png' else 'application/pdf',
                    headers={'Content-Disposition': f"inline; filename*=UTF-8''{quote(name)}", 'Cache-Control': 'no-store'})


# ---------------- ระบบ: แคช / ผลค้าง (3.8) ----------------
def _du(p):
    n = s = 0
    if p.exists():
        for f in p.rglob('*'):
            if f.is_file():
                n += 1
                s += f.stat().st_size
    return dict(files=n, bytes=s)


@app.route('/api/settings/out-crs', methods=['POST'])
def set_out_crs():
    """ระบบพิกัดผลลัพธ์ของทุกงาน: "source" (ตามต้นทาง) | "EPSG:32647" (UTM 47N) — เก็บใน settings.json"""
    from .config import save_settings
    v = (request.get_json(force=True) or {}).get('out_crs') or 'source'
    if v not in ('source', 'EPSG:32647'):
        raise ApiError('out_crs ต้องเป็น source หรือ EPSG:32647')
    save_settings(out_crs=v)
    return jsonify(out_crs=v)


@app.route('/api/system')
def system_info():
    from .config import load_settings
    c = DIRS['cache']
    dead = db.query("SELECT id,title,status,out_dir FROM jobs WHERE status IN ('failed','cancelled') AND out_dir IS NOT NULL")
    dead = [j for j in dead if j['out_dir'] and Path(j['out_dir']).exists()]
    return jsonify(dirs={k: dict(path=str(v), **_du(v)) for k, v in DIRS.items()},
                   cache={k: _du(c / k) for k in ('preview', 'samples', 'vrt')},
                   tile_cache=len(tiles._tc), link_cache=len(links._tc), dead_jobs=dead, secrets=vault.listing(),
                   out_crs=load_settings().get('out_crs') or 'source')


@app.route('/api/system/restart', methods=['POST'])
def system_restart():
    """รีสตาร์ตเซิร์ฟเวอร์ให้ได้โค้ดใหม่: เปิดเซิร์ฟเวอร์ตัวใหม่ (หน้าต่างใหม่) แล้วปิดตัวนี้
    งานที่กำลังรันเป็น process แยก ไม่ถูกปิด — ตัวใหม่ติดตามต่อจาก pid ในตาราง jobs"""
    import threading

    def go():
        import time
        time.sleep(0.6)                                   # ให้ส่งคำตอบกลับก่อน
        flags = 0x00000010 if os.name == 'nt' else 0      # CREATE_NEW_CONSOLE
        subprocess.Popen([sys.executable, '-m', 'app.server', '--wait-port'], cwd=str(ROOT), creationflags=flags)
        os._exit(0)
    threading.Thread(target=go, daemon=True).start()
    return jsonify(ok=True)


@app.route('/api/system/clear', methods=['POST'])
def system_clear():
    """ล้างแคช (สร้างใหม่ได้เอง) หรือลบโฟลเดอร์ผลของงานที่ล้มเหลว/ยกเลิก — ลบเฉพาะไฟล์ที่แอปสร้างใน workspace"""
    import shutil
    what = request.get_json(force=True)['what']
    freed = 0
    if what == 'tiles':
        tiles._tc.clear()
        links._tc.clear()
        tiles._defaults.clear()
    elif what == 'preview':
        p = DIRS['cache'] / 'preview'
        freed = _du(p)['bytes']
        tiles._pool.clear()
        tiles._tc.clear()
        shutil.rmtree(p, ignore_errors=True)
        with db.connect() as con:
            con.execute('UPDATE datasets SET preview_path=NULL, preview_key=NULL')
    elif what == 'dead_jobs':
        for j in db.query("SELECT id,out_dir FROM jobs WHERE status IN ('failed','cancelled') AND out_dir IS NOT NULL"):
            p = Path(j['out_dir'])
            if p.exists() and WORKSPACE in p.parents:
                freed += _du(p)['bytes']
                shutil.rmtree(p, ignore_errors=True)
    else:
        raise ApiError('ไม่รู้จักคำสั่ง')
    return jsonify(ok=True, freed=freed)


# ---------------- ความละเอียด / กริด ----------------
MULTS = [Fraction(1, k) for k in (10, 5, 2)] + [Fraction(1)] + [Fraction(k) for k in (2, 3, 5, 10, 100)]


def res_options(dss):
    """ความละเอียดที่เป็นพหุคูณจำนวนเต็มของทุกชุด (ในกลุ่มกริดเดียวกัน)"""
    m0 = dss[0]['meta']
    geo = m0.get('geographic')
    fr = [Fraction(d['meta']['res_exact']) for d in dss if d['meta'].get('res_exact')]
    if len(fr) != len(dss):
        return []
    cand = set()
    for f in fr:
        for k in MULTS:
            cand.add(f * k)
    others = db.query("SELECT meta FROM datasets WHERE kind='raster'")
    fam = gm.family_key(m0)
    for o in others:
        if gm.family_key(o['meta']) == fam and o['meta'].get('res_exact'):
            cand.add(Fraction(o['meta']['res_exact']))
    specs = [engine.GridSpec(d['meta'], d['name'], d.get('value_type')) for d in dss]
    out, why = [], None
    for c in sorted(cand):
        if all(gm.int_ratio(f / c) for f in fr):
            try:                                   # มุมเริ่มต่างกันได้ · เส้นกริดเหลื่อม → ชุดนั้นถ่วงพื้นที่ (warp)
                al = engine.align(specs, c)
            except engine.EngineError as e:
                why = why or str(e)
                continue
            warp = ', '.join(f'{n} (เหลื่อม {e:.2f} พิกเซล)' for n, e in al['warp'])
            finer = c < min(fr)                    # ละเอียดกว่าข้อมูลทุกชุด = ไม่มีรายละเอียดใหม่ แค่ไฟล์ใหญ่ขึ้น
            out.append(dict(value=gm.frac_str(c), label=gm.res_label(c, geo, m0.get('center_lat')) + (' · ⚠ ละเอียดกว่าข้อมูล' if finer else '')
                            + (' · ↔ จัดกริดถ่วงพื้นที่' if warp else ''), warp=warp or None,
                            finer=finer, is_source=[d['id'] for d, f in zip(dss, fr) if f == c],
                            px=int(min(d['meta']['width'] * Fraction(d['meta']['res_exact']) / c for d in dss) *
                                   min(d['meta']['height'] * Fraction(d['meta']['res_exact']) / c for d in dss))))
    if not out and why:
        raise ApiError(why)
    return out


@app.route('/api/res-options')
def api_res_options():
    ids = [int(i) for i in request.args['ids'].split(',')]
    dss = [ds_or_404(i) for i in ids]
    for d in dss:
        if d['kind'] != 'raster':
            raise ApiError(f'"{d["name"]}" ไม่ใช่ raster')
    if len(dss) == 2:
        a, b = dss[0]['meta'], dss[1]['meta']
        if a.get('crs_key') != b.get('crs_key'):
            raise ApiError(f'CRS ต่างกัน ({a.get("crs_key")} กับ {b.get("crs_key")}) — แปลงเป็น UTM 47N ก่อน (หน้าชุดข้อมูล → "แปลงเป็น UTM 47N")')
    return jsonify(options=res_options(dss))       # มุมเริ่มต่างกันได้ — res_options ตรวจแลตทิซร่วมให้แต่ละความละเอียด


@app.route('/api/classes-preview', methods=['POST'])
def classes_preview():
    """สัดส่วนพิกเซล (และค่านับ ถ้าเป็น count) ต่อคลาส จากค่าสุ่ม ที่ความละเอียดต้นทาง — ไว้ดูก่อนยืนยันเกณฑ์"""
    import numpy as np
    b = request.get_json(force=True)
    d = ds_or_404(int(b['dataset_id']))
    cfg = b['cfg']
    v = ops.load_sample(d, cfg.get('metric', 'density'))
    if v is None:
        raise ApiError('ยังไม่มีค่าสุ่ม — รองานเตรียมข้อมูลให้เสร็จ')
    if cfg.get('method') in ('quantile', 'equal', 'jenks'):
        br = ops.auto_breaks(d, cfg)
    elif cfg.get('method') == 'degurba':
        br = (cfg.get('degurba') or {}).get('dens', [300, 1500])
    else:
        br = [float(x) for x in cfg.get('breaks', [])]
    n = int(cfg.get('n', 3))
    # le=True → ค่า ≤ เกณฑ์อยู่ชั้นล่าง (แบบสัญลักษณ์ / QGIS discrete) · ปกติ ค่า ≥ เกณฑ์ขึ้นชั้น (แบบแกนไบแวเรียต)
    cls = np.digitize(v, br, right=bool(cfg.get('le'))) if n > 1 else np.zeros(v.size, int)
    px = np.bincount(cls, minlength=n)[:n]
    out = dict(breaks=br, n=int(v.size), pixel_share=(px / max(v.size, 1)).tolist())
    if v.size:
        out.update(vmin=float(v.min()), vmax=float(v.max()))   # ตามหน่วยที่แสดง (ความหนาแน่น/ค่า) ไม่ใช่ค่าดิบต่อพิกเซล
    if d['value_type'] == 'count':
        z = np.load(d['stats']['sample_path'])
        cnt = np.bincount(cls, weights=z['v'], minlength=n)[:n]
        if (z['v'] < 0).any():                                # มีค่าลบ (เช่น ประชากรเปลี่ยนแปลง) → % ของผลรวมสุทธิไม่มีความหมาย (ได้ −5%, 105%) → ส่งผลรวมจริงต่อชั้น
            out['value_sum'] = cnt.tolist()
        else:
            out['value_share'] = (cnt / max(cnt.sum(), 1e-12)).tolist()
    # ฮิสโทแกรม: เชิงเส้น / log (บวกล้วนเบ้มาก) / symlog (มีทั้งค่าลบและบวก เช่น ประชากรเปลี่ยนแปลง)
    from . import histo
    out['hist'] = histo.hist(v, 40, d['value_type'])
    if cfg.get('method') == 'degurba':
        out['note'] = 'DEGURBA: สัดส่วนนี้คิดจากเกณฑ์ความหนาแน่นอย่างเดียว ยังไม่รวมเงื่อนไขกลุ่มช่องติดกัน/ประชากรรวม'
    return jsonify(out)


# ---------------- งาน ----------------
def _apply_aoi(p, g, ogs):
    """ประเมินหน้าต่างตามพื้นที่ศึกษา (ให้ขนาดผลลัพธ์ตรงกับตอนรันจริง)"""
    if not p.get('aoi_id'):
        return None
    f = 1
    if p.get('aoi_mask_res'):
        r = gm.int_ratio(Fraction(p['aoi_mask_res']) / g.res_frac)
        if r is None or r[0] == 'down':
            raise ApiError('ความละเอียดที่ใช้ตัดพื้นที่ศึกษาต้องเท่าหรือหยาบกว่าผลลัพธ์ และเป็นพหุคูณจำนวนเต็ม')
        f = r[1]
    geom = aoimod.geom_in(int(p['aoi_id']), g.crs)
    g.set_window(geom.bounds, engine.snap_unit(ogs, f))
    return aoimod.get(int(p['aoi_id']))['name']


def _confirmed_raster(did):
    d = ds_or_404(int(did))
    if d['kind'] != 'raster':
        raise ApiError(f'"{d["name"]}" ไม่ใช่ raster')
    if not d.get('value_type_confirmed'):
        raise ApiError(f'ยืนยันประเภทค่าของ "{d["name"]}" ก่อน')
    return d


def validate_job(kind, p):
    """ตรวจค่าที่ตั้ง + ประเมินขนาดผลลัพธ์ก่อนรัน"""
    warns = []
    if kind == 'satellite':
        from . import ops_sat
        return ops_sat.estimate(p)
    if kind in ('calc', 'trend', 'mosaic', 'vmerge'):
        from . import ops_tools
        if kind in ('calc', 'trend'):
            for v in (p.get('vars') or {}).values() if kind == 'calc' else (p.get('items') or []):
                _confirmed_raster(v['dataset_id'])
        return ops_tools.estimate(kind, p)
    if kind in ('hex', 'hexbiv'):
        from . import ops_hex
        if kind == 'hexbiv':
            for a in ('x', 'y'):
                if not (p.get(a) or {}).get('dataset_id'):
                    raise ApiError(f'เลือกชุดข้อมูลแกน {a.upper()}')
        elif not p.get('dataset_ids'):
            raise ApiError('เลือกชุดข้อมูลอย่างน้อย 1 ชุด')
        est = ops_hex.estimate(kind, p)
        if p.get('aoi_id'):
            est['aoi'] = aoimod.get(int(p['aoi_id']))['name']
        return est
    if kind == 'reproject':
        from . import ops_proj
        d = _confirmed_raster(p['dataset_id'])
        ab = aoimod.geom_in(int(p['aoi_id']), p.get('crs') or ops_proj.TARGET).bounds if p.get('aoi_id') else None
        g = ops_proj.plan(d, p.get('target_res'), p.get('crs') or ops_proj.TARGET, ab)
        sm = ops_proj.native_m(d)
        if g.rx < sm / 1.5:
            warns.append(f'ละเอียดกว่าต้นทาง (~{sm:.0f} ม. → {g.rx:g} ม.) — ดูละเอียดขึ้นแต่ไม่มีข้อมูลใหม่')
        raw = g.width * g.height * 4
        if raw > 20e9:
            warns.append(f'ผลลัพธ์ใหญ่มาก {g.width:,} × {g.height:,} พิกเซล — ส่วนที่ว่างถูกข้าม แต่อาจใช้เวลานาน · ตัดตามพื้นที่ศึกษาหรือเลือกความละเอียดหยาบขึ้นได้')
        return dict(grid=g.describe(), raw_bytes=raw, aoi=aoimod.get(int(p['aoi_id']))['name'] if p.get('aoi_id') else None,
                    suggested_res=ops_proj.suggest_res(d), warnings=warns)
    if kind == 'resample':
        d = _confirmed_raster(p['dataset_id'])
        s = engine.Source(d)
        g = engine.make_grid([s], Fraction(p['target_res']))
        og = engine.OnGrid(s, g)
        aoi_name = _apply_aoi(p, g, [og])
        s.close()
        engine.check_tiles(g, [og])
        if og.mode == 'same' and not aoi_name:
            raise ApiError('ความละเอียดเป้าหมายเท่ากับต้นฉบับ (เลือกพื้นที่ศึกษาถ้าต้องการตัดอย่างเดียว)')
        if og.mode == 'up' and d['value_type'] == 'count':
            warns.append(f'ความแม่นยำเทียม: แบ่งค่านับลง {og.k}×{og.k} แบบเท่ากัน ดูละเอียดขึ้นแต่ไม่มีข้อมูลใหม่')
        H, W = g.out_shape
        bpp = 8 if d['value_type'] == 'count' and og.mode == 'down' else 4
        raw = H * W * bpp
        if raw > 10e9:
            warns.append(f'ผลลัพธ์ใหญ่มาก: {W:,} × {H:,} พิกเซล (~{raw / 1e9:,.0f} GB ก่อนบีบอัด) — อาจใช้เวลาหลายสิบนาทีและพื้นที่ดิสก์มาก '
                         'ขั้นสร้าง overview ตอนท้ายหยุดกลางทางไม่ได้ (ยกเลิก = บังคับหยุด) · ถ้าต้องการแค่ไขว้ ไม่ต้องแปลงก่อน — หน้าไบแวเรียตแตกพิกเซลให้ระหว่างคำนวณเอง')
        return dict(grid=g.describe(), mode=og.mode, factor=og.k, raw_bytes=raw, aoi=aoi_name, warnings=warns)
    if kind == 'bivariate':
        dx, dy = _confirmed_raster(p['x']['dataset_id']), _confirmed_raster(p['y']['dataset_id'])
        sx, sy = engine.Source(dx), engine.Source(dy)
        g = engine.make_grid([sx, sy], Fraction(p['target_res']))
        # ไขว้ได้เฉพาะส่วนที่ทับกัน → เตือนเมื่อส่วนที่ทับกัน "ขาด" จากพื้นที่ที่ผู้ใช้ต้องการ (พื้นที่ศึกษา หรือชุดที่เล็กกว่า)
        # ไม่เตือนกรณีปกติ เช่น ประชากรไทย × night light ทั้งโลก (ทับกันครบทั้งไทย แม้เป็น 0% ของทั้งโลก)
        need = None
        if p.get('aoi_id'):
            ab = aoimod.geom_in(int(p['aoi_id']), g.crs).bounds
            need = ((ab[2] - ab[0]) * (ab[3] - ab[1]), aoimod.get(int(p['aoi_id']))['name'])
        else:
            small = min((sx, sy), key=lambda s: s.w * s.rx * s.h * s.ry)
            need = (small.w * small.rx * small.h * small.ry, small.name)
        if need and need[0] > 0:
            x0, y0 = g.x0, g.y0 - g.height * g.ry
            gb = (x0, y0, g.x0 + g.width * g.rx, g.y0)
            tb = ab if p.get('aoi_id') else None
            inter = (max(0, min(gb[2], tb[2]) - max(gb[0], tb[0])) * max(0, min(gb[3], tb[3]) - max(gb[1], tb[1]))) if tb else g.width * g.rx * g.height * g.ry
            cover = inter / need[0]
            if cover < 0.95:
                warns.append(f'ส่วนที่ "{sx.name}" กับ "{sy.name}" ทับกัน ครอบ "{need[1]}" แค่ {cover:.0%} — แผนที่จะมีเฉพาะส่วนที่ทับกัน '
                             '· ถ้าชุดหนึ่งแปลงมาจากเวกเตอร์ ให้แปลงใหม่โดยตั้ง "ขอบเขตผลลัพธ์" = ชุดราสเตอร์อีกชุด (นอกรูป = 0)')
        # ชุดที่แปลงจากเวกเตอร์ (กรอบ = แค่รูป เช่น น้ำท่วมบางพื้นที่) ไขว้กับข้อมูลทั้งผืน → ผลจะเหลือแค่กรอบรูป ซึ่งมักไม่ใช่สิ่งที่ต้องการ
        if not p.get('aoi_id'):
            for s_, o_ in ((sx, sy), (sy, sx)):
                d_ = db.get('datasets', s_.id) if s_.id else None
                j_ = db.get('jobs', d_['job_id']) if d_ and d_.get('job_id') else None
                if j_ and j_['kind'] == 'rasterize':
                    cov = (g.width * g.rx * g.height * g.ry) / (o_.w * o_.rx * o_.h * o_.ry)
                    if cov < 0.95:
                        warns.append(f'"{s_.name}" แปลงมาจากเวกเตอร์ ครอบ "{o_.name}" แค่ {cov:.0%} — แผนที่จะมีเฉพาะกรอบของรูป '
                                     f'· ถ้าต้องการทั้งผืน ให้แปลงใหม่โดยตั้ง "ขอบเขตผลลัพธ์" = "{o_.name}" (นอกรูป = 0)')
        ox, oy = engine.OnGrid(sx, g), engine.OnGrid(sy, g)
        aoi_name = _apply_aoi(p, g, [ox, oy])
        engine.check_tiles(g, [ox, oy])
        engine.Classifier(p['x']) if p['x'].get('method') == 'breaks' else None
        engine.Classifier(p['y']) if p['y'].get('method') == 'breaks' else None
        sx.close(), sy.close()
        for o, d in ((ox, dx), (oy, dy)):
            if o.mode == 'up' and d['value_type'] == 'count':
                warns.append(f'ความแม่นยำเทียม: "{d["name"]}" ถูกแบ่งลง {o.k}×{o.k} แบบเท่ากัน')
        nx, ny = int(p['x']['n']), int(p['y']['n'])
        if nx * ny > 16:
            warns.append(f'{nx}×{ny} = {nx * ny} สี อ่านยาก แนะนำไม่เกิน 4×4')
        for c in (p['x'], p['y']):
            if c.get('method') == 'degurba' and g.width * g.height > 30_000_000:
                raise ApiError('DEGURBA คำนวณทั้งประเทศในหน่วยความจำ ใช้ได้กับความละเอียดหยาบ (≤ 30 ล้านพิกเซล เช่น 1 กม.)')
        H, W = g.out_shape
        return dict(grid=g.describe(), x=dict(mode=ox.mode, factor=ox.k), y=dict(mode=oy.mode, factor=oy.k),
                    raw_bytes=H * W, aoi=aoi_name, warnings=warns)
    if kind == 'rasterize':
        v = ds_or_404(int(p['dataset_id']))
        if v['kind'] != 'vector':
            raise ApiError('ต้องเป็นชุดข้อมูล vector')
        g, gmode = ops.rasterize_grid(p, v)
        aoi_name = _apply_aoi(p, g, [])
        ref = ds_or_404(int(p['ref_dataset_id'])) if gmode == 'ref' else None
        if p.get('mode') in ('attribute', 'majority') and not p.get('field'):
            raise ApiError('เลือกฟิลด์ก่อน')
        H, W = g.out_shape
        if p.get('mode') in ('fraction', 'majority'):
            warns.append(f'โหมดนี้ rasterize ละเอียดขึ้น {p.get("supersample", 10)} เท่าแล้วย่อ — ช้ากว่าแบบปกติ')
        if ref and Fraction(str(p['target_res'])) < Fraction(ref['meta']['res_exact']):
            warns.append(f'ความละเอียดละเอียดกว่ากริดอ้างอิง ({ref["meta"]["res_label"].split(" (")[0]}) — ไฟล์ใหญ่ขึ้นมากแต่ได้รายละเอียดเท่าความแม่นยำของ vector ต้นทาง')
        if H * W > 2e9:
            warns.append(f'ผลลัพธ์ใหญ่มาก ({H * W / 1e9:,.0f} พันล้านพิกเซล) — ไทล์ว่างถูกข้ามให้ แต่ขั้นสร้าง overview ตอนท้ายใช้เวลานานตามขนาดภาพ')
        return dict(grid=g.describe(), raw_bytes=H * W, aoi=aoi_name, warnings=warns)
    if kind == 'vgrid':
        dss = [_confirmed_raster(i) for i in p['dataset_ids']]
        srcs = [engine.Source(d) for d in dss]
        g = engine.make_grid(srcs, Fraction(p['target_res']))
        ogs = [engine.OnGrid(s, g) for s in srcs]
        aoi_name = _apply_aoi(p, g, ogs)
        for s in srcs:
            s.close()
        H, W = g.out_shape
        cells = H * W
        if cells > ops.VGRID_MAX * 4:
            raise ApiError(f'สูงสุด {ops.VGRID_MAX:,} ช่อง แต่กรอบนี้มี {cells:,} ช่อง — เลือกพื้นที่ศึกษาหรือความละเอียดหยาบขึ้น')
        if cells > 300_000:
            warns.append(f'กรอบมีได้ถึง {cells:,} ช่อง — เปิดใน QGIS อาจช้า (ช่องว่าง/ค่า 0 ถูกตัดทิ้ง)')
        return dict(grid=g.describe(), cells_max=cells, aoi=aoi_name, warnings=warns)
    if kind == 'download':
        lk = ds_or_404(int(p['link_id']))
        if lk['kind'] != 'link' or lk['meta']['type'] not in links.DATA_TYPES:
            raise ApiError('ลิงก์นี้ดูได้อย่างเดียว ดาวน์โหลดเป็นข้อมูลไม่ได้')
        if p.get('aoi_id'):
            aoimod.get(int(p['aoi_id']))
        return dict(grid=dict(res_label=lk['meta'].get('type_label'), width=0, height=0), aoi=aoimod.get(int(p['aoi_id']))['name'] if p.get('aoi_id') else None,
                    warnings=[] if p.get('aoi_id') or lk['meta']['type'] != 'cog' else ['ดาวน์โหลดทั้งไฟล์ — ถ้าไฟล์ใหญ่ เลือกพื้นที่ศึกษาเพื่อตัดเฉพาะส่วน'])
    if kind == 'zonal':
        z = ds_or_404(int(p['zones_dataset_id']))
        if z['kind'] not in ('vector', 'link') or (z['kind'] == 'link' and z['meta']['type'] not in links.DATA_TYPES - {'cog'}):
            raise ApiError('ชั้นพื้นที่ต้องเป็น vector โพลิกอน หรือลิงก์ขอบเขต (Feature layer / WFS / GeoJSON)')
        ids = {int(p[a][k]) for a in ('x', 'y') for k in ('dataset_id', 'weight_dataset_id') if p[a].get(k)}
        dss = [_confirmed_raster(i) for i in ids]
        for a in ('x', 'y'):
            if p[a].get('stat') == 'share_weight' and not p[a].get('weight_dataset_id'):
                raise ApiError(f'แกน {a.upper()}: สัดส่วนน้ำหนักต้องเลือกชุดน้ำหนัก (เช่น ประชากร)')
        srcs = [engine.Source(d) for d in dss]
        g = engine.make_grid(srcs, Fraction(p['target_res']))
        for s in srcs:
            engine.OnGrid(s, g)
            s.close()
        return dict(grid=g.describe(), aoi=aoimod.get(int(p['aoi_id']))['name'] if p.get('aoi_id') else None,
                    warnings=([f'ชั้นพื้นที่มี {z["meta"]["features"]:,} โพลิกอน'] if (z['meta'].get('features') or 0) > 20000 else [])
                    + (['ชั้นพื้นที่เป็นลิงก์ — ดึงโพลิกอนจากบริการตอนรัน (ต้องต่อเน็ต)'] if z['kind'] == 'link' else []))
    if kind == 'change':
        da, dbb = _confirmed_raster(p['a_id']), _confirmed_raster(p['b_id'])
        if p.get('mode') == 'transition' and (da['value_type'] != 'class' or dbb['value_type'] != 'class'):
            raise ApiError('การเปลี่ยนชั้นใช้กับข้อมูลประเภท "ชั้น" ทั้งสองชุด')
        sa, sb = engine.Source(da), engine.Source(dbb)
        g = engine.make_grid([sa, sb], Fraction(p['target_res']))
        oa, ob = engine.OnGrid(sa, g), engine.OnGrid(sb, g)
        aoi_name = _apply_aoi(p, g, [oa, ob])
        engine.check_tiles(g, [oa, ob])
        sa.close(), sb.close()
        H, W = g.out_shape
        return dict(grid=g.describe(), raw_bytes=H * W * 4, aoi=aoi_name, warnings=[])
    if kind == 'sensitivity':
        b = p['base']
        n = len(p.get('x_breaks_sets') or [1]) * len(p.get('y_breaks_sets') or [1]) * len(p.get('resolutions') or [1])
        if n > 40:
            raise ApiError(f'{n} ชุดค่า มากเกิน (สูงสุด 40)')
        est = validate_job('bivariate', b)
        est['warnings'] = est['warnings'] + [f'รัน {n} ชุดค่า (สถิติอย่างเดียว ไม่เขียนแผนที่) — ใช้เวลาประมาณ {n} เท่าของงานเดียว']
        return est
    raise ApiError('ชนิดงานไม่ถูกต้อง')

@app.route('/api/estimate', methods=['POST'])
def estimate():
    b = request.get_json(force=True)
    try:
        return jsonify(ok=True, **validate_job(b['kind'], b['params']))
    except (engine.EngineError, ApiError) as e:
        return jsonify(ok=False, error=str(e))


@app.route('/api/satellite/catalog')
def sat_catalog():
    from . import ops_sat
    return jsonify(collections=ops_sat.COLLECTIONS, zooms=ops_sat.zoom_options(), source='Microsoft Planetary Computer', home='https://planetarycomputer.microsoft.com/catalog')


@app.route('/api/satellite/search', methods=['POST'])
def sat_search():
    from . import ops_sat
    p = request.get_json(force=True)
    try:
        _, g = ops_sat._aoi(p)
        return jsonify(ops_sat.search(p, list(g.bounds), limit=500))
    except engine.EngineError as e:
        raise ApiError(str(e))


@app.route('/api/jobs', methods=['POST'])
def create_job():
    b = request.get_json(force=True)
    kind, p = b['kind'], b['params']
    try:
        est = validate_job(kind, p)
    except engine.EngineError as e:
        raise ApiError(str(e))
    res = est['grid']['res_label'].split(' (')[0]
    aoi_txt = f' · {est["aoi"]}' if est.get('aoi') else ''
    if kind == 'reproject':
        from . import ops_proj
        title = f'แปลงเป็น {ops_proj.CRS_TH.get(p.get("crs") or ops_proj.TARGET)}: {db.get("datasets", int(p["dataset_id"]))["name"]} → {res}{aoi_txt}'
    elif kind == 'resample':
        title = f'ปรับความละเอียด: {db.get("datasets", int(p["dataset_id"]))["name"]} → {res}{aoi_txt}'
    elif kind == 'rasterize':
        title = p.get('name') or f'แปลงเป็นราสเตอร์: {db.get("datasets", int(p["dataset_id"]))["name"]} → {res}{aoi_txt}'
    elif kind == 'vgrid':
        title = p.get('name') or f'กริดเวกเตอร์ {res}{aoi_txt}'
    elif kind == 'download':
        title = f'ดาวน์โหลด: {db.get("datasets", int(p["link_id"]))["name"]}{aoi_txt}'
    elif kind == 'zonal':
        title = (p.get('name') or 'ไบแวเรียตรายพื้นที่') + f' · {res}{aoi_txt}'
    elif kind == 'change':
        title = p.get('name') or f'เปลี่ยนแปลง ({p.get("mode")}) · {res}{aoi_txt}'
    elif kind == 'sensitivity':
        title = (p.get('name') or 'เทียบหลายค่าที่ตั้ง') + aoi_txt
    elif kind == 'hex':
        title = p.get('name') or f'แปลงเป็นหกเหลี่ยม {res}: ' + ', '.join(db.get('datasets', int(i))['name'] for i in p['dataset_ids'][:3]) + aoi_txt
    elif kind == 'hexbiv':
        title = (p.get('name') or 'ไบแวเรียตหกเหลี่ยม') + f' · {res}{aoi_txt}'
    elif kind == 'satellite':
        from . import ops_sat
        c = ops_sat.BY_ID[p['collection']]
        title = p.get('name') or f'ภาพดาวเทียม: {c["name"].split(" (")[0]} {", ".join(p.get("bands") or c["default"])} · {p.get("date_from") or ""}–{p.get("date_to") or ""} · {res}{aoi_txt}'
    elif kind == 'calc':
        title = p.get('name') or f'คำนวณ: {p.get("expr", "")[:50]} · {res}{aoi_txt}'
    elif kind == 'trend':
        title = p.get('name') or f'อนุกรมเวลา ({p.get("stat")}) {len(p.get("items") or [])} ปี · {res}{aoi_txt}'
    elif kind == 'mosaic':
        title = p.get('name') or f'รวมราสเตอร์ {len(p.get("dataset_ids") or [])} ไฟล์'
    elif kind == 'vmerge':
        title = p.get('name') or f'รวมเวกเตอร์ {len(p.get("dataset_ids") or [])} ชั้น'
    else:
        title = (p.get('name') or 'ไบแวเรียต') + f' · {res}{aoi_txt}'
    jid = jobs.submit(kind, p, title)
    return jsonify(job=jid, estimate=est)


@app.route('/api/jobs/<int:jid>/rerun', methods=['POST'])
def rerun_job(jid):
    """รันซ้ำด้วยค่าที่ตั้งเดิม (เช่น ต้นทางเปลี่ยน) → โฟลเดอร์ผลใหม่"""
    j = db.get('jobs', jid)
    if j is None:
        raise ApiError('ไม่พบงาน')
    if j['kind'] != 'prepare':
        try:
            validate_job(j['kind'], j['params'])
        except engine.EngineError as e:
            raise ApiError(str(e))
    return jsonify(job=jobs.submit(j['kind'], j['params'], j['title'] + ' (รันซ้ำ)'))


@app.route('/api/jobs')
def list_jobs():
    return jsonify(db.query('SELECT id,kind,title,status,progress,message,out_dir,created_at,started_at,finished_at,error,result,eta_s,elapsed_s '
                            'FROM jobs ORDER BY id DESC LIMIT 100'))


@app.route('/api/jobs/<int:jid>')
def get_job(jid):
    j = db.get('jobs', jid)
    if j is None:
        raise ApiError('ไม่พบงาน')
    j['log'] = jobs.log_tail(j, 200)
    return jsonify(j)


@app.route('/api/jobs/<int:jid>/cancel', methods=['POST'])
def cancel_job(jid):
    return jsonify(ok=jobs.cancel(jid, force=bool((request.get_json(silent=True) or {}).get('force'))))


# ---------------- พื้นที่ศึกษา ----------------
@app.route('/api/aoi')
def aoi_list():
    rows = db.query('SELECT * FROM aoi WHERE trashed_at IS NULL ORDER BY id DESC')
    for a in rows:                                        # พื้นที่ศึกษาพื้นฐาน (เช่น ประเทศไทย) ขึ้นก่อน
        a['builtin'] = isinstance(a.get('source'), dict) and a['source'].get('type') == 'base'
    rows.sort(key=lambda a: not a['builtin'])
    return jsonify(rows)


@app.route('/api/aoi', methods=['POST'])
def aoi_create():
    b = request.get_json(force=True)
    name = (b.get('name') or '').strip()
    if not name:
        raise ApiError('ตั้งชื่อพื้นที่ศึกษาก่อน')
    if b.get('coords'):                                   # พิมพ์พิกัดเอง → แปลง/ตรวจที่เซิร์ฟเวอร์อีกรอบ (ไม่เชื่อ geojson จากหน้าเว็บ)
        c = aoimod.parse_coords(b['coords'], b.get('order', 'auto'), b.get('crs', 'auto'))
        aid = aoimod.create_from_geojson(name, c['geojson'], dict(type='coords', crs=c['crs'], points=c['points'], parts=c['parts']))
    elif b.get('geojson'):
        aid = aoimod.create_from_geojson(name, b['geojson'])
    elif b.get('link_id'):
        try:
            aid = aoimod.create_from_link(name, ds_or_404(int(b['link_id'])), b.get('field'), b.get('values') or [])
        except links.LinkError as e:
            raise ApiError(str(e))
    else:
        aid = aoimod.create_from_dataset(name, ds_or_404(int(b['dataset_id'])), b.get('field'), b.get('values') or [])
    return jsonify(id=aid, aoi=db.get('aoi', aid))


@app.route('/api/aoi/parse-coords', methods=['POST'])
def aoi_parse_coords():
    """พรีวิวพิกัดที่พิมพ์ (ยังไม่บันทึก): รูปใน EPSG:4326 + พื้นที่ + สิ่งที่ตรวจพบ + คำเตือน"""
    b = request.get_json(force=True)
    try:
        return jsonify(aoimod.parse_coords(b.get('text', ''), b.get('order', 'auto'), b.get('crs', 'auto')))
    except aoimod.AoiError as e:
        raise ApiError(str(e))


@app.route('/api/aoi/<int:aid>', methods=['DELETE'])
def aoi_delete(aid):
    aoimod.get(aid)
    db.update('aoi', aid, trashed_at=db.now())                # ย้ายเข้าถังขยะ · ลบไฟล์ตอนลบถาวร
    return jsonify(ok=True, trash=trash.count())


@app.route('/api/aoi/<int:aid>.geojson')
def aoi_geojson(aid):
    return Response(aoimod.geojson(aid), mimetype='application/geo+json')


@app.route('/api/datasets/<int:did>/field-values')
def field_values(did):
    d = ds_or_404(did)
    vals, total = aoimod.field_values(d, request.args['field'], request.args.get('q', ''), int(request.args.get('limit', 300)))
    return jsonify(values=vals, total=total, text_lost=aoimod.text_lost(vals))


@app.route('/api/datasets/<int:did>/relink', methods=['POST'])
def relink(did):
    d = ds_or_404(did)
    w = catalog.relink(d, request.get_json(force=True)['path'])
    tiles.drop_pool(d.get('read_path') or d['path'])
    db.update('datasets', did, preview_key=None)
    prepare_if_needed(did)
    return jsonify(ok=True, warnings=w)


# ---------------- พาเลท ----------------
@app.route('/api/palettes')
def palettes_list():
    custom = db.query('SELECT * FROM palettes ORDER BY id')
    return jsonify(builtin=palettes.PALETTES, custom=custom)


@app.route('/api/palettes', methods=['POST'])
def palette_save():
    b = request.get_json(force=True)
    nx, ny, cols = int(b['nx']), int(b['ny']), b['colors']
    if len(cols) != nx * ny or not all(isinstance(c, str) and len(c.lstrip('#')) == 6 for c in cols):
        raise ApiError(f'ต้องมีสี {nx * ny} สี รูปแบบ #rrggbb')
    name = (b.get('name') or '').strip() or f'พาเลท {nx}×{ny}'
    pid = db.insert('palettes', name=name, nx=nx, ny=ny, colors=['#' + c.lstrip('#').lower() for c in cols], created_at=db.now())
    return jsonify(id=pid)


@app.route('/api/palettes/<int:pid>', methods=['DELETE'])
def palette_delete(pid):
    db.delete('palettes', pid)
    return jsonify(ok=True)


@app.route('/api/open-folder', methods=['POST'])
def open_folder():
    p = Path(request.get_json(force=True)['path'])
    if p.is_file():
        p = p.parent
    if not p.is_dir():
        raise ApiError(f'ไม่พบโฟลเดอร์ {p}')
    os.startfile(str(p))
    return jsonify(ok=True)


@app.errorhandler(Exception)
def on_error(e):
    if isinstance(e, HTTPException):
        return e
    if isinstance(e, (ApiError, engine.EngineError, catalog.CatalogError, aoimod.AoiError)):
        return jsonify(error=str(e)), 400
    import traceback
    traceback.print_exc()
    return jsonify(error=f'เกิดข้อผิดพลาดที่เซิร์ฟเวอร์: {e}'), 500


def main():
    ensure_workspace()
    if '--wait-port' in sys.argv:                         # มาจากปุ่มรีสตาร์ต: รอตัวเก่าปล่อยพอร์ตก่อน
        import socket
        import time
        for _ in range(50):
            with socket.socket() as s:
                if s.connect_ex(('127.0.0.1', PORT)) != 0:
                    break
            time.sleep(0.2)
    import socket
    with socket.socket() as s:                          # มีตัวประมวลผลเปิดอยู่แล้ว (เช่น ดับเบิลคลิกซ้ำ) → ไม่เปิดตัวที่สอง แค่เปิดหน้าเว็บ
        busy = s.connect_ex(('127.0.0.1', PORT)) == 0
    if busy:
        tok = engine_token()
        web = (engine_cfg().get('web_url') or '').strip()
        url = f'{web}#pair={tok}&engine=http://127.0.0.1:{PORT}' if web else f'http://127.0.0.1:{PORT}/ui/'
        print(f'พอร์ต {PORT} มีโปรแกรมใช้อยู่แล้ว (ตัวประมวลผลเปิดอยู่?) — เปิดหน้าเว็บแทน')
        if '--no-browser' not in sys.argv:
            webbrowser.open(url)
        sys.exit(0)
    db.init()
    try:
        n, freed = ops.migrate_previews()
        if n:
            print(f'ลบสำเนาพรีวิวเต็มขนาดแบบเก่า {n} ไฟล์ · คืนพื้นที่ {freed / 1e9:.2f} GB (สร้างแบบย่อใหม่เมื่อเปิดชุดนั้น)')
    except Exception as e:
        print('[migrate previews]', e)
    jobs.start_dispatcher()
    try:
        from . import recipes
        n = recipes.recover()
        if n:
            print(f'สูตรงานที่ค้างจากรอบก่อน {n} รายการ → ตั้งเป็น "ถูกขัดจังหวะ"')
    except Exception as e:
        print('[recipes recover]', e)
    basedata.seed_background()                            # ขอบเขตการปกครอง GISTDA (เบื้องหลัง · ออฟไลน์ = ลองใหม่ครั้งหน้า)
    print(f'{APP_NAME} {APP_VERSION}')
    print(f'workspace: {WORKSPACE}')
    tok = engine_token()
    web = (engine_cfg().get('web_url') or '').strip()
    url = f'{web}#pair={tok}&engine=http://127.0.0.1:{PORT}' if web else f'http://127.0.0.1:{PORT}/ui/'
    print(f'ตัวประมวลผลพร้อมที่ http://127.0.0.1:{PORT}')
    print(f'หน้าเว็บ (จับคู่อัตโนมัติ): {url}')
    print(f'หน้าเว็บสำรองในเครื่อง: http://127.0.0.1:{PORT}/ui/')
    if '--no-browser' not in sys.argv and '--wait-port' not in sys.argv:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    app.run(host='127.0.0.1', port=PORT, threaded=True, debug=False)


if __name__ == '__main__':
    main()
