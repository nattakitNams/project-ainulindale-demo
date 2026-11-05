# -*- coding: utf-8 -*-
"""จัดหน้าแผนที่สำหรับพิมพ์/รายงาน (Print layout) — 6 รูปแบบ + แผนที่พื้นหลัง + ขอบเขต + มาตราส่วน + ลูกศรทิศเหนือ

spec (จากหน้า "ออกแบบรายงาน"):
  template   gov_landscape | gov_portrait | ocha | journal | poster_a3 | dashboard
  title, subtitle, org, author, map_no, note, caption
  layers     [{key: 'ds:5'|'lk:11'|'aoi:2', opacity, style{stroke,width,fill,fillOpacity,useColor}}]  (บนสุดก่อน)
  extent     {type: data|aoi|bbox, aoi_id, bbox:[x0,y0,x1,y1]}
  basemap    none | carto_light | carto_dark | osm | esri_imagery | google_hybrid ; basemap_opacity
  boundary   {key, color, width, label_field}
  elements   {north, scale, grid, legend, inset, stats, lineage, attribution}
  dpi, format pdf | png
ทุกอย่างวาดใน EPSG:4326 (แผนที่พื้นหลัง Web Mercator ถูก warp มาให้ตรง)"""
import io
import json
import math
import threading
from datetime import datetime
from pathlib import Path

import numpy as np

from . import db, symbology, tiles
from .config import APP_VERSION, DIRS

# ---------- แผนที่พื้นหลัง ----------
BASEMAPS = {
    # CARTO ส่งภาพ "API KEY REQUIRED" ให้คำขอที่ไม่ได้มาจากเบราว์เซอร์ → ใช้ Esri Canvas (เทาอ่อน/เทาเข้ม) แทนสำหรับงานพิมพ์
    'esri_light': ('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}',
                   'Basemap © Esri, HERE, Garmin, © OpenStreetMap contributors', ''),
    'esri_dark': ('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}',
                  'Basemap © Esri, HERE, Garmin, © OpenStreetMap contributors', ''),
    'esri_topo': ('https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}',
                  'Basemap © Esri and contributors', ''),
    'osm': ('https://tile.openstreetmap.org/{z}/{x}/{y}.png', '© OpenStreetMap contributors', ''),
    'esri_imagery': ('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                     'Imagery © Esri, Maxar, Earthstar Geographics', ''),
    'google_hybrid': ('https://mt{s}.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', '© Google (ตรวจข้อกำหนดการใช้งานก่อนเผยแพร่)', '0123'),
}
TEMPLATES = {
    'gov_landscape': dict(name='ราชการ A4 แนวนอน', paper=(11.69, 8.27)),
    'gov_portrait': dict(name='ราชการ A4 แนวตั้ง', paper=(8.27, 11.69)),
    'ocha': dict(name='มาตรฐานแผนที่มนุษยธรรม (UN-OCHA style)', paper=(11.69, 8.27)),
    'journal': dict(name='ภาพประกอบบทความวิชาการ', paper=(8.27, 8.0)),
    'poster_a3': dict(name='โปสเตอร์ A3 แนวตั้ง', paper=(11.69, 16.54)),
    'dashboard': dict(name='Dashboard / อินโฟกราฟิก A4', paper=(11.69, 8.27)),
}
BASEMAP_ALIAS = {'carto_light': 'esri_light', 'carto_dark': 'esri_dark'}     # spec เก่าที่บันทึกไว้
INK, MUTED, LINE = '#1d2233', '#5d6478', '#c9ccd6'


def _wrap(s, width):
    import textwrap
    return '\n'.join(textwrap.wrap(str(s), max(8, int(width)), break_long_words=True)) or str(s)


def _short(s, n):
    s = str(s)
    return s if len(s) <= n else s[:n - 1] + '…'
_tlock = threading.Lock()


def _font():
    import matplotlib
    from matplotlib import font_manager
    for f in ('Tahoma', 'Leelawadee UI', 'Leelawadee'):
        if any(f == x.name for x in font_manager.fontManager.ttflist):
            matplotlib.rcParams['font.family'] = f
            return
    matplotlib.rcParams['font.family'] = 'sans-serif'


def _tile_bytes(name, z, x, y):
    """ไทล์แผนที่พื้นหลัง (แคชลงดิสก์ cache/basemap — พิมพ์ซ้ำไม่ต้องโหลดใหม่)"""
    import requests
    url, _, subs = BASEMAPS[name]
    p = DIRS['cache'] / 'basemap' / name / str(z) / str(x) / f'{y}.png'
    if p.exists():
        return p.read_bytes()
    u = url.format(s=subs[(x + y) % len(subs)] if subs else '', z=z, x=x, y=y)
    r = requests.get(u, headers={'User-Agent': f'Ainulindale/{APP_VERSION} (map print)'}, timeout=20)
    if r.status_code != 200 or not r.headers.get('Content-Type', '').startswith('image'):
        return None
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(r.content)
    return r.content


def _mosaic_4326(fetch, ext, out_w, out_h, max_tiles=80):
    """ต่อไทล์ XYZ (3857) ให้ครอบกรอบ ext (WGS84) แล้ว warp เป็นภาพ out_w×out_h ใน EPSG:4326"""
    from PIL import Image
    from rasterio.transform import from_bounds
    from rasterio.warp import Resampling, reproject
    x0, y0, x1, y1 = ext
    lat = (y0 + y1) / 2
    res_m = (x1 - x0) * 111320 * math.cos(math.radians(lat)) / max(out_w, 1)
    z = int(max(1, min(18, math.floor(math.log2(156543.034 * math.cos(math.radians(lat)) / max(res_m, 0.1))))))

    def t(lon, la, zz):
        n = 2 ** zz
        la = max(min(la, 85.05), -85.05)
        return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(la))) / math.pi) / 2 * n
    while True:
        tx0, ty0 = t(x0, y1, z)
        tx1, ty1 = t(x1, y0, z)
        xs, ys = range(int(tx0), int(tx1) + 1), range(int(ty0), int(ty1) + 1)
        if len(xs) * len(ys) <= max_tiles or z <= 1:
            break
        z -= 1
    img = Image.new('RGBA', (len(xs) * 256, len(ys) * 256), (0, 0, 0, 0))
    got = 0
    for i, X in enumerate(xs):
        for j, Y in enumerate(ys):
            try:
                b = fetch(z, X % 2 ** z, Y)
            except Exception:
                b = None
            if b:
                img.paste(Image.open(io.BytesIO(b)).convert('RGBA'), (i * 256, j * 256))
                got += 1
    if not got:
        return None
    R = 20037508.342789244
    s = 2 * R / 2 ** z
    src_tr = from_bounds(-R + xs[0] * s, R - (ys[-1] + 1) * s, -R + (xs[-1] + 1) * s, R - ys[0] * s, img.width, img.height)
    src = np.asarray(img).transpose(2, 0, 1)
    dst = np.zeros((4, out_h, out_w), 'uint8')
    for b in range(4):
        reproject(src[b], dst[b], src_transform=src_tr, src_crs='EPSG:3857', dst_transform=from_bounds(*ext, out_w, out_h),
                  dst_crs='EPSG:4326', resampling=Resampling.bilinear)
    return dst.transpose(1, 2, 0)


# ---------- ชั้นข้อมูล ----------
def _resolve(key):
    kind, i = key.split(':')
    if kind == 'aoi':
        a = db.get('aoi', int(i))
        return ('aoi', a) if a else (None, None)
    d = db.get('datasets', int(i))
    if d is None:
        return None, None
    if d['kind'] == 'link':
        return ('linktile' if d['meta'].get('view') else 'linkdata'), d
    return d['kind'], d


def _bounds(kind, d):
    if kind == 'aoi':
        return d.get('bbox')
    return (d.get('meta') or {}).get('bounds_wgs84')


def _raster(ax, d, ext, px_w, px_h, opacity):
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds as wfb
    style = tiles.style_of(d) or {}
    with rasterio.open(d.get('read_path') or d['path']) as s:
        bb = transform_bounds('EPSG:4326', s.crs, *ext) if s.crs and s.crs.to_epsg() != 4326 else ext
        win = wfb(*bb, s.transform).intersection(rasterio.windows.Window(0, 0, s.width, s.height))
        if win.width < 1 or win.height < 1:
            return
        ow = int(min(px_w * 1.2, win.width, 3200))
        oh = int(max(1, ow * win.height / win.width))
        rs = Resampling.nearest if style.get('type') == 'paletted' or d.get('value_type') == 'class' else Resampling.average
        arr = s.read(int(d.get('band') or 1), window=win, out_shape=(oh, ow), masked=True, resampling=rs)
        wb = rasterio.windows.bounds(win, s.transform)
        res = abs(s.transform.a)
        lat = wb[3] - (np.arange(oh) + 0.5) * (wb[3] - wb[1]) / oh
    a = np.asarray(arr.filled(0)).astype('float64')
    rgba = symbology.render(d, style, a, ~np.ma.getmaskarray(arr), res, lat)
    rgba[..., 3] = (rgba[..., 3] * opacity).astype('uint8')
    ax.imshow(rgba, extent=[wb[0], wb[2], wb[1], wb[3]], interpolation='nearest', zorder=3)


_gcache = {}                                               # (key, กรอบ, เวลาแก้ไข) → GeoDataFrame ที่ย่อรูปแล้ว — พรีวิวซ้ำไม่ต้องอ่าน/ดึงใหม่


def _vector_gdf(kind, d, ext, px_w=None):
    """อ่านเวกเตอร์ในกรอบ (แคชไว้ 8 ชุด) · px_w ให้มา = ย่อรูปทรงตามขนาดพิกเซล (วาดเร็วขึ้นมาก ภาพไม่ต่าง)"""
    ck = (kind, d.get('id'), tuple(round(v, 4) for v in ext), d.get('updated_at') or d.get('created_at'), int(px_w or 0) // 200)
    if ck in _gcache:
        return _gcache[ck]
    g = _vector_gdf_raw(kind, d, ext)
    if g is not None and len(g) and px_w:
        tol = (ext[2] - ext[0]) / px_w / 2
        geo = g.geometry.simplify(tol, preserve_topology=False)
        g = g.set_geometry(geo)
        g = g[[x is not None and not x.is_empty for x in g.geometry]]
    with _tlock:
        if len(_gcache) >= 8:
            _gcache.pop(next(iter(_gcache)))
        _gcache[ck] = g
    return g


def _vector_gdf_raw(kind, d, ext):
    import geopandas as gpd
    if kind == 'aoi':
        return gpd.read_file(d['path'])
    if kind == 'linkdata':
        from . import links
        g, _ = links.features(d, ext, 10, limit=20000)
        return gpd.GeoDataFrame.from_features(g.get('features', []), crs='EPSG:4326') if g.get('features') else None
    from .dsinfo import read_vector
    bb = tiles._bbox_to_crs(ext, d['meta'].get('crs'))
    g = read_vector(d, bbox=tuple(bb), max_features=60000)
    if g.crs is not None and g.crs.to_epsg() != 4326:
        g = g.to_crs(4326)
    return g


def _vector(ax, kind, d, ext, st, opacity, z=4, px_w=None):
    g = _vector_gdf(kind, d, ext, px_w)
    if g is None or not len(g):
        return
    st = st or {}
    gt = str(g.geom_type.iloc[0])
    if st.get('useColor') and 'color' in g.columns:
        g.plot(ax=ax, color=g['color'], edgecolor='#ffffff', linewidth=.25, alpha=opacity, zorder=z)
    elif 'Point' in gt:
        g.plot(ax=ax, color=st.get('fill', '#c3b6ff'), edgecolor=st.get('stroke', '#333'), markersize=8, linewidth=.4, alpha=opacity, zorder=z)
    else:
        g.plot(ax=ax, facecolor=st.get('fill', '#c3b6ff') if st.get('fillOpacity', .15) > 0 else 'none',
               edgecolor=st.get('stroke', '#555'), linewidth=float(st.get('width', 1)) * .7, alpha=None, zorder=z)
        if st.get('fillOpacity', .15) > 0:
            for c in ax.collections[-1:]:
                fc = c.get_facecolor()
                if len(fc):
                    fc[:, 3] = float(st.get('fillOpacity', .15)) * opacity
                    c.set_facecolor(fc)


def _linktile(ax, d, ext, px_w, px_h, opacity):
    from . import links
    img = _mosaic_4326(lambda z, x, y: links.tile(d, z, x, y)[0], ext, px_w, px_h, 60)
    if img is not None:
        img = img.copy()
        img[..., 3] = (img[..., 3] * opacity).astype('uint8')
        ax.imshow(img, extent=[ext[0], ext[2], ext[1], ext[3]], zorder=3)


# ---------- องค์ประกอบแผนที่ ----------
def _nice(x):
    e = 10 ** math.floor(math.log10(x))
    for m in (1, 2, 2.5, 5, 10):
        if m * e >= x:
            return m * e
    return 10 * e


def _scalebar(ax, ext, loc='lower left', dark=False):
    from matplotlib.patches import Rectangle
    x0, y0, x1, y1 = ext
    lat = (y0 + y1) / 2
    kmdeg = 111.32 * math.cos(math.radians(lat))
    width_km = (x1 - x0) * kmdeg
    L = _nice(width_km / 5)
    n = 4
    seg = L / n / kmdeg
    bx = x0 + (x1 - x0) * (0.05 if 'left' in loc else 0.62)
    by = y0 + (y1 - y0) * 0.045
    h = (y1 - y0) * 0.009
    fg = '#ffffff' if dark else INK
    for i in range(n):
        ax.add_patch(Rectangle((bx + i * seg, by), seg, h, facecolor=fg if i % 2 == 0 else ('#00000000' if not dark else '#00000055'),
                               edgecolor=fg, linewidth=.6, zorder=20))
    unit = 'กม.' if L >= 1 else 'ม.'
    lab = (lambda v: f'{v:g}') if L >= 1 else (lambda v: f'{v * 1000:g}')
    for i in (0, n // 2, n):
        ax.text(bx + i * seg, by + h * 1.8, lab(L * i / n), ha='center', va='bottom', fontsize=6.5, color=fg, zorder=20)
    ax.text(bx + n * seg + seg * .25, by + h / 2, unit, ha='left', va='center', fontsize=6.5, color=fg, zorder=20)


def _north(ax, x=0.94, y=0.88, size=0.06, dark=False):
    from matplotlib.patches import Polygon
    fg = '#ffffff' if dark else INK
    tr = ax.transAxes
    s = size
    ax.add_patch(Polygon([(x, y + s * .55), (x - s * .22, y - s * .35), (x, y - s * .15)], closed=True, facecolor=fg, edgecolor=fg, lw=.6, transform=tr, zorder=21))
    ax.add_patch(Polygon([(x, y + s * .55), (x + s * .22, y - s * .35), (x, y - s * .15)], closed=True, facecolor='none', edgecolor=fg, lw=.6, transform=tr, zorder=21))
    ax.text(x, y + s * .62, 'N', transform=tr, ha='center', va='bottom', fontsize=9, fontweight='bold', color=fg, zorder=21)


def _graticule(ax, ext, show):
    from matplotlib.ticker import FuncFormatter, MaxNLocator
    ax.xaxis.set_major_locator(MaxNLocator(5, steps=[1, 2, 2.5, 5, 10]))
    ax.yaxis.set_major_locator(MaxNLocator(5, steps=[1, 2, 2.5, 5, 10]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, p: f'{abs(v):g}°{"E" if v >= 0 else "W"}'))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f'{abs(v):g}°{"N" if v >= 0 else "S"}'))
    ax.tick_params(labelsize=6.5, colors=MUTED, length=2, direction='out')
    if show:
        ax.grid(True, color='#8a90a8', linewidth=.3, alpha=.6, linestyle='--')
        ax.set_axisbelow(False)
    else:
        ax.set_xticks([]), ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color(INK), s.set_linewidth(.8)


def _fit_extent(ext, ax_w, ax_h):
    """ขยายกรอบให้สัดส่วนตรงกับกล่องแผนที่ (คิดการหดของลองจิจูดตามละติจูด)"""
    x0, y0, x1, y1 = ext
    k = math.cos(math.radians((y0 + y1) / 2))
    dw, dh = (x1 - x0) * k, (y1 - y0)
    want = ax_w / ax_h
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if dw / dh < want:
        dw = dh * want
    else:
        dh = dw / want
    return [cx - dw / k / 2, cy - dh / 2, cx + dw / k / 2, cy + dh / 2]


# ---------- คำอธิบาย / สถิติ / ที่มา ----------
def _lineage(d):
    if not d or not d.get('job_id'):
        return None
    j = db.get('jobs', d['job_id'])
    p = Path(j['out_dir']) / 'lineage.json' if j and j.get('out_dir') else None
    return json.loads(p.read_text(encoding='utf-8')) if p and p.exists() else None


def _legend_items(items):
    """[(ชื่อชั้น, ชนิด, d, style)] → รายการคำอธิบาย"""
    from . import export
    out = []
    for name, kind, d, st in items:
        lin = _lineage(d) if kind in ('raster', 'vector') else None
        lp = (lin or {}).get('params') or {}
        if lin and lin.get('operation') in ('bivariate', 'zonal') and isinstance(lp.get('x'), dict):
            nx, ny = int(lp['x']['n']), int(lp['y']['n'])
            cols = (lin.get('palette_edits') or [{}])[-1].get('colors') or lp.get('colors')
            xl = export.class_labels(dict(lp['x'], breaks=lp['x'].get('resolved_breaks', lp['x'].get('breaks', []))))
            yl = export.class_labels(dict(lp['y'], breaks=lp['y'].get('resolved_breaks', lp['y'].get('breaks', []))))
            out.append(dict(type='biv', name=name, nx=nx, ny=ny, colors=cols, xl=xl, yl=yl, xn=lp['x'].get('label') or 'X',
                            yn=lp['y'].get('label') or 'Y', hl=lp.get('highlight') or [], lin=lin))
        elif kind == 'raster':
            s = tiles.style_of(d) or {}
            it = [e for e in ((s.get('entries') if s.get('type') == 'paletted' else s.get('stops')) or []) if e.get('visible', True)]
            out.append(dict(type='ramp' if s.get('type') == 'pseudocolor' and s.get('interp') == 'linear' else 'list', name=name, items=it[:12],
                            more=max(0, len(it) - 12), unit='ต่อ ตร.กม.' if s.get('metric') == 'density' else ''))
        elif kind in ('vector', 'linkdata', 'aoi'):
            out.append(dict(type='patch', name=name, fill=(st or {}).get('fill', '#c3b6ff'), stroke=(st or {}).get('stroke', '#555'),
                            useColor=(st or {}).get('useColor')))
        else:
            out.append(dict(type='text', name=name, text='ภาพจากบริการแผนที่'))
    return out


def _draw_legend(ax, items, fs=7.5, title='คำอธิบายสัญลักษณ์', box=False):
    """วาดคำอธิบาย คืนค่า y ล่างสุดที่ใช้ (สัดส่วนแกน) · box=True วาดกรอบขาวพอดีเนื้อหา (ใช้เมื่อวางทับแผนที่)"""
    from matplotlib.patches import Rectangle
    ax.axis('off')
    hin = ax.bbox.height / ax.figure.dpi                 # ความสูงแกน (นิ้ว) → แปลงขนาดตัวอักษรเป็นสัดส่วนแกน
    line = fs * 1.45 / 72 / hin
    cpl = ax.bbox.width / ax.figure.dpi * 72 / (fs * 0.62)
    y = 0.98
    ax.text(0, y, title, fontsize=fs + 2, fontweight='bold', color=INK, va='top', transform=ax.transAxes)
    y -= line * 1.6
    asp = ax.bbox.height / max(ax.bbox.width, 1)
    for it in items:
        if y < 0.05:
            break
        nm = _wrap(it['name'], cpl)
        ax.text(0, y, nm, fontsize=fs, fontweight='bold', color=INK, va='top', transform=ax.transAxes, linespacing=1.3)
        y -= line * (nm.count('\n') + 1) + line * .3
        sw, sh = line * 1.1 / asp * 1.4, line * .8          # ช่องสี (กว้าง, สูง)
        if it['type'] == 'biv':
            nx, ny = it['nx'], it['ny']
            ch = min(line * 1.9, 0.5 / ny)                    # ช่องสี่เหลี่ยมจัตุรัส
            cell = ch * asp
            if cell * nx > 0.55:
                cell = 0.55 / nx
                ch = cell / asp
            gx = 0.3
            top = y - line * .3
            for yy in range(ny):
                for xx in range(nx):
                    code = yy * nx + xx + 1
                    r = Rectangle((gx + xx * cell, top - (ny - yy) * ch), cell * .96, ch * .96, transform=ax.transAxes,
                                  facecolor=it['colors'][code - 1], edgecolor=INK if code in it['hl'] else 'white', linewidth=1.2 if code in it['hl'] else .4)
                    ax.add_patch(r)
                ax.text(gx - 0.02, top - (ny - yy - .5) * ch, it['yl'][yy], fontsize=fs - 1.5, ha='right', va='center', color=MUTED, transform=ax.transAxes)
            for xx in range(nx):
                ax.text(gx + (xx + .5) * cell, top - ny * ch - line * .2, it['xl'][xx], fontsize=fs - 1.5, ha='right', va='top', rotation=35,
                        rotation_mode='anchor', color=MUTED, transform=ax.transAxes)
            ax.text(gx + nx * cell / 2, top - ny * ch - line * 2.4, _short(it['xn'], 28) + ' →', fontsize=fs - .5, ha='center', va='top', color=INK, transform=ax.transAxes)
            ax.text(gx + nx * cell + 0.03, top - ny * ch / 2, '↑ ' + _short(it['yn'], 24), fontsize=fs - .5, ha='left', va='center', color=INK, transform=ax.transAxes)
            y = top - ny * ch - line * 3.6
            if it['hl']:
                ax.add_patch(Rectangle((0.0, y - sh), sw, sh, transform=ax.transAxes, facecolor='white', edgecolor=INK, lw=1.2))
                ax.text(sw + 0.03, y - sh / 2, f'กรอบเข้ม = เขตเน้น (รหัส {", ".join(map(str, it["hl"]))})', fontsize=fs - 1, va='center', color=MUTED, transform=ax.transAxes)
                y -= line * 1.4
        elif it['type'] == 'ramp':
            cols = [e['color'] for e in it['items']] or ['#000', '#fff']
            grad = np.array([[symbology._rgb(c) / 255 for c in cols]])
            ax.imshow(grad, extent=(0.0, 0.75, y - line, y), transform=ax.transAxes, aspect='auto', interpolation='bilinear')
            ax.text(0.0, y - line * 1.2, str(it['items'][0].get('label', '')) if it['items'] else '', fontsize=fs - 1.5, va='top', color=MUTED, transform=ax.transAxes)
            ax.text(0.75, y - line * 1.2, str(it['items'][-1].get('label', '')) + (f' {it["unit"]}' if it['unit'] else ''), fontsize=fs - 1.5, va='top', ha='right', color=MUTED, transform=ax.transAxes)
            y -= line * 2.6
        elif it['type'] == 'list':
            for e in it['items']:
                if y < 0.03:
                    break
                ax.add_patch(Rectangle((0.0, y - sh), sw, sh, transform=ax.transAxes, facecolor=e['color'], edgecolor='#999', lw=.3))
                ax.text(sw + 0.03, y - sh / 2, _short(e.get('label', e['value']), int(cpl * 1.1)), fontsize=fs - 1, va='center', color=INK, transform=ax.transAxes)
                y -= line * 1.1
            if it['more']:
                ax.text(sw + 0.03, y, f'… อีก {it["more"]}', fontsize=fs - 1.5, color=MUTED, va='top', transform=ax.transAxes)
                y -= line
            if it['unit']:
                ax.text(sw + 0.03, y, f'({it["unit"]})', fontsize=fs - 1.5, color=MUTED, va='top', transform=ax.transAxes)
                y -= line
            y -= line * .5
        elif it['type'] == 'patch':
            ax.add_patch(Rectangle((0.0, y - sh), sw, sh, transform=ax.transAxes,
                                   facecolor='#cfc6f5' if it['useColor'] else it['fill'], edgecolor=it['stroke'], lw=1))
            ax.text(sw + 0.03, y - sh / 2, 'สีตามข้อมูล' if it['useColor'] else 'ขอบเขต/พื้นที่', fontsize=fs - 1, va='center', color=INK, transform=ax.transAxes)
            y -= line * 1.6
        else:
            ax.text(0.0, y, it['text'], fontsize=fs - 1, color=MUTED, va='top', transform=ax.transAxes)
            y -= line * 1.4
    if box:
        pad = line * .6
        ax.add_patch(Rectangle((-0.05, y - pad), 1.1, 1.0 - y + pad + 0.02, transform=ax.transAxes, facecolor='#ffffffee',
                               edgecolor=LINE, lw=.6, zorder=-1, clip_on=False))
    return y


def _stats(main):
    """ตัวเลขสรุปจาก lineage ของชั้นหลัก (ไบแวเรียต/รายพื้นที่)"""
    lin = _lineage(main) if main else None
    if not lin:
        return None
    s = lin.get('stats_summary') or {}
    p = lin.get('params') or {}
    out = dict(kpi=[], bars=[])
    if s.get('weight_total') is not None:
        out['kpi'] = [(f'{s["weight_total"]:,.0f}', f'{s.get("weight_dataset") or "น้ำหนัก"} ทั้งหมด'),
                      (f'{s.get("highlight_weight") or 0:,.0f}', (f'ในเขตเน้น (รหัส {", ".join(map(str, s["highlight"]))})' if s.get('highlight') else 'ในเขตเน้น (ไม่ได้กำหนด)')),
                      (f'{s.get("area_coded_km2", 0):,.0f}', 'พื้นที่มีรหัส (ตร.กม.)')]
        cols = (lin.get('palette_edits') or [{}])[-1].get('colors') or p.get('colors') or []
        wbc = s.get('weight_by_code') or {}
        out['bars'] = [(int(k), v, cols[int(k) - 1] if int(k) - 1 < len(cols) else '#999') for k, v in sorted(wbc.items(), key=lambda t: int(t[0]))]
        out['bar_title'] = f'{s.get("weight_dataset") or "น้ำหนัก"} ต่อรหัส'
    elif s.get('zones') is not None:
        out['kpi'] = [(f'{s["zones"]:,}', 'พื้นที่ทั้งหมด'), (f'{s.get("zones_highlight", 0):,}', 'พื้นที่ในเขตเน้น'), (f'{s.get("zones_coded", 0):,}', 'พื้นที่มีรหัส')]
        cols = p.get('colors') or []
        out['bars'] = [(int(k), v, cols[int(k) - 1] if int(k) - 1 < len(cols) else '#999') for k, v in sorted((s.get('zones_by_code') or {}).items(), key=lambda t: int(t[0]))]
        out['bar_title'] = 'จำนวนพื้นที่ต่อรหัส'
    elif s.get('sum') is not None:
        out['kpi'] = [(f'{s["sum"]:,.0f}', 'ผลรวมค่า')]
    return out


def _draw_bars(ax, st, fs=7):
    from matplotlib.ticker import MaxNLocator
    cpl = ax.bbox.width / ax.figure.dpi * 72 / ((fs + 1) * .62)
    ax.set_title(_short(st.get('bar_title', ''), int(cpl * 1.15)), fontsize=fs + 1, loc='left', color=INK, fontweight='bold')
    ax.xaxis.set_major_locator(MaxNLocator(max(2, int(ax.bbox.width / ax.figure.dpi / .7)), min_n_ticks=2))
    b = st['bars']
    ax.barh([str(c) for c, _, _ in b][::-1], [v for _, v, _ in b][::-1], color=[c for _, _, c in b][::-1], edgecolor='#00000033', linewidth=.4)
    ax.tick_params(labelsize=fs - 1, colors=MUTED)
    ax.xaxis.set_major_formatter(__import__('matplotlib').ticker.FuncFormatter(lambda v, p: f'{v:,.0f}' if v < 1e6 else f'{v / 1e6:,.1f} ล้าน'))
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    for s in ('left', 'bottom'):
        ax.spines[s].set_color(LINE)


def _provenance(main, layers):
    lin = _lineage(main) if main else None
    lines = []
    if lin:
        lines.append(f'{lin.get("operation")} · {lin.get("created_at", "").replace("T", " ")}')
        for i in lin.get('inputs', [])[:4]:
            lines.append(f'• {i.get("name")}')
        pr = lin.get('params') or {}
        for a in ('x', 'y'):
            if isinstance(pr.get(a), dict):
                c = pr[a]
                br = c.get('resolved_breaks', c.get('breaks')) or []
                lines.append(f'{a.upper()}: {c.get("label") or ""} — เกณฑ์ {" / ".join(f"{v:g}" for v in br)}')
        if (lin.get('stats_summary') or {}).get('aoi'):
            lines.append(f'พื้นที่ศึกษา: {lin["stats_summary"]["aoi"].get("name")}')
    else:
        lines += [f'• {n}' for n, *_ in layers[:5]]
    return lines


# ---------- ประกอบหน้า ----------
def render(spec, fmt='pdf', dpi=None, preview=False):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    _font()
    tpl = spec.get('template') or 'gov_landscape'
    W, H = TEMPLATES[tpl]['paper']
    if spec.get('orientation') == 'portrait' and W > H or spec.get('orientation') == 'landscape' and H > W:
        W, H = H, W
    dpi = dpi or (70 if preview else int(spec.get('dpi') or 200))
    el = dict(north=True, scale=True, grid=True, legend=True, inset=True, stats=True, lineage=True, attribution=True)
    el.update(spec.get('elements') or {})
    # ชั้น (บนสุดก่อน) → วาดล่างขึ้นบน
    layers = []
    for l in spec.get('layers') or []:
        kind, d = _resolve(l['key'])
        if d is not None:
            if kind == 'raster' and l.get('rstyle'):          # สไตล์ที่ปรับเฉพาะในแผนที่ซ้อนชั้น
                d = dict(d, style=l['rstyle'])
            layers.append((d.get('name'), kind, d, l.get('style'), float(l.get('opacity', 1))))
    main = next((d for _, k, d, *_ in layers if k in ('raster', 'vector') and _lineage(d)), None) or next((d for _, k, d, *_ in layers if k == 'raster'), None)
    # กรอบแผนที่
    ex = spec.get('extent') or {}
    if ex.get('type') == 'aoi' and ex.get('aoi_id'):
        ext = list(db.get('aoi', int(ex['aoi_id']))['bbox'])
    elif ex.get('type') == 'bbox' and ex.get('bbox'):
        ext = list(ex['bbox'])
    else:
        bs = [b for b in (_bounds(k, d) for _, k, d, *_ in layers) if b]
        ext = [min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs)] if bs else [97.3, 5.6, 105.7, 20.5]
    pad = 0.03
    ext = [ext[0] - (ext[2] - ext[0]) * pad, ext[1] - (ext[3] - ext[1]) * pad, ext[2] + (ext[2] - ext[0]) * pad, ext[3] + (ext[3] - ext[1]) * pad]

    fig = plt.figure(figsize=(W, H), dpi=dpi)
    fig.patch.set_facecolor('white')
    title, sub = spec.get('title') or (main or {}).get('name') or 'แผนที่', spec.get('subtitle') or ''
    org, author, map_no = spec.get('org') or '', spec.get('author') or '', spec.get('map_no') or ''
    date = datetime.now().strftime('%d/%m/%Y')
    bm = BASEMAP_ALIAS.get(spec.get('basemap'), spec.get('basemap') or 'none')
    attrib = []
    if bm in BASEMAPS:
        attrib.append('แผนที่พื้นหลัง: ' + BASEMAPS[bm][1])
    src_names = [n for n, *_ in layers]
    legend_items = _legend_items([(n, k, d, st) for n, k, d, st, _ in layers])
    stats = _stats(main) if el['stats'] else None
    prov = _provenance(main, layers) if el['lineage'] else []
    dark_map = bm in ('esri_dark', 'esri_imagery', 'google_hybrid') and float(spec.get('basemap_opacity', 1)) > .5
    R = {}                                                     # กล่องของแต่ละส่วน [x, y, w, h] (สัดส่วนหน้า)
    extra_foot = []

    def header(color, sub_color, ys, fs_t, mno_fmt):
        y0, yt, ys_ = ys
        fig.add_artist(Rectangle((0, y0), 1, 1 - y0, transform=fig.transFigure, facecolor=color, zorder=0))
        fig.text(.03, yt, _short(title, 70), fontsize=fs_t, fontweight='bold', color='white', va='center')
        fig.text(.03, ys_, _short(sub, 110), fontsize=fs_t * .56, color=sub_color, va='center')
        fig.text(.97, yt, org, fontsize=fs_t * .6, color='white', va='center', ha='right', fontweight='bold')
        fig.text(.97, ys_, mno_fmt.format(map_no) if map_no else date, fontsize=fs_t * .5, color=sub_color, va='center', ha='right')

    # ---------- โครงแต่ละแบบ ----------
    if tpl == 'gov_landscape':
        header('#1f3a5f', '#d9e2f0', (.9, .955, .918), 17, 'แผนที่หมายเลข {}')
        fig.add_artist(Rectangle((.685, .095), .29, .79, transform=fig.transFigure, facecolor='#f4f6fa', edgecolor=LINE, lw=.6, zorder=0))
        R = dict(map=[.045, .1, .62, .78], legend=[.70, .55, .26, .315], stats=[.735, .36, .22, .13],
                 inset=[.70, .11, .11, .19], prov=[.822, .29, 33])
    elif tpl == 'gov_portrait':
        header('#1f3a5f', '#d9e2f0', (.93, .968, .943), 16, 'แผนที่หมายเลข {}')
        fig.add_artist(Rectangle((.05, .07), .9, .25, transform=fig.transFigure, facecolor='#f4f6fa', edgecolor=LINE, lw=.6, zorder=0))
        R = dict(map=[.08, .355, .86, .56], legend=[.065, .08, .33, .23], inset=[.42, .1, .2, .17], stats=[.69, .12, .24, .15])
    elif tpl == 'ocha':
        header('#007CBB', '#e6f3fa', (.905, .962, .925), 16, 'Map No. {}')
        R = dict(map=[.045, .125, .935, .765], legend_in=[.06, .135, .21, .42], inset_in=[.835, .67, .13, .19])
        extra_foot.append('The boundaries and names shown and the designations used on this map do not imply official endorsement or acceptance. · '
                          'ขอบเขตและชื่อบนแผนที่นี้ไม่ได้แสดงการรับรองอย่างเป็นทางการ')
    elif tpl == 'journal':
        R = dict(map=[.1, .25, .85, .72], legend_in=[.72, .28, .2, .32])
        cap = spec.get('caption') or f'ภาพที่ 1 {title}{" — " + sub if sub else ""}'
        fig.text(.1, .17, _wrap(cap, 105), fontsize=9, color=INK, va='top', linespacing=1.4)
    elif tpl == 'poster_a3':
        fig.text(.05, .965, _short(title, 60), fontsize=26, fontweight='bold', color=INK, va='center')
        fig.text(.05, .938, _short(sub, 100), fontsize=12, color=MUTED, va='center')
        fig.text(.95, .965, org, fontsize=12, color=INK, va='center', ha='right', fontweight='bold')
        fig.text(.95, .938, f'แผนที่หมายเลข {map_no}' if map_no else date, fontsize=9, color=MUTED, va='center', ha='right')
        fig.add_artist(plt.Line2D([.05, .95], [.92, .92], transform=fig.transFigure, color=INK, lw=1.5))
        R = dict(map=[.06, .33, .89, .57], legend=[.05, .07, .28, .22], inset=[.37, .1, .2, .18], stats=[.65, .17, .3, .1], prov=[.62, .135, 60])
    else:                                                       # dashboard
        fig.patch.set_facecolor('#f6f7fb')
        fig.text(.03, .955, _short(title, 70), fontsize=18, fontweight='bold', color=INK, va='center')
        fig.text(.03, .915, _short(sub or org, 110), fontsize=9.5, color=MUTED, va='center')
        fig.text(.97, .955, org if sub else '', fontsize=10, color=INK, va='center', ha='right', fontweight='bold')
        fig.text(.97, .915, date, fontsize=8, color=MUTED, va='center', ha='right')
        R = dict(map=[.045, .115, .54, .76], kpi=[.61, .72, .36, .15], stats=[.65, .43, .31, .21], legend=[.61, .115, .2, .27], inset=[.83, .12, .14, .2])

    # ---------- แผนที่หลัก ----------
    mx, my, mw, mh = R['map']
    ext = _fit_extent(ext, mw * W, mh * H)
    ax = fig.add_axes(R['map'])
    ax.set_xlim(ext[0], ext[2]), ax.set_ylim(ext[1], ext[3])
    ax.set_facecolor('#eef1f6' if bm == 'none' else 'white')
    px_w, px_h = int(mw * W * dpi), int(mh * H * dpi)
    if bm in BASEMAPS:
        img = _mosaic_4326(lambda z, x, y: _tile_bytes(bm, z, x, y), ext, max(px_w, 300), max(px_h, 300), 40 if preview else 120)
        if img is not None:
            ax.imshow(img, extent=[ext[0], ext[2], ext[1], ext[3]], alpha=float(spec.get('basemap_opacity', 1)), zorder=1, interpolation='bilinear')
        else:
            attrib.append('(โหลดแผนที่พื้นหลังไม่ได้ — ออฟไลน์?)')
    for n, kind, d, st, op in reversed(layers):                # ล่างขึ้นบน
        try:
            if kind == 'raster':
                _raster(ax, d, ext, px_w, px_h, op)
            elif kind in ('vector', 'linkdata', 'aoi'):
                _vector(ax, kind, d, ext, st, op, px_w=px_w)
            elif kind == 'linktile':
                _linktile(ax, d, ext, px_w, px_h, op)
        except Exception as e:
            print('[รายงาน] วาดชั้นไม่ได้', n, e)
    bd = spec.get('boundary') or {}
    if bd.get('key'):
        kind, d = _resolve(bd['key'])
        if d is not None:
            try:
                g = _vector_gdf(kind, d, ext, px_w)
                if g is not None and len(g):
                    g.boundary.plot(ax=ax, color=bd.get('color', '#333333'), linewidth=float(bd.get('width', .8)), zorder=12)
                    lf = bd.get('label_field')
                    if lf and lf in g.columns and len(g) <= 400:
                        from matplotlib import patheffects
                        pts = g.representative_point()
                        for (_, r), pt in zip(g.iterrows(), pts):
                            if ext[0] < pt.x < ext[2] and ext[1] < pt.y < ext[3]:
                                ax.text(pt.x, pt.y, str(r[lf]), fontsize=5.5 if len(g) > 40 else 7, ha='center', va='center', zorder=13,
                                        color='#ffffff' if dark_map else INK, clip_on=True,
                                        path_effects=[patheffects.withStroke(linewidth=1.6, foreground='#00000088' if dark_map else 'white')])
                    src_names.append(d.get('name'))
            except Exception as e:
                print('[รายงาน] ขอบเขต', e)
    ax.set_xlim(ext[0], ext[2]), ax.set_ylim(ext[1], ext[3])
    ax.set_aspect(1 / math.cos(math.radians((ext[1] + ext[3]) / 2)), adjustable='box')
    ax.set_xlabel(''), ax.set_ylabel('')                       # geopandas ใส่ "Geodetic longitude [degree]" มาให้ — ไม่ต้องการ
    _graticule(ax, ext, el['grid'])
    if el['scale']:
        _scalebar(ax, ext, 'lower right' if tpl == 'ocha' else 'lower left', dark_map)
    if el['north']:
        _north(ax, .95, .87, .07, dark_map)

    # ---------- คำอธิบาย ----------
    if el['legend'] and legend_items:
        inside = bool(R.get('legend_in'))
        la = fig.add_axes(R['legend_in'] if inside else R['legend'], zorder=31 if inside else 2)
        _draw_legend(la, legend_items, 10 if tpl == 'poster_a3' else 7.5, box=inside)
    # ---------- แผนที่ระบุตำแหน่ง ----------
    ins = R.get('inset') or R.get('inset_in')
    if el['inset'] and ins:
        ia = fig.add_axes(ins, zorder=32 if R.get('inset_in') else 2)
        cx, cy = (ext[0] + ext[2]) / 2, (ext[1] + ext[3]) / 2
        span = min(max(ext[2] - ext[0], ext[3] - ext[1]) * 4 + 6, 170)
        iext = _fit_extent([cx - span / 2, cy - span / 2, cx + span / 2, cy + span / 2], ins[2] * W, ins[3] * H)
        ia.set_xlim(iext[0], iext[2]), ia.set_ylim(iext[1], iext[3])
        img = _mosaic_4326(lambda z, x, y: _tile_bytes('esri_light', z, x, y), iext, int(ins[2] * W * dpi), int(ins[3] * H * dpi), 16)
        if img is not None:
            ia.imshow(img, extent=[iext[0], iext[2], iext[1], iext[3]], zorder=1)
        else:
            ia.set_facecolor('#eef1f6')
        ia.add_patch(Rectangle((ext[0], ext[1]), ext[2] - ext[0], ext[3] - ext[1], facecolor='#e5484d33', edgecolor='#e5484d', lw=1.2, zorder=3))
        ia.set_xlim(iext[0], iext[2]), ia.set_ylim(iext[1], iext[3])
        ia.set_aspect(1 / math.cos(math.radians(cy)), adjustable='box')
        ia.set_xticks([]), ia.set_yticks([])
        for s in ia.spines.values():
            s.set_color(INK), s.set_linewidth(.6)
        ia.set_title('แผนที่แสดงตำแหน่ง', fontsize=6.5, color=MUTED, pad=2)
    # ---------- สถิติ ----------
    if stats and R.get('kpi') and stats['kpi']:
        kx, ky, kw, kh = R['kpi']
        n = len(stats['kpi'])
        for i, (v, lab) in enumerate(stats['kpi']):
            bx = kx + i * kw / n
            fig.add_artist(Rectangle((bx + .004, ky), kw / n - .012, kh, transform=fig.transFigure, facecolor='white', edgecolor=LINE, lw=.6, zorder=1))
            fig.text(bx + kw / n / 2 - .004, ky + kh * .62, v, fontsize=14, fontweight='bold', color='#1f3a5f', ha='center', va='center')
            fig.text(bx + kw / n / 2 - .004, ky + kh * .26, _wrap(lab, 26), fontsize=6.5, color=MUTED, ha='center', va='center', linespacing=1.3)
    if stats and R.get('stats') and stats.get('bars'):
        sa = fig.add_axes(R['stats'])
        _draw_bars(sa, stats, 9 if tpl == 'poster_a3' else 7)
    elif stats and R.get('stats') and stats['kpi'] and not R.get('kpi'):
        sx, sy, sw, sh = R['stats']
        for i, (v, lab) in enumerate(stats['kpi'][:3]):
            fig.text(sx, sy + sh - i * sh / 3, v, fontsize=11, fontweight='bold', color='#1f3a5f', va='top')
            fig.text(sx, sy + sh - i * sh / 3 - .035, _short(lab, 40), fontsize=6.5, color=MUTED, va='top')
    # ---------- ที่มา/หมายเหตุ ในแผงข้าง ----------
    note = spec.get('note') or ''
    if R.get('prov') and (prov or note):
        px_, py_, cw = R['prov']
        lines = ([_wrap(note, cw)] if note else []) + ([('ข้อมูลและวิธีการ')] if prov else []) + [_short(x, cw) for x in prov[:7]]
        fig.text(px_, py_, '\n'.join(lines), fontsize=7.5 if tpl == 'poster_a3' else 6, color=MUTED, va='top', linespacing=1.45)
    elif note:
        extra_foot.insert(0, 'หมายเหตุ: ' + note)
    # ---------- ส่วนท้าย (ยึดขอบล่าง): ที่มา / วันที่ / ผู้จัดทำ ----------
    foot = [_short('แหล่งข้อมูล: ' + ', '.join(dict.fromkeys(src_names)), 230)] if src_names else []
    if el['attribution'] and attrib:
        foot.append(' · '.join(attrib))
    foot.append(' · '.join(x for x in [f'จัดทำโดย {author}' if author else '', f'วันที่ {date}', 'ระบบพิกัด WGS 84 (EPSG:4326)', f'Ainulindalë {APP_VERSION}'] if x))
    fx = R['map'][0]
    fig.text(fx, .014, '\n'.join(extra_foot + foot), fontsize=6.2, color=MUTED, va='bottom', linespacing=1.5)
    buf = io.BytesIO()
    fig.savefig(buf, format='png' if fmt == 'png' else 'pdf', dpi=dpi, facecolor=fig.get_facecolor())
    plt.close(fig)
    return buf.getvalue()
