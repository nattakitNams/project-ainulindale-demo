# -*- coding: utf-8 -*-
"""จัดหน้าแผนที่แบบแคนวาส (v0.5)

เซิร์ฟเวอร์วาดเฉพาะ "ภาพ" ที่เบราว์เซอร์ทำเองไม่ได้:
  • ภาพแผนที่หลัก (แผนที่พื้นหลัง + ชั้นข้อมูล + เส้นขอบเขต) — ภาพเป็น EPSG:4326 เชิงเส้น เต็มกรอบพอดี
    → เบราว์เซอร์วางกริดพิกัด ป้ายชื่อ มาตราส่วน ทับได้ตรงพิกัด
  • ภาพแผนที่แสดงตำแหน่ง (inset)
ส่วนอื่นทั้งหมด (ข้อความ คำอธิบาย มาตราส่วน ทิศเหนือ กราฟ) เป็น HTML/SVG ใน static/report.js
ส่งออก PDF/PNG = เปิดหน้าเดียวกันใน Edge/Chrome แบบ headless แล้วสั่งพิมพ์
→ ตัวอักษรไทยจัดวางถูกต้อง (สระ/วรรณยุกต์ซ้อน) และหน้าจอ = ไฟล์ที่ได้"""
import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path

from . import db, layout, tiles
from .config import APP_VERSION, DIRS

RDIR = DIRS['cache'] / 'report'
_plock = threading.Lock()                 # matplotlib (pyplot) ไม่ปลอดภัยต่อหลายเธรด
PRINTS = {}                               # token → เอกสารที่รอ Edge มาเปิด


def _h(obj):
    return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:20]


def _layers(m):
    out = []
    for l in m.get('layers') or []:
        kind, d = layout._resolve(l['key'])
        if d is None:
            continue
        if kind == 'raster' and l.get('rstyle'):
            d = dict(d, style=l['rstyle'])
        out.append((d.get('name'), kind, d, l.get('style'), float(l.get('opacity', 1))))
    return out


def _sig(layers, m):
    """ลายเซ็นข้อมูลที่มีผลต่อภาพ (ไฟล์เปลี่ยน/สไตล์เปลี่ยน → วาดใหม่)"""
    sig = []
    for n, k, d, st, op in layers:
        # raster: สไตล์ที่ใช้วาดจริง (รวมสไตล์เริ่มต้นที่ไม่ได้บันทึก) — ไม่งั้นเปลี่ยนสไตล์เริ่มต้นแล้วได้ภาพเก่าจากแคช
        sig.append((k, d.get('id'), d.get('fingerprint'), tiles.style_of(d) if k == 'raster' else st, op))
    bd = (m.get('boundary') or {}).get('key')
    if bd:
        k, d = layout._resolve(bd)
        sig.append(('bd', bd, (d or {}).get('fingerprint')))
    return sig


def base_extent(m, layers):
    ex = m.get('extent') or {}
    ext = None
    if ex.get('type') == 'aoi' and ex.get('aoi_id'):
        a = db.get('aoi', int(ex['aoi_id']))
        ext = list(a['bbox']) if a else None
    elif ex.get('type') == 'bbox' and ex.get('bbox'):
        ext = list(ex['bbox'])
    if not ext:
        bs = [b for b in (layout._bounds(k, d) for _, k, d, *_ in layers) if b]
        ext = [min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs)] if bs else [97.3, 5.6, 105.7, 20.5]
    p = 0.04
    return [ext[0] - (ext[2] - ext[0]) * p, ext[1] - (ext[3] - ext[1]) * p, ext[2] + (ext[2] - ext[0]) * p, ext[3] + (ext[3] - ext[1]) * p]


def ext_from_view(v, w, h):
    """view = {cx, cy, span (ความสูงเป็นองศาละติจูด)} + ขนาดกรอบ (มม.) → [x0, y0, x1, y1]"""
    k = math.cos(math.radians(max(min(v['cy'], 85), -85)))
    dh = float(v['span'])
    dw = dh * (w / h) / k
    return [v['cx'] - dw / 2, v['cy'] - dh / 2, v['cx'] + dw / 2, v['cy'] + dh / 2]


def auto_view(m, w, h, layers=None):
    layers = layers if layers is not None else _layers(m)
    e = layout._fit_extent(base_extent(m, layers), w, h)
    return dict(cx=(e[0] + e[2]) / 2, cy=(e[1] + e[3]) / 2, span=e[3] - e[1])


def _fig(w_mm, h_mm, dpi):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(w_mm / 25.4, h_mm / 25.4), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis('off')
    return plt, fig, ax


def render_map(m, w, h, dpi=110, view=None):
    """ภาพแผนที่หลัก → {src, ext, view, labels, attrib, sources}"""
    w, h, dpi = float(w), float(h), int(dpi)
    layers = _layers(m)
    view = view or auto_view(m, w, h, layers)
    ext = ext_from_view(view, w, h)
    key = _h(dict(m={k: m.get(k) for k in ('basemap', 'basemap_opacity', 'boundary', 'layers')}, w=round(w, 1), h=round(h, 1), dpi=dpi,
                  view={k: round(float(v), 6) for k, v in view.items()}, sig=_sig(layers, m), v=2))
    RDIR.mkdir(parents=True, exist_ok=True)
    png, meta = RDIR / f'{key}.png', RDIR / f'{key}.json'
    if png.exists() and meta.exists():
        return json.loads(meta.read_text(encoding='utf-8'))
    px_w, px_h = max(int(w / 25.4 * dpi), 50), max(int(h / 25.4 * dpi), 50)
    bm = layout.BASEMAP_ALIAS.get(m.get('basemap'), m.get('basemap') or 'none')
    attrib, labels, sources = [], [], [n for n, *_ in layers]
    with _plock:
        plt, fig, ax = _fig(w, h, dpi)
        try:
            ax.set_xlim(ext[0], ext[2]), ax.set_ylim(ext[1], ext[3])
            if bm in layout.BASEMAPS:
                img = layout._mosaic_4326(lambda z, x, y: layout._tile_bytes(bm, z, x, y), ext, px_w, px_h, 160)
                if img is not None:
                    ax.imshow(img, extent=[ext[0], ext[2], ext[1], ext[3]], alpha=float(m.get('basemap_opacity', 1)), zorder=1, interpolation='bilinear')
                    attrib.append(layout.BASEMAPS[bm][1])
                else:
                    attrib.append('(โหลดแผนที่พื้นหลังไม่ได้)')
            for n, kind, d, st, op in reversed(layers):
                try:
                    if kind == 'raster':
                        layout._raster(ax, d, ext, px_w, px_h, op)
                    elif kind in ('vector', 'linkdata', 'aoi'):
                        layout._vector(ax, kind, d, ext, st, op, px_w=px_w)
                    elif kind == 'linktile':
                        layout._linktile(ax, d, ext, px_w, px_h, op)
                except Exception as e:
                    print('[แคนวาส] วาดชั้นไม่ได้', n, e)
            bd = m.get('boundary') or {}
            if bd.get('key'):
                kind, d = layout._resolve(bd['key'])
                if d is not None:
                    try:
                        g = layout._vector_gdf(kind, d, ext, px_w)
                        if g is not None and len(g):
                            g.boundary.plot(ax=ax, color=bd.get('color', '#333333'), linewidth=float(bd.get('width', .8)), zorder=12)
                            sources.append(d.get('name'))
                            lf = bd.get('label_field')
                            if lf and lf in g.columns and len(g) <= 600:
                                for (_, r), pt in zip(g.iterrows(), g.representative_point()):
                                    if ext[0] < pt.x < ext[2] and ext[1] < pt.y < ext[3] and r[lf] is not None:
                                        labels.append(dict(x=round(pt.x, 5), y=round(pt.y, 5), t=str(r[lf])))
                    except Exception as e:
                        print('[แคนวาส] ขอบเขต', e)
            ax.set_xlim(ext[0], ext[2]), ax.set_ylim(ext[1], ext[3])
            fig.savefig(png, dpi=dpi, transparent=True)
        finally:
            plt.close(fig)
    out = dict(src=f'/api/report/img/{key}.png', ext=ext, view=view, labels=labels, attrib=attrib, sources=list(dict.fromkeys(sources)), w=w, h=h)
    meta.write_text(json.dumps(out, ensure_ascii=False), encoding='utf-8')
    return out


def render_inset(main_ext, w, h, dpi=110, basemap='esri_light', zoom=1.0):
    """แผนที่แสดงตำแหน่ง: พื้นหลังรอบกรอบแผนที่หลัก (กรอบสีแดงวาดในเบราว์เซอร์)"""
    w, h, dpi = float(w), float(h), int(dpi)
    cx, cy = (main_ext[0] + main_ext[2]) / 2, (main_ext[1] + main_ext[3]) / 2
    span = min(max(main_ext[2] - main_ext[0], main_ext[3] - main_ext[1]) * 3 + 4, 150) / max(float(zoom), .1)
    iext = layout._fit_extent([cx - span / 2, cy - span / 2, cx + span / 2, cy + span / 2], w, h)
    iext[1], iext[3] = max(iext[1], -85), min(iext[3], 85)
    bm = layout.BASEMAP_ALIAS.get(basemap, basemap)
    key = _h(dict(t='inset', e=[round(v, 5) for v in iext], w=round(w, 1), h=round(h, 1), dpi=dpi, bm=bm))
    RDIR.mkdir(parents=True, exist_ok=True)
    png = RDIR / f'{key}.png'
    if not png.exists():
        px_w, px_h = max(int(w / 25.4 * dpi), 40), max(int(h / 25.4 * dpi), 40)
        with _plock:
            plt, fig, ax = _fig(w, h, dpi)
            try:
                ax.set_xlim(iext[0], iext[2]), ax.set_ylim(iext[1], iext[3])
                img = layout._mosaic_4326(lambda z, x, y: layout._tile_bytes(bm, z, x, y), iext, px_w, px_h, 24) if bm in layout.BASEMAPS else None
                if img is not None:
                    ax.imshow(img, extent=[iext[0], iext[2], iext[1], iext[3]], zorder=1)
                else:
                    ax.set_facecolor('#e9edf3')
                ax.set_xlim(iext[0], iext[2]), ax.set_ylim(iext[1], iext[3])
                fig.savefig(png, dpi=dpi, facecolor='#e9edf3')
            finally:
                plt.close(fig)
    return dict(src=f'/api/report/img/{key}.png', ext=iext)


def info(m):
    """ข้อมูลประกอบหน้า: รายการคำอธิบาย · สถิติ · ที่มา · ชื่อแหล่งข้อมูล"""
    layers = _layers(m)
    leg = layout._legend_items([(n, k, d, st) for n, k, d, st, _ in layers])
    for it in leg:
        it.pop('lin', None)
    bd = m.get('boundary') or {}
    if bd.get('key'):
        k, d = layout._resolve(bd['key'])
        if d is not None:
            leg.append(dict(type='line', name=d.get('name'), color=bd.get('color', '#333333'), width=float(bd.get('width', .8))))
    main = next((d for _, k, d, *_ in layers if k in ('raster', 'vector') and layout._lineage(d)), None) \
        or next((d for _, k, d, *_ in layers if k == 'raster'), None)
    stats = layout._stats(main) if main else None
    if (not stats or not stats.get('kpi')) and main and main.get('stats'):          # ไม่มี lineage → ตัวเลขจากสถิติของไฟล์
        s, vt = main['stats'], main.get('value_type')
        k = []
        if vt == 'count' and s.get('sum') is not None:
            k.append((f'{s["sum"]:,.0f}', 'ผลรวมทั้งหมด'))
        if s.get('mean') is not None:
            k.append((f'{s["mean"]:,.2f}', 'ค่าเฉลี่ยต่อพิกเซล'))
        if s.get('max') is not None:
            k.append((f'{s["max"]:,.2f}', 'ค่าสูงสุดต่อพิกเซล'))
        stats = dict(kpi=k, bars=[]) if k else None
    if stats:
        stats['kpi'] = [list(x) for x in stats.get('kpi') or []]
        stats['bars'] = [list(x) for x in stats.get('bars') or []]
    bm = layout.BASEMAP_ALIAS.get(m.get('basemap'), m.get('basemap') or 'none')
    sources = [n for n, *_ in layers]
    if bd.get('key'):
        bdd = layout._resolve(bd['key'])[1]
        if bdd:
            sources.append(bdd.get('name'))
    return dict(legend=leg, stats=stats, prov=layout._provenance(main, layers) if main else [f'• {n}' for n, *_ in layers],
                sources=list(dict.fromkeys(sources)), basemap_attrib=layout.BASEMAPS[bm][1] if bm in layout.BASEMAPS else '', version=APP_VERSION)


# ---------- ส่งออกด้วย Edge/Chrome headless ----------
def browser():
    cands = [os.environ.get('AINU_BROWSER'),
             r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
             r'C:\Program Files\Google\Chrome\Application\chrome.exe', r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
             shutil.which('msedge'), shutil.which('chrome')]
    return next((c for c in cands if c and Path(c).exists()), None)


def page_size(doc):
    from_paper = {'A4': (210, 297), 'A3': (297, 420), 'A5': (148, 210), 'LETTER': (215.9, 279.4)}
    pp = doc.get('paper') or {}
    if pp.get('size') == 'custom':
        return float(pp['w']), float(pp['h'])
    a, b = from_paper.get(pp.get('size', 'A4'), (210, 297))
    return (b, a) if pp.get('orient', 'landscape') == 'landscape' else (a, b)


def prepare(doc, dpi):
    """วาดภาพแผนที่/แผนที่ตำแหน่งทุกกรอบที่ความละเอียดส่งออก แล้วใส่ใน doc._data"""
    m = doc.get('map') or {}
    data = dict(maps={}, insets={}, info=info(m))
    els = doc.get('els') or []
    for e in els:
        if e.get('type') == 'map' and not e.get('hidden'):
            data['maps'][e['id']] = render_map(m, e['w'], e['h'], dpi, (e.get('p') or {}).get('view'))
    first = next(iter(data['maps'].values()), None)
    for e in els:
        if e.get('type') == 'inset' and not e.get('hidden'):
            p = e.get('p') or {}
            mm = data['maps'].get(p.get('link')) or first
            if mm:
                data['insets'][e['id']] = render_inset(mm['ext'], e['w'], e['h'], dpi, p.get('basemap', 'esri_light'), p.get('zoom', 1))
    return data


def export(doc, fmt, dpi, base_url):
    exe = browser()
    if not exe:
        raise RuntimeError('ไม่พบ Microsoft Edge หรือ Google Chrome ในเครื่อง (ใช้พิมพ์ PDF)')
    dpi = int(dpi or 200)
    doc = dict(doc)
    doc['_data'] = prepare(doc, dpi)
    tok = uuid.uuid4().hex
    PRINTS[tok] = doc
    W, H = page_size(doc)
    tmp = Path(tempfile.mkdtemp(prefix='ainu_print_'))
    out = tmp / ('out.pdf' if fmt == 'pdf' else 'out.png')
    prof = DIRS['cache'] / 'edge_profile'
    args = [exe, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run', '--no-default-browser-check',
            '--disable-extensions', f'--user-data-dir={prof}', '--virtual-time-budget=20000', '--run-all-compositor-stages-before-draw']
    if fmt == 'pdf':
        args += ['--no-pdf-header-footer', f'--print-to-pdf={out}']
    else:
        args += [f'--window-size={round(W / 25.4 * 96)},{round(H / 25.4 * 96)}', f'--force-device-scale-factor={dpi / 96:.4f}', f'--screenshot={out}']
    args.append(f'{base_url.rstrip("/")}/report/print/{tok}')
    try:
        r = subprocess.run(args, capture_output=True, timeout=180, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if not out.exists():
            raise RuntimeError('เบราว์เซอร์ไม่ได้สร้างไฟล์: ' + (r.stderr or b'').decode('utf-8', 'replace')[-300:])
        b = out.read_bytes()
        try:
            (RDIR / f'last_{doc.get("template") or "doc"}.{fmt}').write_bytes(b)     # สำเนาล่าสุดต่อแบบหน้า (ไว้ตรวจ)
        except OSError:
            pass
        return b
    finally:
        PRINTS.pop(tok, None)
        shutil.rmtree(tmp, ignore_errors=True)


def print_html(doc):
    W, H = page_size(doc)
    font = doc.get('font') or 'Sarabun'
    fam = '&'.join(f'family={f.replace(" ", "+")}:wght@300;400;500;600;700' for f in dict.fromkeys([font, 'Sarabun']))
    js = json.dumps(doc, ensure_ascii=False).replace('</', '<\\/')
    return f'''<!doctype html><html><head><meta charset="utf-8"><title>print</title>
<link href="https://fonts.googleapis.com/css2?{fam}&display=block" rel="stylesheet">
<link rel="stylesheet" href="/static/report.css?v={APP_VERSION}">
<style>@page {{ size: {W}mm {H}mm; margin: 0 }} html, body {{ margin: 0; padding: 0; width: {W}mm; height: {H}mm; overflow: hidden; background: #fff }}
* {{ -webkit-print-color-adjust: exact; print-color-adjust: exact }}</style></head>
<body><div id="page"></div><script src="/static/report.js?v={APP_VERSION}"></script>
<script>const DOC = {js}; RPT.render(document.getElementById('page'), DOC, DOC._data, {{ print: true }});</script></body></html>'''
