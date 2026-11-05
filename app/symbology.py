# -*- coding: utf-8 -*-
"""สไตล์การแสดงผล raster แบบ QGIS (เก็บใน datasets.style เป็น JSON)

type = 'paletted'     ค่าเฉพาะ → สี (Paletted/Unique values)        entries: [{value, color, label, visible}]
     = 'pseudocolor'  ค่าต่อเนื่อง + color ramp (Singleband pseudocolor) stops: [{value, color, label, visible}]
                      interp: discrete (ค่า ≤ ขอบบน) / linear (ไล่สีระหว่างจุด) / exact (เท่ากันพอดี)
                      mode: continuous / equal / quantile · classes · min · max
     = 'gray'         ขาวดำยืดค่า min–max (Singleband gray)
ร่วมกัน: metric (count → 'density' แสดงเป็นต่อ ตร.กม. / 'value' ค่าดิบ) · hide_values (ซ่อนค่าเหล่านี้) ·
         range [lo, hi] (แสดงเฉพาะช่วง) · opacity (ฝั่งหน้าเว็บ)
สไตล์มีผลกับการแสดงผลเท่านั้น — การคำนวณใช้ "ค่าที่ไม่นับ" (exclude_values) ในการตั้งค่าชุดข้อมูลแทน"""
import math
from xml.sax.saxutils import quoteattr

import numpy as np

from . import gridmath as gm

# ---------- color ramps ----------
RAMPS = {
    'viridis': '#440154 #482878 #3e4989 #31688e #26828e #1f9e89 #35b779 #6ece58 #b5de2b #fde725',
    'magma': '#000004 #1c1044 #4f127b #812581 #b5367a #e55964 #fb8761 #fec287 #fcfdbf',
    'inferno': '#000004 #1f0c48 #550f6d #88226a #ba3655 #e35933 #f98e09 #f9cb35 #fcffa4',
    'plasma': '#0d0887 #4c02a1 #7e03a8 #a92395 #cc4778 #e56b5d #f89540 #fdc527 #f0f921',
    'cividis': '#00224e #123570 #3b496c #575d6d #707173 #8a8678 #a59c74 #c3b369 #e1cc55 #fee838',
    'YlOrBr': '#fff7bc #fee391 #fec44f #fe9929 #ec7014 #cc4c02 #993404 #662506',
    'YlOrRd': '#ffffcc #ffeda0 #fed976 #feb24c #fd8d3c #fc4e2a #e31a1c #bd0026 #800026',
    'YlGnBu': '#ffffd9 #edf8b1 #c7e9b4 #7fcdbb #41b6c4 #1d91c0 #225ea8 #253494 #081d58',
    'Blues': '#f7fbff #deebf7 #c6dbef #9ecae1 #6baed6 #4292c6 #2171b5 #08519c #08306b',
    'Greens': '#f7fcf5 #e5f5e0 #c7e9c0 #a1d99b #74c476 #41ab5d #238b45 #006d2c #00441b',
    'Reds': '#fff5f0 #fee0d2 #fcbba1 #fc9272 #fb6a4a #ef3b2c #cb181d #a50f15 #67000d',
    'Purples': '#fcfbfd #efedf5 #dadaeb #bcbddc #9e9ac8 #807dba #6a51a3 #54278f #3f007d',
    'Greys': '#ffffff #f0f0f0 #d9d9d9 #bdbdbd #969696 #737373 #525252 #252525 #000000',
    'RdYlGn': '#a50026 #d73027 #f46d43 #fdae61 #fee08b #ffffbf #d9ef8b #a6d96a #66bd63 #1a9850 #006837',
    'Spectral': '#9e0142 #d53e4f #f46d43 #fdae61 #fee08b #ffffbf #e6f598 #abdda4 #66c2a5 #3288bd #5e4fa2',
    'RdYlBu': '#a50026 #d73027 #f46d43 #fdae61 #fee090 #ffffbf #e0f3f8 #abd9e9 #74add1 #4575b4 #313695',
    'RdBu': '#67001f #b2182b #d6604d #f4a582 #fddbc7 #f7f7f7 #d1e5f0 #92c5de #4393c3 #2166ac #053061',
    'pastel dusk': '#2d3561 #6b5b95 #a389d4 #c3b6ff #f7a8cc #ffc2a8 #f6e3a1',
    'mint lavender': '#1f3b4d #2f6f7a #5fb3a6 #9ee8d4 #c3b6ff #efe9ff',
    'Set3 (หมวดหมู่)': '#8dd3c7 #ffffb3 #bebada #fb8072 #80b1d3 #fdb462 #b3de69 #fccde5 #d9d9d9 #bc80bd #ccebc5 #ffed6f',
    'Pastel1 (หมวดหมู่)': '#fbb4ae #b3cde3 #ccebc5 #decbe4 #fed9a6 #ffffcc #e5d8bd #fddaec #f2f2f2',
}
RAMPS = {k: v.split() for k, v in RAMPS.items()}
CATEGORICAL = {k for k in RAMPS if 'หมวดหมู่' in k}
DENS_BINS = [10, 50, 100, 300, 600, 1500, 3000]


def _rgb(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], float)


def _hex(c):
    return '#%02x%02x%02x' % tuple(int(round(x)) for x in np.clip(c, 0, 255))


def ramp_at(name, t, invert=False):
    """สีที่ตำแหน่ง t (0–1) ของ ramp — ไล่แบบเส้นตรงใน RGB เหมือน QGIS gradient"""
    st = RAMPS.get(name) or RAMPS['viridis']
    if invert:
        st = st[::-1]
    t = min(max(float(t), 0.0), 1.0) * (len(st) - 1)
    i = min(int(t), len(st) - 2)
    f = t - i
    return _hex(_rgb(st[i]) * (1 - f) + _rgb(st[i + 1]) * f)


def ramp_colors(name, n, invert=False):
    if name in CATEGORICAL:
        st = RAMPS[name]
        return [st[i % len(st)] for i in range(n)]
    return [ramp_at(name, i / max(n - 1, 1), invert) for i in range(n)]


def fmtv(v):
    if v is None or (isinstance(v, float) and math.isinf(v)):
        return '∞'
    v = float(v)
    if v.is_integer():
        return f'{int(v):,}'
    return f'{v:,.4g}' if abs(v) < 1e4 else f'{v:,.0f}'


# ---------- ค่าตัวอย่าง ----------
def sample_values(ds, metric):
    from . import ops
    v = ops.load_sample(ds, 'density' if (ds.get('value_type') == 'count' and metric == 'density') else 'value')
    if v is None:
        return None
    ex = ds.get('exclude_values') or []
    if ex:
        v = v[~np.isin(v, ex)]
    return v[np.isfinite(v)]


# ---------- สไตล์เริ่มต้น ----------
def map_entries(ds):
    """แผนที่ไบแวเรียต: entries จากตารางสีในไฟล์ + ป้ายจาก lineage"""
    import json
    from pathlib import Path
    import rasterio
    with rasterio.open(ds.get('read_path') or ds['path']) as d:
        cm = d.colormap(1)
    labels = {}
    try:
        from . import db, export
        j = db.get('jobs', ds['job_id']) if ds.get('job_id') else None
        lin = json.loads((Path(j['out_dir']) / 'lineage.json').read_text(encoding='utf-8')) if j else None
        lp = lin['params']
        nx, ny = int(lp['x']['n']), int(lp['y']['n'])
        xl = export.class_labels(dict(lp['x'], breaks=lp['x'].get('resolved_breaks', lp['x'].get('breaks', []))))
        yl = export.class_labels(dict(lp['y'], breaks=lp['y'].get('resolved_breaks', lp['y'].get('breaks', []))))
        for c in range(1, nx * ny + 1):
            labels[c] = f'{lp["y"].get("label") or "Y"} {yl[(c - 1) // nx]} · {lp["x"].get("label") or "X"} {xl[(c - 1) % nx]}'
        codes = range(1, nx * ny + 1)
    except Exception:
        codes = [k for k, v in cm.items() if k > 0 and v[3] > 0]
    return [dict(value=c, color='#%02x%02x%02x' % cm.get(c, (0, 0, 0, 0))[:3], label=labels.get(c, str(c)), visible=True) for c in codes]


def default_style(ds):
    vt = ds.get('value_type')
    m = ds['meta']
    st = ds.get('stats') or {}
    if m.get('has_colormap'):
        try:
            return dict(type='paletted', entries=map_entries(ds), ramp='Set3 (หมวดหมู่)', source='colormap')
        except Exception:
            pass
    if vt == 'count':
        cols = RAMPS['YlOrBr']
        bounds = DENS_BINS + [math.inf]
        stops = [dict(value=b, color=cols[i], label=('≤ ' + fmtv(b)) if i == 0 else (f'{fmtv(bounds[i - 1])} – {fmtv(b)}' if not math.isinf(b) else f'> {fmtv(bounds[i - 1])}'), visible=True)
                 for i, b in enumerate(bounds)]
        return dict(type='pseudocolor', metric='density', interp='discrete', mode='manual', ramp='YlOrBr', classes=len(stops),
                    min=0, max=3000, stops=stops, hide_values=[0])
    vals = [v for v, _ in (st.get('hist_int') or [])]
    if vt == 'class' and vals and len(vals) <= 64:
        ordinal = vals[-1] - vals[0] == len(vals) - 1
        ramp = 'YlGnBu' if ordinal else 'Set3 (หมวดหมู่)'
        cols = ramp_colors(ramp, len(vals)) if not ordinal else [ramp_at(ramp, 0.25 + 0.75 * i / max(len(vals) - 1, 1)) for i in range(len(vals))]
        # ลำดับที่เริ่มจาก 0 (เช่น จำนวนปีท่วม 0 = ไม่เคยท่วม) → ซ่อน 0 ไว้ก่อน ไม่ให้ทับทั้งแผนที่ (เปิดคืนได้)
        hide0 = ordinal and vals[0] == 0 and len(vals) > 1
        return dict(type='paletted', ramp=ramp, hide_values=[0] if hide0 else [],
                    entries=[dict(value=v, color=c, label=fmtv(v), visible=not (hide0 and v == 0)) for v, c in zip(vals, cols)])
    return continuous_default(ds)


def data_profile(ds, s=None):
    """ชนิดข้อมูลต่อเนื่องเพื่อเลือกสีเริ่มต้นแบบ QGIS: 'index' (NDVI ฯลฯ) · 'nightlight' · 'generic'"""
    import re
    n = (ds.get('name') or '').lower()
    st = ds.get('stats') or {}
    lo, hi = st.get('min'), st.get('max')
    if re.search(r'ndvi|evi|savi|ndwi|ndbi|nbr|ndmi|lai|ดัชนี|index', n):
        return 'index'
    if re.search(r'night|viirs|vnl|ntl|dnb|black.?marble|radiance|แสงไฟ|ไฟกลางคืน', n):
        return 'nightlight'
    if lo is not None and hi is not None and -1.0001 <= lo < 0 < hi <= 1.0001:
        return 'index'                                       # ค่าอยู่ในช่วง −1…1 และมีทั้งลบและบวก → น่าจะเป็นดัชนี
    if s is not None and s.size and lo is not None and lo >= 0 and (s == 0).mean() > 0.3:
        return 'nightlight'                                  # ไม่ติดลบ + ศูนย์เกิน 30% (พื้นหลังมืด/ไม่มีสัญญาณ)
    return 'generic'


def continuous_default(ds):
    """สไตล์เริ่มต้นของข้อมูลต่อเนื่อง แบบ QGIS: Singleband pseudocolor · ไล่สีเชิงเส้น · min/max ตัดสะสม 2–98%
    index → RdYlGn (น้ำตาล→เขียว) · nightlight → inferno + ซ่อน 0 + ยืดสีจากพิกเซลที่มีค่า · อื่นๆ → viridis"""
    st = ds.get('stats') or {}
    s = sample_values(ds, 'value')
    prof = data_profile(ds, s)
    hide = []
    if s is not None and s.size:
        base = s
        if prof == 'nightlight' and (s > 0).any():
            base, hide = s[s > 0], [0]
        lo, hi = float(np.quantile(base, 0.02)), float(np.quantile(base, 0.98))
    else:
        pct = st.get('pct') or {}
        lo, hi = pct.get('2'), pct.get('98')
        if lo is None or hi is None:
            lo, hi = st.get('min', 0) or 0, st.get('max', 1) or 1
    if hi <= lo:
        hi = lo + (abs(lo) or 1) * 1e-3
    ramp = {'index': 'RdYlGn', 'nightlight': 'inferno'}.get(prof, 'viridis')
    out = classify(ds, dict(type='pseudocolor', ramp=ramp, mode='continuous', interp='linear', classes=5, min=lo, max=hi, metric='value',
                            hide_values=hide))
    out['profile'] = prof
    return out


# ---------- จัดชั้น (ปุ่ม Classify) ----------
def classify(ds, req):
    t = req.get('type', 'pseudocolor')
    ramp, inv = req.get('ramp') or 'viridis', bool(req.get('invert'))
    out = {k: v for k, v in req.items() if k not in ('stops', 'entries')}
    metric = req.get('metric', 'value')
    if t == 'paletted':
        st = ds.get('stats') or {}
        vals = [v for v, _ in (st.get('hist_int') or [])]
        if not vals:
            s = sample_values(ds, 'value')
            if s is None:
                raise ValueError('ยังไม่มีสถิติ — รองานเตรียมข้อมูลให้เสร็จก่อน')
            vals = sorted(np.unique(s).tolist())
        if len(vals) > 256:
            raise ValueError(f'ค่าไม่ซ้ำ {len(vals):,} ค่า มากเกินสำหรับแบบค่าเฉพาะ (≤ 256) — ใช้ Singleband pseudocolor แทน')
        ex = ds.get('exclude_values') or []
        vals = [v for v in vals if v not in ex]
        cols = ramp_colors(ramp, len(vals), inv)
        out['entries'] = [dict(value=v, color=c, label=fmtv(v), visible=True) for v, c in zip(vals, cols)]
        return out
    if t == 'gray':
        return out
    n = max(2, min(int(req.get('classes', 5)), 64))
    mode, interp = req.get('mode', 'continuous'), req.get('interp', 'linear')
    lo, hi = req.get('min'), req.get('max')
    s = None
    if lo is None or hi is None or mode == 'quantile':
        s = sample_values(ds, metric)
        if s is None or not s.size:
            raise ValueError('ยังไม่มีค่าสุ่ม — รองานเตรียมข้อมูลให้เสร็จก่อน')
        if lo is None:
            lo = float(np.quantile(s, 0.02))
        if hi is None:
            hi = float(np.quantile(s, 0.98))
    lo, hi = float(lo), float(hi)
    if hi <= lo:
        hi = lo + 1
    if mode == 'quantile':
        ss = s[(s >= lo) & (s <= hi)] if s is not None else None
        ss = ss if ss is not None and ss.size else s
        if interp == 'discrete':
            from .engine import EngineError, quantile_breaks
            try:
                vals = quantile_breaks(ss, n)               # ทนค่าซ้ำ: ค่าที่กอง (เช่น 0) ได้ชั้นของตัวเอง
            except EngineError as e:
                raise ValueError(str(e))
        else:
            vals = [float(np.quantile(ss, i / (n - 1))) for i in range(n)]
    else:                                         # continuous / equal
        vals = [lo + (hi - lo) * i / n for i in range(1, n)] if interp == 'discrete' else [lo + (hi - lo) * i / (n - 1) for i in range(n)]
    vals = sorted(set(vals))                     # ข้อมูลกองที่ค่าเดียว (เช่น จำนวนเต็ม) → เกณฑ์ซ้ำ → รวมชั้น
    if interp == 'discrete':
        vals = vals + [math.inf]
    n = len(vals)
    cols = ramp_colors(ramp, n, inv)
    from .engine import fmt_breaks
    fv = fmt_breaks(vals)                                    # หลักพอให้ป้ายไม่ซ้ำกัน
    stops = []
    for i, v in enumerate(vals):
        if interp == 'discrete':
            lbl = f'≤ {fv[0]}' if i == 0 else (f'> {fv[i - 1]}' if math.isinf(v) else f'{fv[i - 1]} – {fv[i]}')
        else:
            lbl = fv[i]
        stops.append(dict(value=v, color=cols[i], label=lbl, visible=True))
    out.update(min=lo, max=hi, classes=n, stops=stops)
    return out


def jsonable(style):
    """inf → 'inf' สำหรับ JSON"""
    def f(v):
        return 'inf' if isinstance(v, float) and math.isinf(v) else v
    s = dict(style)
    for k in ('stops', 'entries'):
        if k in s:
            s[k] = [dict(e, value=f(e['value'])) for e in s[k]]
    return s


def _num(v):
    return math.inf if v in ('inf', 'Infinity', None) else float(v)


# ---------- วาดไทล์ ----------
def render(ds, style, a, valid, res, row_lat):
    """a = ค่าดิบ (float64), valid = มีข้อมูล ; row_lat = ละติจูดแต่ละแถว (สำหรับคิดความหนาแน่น)"""
    rgba = np.zeros(a.shape + (4,), 'uint8')
    if style.get('metric') == 'density' and ds.get('value_type') == 'count':
        if ds['meta'].get('geographic'):
            a = a / gm.row_area_km2(res, row_lat)[:, None]
        else:
            a = a / (res * res / 1e6)
    ok = valid & np.isfinite(a)
    hv = style.get('hide_values') or []
    if hv:
        ok &= ~np.isin(a, [float(x) for x in hv])
    rg = style.get('range')
    if rg and len(rg) == 2:
        if rg[0] not in (None, ''):
            ok &= a >= float(rg[0])
        if rg[1] not in (None, ''):
            ok &= a <= float(rg[1])
    t = style.get('type')
    if t == 'paletted':
        ents = style.get('entries') or []
        if not ents:
            return rgba
        vals = np.array([float(e['value']) for e in ents])
        order = np.argsort(vals)
        vals = vals[order]
        lut = np.array([(*_rgb(ents[i]['color']).astype(int), 255 if ents[i].get('visible', True) else 0) for i in order], 'uint8')
        idx = np.clip(np.searchsorted(vals, a), 0, len(vals) - 1)
        hit = ok & (vals[idx] == a)
        rgba[hit] = lut[idx[hit]]
        return rgba
    if t == 'gray':
        lo, hi = float(style.get('min', 0)), float(style.get('max', 1))
        g = np.clip((a - lo) / ((hi - lo) or 1), 0, 1)
        if style.get('invert'):
            g = 1 - g
        g8 = (g * 255).astype('uint8')
        rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = g8
        rgba[..., 3] = np.where(ok, 255, 0)
        return rgba
    stops = style.get('stops') or []
    if not stops:
        return rgba
    sv = np.array([_num(s['value']) for s in stops])
    cols = np.array([_rgb(s['color']) for s in stops])
    vis = np.array([s.get('visible', True) for s in stops])
    interp = style.get('interp', 'linear')
    if interp == 'discrete':
        idx = np.clip(np.searchsorted(sv, a, side='left'), 0, len(sv) - 1)   # ค่า ≤ ขอบบน → ชั้นนั้น (แบบ QGIS)
        show = ok & vis[idx] & (a <= sv[idx])
        rgba[show, :3] = cols[idx[show]].astype('uint8')
        rgba[show, 3] = 255
    elif interp == 'exact':
        idx = np.clip(np.searchsorted(sv, a), 0, len(sv) - 1)
        show = ok & (sv[idx] == a) & vis[idx]
        rgba[show, :3] = cols[idx[show]].astype('uint8')
        rgba[show, 3] = 255
    else:
        av = np.clip(a, sv[0], sv[-1])
        for ch in range(3):
            rgba[..., ch] = np.interp(av, sv, cols[:, ch]).astype('uint8')
        idx = np.clip(np.searchsorted(sv, av, side='right') - 1, 0, len(sv) - 1)
        rgba[..., 3] = np.where(ok & vis[idx], 255, 0)
    return rgba


# ---------- QML ----------
def qml(ds, style):
    t = style.get('type')
    band = int(ds.get('band') or 1)
    head = ('<!DOCTYPE qgis PUBLIC \'http://mrcc.com/qgis.dtd\' \'SYSTEM\'>\n<qgis version="3.28" styleCategories="AllStyleCategories">\n <pipe>\n')
    tail = ' </pipe>\n</qgis>\n'
    hide = set(float(x) for x in (style.get('hide_values') or []))
    note = ''
    conv = 1.0
    if style.get('metric') == 'density' and ds.get('value_type') == 'count':
        # QGIS เห็นค่าดิบ (คน/พิกเซล) → แปลงเกณฑ์ความหนาแน่นเป็นค่าต่อพิกเซล ที่ละติจูดกลางของข้อมูล (ประมาณ)
        m = ds['meta']
        res = abs(m['transform'][0])
        conv = float(gm.row_area_km2(res, m.get('center_lat') or 0)) if m.get('geographic') else res * res / 1e6
        note = ' (แปลงจากความหนาแน่น ที่ละติจูดกลาง)'
    if t == 'paletted':
        ents = ''.join(f'<paletteEntry value="{e["value"]}" color="{e["color"]}" alpha="{255 if e.get("visible", True) and float(e["value"]) not in hide else 0}" '
                       f'label={quoteattr(str(e.get("label", e["value"])))}/>' for e in style.get('entries', []))
        return head + (f'  <rasterrenderer type="paletted" band="{band}" opacity="{style.get("opacity", 1)}" alphaBand="-1" nodataColor="">\n'
                       f'   <colorPalette>{ents}</colorPalette>\n  </rasterrenderer>\n') + tail
    if t == 'gray':
        inv = 'WhiteToBlack' if style.get('invert') else 'BlackToWhite'
        return head + (f'  <rasterrenderer type="singlebandgray" grayBand="{band}" gradient="{inv}" opacity="{style.get("opacity", 1)}" alphaBand="-1">\n'
                       f'   <contrastEnhancement><minValue>{style.get("min", 0)}</minValue><maxValue>{style.get("max", 1)}</maxValue>'
                       '<algorithm>StretchToMinimumMaximum</algorithm></contrastEnhancement>\n  </rasterrenderer>\n') + tail
    typ = {'discrete': 'DISCRETE', 'exact': 'EXACT'}.get(style.get('interp'), 'INTERPOLATED')
    items = ''
    for s in style.get('stops', []):
        v = _num(s['value'])
        vs = 'inf' if math.isinf(v) else repr(v * conv)
        items += f'<item value="{vs}" color="{s["color"]}" alpha="{255 if s.get("visible", True) else 0}" label={quoteattr(str(s.get("label", "")) + note)}/>'
    mn, mx = float(style.get('min', 0)) * conv, float(style.get('max', 1)) * conv
    return head + (f'  <rasterrenderer type="singlebandpseudocolor" band="{band}" opacity="{style.get("opacity", 1)}" alphaBand="-1" '
                   f'classificationMin="{mn}" classificationMax="{mx}">\n   <rastershader><colorrampshader colorRampType="{typ}" '
                   f'classificationMode="{ {"continuous": 1, "equal": 2, "quantile": 3}.get(style.get("mode"), 1) }" clip="0">{items}</colorrampshader></rastershader>\n'
                   '  </rasterrenderer>\n') + tail
