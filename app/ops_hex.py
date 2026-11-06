# -*- coding: utf-8 -*-
"""งานหกเหลี่ยม: hex (แปลง raster/vector → hex) · hexbiv (ไบแวเรียตบน hex)"""
import math
from pathlib import Path

import numpy as np

from . import db, engine, export, hexgrid
from .engine import EngineError
from .ops import register_output


def _inputs(ids):
    dss = [db.get('datasets', int(i)) for i in ids]
    for d in dss:
        if d is None:
            raise EngineError('ไม่พบชุดข้อมูล')
        if d['kind'] == 'raster' and not d.get('value_type_confirmed'):
            raise EngineError(f'ยืนยันประเภทค่าของ "{d["name"]}" ก่อน')
        if d['kind'] not in ('raster', 'vector'):
            raise EngineError(f'"{d["name"]}" ใช้ทำ hex ไม่ได้ (รองรับ raster / vector ในเครื่อง)')
    return dss


def _hexes_for(p, dss, hexref=None):
    """กริดหกเหลี่ยมของงาน: ใช้กริดของชุด hex อ้างอิง (ต่อกันได้) หรือสร้างใหม่จากขนาด + พื้นที่"""
    ext = hexgrid.extent_4326([d for d in dss if d['kind'] == 'raster' or d['meta'].get('bounds_wgs84')], p.get('aoi_id'))
    if hexref:
        return hexgrid.make_gdf(ext, hexref['d_km'], hexref['crs'])
    size = float(p.get('size_km') or 0)
    if size <= 0:
        raise EngineError('ใส่ขนาดหกเหลี่ยม (กม.)')
    return hexgrid.make_gdf(ext, size)


def estimate(kind, p):
    """ประเมินก่อนรัน: จำนวนช่อง · พื้นที่ช่อง · พิกัดฉาย · คำเตือน"""
    import shapely
    ids = p.get('dataset_ids') or [p[a]['dataset_id'] for a in ('x', 'y') if p.get(a, {}).get('dataset_id')]
    dss = _inputs(ids)
    hexref = next((d['meta']['hex'] for d in dss if (d['meta'] or {}).get('hex')), None)
    rasters = [d for d in dss if d['kind'] == 'raster']
    ext = hexgrid.extent_4326(rasters or dss, p.get('aoi_id'))
    d_km = hexref['d_km'] if hexref else float(p.get('size_km') or 0)
    if d_km <= 0:
        raise EngineError('ใส่ขนาดหกเหลี่ยม (กม.)')
    crs, label = (hexref['crs'], hexref.get('crs_label')) if hexref else hexgrid.pick_crs(ext.bounds)
    n = int(hexgrid.geod_area_km2(ext) / hexgrid.hex_area_km2(d_km)) + 1        # พื้นที่บนทรงรี (ไม่ขึ้นกับพิกัดฉาย)
    warns = []
    if n > hexgrid.HEX_MAX:
        raise EngineError(f'ประมาณ {n:,} ช่อง เกินขีด {hexgrid.HEX_MAX:,} — เพิ่มขนาดช่อง หรือเลือกพื้นที่ศึกษา')
    for d in rasters:
        px = (d['meta'].get('pixel_area_km2') or 0)
        if not px and d['meta'].get('res_exact'):
            res = float(Fraction_(d['meta']['res_exact']))
            res = res / 3600 if d['meta'].get('geographic') else res          # res_exact ของข้อมูลองศาเป็นฟิลิปดา
            px = (res * 111.32) ** 2 * math.cos(math.radians((ext.bounds[1] + ext.bounds[3]) / 2)) if d['meta'].get('geographic') else res * res / 1e6
        if px and hexgrid.hex_area_km2(d_km) < px * 4:
            warns.append(f'"{d["name"]}": ช่องหกเหลี่ยมเล็กกว่า 4 พิกเซลของข้อมูล — หลายช่องจะว่าง ควรใช้ช่องใหญ่ขึ้น')
    if hexref:
        warns.append(f'ใช้กริดเดียวกับชุด hex ที่เลือก: {d_km:g} กม. · {label}')
    if not p.get('aoi_id'):
        warns.append('ไม่ได้เลือกพื้นที่ศึกษา — ใช้ส่วนที่ทับกันของข้อมูลทั้งหมด')
    return dict(grid=dict(res_label=f'หกเหลี่ยม {d_km:g} กม. ({hexgrid.hex_area_km2(d_km):,.3g} ตร.กม./ช่อง)', width=n, height=1),
                hex=dict(n=n, d_km=d_km, area_km2=hexgrid.hex_area_km2(d_km), crs=label or crs), warnings=warns)


def Fraction_(s):
    from fractions import Fraction
    return Fraction(s)


def _aggregate(hexes, dss, P, log):
    cols, info, warns, used = {}, [], [], {'hex_id', 'q', 'r', 'area_km2', 'geometry'}
    n = len(dss)
    for i, d in enumerate(dss):
        sub = lambda f, msg=None, i=i: P(0.05 + 0.8 * (i + f) / n, msg)
        if d['kind'] == 'raster':
            vals, inf, w = hexgrid.agg_raster(hexes, d, sub, log)
        else:
            vals, inf, w = hexgrid.agg_vector(hexes, d, log)
            sub(1, f'{d["name"]}: เสร็จ')
        base = hexgrid.col_name(d, used)
        inf['columns'] = {}
        for suf, arr in vals.items():
            cn = base + suf
            used.add(cn)
            cols[cn] = arr
            inf['columns'][cn] = {'': 'ค่า', '_km2': 'ต่อ ตร.กม.', '_pct': '%', '_cover': '% พื้นที่ช่องที่มีข้อมูล', '_km': 'กม.', '_n': 'จำนวน'}.get(suf, suf)
        inf['main'] = base + ('' if '' in vals else next(iter(vals)))
        info.append(inf)
        warns += w
        log(f'{d["name"]}: {inf.get("rule")}')
    return cols, info, warns


def _write_hex(job, hexes, cols, name, log):
    out = hexes.copy()
    for k, v in cols.items():
        out[k] = v
    out_dir = Path(job['out_dir'])
    base = export.slug(name, 60)
    outp = out_dir / f'{base}.gpkg'
    out.to_file(outp, layer=base, driver='GPKG')
    return out, outp, base


def _hexmeta(hexes):
    a = hexes.attrs
    return dict(d_km=a['d_km'], d_m=a['d_m'], crs=a['crs'], crs_label=a['crs_label'], sig=a['sig'], area_km2=hexgrid.hex_area_km2(a['d_km']))


def op_hex(job, P, log):
    p = job['params']
    dss = _inputs(p['dataset_ids'])
    P(0.02, 'สร้างกริดหกเหลี่ยม…')
    hexes = _hexes_for(p, dss)
    hm = _hexmeta(hexes)
    log(f'หกเหลี่ยม {len(hexes):,} ช่อง · {hm["d_km"]:g} กม. ({hm["area_km2"]:,.4g} ตร.กม./ช่อง) · {hm["crs_label"]}')
    cols, info, warns = _aggregate(hexes, dss, P, log)
    keep = np.zeros(len(hexes), bool)
    for inf in info:
        v = cols[inf['main']]
        keep |= np.isfinite(v) & (v != 0) if p.get('drop_empty', True) else np.isfinite(v)
    if p.get('drop_empty', True) and keep.any():
        hexes = hexes[keep].reset_index(drop=True)
        cols = {k: v[keep] for k, v in cols.items()}
        log(f'ตัดช่องที่ว่าง/เป็น 0 ทุกชุดออก เหลือ {len(hexes):,} ช่อง')
    hexes.attrs.update(d_km=hm['d_km'], d_m=hm['d_m'], crs=hm['crs'], crs_label=hm['crs_label'], sig=hm['sig'])
    name = p.get('name') or 'hex_' + '_'.join(export.slug(d['name'], 20) for d in dss[:3]) + f'_{hm["d_km"]:g}km'
    P(0.9, 'เขียน GeoPackage…')
    out, outp, base = _write_hex(job, hexes, cols, name, log)
    summary = dict(hexes=len(out), hex=hm, layers=info)
    params = dict(p, hex=hm, method='ค่าคิดที่ความละเอียดต้นทางของแต่ละชุด (ไม่แตกพิกเซล) · พิกเซลเป็นของช่องที่ศูนย์กลางพิกเซลตก')
    export.write_lineage(Path(job['out_dir']), 'hex', [export.lineage_input(d) for d in dss], params, [outp], summary, warns)
    did = register_output(outp, p.get('name') or f'{", ".join(d["name"] for d in dss[:2])} · หกเหลี่ยม {hm["d_km"]:g} กม.', None, job['id'], 'derived', kind='vector')
    d = db.get('datasets', did)
    db.update('datasets', did, meta=dict(d['meta'], hex=dict(hm, fields=info)))
    return dict(output=str(outp), dataset_id=did, summary=summary, warnings=warns)


def _axis_values(p, ax, hexes, P, log, cache):
    """ค่าของแกนบนกริด hex: จากชุด hex (เลือกฟิลด์) หรือจาก raster/vector (รวมค่าใหม่)"""
    c = p[ax]
    d = db.get('datasets', int(c['dataset_id']))
    if (d['meta'] or {}).get('hex'):
        g, hx = hexgrid.read_hex(d)
        if hx['sig'] != hexes.attrs['sig']:
            raise EngineError(f'"{d["name"]}" ใช้กริดหกเหลี่ยมคนละแบบ ({hx["d_km"]:g} กม. · {hx.get("crs_label")}) — สร้าง hex ใหม่ให้ขนาด/พิกัดฉายตรงกัน')
        f = c.get('field') or next((i['main'] for i in hx.get('fields', [])), None)
        if f not in g.columns:
            raise EngineError(f'ไม่พบฟิลด์ "{f}" ใน "{d["name"]}"')
        s = dict(zip(g['hex_id'], g[f].astype(float)))
        vals = np.array([s.get(h, np.nan) for h in hexes['hex_id']], float)
        info = next((i for i in hx.get('fields', []) if f in i.get('columns', {})), {})
        return vals, dict(source=info.get('name') or d['name'], field=f, value_type=info.get('value_type'), rule=info.get('rule')), [], d
    key = d['id']
    if key not in cache:
        cache[key] = _aggregate(hexes, [d], lambda f, m=None: P(0.05 + 0.4 * f + (0.4 if ax == 'y' else 0), m), log)
    cols, info, warns = cache[key]
    inf = info[0]
    col = inf['main']
    if d.get('value_type') == 'count' and c.get('metric', 'density') == 'density':
        col = col + '_km2'
    return cols[col], dict(source=d['name'], field=col, value_type=d.get('value_type'), rule=inf.get('rule'),
                           metric='ต่อ ตร.กม.' if col.endswith('_km2') else None), warns, d


def _breaks(v, cfg):
    n = int(cfg.get('n', 3))
    ok = np.isfinite(v)
    if n <= 1:
        return []
    if cfg.get('method') == 'quantile':
        return [float(b) for b in engine.quantile_breaks(v[ok], n)] if ok.any() else []
    if cfg.get('method') == 'equal':
        lo, hi = (float(v[ok].min()), float(v[ok].max())) if ok.any() else (0, 1)
        return [lo + (hi - lo) * i / n for i in range(1, n)]
    br = [float(b) for b in cfg.get('breaks', [])]
    if len(br) != n - 1:
        raise EngineError(f'แกน: ต้องมีเกณฑ์ {n - 1} ค่า')
    return br


def op_hexbiv(job, P, log):
    from .ops3 import qml_categorized
    p = job['params']
    dss = _inputs([p[a]['dataset_id'] for a in ('x', 'y')])
    hexref = next((d['meta']['hex'] for d in dss if (d['meta'] or {}).get('hex')), None)
    P(0.02, 'สร้างกริดหกเหลี่ยม…')
    if hexref and all((d['meta'] or {}).get('hex') for d in dss):
        g, _ = hexgrid.read_hex(dss[0])                   # ทั้งสองแกนเป็น hex → ใช้ช่องของชุดแรก
        hexes = g[['hex_id', 'q', 'r', 'area_km2', 'geometry']].copy()
        hexes.attrs.update(d_km=hexref['d_km'], d_m=hexref['d_m'], crs=hexref['crs'], crs_label=hexref.get('crs_label'), sig=hexref['sig'])
        if p.get('aoi_id'):
            from . import aoi as aoimod
            hexes = hexes[hexes.intersects(aoimod.geom_in(int(p['aoi_id']), hexes.crs))].reset_index(drop=True)
            hexes.attrs.update(d_km=hexref['d_km'], d_m=hexref['d_m'], crs=hexref['crs'], crs_label=hexref.get('crs_label'), sig=hexref['sig'])
    else:
        hexes = _hexes_for(p, dss, hexref)
    hm = _hexmeta(hexes)
    log(f'หกเหลี่ยม {len(hexes):,} ช่อง · {hm["d_km"]:g} กม. · {hm["crs_label"]}')
    cache, vals, ainfo, warns = {}, {}, {}, []
    for a in ('x', 'y'):
        vals[a], ainfo[a], w, _ = _axis_values(p, a, hexes, P, log, cache)
        warns += w
    cfg = {a: dict(p[a]) for a in ('x', 'y')}
    br = {a: _breaks(vals[a], cfg[a]) for a in ('x', 'y')}
    cls = {a: np.where(np.isfinite(vals[a]), np.digitize(np.nan_to_num(vals[a]), br[a]), -1) for a in ('x', 'y')}   # เท่าเกณฑ์ → ชั้นบน
    nx, ny = int(cfg['x'].get('n', 3)), int(cfg['y'].get('n', 3))
    code = np.where((cls['x'] >= 0) & (cls['y'] >= 0), cls['y'] * nx + cls['x'] + 1, 0)
    colors = p['colors']
    hl = [int(c) for c in p.get('highlight', [])]
    out = hexes.copy()
    out['x_value'], out['y_value'] = vals['x'], vals['y']
    out['x_class'], out['y_class'], out['code'] = cls['x'] + 1, cls['y'] + 1, code
    out['color'] = [colors[c - 1] if c > 0 else '#000000' for c in code]
    out['highlight'] = np.isin(code, hl).astype(int)
    # น้ำหนัก (เช่น คนต่อรหัส): แกนที่เป็นจำนวนนับ → ผลรวมต่อช่อง
    wcol = None
    for a in ('x', 'y'):
        if ainfo[a].get('value_type') == 'count':
            d = db.get('datasets', int(p[a]['dataset_id']))
            if (d['meta'] or {}).get('hex'):
                f = ainfo[a]['field'][:-4] if ainfo[a]['field'].endswith('_km2') else ainfo[a]['field']
                g, _ = hexgrid.read_hex(d)
                s = dict(zip(g['hex_id'], g[f].astype(float))) if f in g.columns else {}
                out['weight'] = [s.get(h, np.nan) for h in out['hex_id']]
            else:
                cols = cache[d['id']][0]
                out['weight'] = cols[cache[d['id']][1][0]['main']]
            wcol = ainfo[a]['source']
            break
    out = out[out['code'] > 0].reset_index(drop=True) if p.get('drop_empty', True) else out
    out_dir = Path(job['out_dir'])
    base = export.slug(p.get('name') or f'hexbiv_{hm["d_km"]:g}km', 60)
    outp = out_dir / f'{base}.gpkg'
    P(0.9, 'เขียน GeoPackage…')
    out.to_file(outp, layer=base, driver='GPKG')
    xl = export.class_labels(dict(cfg['x'], breaks=br['x'])) if nx > 1 else ['ทั้งหมด']
    yl = export.class_labels(dict(cfg['y'], breaks=br['y'])) if ny > 1 else ['ทั้งหมด']
    xname, yname = cfg['x'].get('label') or ainfo['x']['source'], cfg['y'].get('label') or ainfo['y']['source']
    ent = [(c, colors[c - 1], f'{c}: {yname} {yl[(c - 1) // nx]} · {xname} {xl[(c - 1) % nx]}') for c in range(1, nx * ny + 1)]
    (out_dir / f'{base}.qml').write_text(qml_categorized('code', ent), encoding='utf-8')
    export.legend_png(out_dir / f'{base}_legend.png', nx, ny, colors, xname, yname, xl, yl, hl)
    out.drop(columns='geometry').to_csv(out_dir / f'{base}_table.csv', index=False, encoding='utf-8-sig')
    cnt = {str(c): int((out['code'] == c).sum()) for c in range(1, nx * ny + 1)}
    summary = dict(hexes=len(out), hex=hm, hexes_by_code=cnt, highlight=hl, hexes_highlight=int(out['highlight'].sum()), x_breaks=br['x'], y_breaks=br['y'],
                   area_by_code={k: v * hm['area_km2'] for k, v in cnt.items()})
    if 'weight' in out.columns:
        w = out['weight'].astype(float).fillna(0).values
        summary.update(weight_name=wcol, weight_total=float(w.sum()), weight_by_code={str(c): float(w[out['code'] == c].sum()) for c in range(1, nx * ny + 1)},
                       weight_highlight=float(w[out['highlight'] == 1].sum()))
    params = dict(p, hex=hm, x=dict(cfg['x'], resolved_breaks=br['x'], **{k: v for k, v in ainfo['x'].items() if k != 'source'}),
                  y=dict(cfg['y'], resolved_breaks=br['y'], **{k: v for k, v in ainfo['y'].items() if k != 'source'}))
    export.write_lineage(out_dir, 'hexbiv', [export.lineage_input(d) for d in dss], params,
                         [outp, out_dir / f'{base}.qml', out_dir / f'{base}_legend.png', out_dir / f'{base}_table.csv'], summary, warns)
    did = register_output(outp, p.get('name') or f'ไบแวเรียตหกเหลี่ยม {xname} × {yname} · {hm["d_km"]:g} กม.', None, job['id'], 'map', kind='vector')
    d = db.get('datasets', did)
    db.update('datasets', did, meta=dict(d['meta'], hex=dict(hm, fields=[])))
    return dict(output=str(outp), dataset_id=did, summary=summary, warnings=warns)


OPS_HEX = dict(hex=op_hex, hexbiv=op_hexbiv)
