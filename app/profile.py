# -*- coding: utf-8 -*-
"""ประวัติชุดข้อมูล (profile) — "ประวัติส่วนตัว" ของทุกชุดในคลัง อ่านได้ทั้งคนและผู้ช่วย AI

- สร้างอัตโนมัติจากข้อมูลที่แอปรู้อยู่แล้ว (ไม่ต้องมี AI): ไฟล์อะไร รูปแบบสำคัญ (CRS, ความละเอียด, ประเภทค่า, nodata, สถิติ / ฟิลด์),
  มาจากไหน (ไฟล์ในเครื่อง / ดาวน์โหลดจาก URL / ชุดใน Data hub + สัญญาอนุญาต / วัตถุประสงค์),
  ถ้าเป็นผลลัพธ์: ชุดต้นทาง (พ่อแม่) + งาน + ค่าที่ตั้งแบบอ่านง่าย + ใครสั่ง (ผู้ใช้ / ผู้ช่วย AI) · ชุดที่ทำต่อจากชุดนี้ (ลูก)
- โน้ต: ผู้ใช้เขียนเอง (meta.note_user) · ผู้ช่วย AI เขียน (meta.note_ai — ติดป้ายว่าเขียนโดย AI ผู้ใช้แก้/ลบได้)
- ส่งออกเป็น Markdown ได้ (`as_markdown`)
"""
import json
from pathlib import Path

from . import db

KIND_TH = {'bivariate': 'ไบแวเรียต (กริด)', 'hexbiv': 'ไบแวเรียตหกเหลี่ยม', 'resample': 'ปรับความละเอียด / ตัดพื้นที่', 'rasterize': 'แปลงเวกเตอร์เป็นราสเตอร์',
           'hex': 'แปลงเป็นหกเหลี่ยม', 'vgrid': 'กริดเวกเตอร์', 'change': 'เปรียบเทียบ 2 ช่วงเวลา', 'download': 'ดาวน์โหลดจากลิงก์', 'zonal': 'ไบแวเรียตรายพื้นที่'}
VT_TH = {'count': 'จำนวนนับ (รวมแล้วผลรวมไม่หาย)', 'density': 'ค่าต่อเนื่อง (เฉลี่ยถ่วงพื้นที่)', 'class': 'ชั้น/รหัส (majority)'}
METRIC_TH = {'density': 'ความหนาแน่น (ต่อ ตร.กม.)', 'per_pixel': 'ค่าต่อพิกเซล', 'value': 'ค่าตามไฟล์'}
METHOD_TH = {'quantile': 'ควอนไทล์', 'equal': 'ช่วงเท่ากัน', 'breaks': 'กำหนดเกณฑ์เอง', 'degurba': 'DEGURBA'}
MODE_TH = {'presence': 'มี / ไม่มี (1 / 0)', 'attribute': 'ค่าจากฟิลด์', 'majority': 'ค่าจากฟิลด์ที่กินพื้นที่มากสุด', 'fraction': 'สัดส่วนพื้นที่ (0–1)',
           'diff': 'ผลต่าง', 'pct': 'ร้อยละที่เปลี่ยน', 'transition': 'การเปลี่ยนชั้น'}


def _lineage(d):
    if not d.get('job_id'):
        return None
    j = db.get('jobs', d['job_id'])
    p = Path(j['out_dir']) / 'lineage.json' if j and j.get('out_dir') else None
    try:
        return json.loads(p.read_text(encoding='utf-8')) if p and p.exists() else None
    except ValueError:
        return None


def _source_json(d):
    """งานดาวน์โหลดเขียน source.json (URL, เวลา, กรอบที่ตัด) ไว้ข้างไฟล์"""
    try:
        p = Path(d['path']).parent / 'source.json'
        return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None
    except (OSError, ValueError, TypeError):
        return None


def _name(i):
    d = db.get('datasets', int(i)) if i else None
    return dict(id=int(i), name=d['name'] if d else '(ถูกลบแล้ว)', exists=bool(d and not d.get('trashed_at')),
                value_type=d.get('value_type') if d else None) if i else None


def _aoi(i):
    a = db.get('aoi', int(i)) if i else None
    return a['name'] if a else (f'#{i}' if i else None)


def settings(kind, p):
    """ค่าที่ตั้งของงานเป็นรายการ (หัวข้อ, ค่า) ภาษาคน"""
    rows = []                                                # วัตถุประสงค์แสดงในหมวด "มาจากไหน" แล้ว ไม่ซ้ำที่นี่
    for ax in ('x', 'y'):
        c = p.get(ax)
        if not isinstance(c, dict):
            continue
        n = _name(c.get('dataset_id')) or {}
        vt = n.get('value_type')
        metric = METRIC_TH.get(c.get('metric') if vt == 'count' else 'value', c.get('metric'))
        brk = c.get('resolved_breaks') or c.get('breaks')
        rows.append((f'แกน {ax.upper()}', f"#{n.get('id')} {n.get('name')}" + (f" — ชื่อแกน {c['label']}" if c.get('label') else '')
                     + f" · ค่าที่ใช้: {metric} · {c.get('n', 3)} คลาส · {METHOD_TH.get(c.get('method'), c.get('method'))}"
                     + (f" · เกณฑ์ {', '.join(f'{b:g}' if isinstance(b, (int, float)) else str(b) for b in brk)}" if brk else '')
                     + (' · จัดชั้นก่อนแล้ว majority' if c.get('order') == 'classify_first' else '') + (f" · คอลัมน์ {c['field']}" if c.get('field') else '')))
    for k, lab in (('dataset_id', 'ชุดข้อมูล'), ('ref_dataset_id', 'กริดอ้างอิง'), ('extent_dataset_id', 'ขอบเขตเท่ากับ'), ('a_id', 'ก่อน'), ('b_id', 'หลัง')):
        if p.get(k):
            n = _name(p[k])
            rows.append((lab, f"#{n['id']} {n['name']}"))
    if kind == 'calc':
        rows.append(('สูตร', str(p.get('expr'))))
        for k, v in (p.get('vars') or {}).items():
            n = _name(v.get('dataset_id')) or {}
            rows.append((f'ตัวแปร {k}', f"#{n.get('id')} {n.get('name')} · แบนด์ {v.get('band') or 1}"))
    if kind == 'trend':
        from .ops_tools import STATS
        rows.append(('สถิติ', STATS.get(p.get('stat'), p.get('stat')) + (f" · เกณฑ์ {p['threshold']}" if p.get('threshold') is not None else '')))
        rows.append(('ปี', ', '.join(f"{it.get('year')}: #{(_name(it.get('dataset_id')) or {}).get('id')} {(_name(it.get('dataset_id')) or {}).get('name')}" for it in p.get('items') or [])))
    if kind == 'mosaic':
        rows.append(('ส่วนที่ซ้อนกัน', {'first': 'ใช้ไฟล์แรกที่มีค่า', 'last': 'ใช้ไฟล์หลังสุด', 'min': 'ค่าต่ำสุด', 'max': 'ค่าสูงสุด'}.get(p.get('method', 'first'))))
    if kind == 'vmerge' and p.get('dissolve'):
        rows.append(('รวมรูป', f"ตามฟิลด์ {p['dissolve_field']}" if p.get('dissolve_field') else 'รวมเป็นรูปเดียว'))
    if p.get('dataset_ids'):
        rows.append(('ชุดข้อมูล', ', '.join(f"#{n['id']} {n['name']}" for n in map(_name, p['dataset_ids']))))
    if p.get('mode'):
        rows.append(('วิธี', MODE_TH.get(p['mode'], p['mode'])))
    if p.get('field') and not p.get('x'):
        rows.append(('ฟิลด์', p['field']))
    if p.get('target_res'):
        rows.append(('ความละเอียดเป้าหมาย', str(p['target_res']) + ' (ฟิลิปดาถ้าข้อมูลเป็นองศา / เมตรถ้าเป็นพิกัดฉาก)'))
    if p.get('size_km'):
        rows.append(('ขนาดหกเหลี่ยม', f"{p['size_km']} กม."))
    if p.get('aoi_id'):
        rows.append(('พื้นที่ศึกษา', _aoi(p['aoi_id']) + (f" · กติกา{'ศูนย์กลางพิกเซล' if p.get('aoi_rule', 'center') == 'center' else 'แตะ'}" if kind != 'download' else ' (ตัดตามกรอบ)')))
    if p.get('extent_aoi_id'):
        rows.append(('ขอบเขตผลลัพธ์', _aoi(p['extent_aoi_id'])))
    if p.get('palette'):
        rows.append(('พาเลท', str(p['palette']).replace('b:', '')))
    if p.get('highlight'):
        rows.append(('เขตเน้น', 'รหัส ' + ', '.join(map(str, p['highlight']))))
    rb = p.get('requested_by') or {}
    if rb.get('by') == 'ai_assistant':
        rows.append(('สั่งโดย', f"ผู้ช่วย AI ({rb.get('model')}) · ผู้ใช้กดยืนยัน {rb.get('confirmed_at', '')}" + (' · ผู้ใช้แก้ค่าในการ์ด' if rb.get('edited_by_user') else '')))
    return rows


def build(did):
    d = db.get('datasets', int(did))
    if d is None:
        return None
    m = d.get('meta') or {}
    st = d.get('stats') or {}
    out = dict(id=d['id'], name=d['name'], kind=d['kind'], role=d.get('role'), added_at=d.get('added_at'), status=d.get('status'))
    # ---------- ไฟล์อะไร / รูปแบบสำคัญ ----------
    facts = [('ชนิด', {'raster': 'ราสเตอร์', 'vector': 'เวกเตอร์', 'link': 'ลิงก์บริการแผนที่'}.get(d['kind'], d['kind']) + f" · {(d.get('format') or '').upper()}")]
    if d['kind'] == 'raster':
        facts += [('ระบบพิกัด', m.get('crs_name')), ('ความละเอียด', m.get('res_label')), ('ขนาด', f"{m.get('width', 0):,} × {m.get('height', 0):,} พิกเซล · {m.get('count', 1)} แบนด์ · {', '.join(m.get('dtypes') or [])}"),
                  ('nodata', str(m.get('nodata')) + (f" (นับเป็น {d['nodata_as']})" if d.get('nodata_as') is not None else '')),
                  ('ประเภทค่า', VT_TH.get(d.get('value_type'), d.get('value_type') or '—') + ('' if d.get('value_type_confirmed') else ' · ยังไม่ยืนยัน'))]
        sc = m.get('scales')
        if sc and any(s not in (None, 1, 1.0) for s in sc):
            facts.append(('scale / offset', f"{sc} / {m.get('offsets')} (ค่าที่แสดงคูณแล้ว)"))
        if st.get('valid') is not None:
            facts.append(('สถิติ', f"min {st.get('min'):.4g} · max {st.get('max'):.4g} · เฉลี่ย {st.get('mean'):.4g} · ผลรวม {st.get('sum'):,.6g}"))
    elif d['kind'] == 'vector':
        facts += [('ระบบพิกัด', m.get('crs_name')), ('เรขาคณิต', f"{m.get('geometry_type')} · {m.get('features', 0):,} feature"),
                  ('ฟิลด์', ', '.join(f['name'] for f in (m.get('fields') or [])[:30])), ('การเข้ารหัสข้อความ', m.get('encoding') or m.get('encoding_auto') or 'อัตโนมัติ')]
        if m.get('hex'):
            facts.append(('หกเหลี่ยม', f"{m['hex'].get('d_km')} กม. · {m['hex'].get('crs_label')}"))
    else:
        facts += [('ชนิดลิงก์', m.get('type_label')), ('URL', d.get('path'))]
    if m.get('bounds_wgs84'):
        facts.append(('ขอบเขต (WGS84)', ', '.join(f'{x:.4f}' for x in m['bounds_wgs84'])))
    if m.get('file_bytes'):
        facts.append(('ขนาดไฟล์', f"{m['file_bytes'] / 1e6:,.1f} MB"))
    out['facts'] = [(k, v) for k, v in facts if v]
    # ---------- มาจากไหน ----------
    lin = _lineage(d)
    origin = []
    src = _source_json(d) if d.get('job_id') else None
    if lin and lin.get('operation') != 'download':
        out['made_by'] = dict(operation=lin.get('operation'), operation_th=KIND_TH.get(lin.get('operation'), lin.get('operation')),
                              created_at=lin.get('created_at'), app_version=lin.get('app_version'),
                              parents=[dict(_name(i['dataset_id']) or {}, value_type_used=i.get('value_type')) for i in lin.get('inputs') or [] if i.get('dataset_id')],
                              settings=settings(lin.get('operation'), lin.get('params') or {}),
                              summary={k: v for k, v in (lin.get('stats_summary') or {}).items() if isinstance(v, (int, float, str)) and k != 'grid'},
                              warnings=lin.get('warnings') or [])
    elif src or (lin and lin.get('operation') == 'download'):
        origin.append(('ดาวน์โหลดจาก', (src or {}).get('url') or (lin or {}).get('params', {}).get('url')))
        if src and src.get('downloaded_at'):
            origin.append(('เมื่อ', src['downloaded_at']))
        if src and src.get('aoi_bbox'):
            origin.append(('ตัดตามกรอบ', ', '.join(f'{x:.3f}' for x in src['aoi_bbox'])))
    else:
        origin.append(('ไฟล์ต้นฉบับ', d.get('source_path') or d.get('path')))
        if d.get('copied'):
            origin.append(('สำเนาในคลัง', d.get('path')))
    if m.get('hub_key'):
        try:
            from . import ai_tools
            hub = ai_tools.t_get_hub_item(m['hub_key'])
            origin += [('ชุดใน Data hub', f"{hub['title']} ({hub.get('platform')})"), ('ผู้ผลิต', hub.get('provider')), ('สัญญาอนุญาต', hub.get('license')),
                       ('หน้าต้นทาง', hub.get('url'))]
        except Exception:
            origin.append(('ชุดใน Data hub', m['hub_key']))
    purpose = m.get('purpose') or ((lin or {}).get('params') or {}).get('purpose')
    if purpose:
        origin.append(('วัตถุประสงค์', purpose))
    out['origin'] = [(k, v) for k, v in origin if v]
    # ---------- ชุดที่ทำต่อจากชุดนี้ (ลูก) ----------
    kids = []
    for r in db.query('SELECT id, name, job_id FROM datasets WHERE job_id IS NOT NULL AND trashed_at IS NULL AND id != ?', (d['id'],)):
        li = _lineage(r)
        if li and any(i.get('dataset_id') == d['id'] for i in li.get('inputs') or []):
            kids.append(dict(id=r['id'], name=r['name'], operation_th=KIND_TH.get(li.get('operation'), li.get('operation'))))
    out['children'] = kids
    out['notes'] = dict(user=m.get('note_user'), ai=m.get('note_ai'))
    out['warnings'] = m.get('warnings') or []
    return out


def as_markdown(p):
    L = [f"# {p['name']}", '', f"ชุดข้อมูล #{p['id']} · เพิ่มเมื่อ {p.get('added_at') or '—'}", '']
    if p['notes'].get('user'):
        L += ['## โน้ต', p['notes']['user'], '']
    if p['notes'].get('ai'):
        a = p['notes']['ai']
        L += ['## โน้ตจากผู้ช่วย AI', a.get('text', ''), f"_({a.get('model')} · {a.get('at')})_", '']
    L += ['## ไฟล์อะไร / รูปแบบสำคัญ'] + [f'- **{k}**: {v}' for k, v in p['facts']] + ['']
    if p.get('origin'):
        L += ['## มาจากไหน'] + [f'- **{k}**: {v}' for k, v in p['origin']] + ['']
    mb = p.get('made_by')
    if mb:
        L += [f"## สร้างโดยงาน: {mb['operation_th']}", f"- เมื่อ {mb.get('created_at')} · แอป v{mb.get('app_version')}", '', '### ชุดต้นทาง']
        L += [f"- #{x['id']} {x['name']}" + ('' if x['exists'] else ' (ถูกลบแล้ว)') + (f" · ประเภทค่าที่ใช้ {x['value_type_used']}" if x.get('value_type_used') else '') for x in mb['parents']]
        L += ['', '### ค่าที่ตั้ง'] + [f'- **{k}**: {v}' for k, v in mb['settings']]
        if mb.get('summary'):
            L += ['', '### สรุปผล'] + [f'- {k}: {v}' for k, v in mb['summary'].items()]
        L.append('')
    if p.get('children'):
        L += ['## ชุดที่ทำต่อจากชุดนี้'] + [f"- #{c['id']} {c['name']} ({c['operation_th']})" for c in p['children']] + ['']
    return '\n'.join(L)
