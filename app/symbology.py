# -*- coding: utf-8 -*-
"""สไตล์การแสดงผล raster แบบ QGIS (เก็บใน datasets.style เป็น JSON)

type = 'paletted'     ค่าเฉพาะ → สี (Paletted/Unique values)        entries: [{value, color, label, visible, opacity?}]
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
PALETTED_MAX = 4096          # เท่ากับเพดาน hist_int ของงานเตรียมข้อมูล (QGIS ไม่จำกัด แต่ตารางหลายพันแถวช้า)
DISCRETE_MAX = 32            # จำนวนเต็มไม่เกินเท่านี้ค่า (เช่น จำนวนปีท่วม 0–14) → สไตล์เริ่มต้นแสดงทีละค่า
# วิธีแบ่งชั้นของ Singleband pseudocolor — 3 ตัวแรกเหมือน QGIS (raster) · ที่เหลือ QGIS มีเฉพาะชั้นเวกเตอร์ หรือไม่มี
CLASS_MODES = ('continuous', 'equal', 'quantile', 'pretty', 'log', 'jenks', 'headtail', 'stddev')
SAMPLE_MODES = {'quantile', 'jenks', 'headtail', 'stddev', 'log'}   # ต้องใช้ค่าสุ่ม ไม่ใช่แค่ min/max
MODE_TH = {'continuous': 'ช่วงเท่ากัน', 'equal': 'ช่วงเท่ากัน', 'quantile': 'ควอนไทล์', 'pretty': 'เลขกลม',
           'log': 'ลอการิทึมเลขกลม', 'jenks': 'Natural breaks (Jenks)', 'headtail': 'Head/tail breaks', 'stddev': 'ส่วนเบี่ยงเบนมาตรฐาน'}


def _rgb(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], float)


def ent_alpha(e):
    """ความทึบของรายการสี 0–255: ซ่อน = 0 · opacity (0–1, ค่าเริ่ม 1) = ปรับเฉพาะสีนั้น"""
    if not e.get('visible', True):
        return 0
    try:
        return int(round(255 * min(1.0, max(0.0, float(e.get('opacity', 1))))))
    except (TypeError, ValueError):
        return 255


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


# ---------- อัลกอริทึมแบ่งชั้น: คืน "เกณฑ์ภายใน" (ขอบบนของแต่ละชั้น ยกเว้นชั้นสุดท้าย) ----------
def _nice_step(x):
    """ขนาดช่องแบบเลขกลม 1, 2, 2.5, 5 × 10ᵏ ที่ไม่น้อยกว่า x"""
    e = 10 ** math.floor(math.log10(x))
    return next(m * e for m in (1, 2, 2.5, 5, 10) if x <= m * e * (1 + 1e-9))


def pretty_breaks(lo, hi, n, integer=False):
    """เกณฑ์เลขกลมระหว่าง lo–hi ให้ได้ราว n ชั้น (แบบ pretty() ของ R / Pretty breaks ของ QGIS)"""
    if not hi > lo:
        return []
    x = (hi - lo) / max(n, 1)
    e = math.floor(math.log10(x))
    best = None
    for step in sorted({float(f'{m * 10 ** k:.12g}') for k in (e - 1, e, e + 1) for m in (1, 2, 2.5, 5)}):
        if integer and (step < 1 or not step.is_integer()):
            continue
        k0, k1 = math.floor(lo / step) + 1, math.ceil(hi / step) - 1
        b = [float(f'{k * step:.12g}') for k in range(k0, k1 + 1) if lo < k * step < hi]
        score = abs(len(b) + 1 - n)                         # จำนวนชั้นใกล้ที่ขอที่สุด · เสมอ → ขั้นเล็กกว่า (ชั้นมากกว่า)
        if 0 < len(b) <= 60 and (best is None or score < best[0]):
            best = (score, b)
    return best[1] if best else []


def log_breaks(plo, hi, n):
    """เกณฑ์ลอการิทึมแบบเลขกลม (1-10-100 / 1-3-10 / 1-2-5 / ละเอียดขึ้น) เลือกชุดที่ได้จำนวนชั้นใกล้ n ที่สุด
    สำหรับข้อมูลบวกที่เบ้ขวามาก (ประชากร ความหนาแน่นอาคาร แสงไฟ) — plo = ค่าบวกต่ำ ๆ ของข้อมูล"""
    if not (plo and plo > 0 and hi > plo):
        return []
    best = None
    for mult in ((1,), (1, 3), (1, 2, 5), (1, 1.5, 2, 3, 5, 7)):
        cand = {float(f'{m * 10 ** k:.6g}') for k in range(math.floor(math.log10(plo)) - 1, math.ceil(math.log10(hi)) + 1) for m in mult}
        vals = sorted(v for v in cand if plo * (1 + 1e-9) < v < hi * (1 - 1e-9))   # ปัดก่อนเทียบ (3×10⁻¹ = 0.30000000000000004)
        score = (abs(len(vals) - (n - 1)), len(vals))
        if best is None or score < best[0]:
            best = (score, vals)
    return best[1]


def jenks_breaks(s, n, m=1000):
    """Natural breaks (Fisher–Jenks) แบบแม่นตรง (ไม่ใช่ Jenks–Caspall แบบวนปรับ): แบ่งให้ผลรวมความแปรปรวนในชั้นน้อยที่สุด (dynamic programming)
    คิดจากควอนไทล์ m จุดของค่าสุ่ม (ตัวแทนการกระจาย) เพื่อให้เร็ว — O(n·m²) ทำแบบ vector ต่อแถว"""
    v = np.sort(np.asarray(s, 'float64'))
    if v.size > m:
        v = np.quantile(v, np.linspace(0, 1, m))
    u, n = v, min(n, np.unique(v).size)
    if n < 2:
        return []
    S, S2 = np.concatenate([[0.0], np.cumsum(u)]), np.concatenate([[0.0], np.cumsum(u * u)])
    M = u.size

    def ssd(j, i):                                         # ผลรวมกำลังสองรอบค่าเฉลี่ยของ u[j:i]
        return S2[i] - S2[j] - (S[i] - S[j]) ** 2 / (i - j)
    cost = np.full((n, M + 1), np.inf)
    back = np.zeros((n, M + 1), int)
    cost[0, 1:] = ssd(np.zeros(M, int), np.arange(1, M + 1))
    for k in range(1, n):
        for i in range(k + 1, M + 1):
            j = np.arange(k, i)
            c = cost[k - 1, j] + ssd(j, i)
            t = int(np.argmin(c))
            cost[k, i], back[k, i] = c[t], j[t]
    out, i = [], M
    for k in range(n - 1, 0, -1):
        j = back[k, i]
        out.append(float((u[j - 1] + u[j]) / 2))           # กึ่งกลางระหว่างชั้น → ถูกทั้งแบบ "≤ เกณฑ์" (สัญลักษณ์) และ "≥ เกณฑ์ ขึ้นชั้น" (ไบแวเรียต)
        i = j
    return sorted(set(out))


def headtail_breaks(s, n, head_max=0.4):
    """Head/tail breaks (Jiang 2013) สำหรับข้อมูลหางยาว: ตัดที่ค่าเฉลี่ยซ้ำ ๆ เฉพาะส่วนหัว (ค่ามากกว่าเฉลี่ย)
    หยุดเมื่อส่วนหัวเกิน 40% (ไม่หางยาวแล้ว) หรือครบ n ชั้น"""
    v, out = np.asarray(s, 'float64'), []
    while len(out) < n - 1 and v.size > 1:
        mu = float(v.mean())
        head = v[v > mu]
        if head.size == 0 or head.size / v.size > head_max:
            break
        out.append(mu)
        v = head
    return out


def stddev_breaks(s, lo, hi):
    """เกณฑ์ที่ค่าเฉลี่ย ± 0.5, 1.5, 2.5 SD (ชั้นกว้าง 1 SD ค่าเฉลี่ยอยู่กลางชั้นกลาง) — เหมาะกับข้อมูลรูประฆัง/หาค่าผิดปกติ"""
    v = np.asarray(s, 'float64')
    mu, sd = float(v.mean()), float(v.std())
    if not sd > 0:
        return []
    return [mu + k * sd for k in (-2.5, -1.5, -0.5, 0.5, 1.5, 2.5) if lo < mu + k * sd < hi]


def tidy(b, sig=2):
    """ปัดเกณฑ์เป็นเลขนัยสำคัญน้อยที่สุดที่ยังไม่ชนกัน → ป้ายอ่านง่าย (เช่น 1,437.82 → 1,400)"""
    for g in range(sig, 8):
        r = [float(f'{x:.{g}g}') for x in b]
        if len(set(r)) == len(r) and r == sorted(r):
            return r
    return list(b)


def mode_breaks(mode, s, lo, hi, n, integer=False):
    """เกณฑ์ภายในของแต่ละวิธี (ขอบบนของชั้น ยกเว้นชั้นสุดท้าย) ทั้งหมดอยู่ในช่วง [lo, hi)"""
    if mode == 'quantile':
        from .engine import EngineError, quantile_breaks
        try:
            return quantile_breaks(s, n)                    # ทนค่าซ้ำ: ค่าที่กอง (เช่น 0) ได้ชั้นของตัวเอง — ไม่ปัดค่า
        except EngineError as e:
            raise ValueError(str(e))
    if mode == 'pretty':
        b = pretty_breaks(lo, hi, n, integer)
    elif mode == 'log':
        pos = s[s > 0] if s is not None else np.array([])
        b = log_breaks(float(np.quantile(pos, 0.05)) if pos.size else lo, hi, n)   # หางล่างสุด 5% (เช่น 0.3–1 คน) ไม่ต้องมีชั้นของตัวเอง
        if not b:
            raise ValueError('ลอการิทึมใช้ได้เฉพาะข้อมูลที่มีค่าบวก — ลองเลขกลมหรือ Jenks')
    elif mode == 'jenks':
        b = tidy(jenks_breaks(s[(s >= lo) & (s <= hi)], n), 3)
    elif mode == 'headtail':
        b = tidy(headtail_breaks(s, n), 2)
        if not b:
            raise ValueError('ข้อมูลไม่หางยาวพอสำหรับ Head/tail breaks (ค่าที่เกินค่าเฉลี่ยมีมากกว่า 40%) — ลอง Jenks หรือควอนไทล์')
    elif mode == 'stddev':
        b = tidy(stddev_breaks(s, lo, hi), 3)
    else:                                                   # continuous / equal
        b = [lo + (hi - lo) * i / n for i in range(1, n)]
    if integer:
        b = [float(math.floor(x)) for x in b]               # ข้อมูลจำนวนเต็ม: เกณฑ์เป็นจำนวนเต็ม (ค่า ≤ เกณฑ์)
    return sorted({x for x in b if lo <= x < hi})


def is_integer_data(s):
    return s is not None and s.size > 0 and bool(np.all(np.mod(s, 1) == 0))


def discrete_values(ds, s=None, limit=DISCRETE_MAX):
    """ค่าทั้งหมดถ้าข้อมูลเป็นจำนวนเต็มไม่กี่ค่า (≤ DISCRETE_MAX) — จากฮิสโทแกรมจำนวนเต็มของงานเตรียมข้อมูล
    หรือจากค่าสุ่ม + min/max (ค่าสุ่มอาจพลาดค่าที่หายาก จึงใช้ทุกจำนวนเต็มระหว่าง min–max)"""
    st = ds.get('stats') or {}
    vals = [v for v, _ in (st.get('hist_int') or [])]
    if vals:
        return vals if len(vals) <= limit else None
    if not is_integer_data(s):
        return None
    lo, hi = st.get('min'), st.get('max')
    if lo is None or hi is None:
        lo, hi = float(s.min()), float(s.max())
    if float(lo).is_integer() and float(hi).is_integer() and 0 <= hi - lo < limit:
        ex = set(ds.get('exclude_values') or [])
        return [v for v in range(int(lo), int(hi) + 1) if v not in ex]
    return None


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
    # ทุกประเภทค่า: จำนวนเต็มไม่กี่ค่า (เช่น จำนวนปีท่วม 0–14, ชั้นที่ดิน) → แสดงทีละค่า
    # (เดิม "จำนวนนับ" ได้ชุดเกณฑ์ประชากร 10–3,000 คน/ตร.กม. ตายตัวเสมอ ไม่ดูข้อมูล → ข้อมูล 0–14 ได้ป้ายมั่ว)
    raw = sample_values(ds, 'value') if not (st.get('hist_int')) else None
    vals = discrete_values(ds, raw, 64 if vt == 'class' else DISCRETE_MAX)
    if vals:
        out = ordinal_style(vals)
        if vt == 'count':
            out['note'] = (f'ข้อมูลเป็นจำนวนเต็ม {len(vals)} ค่า → แสดงทีละค่า (ค่าดิบ) · ถ้าเป็นรหัส/จำนวนครั้ง/จำนวนปี '
                           'ไม่ใช่จำนวนนับที่รวมตามพื้นที่ได้ ควรตั้งประเภทค่าเป็น "ชั้น"')
        return out
    s0 = raw if raw is not None else sample_values(ds, 'value')
    if vt != 'class' and spans_zero(s0) and (data_profile(ds, s0) == 'generic' or CHANGE_NAME.search(ds.get('name') or '')):
        return diverging_default(ds, s0)                       # ดัชนี (NDVI) / night light คงสีของตัวเอง เว้นแต่เป็นผลต่าง/แนวโน้ม
    if vt == 'count':
        return auto_classes(ds, metric='density', ramp='YlOrBr', hide_zero=True)
    return continuous_default(ds)


CHANGE_NAME = __import__('re').compile(r'change|chg|diff|delta|trend|slope|anomal|เปลี่ยน|ผลต่าง|แนวโน้ม', __import__('re').I)


def spans_zero(s, frac=0.02):
    """มีทั้งค่าลบและบวกอย่างละ ≥ 2% (เช่น ประชากรเปลี่ยนแปลง, แนวโน้ม, ผลต่างสองปี) — ไม่ใช่ดัชนี −1…1 ที่มีสีของตัวเอง"""
    if s is None or not s.size:
        return False
    if not ((s < 0).mean() >= frac and (s > 0).mean() >= frac):
        return False
    # สองฝั่งต้องขนาดพอ ๆ กัน: night light ลบเป็นสัญญาณรบกวน (−0.3 กับ +62) · DEM ต่ำกว่าระดับทะเลนิดหน่อย (−5 กับ +1,500) ไม่ใช่ข้อมูลเพิ่ม/ลด
    mn, mp = float(np.quantile(-s[s < 0], 0.98)), float(np.quantile(s[s > 0], 0.98))
    return min(mn, mp) >= 0.05 * max(mn, mp)


def diverging_default(ds, s):
    """ข้อมูลเพิ่ม/ลด: สีสองขั้ว RdBu แยกที่ 0 (แดง = ลด · น้ำเงิน = เพิ่ม) · แต่ละฝั่งแบ่งชั้นของตัวเอง
    ขนาดเบ้มาก (ส่วนใหญ่ใกล้ 0 มีค่าสุดโต่งไม่กี่จุด) → ลอการิทึมเลขกลม ไม่งั้นเลขกลม · ค่า 0 พอดีเยอะ (≥ 5%) → ซ่อน (= ไม่เปลี่ยน)
    ก่อน 1.0.44: ข้อมูลแบบนี้ได้สไตล์ "ความหนาแน่น" หรือ viridis ตัด 2–98% → ค่าลบเกือบหายจากแผนที่ ต้องมาปรับเองทุกครั้ง"""
    a = np.abs(s[s != 0])
    skewed = a.size and np.quantile(a, 0.98) > 20 * max(float(np.quantile(a, 0.5)), 1e-12)
    zero = float((s == 0).mean())
    mode = 'log' if skewed else 'pretty'
    out = classify(ds, dict(type='pseudocolor', ramp='RdBu', mode=mode, interp='discrete', classes=6, center=0, metric='value',
                            hide_values=[0] if zero >= 0.05 else []))
    if out.get('profile') is None and data_profile(ds, s) == 'index':
        out['profile'] = 'index'
    out['note'] = (f'ข้อมูลมีทั้งค่าลบ ({(s < 0).mean() * 100:.0f}%) และบวก ({(s > 0).mean() * 100:.0f}%) → สีสองขั้วแยกที่ 0 '
                   f'(แดง = ลด · น้ำเงิน = เพิ่ม) แต่ละฝั่ง{MODE_TH[mode]}ของตัวเอง'
                   + (f' · ค่า 0 พอดี {zero * 100:.0f}% ซ่อนไว้ (= ไม่เปลี่ยน)' if zero >= 0.05 else '')
                   + ' · ปรับจุดกลางได้ที่ "จุดกลาง"')
    return out


def ordinal_style(vals):
    """Paletted ทีละค่า · เรียงต่อเนื่อง → ไล่สีตามลำดับ (YlGnBu) · ไม่ต่อเนื่อง → สีหมวดหมู่"""
    ordinal = vals[-1] - vals[0] == len(vals) - 1
    ramp = 'YlGnBu' if ordinal else 'Set3 (หมวดหมู่)'
    cols = ramp_colors(ramp, len(vals)) if not ordinal else [ramp_at(ramp, 0.25 + 0.75 * i / max(len(vals) - 1, 1)) for i in range(len(vals))]
    # ลำดับที่เริ่มจาก 0 (เช่น จำนวนปีท่วม 0 = ไม่เคยท่วม) → ซ่อน 0 ไว้ก่อน ไม่ให้ทับทั้งแผนที่ (เปิดคืนได้)
    hide0 = ordinal and vals[0] == 0 and len(vals) > 1
    return dict(type='paletted', ramp=ramp, metric='value', hide_values=[0] if hide0 else [],
                entries=[dict(value=v, color=c, label=fmtv(v), visible=not (hide0 and v == 0)) for v, c in zip(vals, cols)])


def auto_classes(ds, metric='value', ramp='YlOrBr', hide_zero=False):
    """จัดชั้นอัตโนมัติจากข้อมูลจริง (แทนชุดเกณฑ์ตายตัว): ข้อมูลบวกเบ้ขวามาก (p98 / มัธยฐาน > 20 เช่น ประชากร)
    → ลอการิทึมเลขกลม 7 ชั้น · ไม่เบ้ → เลขกลมช่วงเท่ากัน 6 ชั้น · ช่วงบนตัดที่ p98 ชั้นสุดท้ายเปิด (> ค่า)"""
    s = sample_values(ds, metric)
    if s is None or not s.size:
        # ยังไม่มีค่าสุ่ม (งานเตรียมข้อมูลยังไม่เสร็จ/ไฟล์สุ่มหาย) → ความหนาแน่นคิดไม่ได้ ใช้ค่าต่อพิกเซลจากสถิติไฟล์ไปก่อน
        st = ds.get('stats') or {}
        pct = st.get('pct') or {}
        lo, hi = pct.get('2', st.get('min')), pct.get('98', st.get('max'))
        if lo is None or hi is None or not hi > lo:
            return continuous_default(ds)
        out = classify(ds, dict(type='pseudocolor', ramp=ramp, mode='pretty', interp='discrete', classes=6, min=min(float(lo), 0.0),
                                max=float(hi), metric='value', hide_values=[0] if hide_zero else []))
        out['note'] = 'ยังไม่มีค่าสุ่มของชุดนี้ → จัดชั้นเลขกลมจากค่าต่อพิกเซลไปก่อน · เตรียมข้อมูลเสร็จแล้วกด "คืนค่าเริ่มต้น" เพื่อจัดชั้นจากข้อมูลจริง'
        return out
    pos = s[s > 0] if hide_zero else s
    pos = pos if pos.size else s
    lo = float(min(s.min(), 0.0)) if s.min() >= 0 else float(np.quantile(s, 0.02))
    hi = float(np.quantile(pos, 0.98))
    skewed = s.min() >= 0 and pos.size and np.quantile(pos, 0.98) > 20 * max(float(np.quantile(pos, 0.5)), 1e-12)
    mode, n = ('log', 7) if skewed else ('pretty', 6)
    out = classify(ds, dict(type='pseudocolor', ramp=ramp, mode=mode, interp='discrete', classes=n, min=lo, max=hi,
                            metric=metric, hide_values=[0] if hide_zero else []))
    out['note'] = (f'จัดชั้นอัตโนมัติจากข้อมูล: {MODE_TH[mode]} {out["classes"]} ชั้น'
                   + (' (ข้อมูลเบ้ขวามาก ค่าส่วนใหญ่ต่ำ มีค่าสูงไม่กี่จุด)' if skewed else '')
                   + ' · เปลี่ยนวิธีได้ที่ Mode แล้วกด Classify')
    return out


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


def stretch(s):
    """min/max ตัดสะสม 2–98% แบบ QGIS — แต่ถ้าศูนย์กองเกิน 30% (เช่น night light ทั้งโลก: ทะเล/ที่มืด 97%)
    98% ของทุกพิกเซลจะได้แค่ ~1 → ไฟทุกดวงขาวโพลน ; กรณีนี้ใช้ 98% ของพิกเซลที่มีค่า (> 0) เป็นค่าบน
    ศูนย์ยังแสดงเป็นสีปลายล่าง (ดำ) ไม่ได้ถูกซ่อน"""
    lo, hi = float(np.quantile(s, 0.02)), float(np.quantile(s, 0.98))
    pos = s[s > 0]
    if (s == 0).mean() > 0.3 and pos.size:
        lo, hi = min(lo, 0.0), float(np.quantile(pos, 0.98))
    if hi <= lo:
        hi = lo + (abs(lo) or 1) * 1e-3
    return lo, hi


def continuous_default(ds):
    """สไตล์เริ่มต้นของข้อมูลต่อเนื่อง แบบ QGIS: Singleband pseudocolor · ไล่สีเชิงเส้น · min/max ตัดสะสม 2–98%
    index → RdYlGn (น้ำตาล→เขียว) · nightlight → Singleband gray ดำ→ขาว ทึบ 100% (เหมือนเปิดใน QGIS) · อื่นๆ → viridis"""
    st = ds.get('stats') or {}
    s = sample_values(ds, 'value')
    prof = data_profile(ds, s)
    hide = []
    if s is not None and s.size:
        lo, hi = stretch(s)
    else:
        pct = st.get('pct') or {}
        lo, hi = pct.get('2'), pct.get('98')
        if lo is None or hi is None:
            lo, hi = st.get('min', 0) or 0, st.get('max', 1) or 1
    if hi <= lo:
        hi = lo + (abs(lo) or 1) * 1e-3
    if prof == 'nightlight':
        # แบบที่เปิดใน QGIS: Singleband gray ดำ→ขาว · ทึบ 100% · ไม่ซ่อนค่า
        # (เดิมซ่อน 0 + ทึบ 85% → พื้นมืดโปร่งสลับกับพิกเซลแสงจาง เป็นลายกระดำกระด่างทับภาพดาวเทียม)
        return dict(type='gray', min=lo, max=hi, invert=False, metric='value', hide_values=[], opacity=1.0, profile=prof)
    ramp = {'index': 'RdYlGn'}.get(prof, 'viridis')
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
        if len(vals) > PALETTED_MAX:
            raise ValueError(f'ค่าไม่ซ้ำ {len(vals):,} ค่า มากเกินสำหรับแบบค่าเฉพาะ (≤ {PALETTED_MAX:,}) — ข้อมูลต่อเนื่อง/ทศนิยมใช้ Singleband pseudocolor แทน')
        ex = ds.get('exclude_values') or []
        vals = [v for v in vals if v not in ex]
        cols = ramp_colors(ramp, len(vals), inv)
        out['entries'] = [dict(value=v, color=c, label=fmtv(v), visible=True) for v, c in zip(vals, cols)]
        return out
    if t == 'gray':
        if req.get('min') is None or req.get('max') is None:
            s = sample_values(ds, metric)
            if s is None or not s.size:
                raise ValueError('ยังไม่มีค่าสุ่ม — รองานเตรียมข้อมูลให้เสร็จก่อน')
            out['min'], out['max'] = stretch(s)
        return out
    n = max(2, min(int(req.get('classes', 5)), 64))
    mode, interp = req.get('mode', 'continuous'), req.get('interp', 'linear')
    if mode not in CLASS_MODES:
        mode = out['mode'] = 'continuous'
    lo, hi = req.get('min'), req.get('max')
    s = sample_values(ds, metric)                 # ใช้ตัดสินว่าเป็นจำนวนเต็มด้วย (ป้ายแบบ 1–4, 5–9)
    if req.get('center') not in (None, ''):
        return _classify_center(out, float(req['center']), s, n, mode, interp, ramp, inv, lo, hi)
    out.pop('center', None)
    if (lo is None or hi is None or mode in SAMPLE_MODES) and (s is None or not s.size):
        raise ValueError('ยังไม่มีค่าสุ่ม — รองานเตรียมข้อมูลให้เสร็จก่อน')
    if lo is None or hi is None:
        slo, shi = stretch(s)
        lo = slo if lo is None else lo
        hi = shi if hi is None else hi
    lo, hi = float(lo), float(hi)
    if hi <= lo:
        hi = lo + 1
    integer = is_integer_data(s) and lo.is_integer()
    ss = None
    if s is not None and s.size:
        ss = s[(s >= lo) & (s <= hi)]
        ss = ss if ss.size else s
    if mode == 'quantile' and interp != 'discrete':
        vals = [float(np.quantile(ss, i / (n - 1))) for i in range(n)]
    else:
        b = mode_breaks(mode, ss, lo, hi, n, integer)
        if interp == 'discrete':
            vals = b + [math.inf]
        elif mode in ('continuous', 'equal'):
            vals = [lo + (hi - lo) * i / (n - 1) for i in range(n)]
        else:
            vals = [lo] + [x for x in b if x > lo] + [hi]
    vals = sorted(set(vals))                     # ข้อมูลกองที่ค่าเดียว (เช่น จำนวนเต็ม) → เกณฑ์ซ้ำ → รวมชั้น
    n = len(vals)
    cols = ramp_colors(ramp, n, inv)
    out.update(min=lo, max=hi, classes=n, mode=mode,
               stops=[dict(value=v, color=cols[i], label=l, visible=True) for i, (v, l) in enumerate(zip(vals, class_labels(vals, lo, interp, integer)))])
    return out


def _classify_center(out, c, s, n, mode, interp, ramp, inv, lo=None, hi=None):
    """สองขั้วแยกที่จุดกลาง c (QGIS: Diverging + ตั้ง min/max สมมาตรเอง — ที่นี่ทำให้อัตโนมัติ)
    - ไล่สี: ช่วงสมมาตรรอบ c (c อยู่กลาง ramp พอดี) จาก p98 ของระยะห่างจาก c ฝั่งที่ไกลกว่า
    - แบ่งชั้น: ฝั่งต่ำกว่า c และสูงกว่า c แบ่งด้วยวิธีเดียวกัน (บนขนาดห่างจาก c) คนละครึ่ง · c เป็นเกณฑ์เสมอ
      สีฝั่งลบมาจากครึ่งล่างของ ramp ฝั่งบวกจากครึ่งบน → ชั้นติด c สีอ่อน ไกล c สีเข้ม"""
    if s is None or not s.size:
        raise ValueError('ยังไม่มีค่าสุ่ม — รองานเตรียมข้อมูลให้เสร็จก่อน')
    below, above = c - s[s < c], s[s > c] - c
    mlo = float(c - lo) if lo is not None and lo < c else float(np.quantile(below, 0.98)) if below.size else 0.0
    mhi = float(hi - c) if hi is not None and hi > c else float(np.quantile(above, 0.98)) if above.size else 0.0
    if mlo <= 0 and mhi <= 0:
        raise ValueError(f'ข้อมูลไม่มีค่าห่างจากจุดกลาง {fmtv(c)} — ลองจุดกลางอื่น หรือปิดจุดกลาง')
    if interp != 'discrete':
        m = max(mlo, mhi)
        k = n if n % 2 else n + 1                              # จำนวนจุดสีคี่ → c เป็นจุดสีกลางพอดี
        vals = [c - m + 2 * m * i / (k - 1) for i in range(k)]
        cols = ramp_colors(ramp, k, inv)
        out.update(min=c - m, max=c + m, classes=k, mode=mode, center=c,
                   stops=[dict(value=v, color=col, label=l, visible=True) for v, col, l in zip(vals, cols, class_labels(vals, c - m, interp))])
        return out
    nl = n // 2 if below.size else 0
    nh = n - nl if above.size else 0
    if nl and not nh:
        nl = n

    def side(mag, m, k):
        if k <= 1 or m <= 0:
            return []
        mm = mag[mag <= m] if mag.size else mag
        md = mode if mode not in ('continuous',) else 'equal'
        try:
            if md == 'log':                                    # แต่ละฝั่งเริ่มที่ p25 ของขนาด — p5 ได้ชั้นจิ๋ว (−0.0001 – 0) ที่ไม่มีความหมาย
                b = log_breaks(float(np.quantile(mm, 0.25)), m, k) if mm.size else []
                if not b:
                    raise ValueError
            else:
                b = mode_breaks(md, mm if mm.size else mag, 0.0, m, k)
        except ValueError:                                     # วิธีนี้ใช้กับฝั่งนี้ไม่ได้ (เช่น head/tail ไม่หางยาว) → เลขกลม
            b = mode_breaks('pretty', mm, 0.0, m, k)
        b = [x for x in b if 0 < x < m]
        return tidy(b, 2) if md in ('quantile', 'equal') else b    # ป้ายอ่านง่าย (0.0565 → 0.057)
    neg = sorted(c - x for x in side(below, mlo, nl))
    pos = sorted(c + x for x in side(above, mhi, nh))
    vals = neg + ([c] if nl else []) + pos + [math.inf]
    kn = len(neg) + 1 if nl else 0
    kp = len(vals) - kn
    cols = [ramp_at(ramp, 0.5 * (j + 0.5) / kn * 0.94, inv) for j in range(kn)] + \
           [ramp_at(ramp, 1 - 0.5 * (kp - 1 - j + 0.5) / kp * 0.94, inv) for j in range(kp)]
    labels = class_labels(vals, vals[0], 'discrete')
    out.update(min=c - mlo, max=c + mhi, classes=len(vals), mode=mode, center=c,
               stops=[dict(value=v, color=col, label=l, visible=True) for v, col, l in zip(vals, cols, labels)])
    return out


def fmt_nums(vals):
    """ตัวเลขชุดหนึ่งสำหรับป้าย: ไม่ใช้รูปวิทยาศาสตร์ (1.01e+03 → 1,010) · ทศนิยมตามขนาดค่า
    (≥ 100 ไม่มีทศนิยม · ≥ 1 ไม่เกิน 2 ตำแหน่ง · < 1 เลขนัยสำคัญ 2 ตัว) · เพิ่มทศนิยมจนไม่มีสองค่าแสดงเหมือนกัน"""
    def dec(x):
        a = abs(x)
        if a == 0 or a >= 100:
            return 0
        return 1 if a >= 10 else (2 if a >= 1 else min(8, 1 - math.floor(math.log10(a))))
    xs = [float(x) for x in vals]
    for extra in range(0, 6):
        out = []
        for x in xs:
            if math.isinf(x):
                out.append('∞')
                continue
            d = dec(x) + extra
            s = f'{x:,.{d}f}'
            out.append(s.rstrip('0').rstrip('.') if '.' in s else s)
        fin = [o for o, x in zip(out, xs) if not math.isinf(x)]
        if len(set(fin)) == len(fin):
            return out
    return out


def class_labels(vals, lo, interp, integer=False):
    """ป้ายชั้นที่อ่านเป็นภาษาคน
    จำนวนเต็ม (ค่า ≤ เกณฑ์): 1–4 · 5–9 · ≥ 10   ·   ทศนิยม: 0 – 3 · 3 – 10 · > 1,000   ·   linear: ค่าที่จุดสี"""
    if interp != 'discrete':
        return fmt_nums(vals)
    fin = [v for v in vals if not math.isinf(v)]
    if integer and all(float(v).is_integer() for v in fin):
        def rng(a, b):
            return fmtv(a) if a == b else f'{fmtv(a)}–{fmtv(b)}'
        out, prev = [], lo - 1
        for v in vals:
            out.append(f'≥ {fmtv(prev + 1)}' if math.isinf(v) else rng(prev + 1, v))
            prev = v
        return out
    fv = fmt_nums([lo] + list(vals))                         # หลักพอให้ป้ายไม่ซ้ำกัน ไม่มี 1.01e+03
    out = []
    for i, v in enumerate(vals):
        if math.isinf(v):
            out.append(f'> {fv[i]}')
        elif i == 0:
            out.append(f'{fv[0]} – {fv[1]}' if lo < v else f'≤ {fv[1]}')
        else:
            out.append(f'{fv[i]} – {fv[i + 1]}')
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
        lut = np.array([(*_rgb(ents[i]['color']).astype(int), ent_alpha(ents[i])) for i in order], 'uint8')
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
        ents = ''.join(f'<paletteEntry value="{e["value"]}" color="{e["color"]}" alpha="{ent_alpha(e) if float(e["value"]) not in hide else 0}" '
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
