# -*- coding: utf-8 -*-
"""รายงาน PDF 1 หน้า (3.7): แผนที่ + คำอธิบายสัญลักษณ์ + ที่มา (จาก lineage) + สถิติสรุป"""
import io
import json
import textwrap
from datetime import datetime
from pathlib import Path

import numpy as np

from . import db, engine, symbology, tiles
from .config import APP_VERSION


def _font():
    import matplotlib
    from matplotlib import font_manager
    for f in ('Tahoma', 'Leelawadee UI', 'Leelawadee'):
        if any(f == x.name for x in font_manager.fontManager.ttflist):
            matplotlib.rcParams['font.family'] = f
            return f
    return None


def _lineage(ds):
    if not ds.get('job_id'):
        return None
    j = db.get('jobs', ds['job_id'])
    if not j or not j.get('out_dir'):
        return None
    p = Path(j['out_dir']) / 'lineage.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None


def _raster_img(ds, style, max_px=1600):
    import rasterio
    with rasterio.open(ds.get('read_path') or ds['path']) as d:
        f = max(1, int(np.ceil(max(d.width, d.height) / max_px)))
        H, W = int(np.ceil(d.height / f)), int(np.ceil(d.width / f))
        arr = d.read(int(ds.get('band') or 1), out_shape=(H, W), masked=True,
                     resampling=rasterio.enums.Resampling.nearest if style.get('type') == 'paletted' else rasterio.enums.Resampling.average)
        t = d.transform
        sc = engine.band_scale(d, int(ds.get('band') or 1))
        ext = [t.c, t.c + t.a * d.width, t.f + t.e * d.height, t.f]
        res = abs(t.a) * d.width / W
        lat = t.f - (np.arange(H) + 0.5) * abs(t.e) * d.height / H
    a = engine.unscale(np.asarray(arr.filled(0)).astype('float64'), *sc)
    valid = ~np.ma.getmaskarray(arr)
    if style.get('metric') == 'density' and ds.get('value_type') == 'count':
        res = abs(t.a)                   # average resampling = ค่าเฉลี่ยต่อพิกเซลเดิม → หารด้วยพื้นที่พิกเซลเดิม
    rgba = symbology.render(ds, style, a, valid, res, lat)
    return rgba, ext


def make_pdf(ds):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    _font()
    style = (tiles.style_of(ds) or {}) if ds['kind'] == 'raster' else {}
    lin = _lineage(ds)
    fig = plt.figure(figsize=(11.69, 8.27), dpi=150)               # A4 แนวนอน
    fig.patch.set_facecolor('white')
    ax = fig.add_axes([0.03, 0.08, 0.58, 0.8])
    ax.set_facecolor('#f4f5f9')
    if ds['kind'] == 'raster':
        rgba, ext = _raster_img(ds, style)
        ax.imshow(rgba, extent=ext, interpolation='nearest')
    else:
        import pyogrio
        from .dsinfo import read_vector
        g = read_vector(ds)
        if 'color' in g.columns:
            g.plot(ax=ax, color=g['color'], edgecolor='#ffffff', linewidth=.2)
            if 'code' in g.columns:          # คำอธิบายจากสีในข้อมูล (กรณีไม่มี legend จาก lineage)
                u = g[g['code'] > 0].drop_duplicates('code').sort_values('code')
                style = dict(type='paletted', entries=[dict(value=int(r.code), color=r.color, label=f'รหัส {int(r.code)}') for r in u.itertuples()])
        else:
            g.plot(ax=ax, facecolor='#c3b6ff', edgecolor='#555', linewidth=.3)
    aoi = (lin or {}).get('stats_summary', {}).get('aoi') if lin else None
    if aoi and aoi.get('id'):
        try:
            from . import aoi as aoimod
            import geopandas as gpd
            gpd.GeoSeries([aoimod.geom_in(aoi['id'], 'EPSG:4326')]).boundary.plot(ax=ax, color='#222', linewidth=.8)
        except Exception:
            pass
    ax.set_aspect(1 / np.cos(np.radians(ds['meta'].get('center_lat') or 13)))
    ax.set_xlabel('')
    ax.set_ylabel('')
    ax.tick_params(labelsize=7)
    for s in ax.spines.values():
        s.set_color('#cccccc')
    fig.text(0.03, 0.94, ds['name'], fontsize=17, fontweight='bold', color='#1b1d2c')
    fig.text(0.03, 0.905, f'{ds["meta"].get("res_label", "")} · {ds["meta"].get("crs_name", "")}', fontsize=9, color='#666')
    # คำอธิบายสัญลักษณ์
    lg = fig.add_axes([0.64, 0.5, 0.34, 0.4])
    lg.axis('off')
    leg_png = None
    if lin and lin.get('operation') in ('bivariate', 'zonal'):
        cand = [Path(o) for o in lin.get('outputs', []) if str(o).endswith('_legend.png')]
        leg_png = cand[0] if cand and cand[0].exists() else None
    if leg_png:
        lg.imshow(plt.imread(leg_png))
    else:
        items = (style.get('entries') if style.get('type') == 'paletted' else style.get('stops')) or []
        items = [e for e in items if e.get('visible', True)][:16]
        if items:
            lg.legend(handles=[Patch(facecolor=e['color'], edgecolor='#999', label=str(e.get('label', e['value']))) for e in items],
                      loc='upper left', fontsize=8, frameon=False, title='คำอธิบายสัญลักษณ์', title_fontsize=9)
    # ที่มา + สถิติ
    lines = []
    if lin:
        lines.append(f'งาน: {lin.get("operation")} · สร้างเมื่อ {lin.get("created_at", "").replace("T", " ")}')
        for i in lin.get('inputs', []):
            lines.append(f'• {i.get("name")} ({i.get("value_type") or "vector"})')
        pr = lin.get('params', {})
        for a in ('x', 'y'):
            if isinstance(pr.get(a), dict):
                c = pr[a]
                lines.append(f'{a.upper()}: {c.get("label") or ""} · {c.get("method", "")} · เกณฑ์ {c.get("resolved_breaks", c.get("breaks"))}'
                             + (f' · {c.get("stat_label")}' if c.get('stat_label') else ''))
        s = lin.get('stats_summary', {})
        if s.get('aoi'):
            lines.append(f'พื้นที่ศึกษา: {s["aoi"].get("name")}')
        if s.get('weight_total') is not None:
            lines.append(f'น้ำหนักรวม {s["weight_total"]:,.2f} · เขตเน้น {s.get("highlight_weight") or 0:,.2f}')
        if s.get('zones') is not None:
            lines.append(f'{s["zones"]:,} พื้นที่ · เขตเน้น {s.get("zones_highlight", 0):,} พื้นที่')
        if s.get('sum') is not None:
            lines.append(f'ผลรวมค่า {s["sum"]:,.2f}')
        for w in lin.get('warnings', [])[:3]:
            lines.append('⚠ ' + w)
    else:
        lines.append(f'ไฟล์: {ds["path"]}')
        st = ds.get('stats') or {}
        if st.get('sum') is not None:
            lines.append(f'ผลรวม {st["sum"]:,.2f} · min {st.get("min")} · max {st.get("max")}')
    txt = '\n'.join(sum((textwrap.wrap(l, 70) or [''] for l in lines), []))
    fig.text(0.64, 0.46, 'ที่มา (lineage)', fontsize=10, fontweight='bold', color='#1b1d2c', va='top')
    fig.text(0.64, 0.43, txt, fontsize=7.5, color='#333', va='top', linespacing=1.5)
    fig.text(0.03, 0.03, f'Ainulindalë {APP_VERSION} · {datetime.now():%Y-%m-%d %H:%M} · {ds["path"]}', fontsize=6.5, color='#888')
    buf = io.BytesIO()
    fig.savefig(buf, format='pdf')
    plt.close(fig)
    return buf.getvalue()
