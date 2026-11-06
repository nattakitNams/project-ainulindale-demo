# -*- coding: utf-8 -*-
"""งาน V3: download (ลิงก์ → database) · zonal (ไบแวเรียตรายโพลิกอน) · change (เทียบ 2 ช่วงเวลา) · sensitivity (เทียบหลายค่าที่ตั้ง)"""
import copy
import itertools
import json
import math
import time
from datetime import datetime
from fractions import Fraction
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling

from . import db, engine, export, gridmath as gm, links, symbology, vault
from .engine import EngineError, Source
from .ops import OutWriter, op_bivariate, qml_categorized, register_output, setup_aoi


# ======================================================================
# download: ข้อมูลจากลิงก์ → workspace/database (บันทึก URL + วันที่ ไม่บันทึกโทเคน)
# ======================================================================
def _aoi_bbox4326(p):
    if not p.get('aoi_id'):
        return None
    from . import aoi
    return list(aoi.geom_in(int(p['aoi_id']), 'EPSG:4326').bounds)


def op_download(job, P, log):
    import geopandas as gpd
    import requests
    p = job['params']
    lk = db.get('datasets', int(p['link_id']))
    m = lk['meta']
    t = m['type']
    token = vault.get(m.get('secret_id'))
    bbox = _aoi_bbox4326(p)
    out_dir = Path(job['out_dir'])
    name = export.slug(p.get('name') or lk['name'], 60)
    feats, outp, n = None, None, 0
    if t in ('arcgis_feature', 'wfs', 'geojson'):
        feats = links.fetch_features(m, layer=p.get('layer', m.get('layer')), bbox=bbox, where=p.get('where'), progress=P, log=log)
        if not feats:
            raise EngineError('ไม่มี feature ตามเงื่อนไข')
    elif t == 'cog':
        src = '/vsicurl/' + m['url']
        outp = out_dir / f'{name}.tif'
        if bbox:
            from rasterio.warp import transform_bounds
            from rasterio.windows import from_bounds
            with rasterio.open(src) as d:
                bb = transform_bounds('EPSG:4326', d.crs, *bbox) if d.crs else bbox
                win = from_bounds(*bb, d.transform).round_offsets().round_lengths()
                win = win.intersection(rasterio.windows.Window(0, 0, d.width, d.height))
                prof = d.profile.copy()
                prof.update(width=int(win.width), height=int(win.height), transform=d.window_transform(win), driver='GTiff',
                            tiled=True, blockxsize=512, blockysize=512, compress='deflate', BIGTIFF='IF_SAFER')
                log(f'ตัดตามพื้นที่ศึกษา: {int(win.width):,} × {int(win.height):,} พิกเซล')
                with rasterio.open(outp, 'w', **prof) as o:
                    o.scales, o.offsets = d.scales, d.offsets          # คง scale/offset ของต้นฉบับ (ค่าดิบเหมือนเดิม)
                    for b in range(1, d.count + 1):
                        o.write(d.read(b, window=win), b)
                        P(0.9 * b / d.count, f'แบนด์ {b}/{d.count}')
        else:
            r = requests.get(m['url'], headers=links.UA, stream=True, timeout=60)
            size = int(r.headers.get('Content-Length') or 0)
            got = 0
            with open(outp, 'wb') as f:
                for c in r.iter_content(1 << 20):
                    f.write(c)
                    got += len(c)
                    P(min(0.9, got / size * 0.9) if size else 0.5, f'ดาวน์โหลด {got / 1e6:,.1f}{f" / {size / 1e6:,.1f}" if size else ""} MB')
    else:
        raise EngineError('ลิงก์ชนิดนี้เป็นภาพ (ดูอย่างเดียว) ดาวน์โหลดเป็นข้อมูลไม่ได้')
    if feats is not None:
        if not feats:
            raise EngineError('ไม่ได้ feature เลย')
        gdf = gpd.GeoDataFrame.from_features(feats, crs='EPSG:4326')
        n = len(gdf)
        outp = out_dir / f'{name}.gpkg'
        P(0.93, f'เขียน GeoPackage {n:,} feature')
        gdf.to_file(outp, layer=name, driver='GPKG')
    src = dict(url=m['url'], type=t, type_label=links.LABEL.get(t), layer=p.get('layer', m.get('layer')), aoi_bbox=bbox,
               where=p.get('where'), downloaded_at=datetime.now().isoformat(timespec='seconds'), features=n or None,
               note='ไม่บันทึกโทเคน' if token else None)
    (out_dir / 'source.json').write_text(json.dumps(src, ensure_ascii=False, indent=1), encoding='utf-8')
    from . import catalog
    did = catalog._insert(str(outp), m['url'], True, 'raster' if t == 'cog' else 'vector', None,
                          p.get('name') or f"{lk['name']} (ดาวน์โหลด {datetime.now():%Y-%m-%d})",
                          [f'ดาวน์โหลดจาก {m["url"]} เมื่อ {src["downloaded_at"]}'], role='input', job_id=job['id'])
    log(f'บันทึก {outp}')
    return dict(output=str(outp), dataset_id=did, summary=dict(features=n or None, source=src))


# ======================================================================
# zonal: ไบแวเรียตรายโพลิกอน (อำเภอ/ตำบล) — สรุปค่าในแต่ละพื้นที่แล้วไขว้
# ======================================================================
STATS = {
    'sum': 'ผลรวม', 'mean': 'ค่าเฉลี่ย (ถ่วงพื้นที่)', 'density': 'ผลรวม ÷ พื้นที่ (ต่อ ตร.กม.)',
    'share_area': 'สัดส่วนพื้นที่ที่ค่า ≥ เกณฑ์ (%)', 'share_weight': 'สัดส่วนน้ำหนัก (เช่น คน) ในจุดที่ค่า ≥ เกณฑ์ (%)',
}


def _classify_vals(v, cfg):
    n = int(cfg.get('n', 3))
    ok = np.isfinite(v)
    if cfg.get('method') == 'quantile':
        br = [float(np.quantile(v[ok], i / n)) for i in range(1, n)] if ok.any() else []
    elif cfg.get('method') == 'equal':
        lo, hi = (float(v[ok].min()), float(v[ok].max())) if ok.any() else (0, 1)
        br = [lo + (hi - lo) * i / n for i in range(1, n)]
    else:
        br = [float(b) for b in cfg.get('breaks', [])]
    out = []
    for b in br:
        out.append(math.nextafter(out[-1], math.inf) if out and b <= out[-1] else b)
    c = np.where(ok, np.digitize(np.where(ok, v, 0), out), -1) if n > 1 else np.where(ok, 0, -1)
    return c.astype(int), out


def op_zonal(job, P, log):
    import geopandas as gpd
    import pyogrio
    from rasterio.features import rasterize
    p = job['params']
    zds = db.get('datasets', int(p['zones_dataset_id']))
    zf = p.get('zone_field')
    cfg = {a: dict(p[a]) for a in ('x', 'y')}
    dsets = {}
    for a in ('x', 'y'):
        for k in ('dataset_id', 'weight_dataset_id'):
            if cfg[a].get(k):
                dsets[int(cfg[a][k])] = db.get('datasets', int(cfg[a][k]))
    for d in dsets.values():
        if not d.get('value_type_confirmed'):
            raise EngineError(f'ยืนยันประเภทค่าของ "{d["name"]}" ก่อน')
    srcs = {i: Source(d) for i, d in dsets.items()}
    grid = engine.make_grid(list(srcs.values()), Fraction(p['target_res']))
    ogs = {i: engine.OnGrid(s, grid, 'any', p.get('tie', 'high')) for i, s in srcs.items()}
    if zds['kind'] == 'link':                         # ชั้นพื้นที่เป็นลิงก์ → ดึงจากบริการตอนรัน (เฉพาะกรอบพื้นที่ศึกษาถ้ามี)
        log(f'ดึงโพลิกอนจากลิงก์ {zds["meta"]["url"]}…')
        feats = links.fetch_features(zds['meta'], bbox=_aoi_bbox4326(p), progress=lambda f, msg=None: P(0.05 * (f or 0), msg), log=log)
        if not feats:
            raise EngineError('ลิงก์ไม่คืนโพลิกอน')
        gdf = gpd.GeoDataFrame.from_features(feats, crs='EPSG:4326')
    else:
        from .dsinfo import read_vector
        gdf = read_vector(zds)
    if p.get('aoi_id'):
        from . import aoi
        ag = aoi.geom_in(int(p['aoi_id']), gdf.crs)
        gdf = gdf[gdf.intersects(ag)]
    gdf = gdf[gdf.geometry.notna()].reset_index(drop=True)
    if not len(gdf):
        raise EngineError('ไม่มีโพลิกอนในพื้นที่')
    N = len(gdf)
    zg = gdf.to_crs(grid.crs)
    grid.set_window(zg.total_bounds, engine.snap_unit(list(ogs.values())))
    sidx = zg.sindex
    geoms = zg.geometry.values
    T = engine.tile_size(list(ogs.values()), True)
    tiles = list(engine.iter_tiles(grid, T))
    log(f'{N:,} พื้นที่ · กริด {grid.describe()["res_label"]} · {grid.out_shape[1]:,} × {grid.out_shape[0]:,} · {len(tiles):,} ไทล์')
    zarea = np.zeros(N + 1)
    acc = {a: dict(num=np.zeros(N + 1), den=np.zeros(N + 1)) for a in ('x', 'y')}
    wtot = {a: np.zeros(N + 1) for a in ('x', 'y')}
    t0 = time.time()
    rule = p.get('rule', 'center')
    for ti, (r0, c0, h, w) in enumerate(tiles):
        tt = grid.tile_transform(r0, c0)
        idx = sidx.query(__import__('shapely').box(tt.c, tt.f - h * grid.ry, tt.c + w * grid.rx, tt.f))
        if not len(idx):
            continue
        z = rasterize(zip(geoms[idx], idx + 1), out_shape=(h, w), transform=tt, fill=0, all_touched=rule == 'touch', dtype='int32')
        if not z.any():
            continue
        area = np.broadcast_to(grid.area_rows(r0, h)[:, None], (h, w))
        zarea += np.bincount(z.ravel(), weights=area.ravel(), minlength=N + 1)
        cache = {}

        def vals(i):
            if i not in cache:
                cache[i] = ogs[i].values(r0, c0, h, w)
            return cache[i]
        for a in ('x', 'y'):
            c = cfg[a]
            v, ok = vals(int(c['dataset_id']))
            st = c.get('stat', 'sum')
            ok = ok & (z > 0)
            zz = z[ok]
            if st in ('sum', 'density'):
                acc[a]['num'] += np.bincount(zz, weights=v[ok], minlength=N + 1)
            elif st == 'mean':
                acc[a]['num'] += np.bincount(zz, weights=(v * area)[ok], minlength=N + 1)
                acc[a]['den'] += np.bincount(zz, weights=area[ok], minlength=N + 1)
            elif st in ('share_area', 'share_weight'):
                # "ค่า ≥ เกณฑ์" ใช้ลำดับเดียวกับไบแวเรียต: ข้อมูลชั้นจัดชั้นก่อนแล้ว majority (ไม่ใช่ majority ของค่าดิบ)
                clf2 = engine.Classifier(dict(n=2, method='breaks', breaks=[float(c.get('threshold', 1))], metric='value'))
                cls2 = ogs[int(c['dataset_id'])].classes(clf2, r0, c0, h, w)
                ok = (cls2 >= 0) & (z > 0)
                zz = z[ok]
                hitmap = cls2 == 1
            if st == 'share_area':
                acc[a]['num'] += np.bincount(zz, weights=area[ok] * hitmap[ok], minlength=N + 1)
                acc[a]['den'] += np.bincount(zz, weights=area[ok], minlength=N + 1)
            elif st == 'share_weight':
                wv, wok = vals(int(c['weight_dataset_id']))
                wv = np.where(wok & (z > 0), wv, 0.0)
                hit = ok & hitmap
                acc[a]['num'] += np.bincount(z.ravel(), weights=(wv * hit).ravel(), minlength=N + 1)
                acc[a]['den'] += np.bincount(z.ravel(), weights=wv.ravel(), minlength=N + 1)
            if c.get('weight_dataset_id'):
                wv, wok = vals(int(c['weight_dataset_id']))
                wtot[a] += np.bincount(z[wok & (z > 0)], weights=wv[wok & (z > 0)], minlength=N + 1)
        if ti % 5 == 0 or ti == len(tiles) - 1:
            P(0.85 * (ti + 1) / len(tiles), f'ไทล์ {ti + 1:,}/{len(tiles):,} · {time.time() - t0:,.0f} วินาที')
    res = {}
    for a in ('x', 'y'):
        st = cfg[a].get('stat', 'sum')
        num, den = acc[a]['num'][1:], acc[a]['den'][1:]
        za = zarea[1:]
        with np.errstate(divide='ignore', invalid='ignore'):
            if st == 'sum':
                v = num.copy()
            elif st == 'density':
                v = np.where(za > 0, num / za, np.nan)
            elif st == 'mean':
                v = np.where(den > 0, num / den, np.nan)
            else:
                v = np.where(den > 0, num / den * 100, np.nan)
        v[za <= 0] = np.nan                                   # โพลิกอนเล็กกว่าพิกเซล (ไม่มีศูนย์กลางพิกเซลตก)
        res[a] = v
    cx, bx = _classify_vals(res['x'], cfg['x'])
    cy, by = _classify_vals(res['y'], cfg['y'])
    nx, ny = int(cfg['x'].get('n', 3)), int(cfg['y'].get('n', 3))
    colors = p['colors']
    code = np.where((cx >= 0) & (cy >= 0), cy * nx + cx + 1, 0)
    out = gdf.copy()
    names = gdf[zf].astype(str) if zf and zf in gdf.columns else gdf.index.astype(str)
    out = out[[c for c in ([zf] if zf in gdf.columns else []) if c] + ['geometry']]
    out['x_value'], out['y_value'] = res['x'], res['y']
    out['x_class'], out['y_class'], out['code'] = cx + 1, cy + 1, code
    out['color'] = [colors[c - 1] if c > 0 else '#000000' for c in code]
    out['area_km2'] = zarea[1:]
    for a in ('x', 'y'):
        if cfg[a].get('weight_dataset_id'):
            out[f'{a}_weight'] = wtot[a][1:]
    hl = [int(c) for c in p.get('highlight', [])]
    out['highlight'] = np.isin(code, hl).astype(int)
    out_dir = Path(job['out_dir'])
    base = export.slug(p.get('name') or f'zonal_{zds["name"]}', 60)
    outp = out_dir / f'{base}.gpkg'
    P(0.9, 'เขียน GeoPackage…')
    out.to_file(outp, layer=base, driver='GPKG')
    xl = export.class_labels(dict(cfg['x'], breaks=bx)) if nx > 1 else ['ทั้งหมด']
    yl = export.class_labels(dict(cfg['y'], breaks=by)) if ny > 1 else ['ทั้งหมด']
    xname, yname = cfg['x'].get('label') or 'X', cfg['y'].get('label') or 'Y'
    ent = [(c, colors[c - 1], f'{c}: {yname} {yl[(c - 1) // nx]} · {xname} {xl[(c - 1) % nx]}') for c in range(1, nx * ny + 1)]
    (out_dir / f'{base}.qml').write_text(qml_categorized('code', ent), encoding='utf-8')
    export.legend_png(out_dir / f'{base}_legend.png', nx, ny, colors, xname, yname, xl, yl, hl)
    tab = out.drop(columns='geometry')
    tab.to_csv(out_dir / f'{base}_table.csv', index=False, encoding='utf-8-sig')
    cnt = {str(c): int((code == c).sum()) for c in range(1, nx * ny + 1)}
    summary = dict(zones=N, zones_coded=int((code > 0).sum()), zones_by_code=cnt, highlight=hl, zones_highlight=int(out['highlight'].sum()),
                   grid=grid.describe(), x_breaks=bx, y_breaks=by)
    params = dict(p, x=dict(cfg['x'], resolved_breaks=bx, stat_label=STATS.get(cfg['x'].get('stat'))),
                  y=dict(cfg['y'], resolved_breaks=by, stat_label=STATS.get(cfg['y'].get('stat'))),
                  rule=f'พิกเซลเป็นของพื้นที่ตาม{"ศูนย์กลางพิกเซล" if rule == "center" else "การแตะ"} · ค่าต่อพิกเซลตามประเภทค่า (count รวม / density เฉลี่ย / class majority)')
    export.write_lineage(out_dir, 'zonal', [export.lineage_input(zds)] + [export.lineage_input(d) for d in dsets.values()], params,
                         [outp, out_dir / f'{base}.qml', out_dir / f'{base}_legend.png', out_dir / f'{base}_table.csv'], summary)
    did = register_output(outp, p.get('name') or f'ไบแวเรียตราย{zds["name"]}', None, job['id'], 'map', kind='vector')
    return dict(output=str(outp), dataset_id=did, summary=summary)


# ======================================================================
# change: เทียบ 2 ชุด (เช่น ประชากร 2015 กับ 2024) บนกริดเดียวกัน
# ======================================================================
def op_change(job, P, log):
    p = job['params']
    da, dbb = db.get('datasets', int(p['a_id'])), db.get('datasets', int(p['b_id']))
    for d in (da, dbb):
        if not d.get('value_type_confirmed'):
            raise EngineError(f'ยืนยันประเภทค่าของ "{d["name"]}" ก่อน')
    mode = p.get('mode', 'diff')
    sa, sb = Source(da), Source(dbb)
    grid = engine.make_grid([sa, sb], Fraction(p['target_res']))
    oa, ob = engine.OnGrid(sa, grid, 'any', p.get('tie', 'high')), engine.OnGrid(sb, grid, 'any', p.get('tie', 'high'))
    masker, mf, aoi_info = setup_aoi(p, grid, [oa, ob], log)
    out_dir = Path(job['out_dir'])
    base = export.slug(p.get('name') or f'change_{da["name"]}_{dbb["name"]}', 60)
    outp = out_dir / f'{base}.tif'
    if mode == 'transition':
        va = [v for v, _ in ((da.get('stats') or {}).get('hist_int') or [])]
        vb = [v for v, _ in ((dbb.get('stats') or {}).get('hist_int') or [])]
        if not va or not vb or len(va) * len(vb) > 250:
            raise EngineError('การเปลี่ยนชั้นต้องเป็นข้อมูลชั้นที่มีค่าไม่มาก (ชั้นก่อน × ชั้นหลัง ≤ 250)')
        if da.get('nodata_as') is not None and da['nodata_as'] not in va:
            va = sorted(va + [da['nodata_as']])
        if dbb.get('nodata_as') is not None and dbb['nodata_as'] not in vb:
            vb = sorted(vb + [dbb['nodata_as']])
        W = OutWriter(outp, grid, 'uint8', 0)
    else:
        W = OutWriter(outp, grid, 'float32', -99999.0)
    T = engine.tile_size([oa, ob], W.inmem, mf)
    tiles = list(engine.iter_tiles(grid, T))
    log(f'โหมด {mode} · กริด {grid.describe()["res_label"]} · {len(tiles):,} ไทล์')
    sum_a = sum_b = 0.0
    n_up = n_down = n_same = 0
    mat = np.zeros((len(va) if mode == 'transition' else 1, len(vb) if mode == 'transition' else 1))
    t0 = time.time()
    for i, (r0, c0, h, w) in enumerate(tiles):
        a, ka = oa.values(r0, c0, h, w)
        b, kb = ob.values(r0, c0, h, w)
        ok = ka & kb
        if masker is not None:
            ok &= masker(r0, c0, h, w)
        if not ok.any():
            continue
        area = np.broadcast_to(grid.area_rows(r0, h)[:, None], (h, w))
        if mode == 'transition':
            ia = np.searchsorted(va, a)
            ib = np.searchsorted(vb, b)
            good = ok & (ia < len(va)) & (ib < len(vb))
            good[good] &= (np.asarray(va)[ia[good]] == a[good]) & (np.asarray(vb)[ib[good]] == b[good])
            code = np.where(good, ia * len(vb) + ib + 1, 0).astype('uint8')
            np.add.at(mat, (ia[good], ib[good]), area[good])
            W.write(r0, c0, code)
        else:
            with np.errstate(divide='ignore', invalid='ignore'):
                if mode == 'diff':
                    o = b - a
                elif mode == 'pct':
                    o = np.where(a != 0, (b - a) / a * 100, np.nan)
                else:
                    o = np.where(a != 0, b / a, np.nan)
            ok2 = ok & np.isfinite(o)
            sum_a += float(a[ok].sum())
            sum_b += float(b[ok].sum())
            n_up += int((ok & (b > a)).sum())
            n_down += int((ok & (b < a)).sum())
            n_same += int((ok & (b == a)).sum())
            W.write(r0, c0, np.where(ok2, o, -99999.0).astype('float32'))
        if i % 5 == 0 or i == len(tiles) - 1:
            P(0.88 * (i + 1) / len(tiles), f'ไทล์ {i + 1:,}/{len(tiles):,} · {time.time() - t0:,.0f} วินาที')
    W.close(Resampling.mode if mode == 'transition' else Resampling.average, P=lambda f, msg: P(0.92, msg))
    summary = dict(grid=grid.describe(), aoi=aoi_info, mode=mode)
    style = None
    if mode == 'transition':
        rows = [[f'{x} → {y}', x, y, round(float(mat[i, j]), 6)] for i, x in enumerate(va) for j, y in enumerate(vb) if mat[i, j] > 0]
        export.write_csv(out_dir / f'{base}_transition.csv', ['เปลี่ยน', 'ก่อน', 'หลัง', 'พื้นที่ (ตร.กม.)'], rows)
        ents = []
        for i, x in enumerate(va):
            for j, y in enumerate(vb):
                c = i * len(vb) + j + 1
                col = '#d9d9d9' if x == y else symbology.ramp_at('RdYlBu', 1 - (j / max(len(vb) - 1, 1))) if y != x else '#d9d9d9'
                ents.append(dict(value=c, color=col, label=f'{x} → {y}', visible=bool(mat[i, j] > 0)))
        style = dict(type='paletted', entries=ents, ramp='RdYlBu')
        summary.update(transition_km2={f'{va[i]}→{vb[j]}': float(mat[i, j]) for i in range(len(va)) for j in range(len(vb)) if mat[i, j] > 0})
        vt = 'class'
    else:
        summary.update(sum_before=sum_a, sum_after=sum_b, diff=sum_b - sum_a, pct=(sum_b - sum_a) / sum_a * 100 if sum_a else None,
                       pixels_up=n_up, pixels_down=n_down, pixels_same=n_same)
        export.write_csv(out_dir / f'{base}_summary.csv', ['รายการ', 'ค่า'],
                         [['ผลรวมก่อน', sum_a], ['ผลรวมหลัง', sum_b], ['ผลต่าง', sum_b - sum_a], ['พิกเซลที่เพิ่ม', n_up], ['พิกเซลที่ลด', n_down], ['พิกเซลเท่าเดิม', n_same]])
        vt = 'density' if mode != 'diff' else (da['value_type'] if da['value_type'] != 'class' else 'density')
    export.write_lineage(out_dir, 'change', [export.lineage_input(da), export.lineage_input(dbb)], p, [outp], summary)
    did = register_output(outp, p.get('name') or f'เปลี่ยนแปลง {da["name"]} → {dbb["name"]}', vt, job['id'], 'derived')
    if style:
        db.update('datasets', did, style=symbology.jsonable(style))
        d = db.get('datasets', did)
        Path(outp).with_suffix('.qml').write_text(symbology.qml(d, style), encoding='utf-8')
    elif mode in ('diff', 'pct'):
        d = db.get('datasets', did)
        lim = 100.0 if mode == 'pct' else None
        if lim is None:
            with rasterio.open(outp) as s:
                ov = s.read(1, out_shape=(1, min(s.height, 2000), min(s.width, 2000)), masked=True)
            vals = np.abs(ov.compressed())
            lim = float(np.quantile(vals[vals > 0], 0.98)) if (vals > 0).any() else 1.0
        bounds = [-lim * f for f in (1, .5, .2, .05)] + [lim * f for f in (.05, .2, .5, 1)] + [math.inf]
        cols = symbology.ramp_colors('RdBu', len(bounds))
        stops = [dict(value=b, color=cols[i], label=('≤ ' + symbology.fmtv(b)) if i == 0 else (f'> {symbology.fmtv(bounds[i - 1])}' if math.isinf(b) else f'{symbology.fmtv(bounds[i - 1])} – {symbology.fmtv(b)}'), visible=True)
                 for i, b in enumerate(bounds)]
        style = dict(type='pseudocolor', interp='discrete', mode='manual', ramp='RdBu', min=-lim, max=lim, stops=stops, metric='value')
        db.update('datasets', did, style=symbology.jsonable(style))
        Path(outp).with_suffix('.qml').write_text(symbology.qml(db.get('datasets', did), style), encoding='utf-8')
    return dict(output=str(outp), dataset_id=did, summary=summary)


# ======================================================================
# sensitivity: เทียบหลายเกณฑ์/ความละเอียด → ช่วงของตัวเลขเขตเน้น
# ======================================================================
def op_sensitivity(job, P, log):
    p = job['params']
    base = p['base']
    xs = p.get('x_breaks_sets') or [base['x'].get('breaks')]
    ys = p.get('y_breaks_sets') or [base['y'].get('breaks')]
    rs = p.get('resolutions') or [base['target_res']]
    combos = list(itertools.product(rs, xs, ys))
    if len(combos) > 40:
        raise EngineError(f'{len(combos)} ชุดค่า มากเกิน (สูงสุด 40)')
    rows, results = [], []
    for k, (res, bx, by) in enumerate(combos):
        q = copy.deepcopy(base)
        q['target_res'] = res
        q['x'] = dict(q['x'], breaks=bx, n=len(bx) + 1, method='breaks') if q['x'].get('method') != 'degurba' else q['x']
        q['y'] = dict(q['y'], breaks=by, n=len(by) + 1, method='breaks')
        nx, ny = q['x']['n'], q['y']['n']
        q['colors'] = (q.get('colors') or ['#000000'] * 9)[:nx * ny] + ['#000000'] * max(0, nx * ny - len(q.get('colors') or []))
        lbl = f'{gm.res_label(Fraction(res), True).split(" (")[0]} · X {bx} · Y {by}'
        log(f'[{k + 1}/{len(combos)}] {lbl}')

        def subP(f, msg=None, k=k):
            P((k + (f or 0)) / len(combos), f'ชุดที่ {k + 1}/{len(combos)} · {msg or ""}')
        r = op_bivariate(dict(id=job['id'], params=q, out_dir=None), subP, lambda m: None, stats_only=True)
        s = r['summary']
        results.append(dict(label=lbl, res=res, x_breaks=bx, y_breaks=by, highlight_weight=s.get('highlight_weight'),
                            highlight_area_km2=s.get('highlight_area_km2'), weight_total=s.get('weight_total'),
                            weight_by_y_class=s.get('weight_by_y_class')))
        rows.append([lbl, res, json.dumps(bx), json.dumps(by), s.get('highlight_weight'), s.get('highlight_area_km2'), s.get('weight_total')])
    out_dir = Path(job['out_dir'])
    export.write_csv(out_dir / 'sensitivity.csv', ['ชุดค่า', 'ความละเอียด', 'เกณฑ์ X', 'เกณฑ์ Y', 'น้ำหนักเขตเน้น', 'พื้นที่เขตเน้น (ตร.กม.)', 'น้ำหนักรวม'], rows)
    hw = [r['highlight_weight'] for r in results if r['highlight_weight'] is not None]
    summary = dict(runs=len(results), highlight_min=min(hw) if hw else None, highlight_max=max(hw) if hw else None,
                   highlight_median=float(np.median(hw)) if hw else None, results=results)
    export.write_lineage(out_dir, 'sensitivity', [], p, [out_dir / 'sensitivity.csv'], summary)
    return dict(output=str(out_dir / 'sensitivity.csv'), summary=summary)


OPS3 = dict(download=op_download, zonal=op_zonal, change=op_change, sensitivity=op_sensitivity)
