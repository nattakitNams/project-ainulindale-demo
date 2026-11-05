# -*- coding: utf-8 -*-
"""ไฟล์ส่งออก: QML (QGIS), legend PNG, stats CSV, lineage.json, โฟลเดอร์ผลลัพธ์"""
import csv
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import quoteattr

from .config import APP_VERSION


def slug(s, n=40):
    """ชื่อไฟล์/โฟลเดอร์ที่ปลอดภัย — เก็บสระ/วรรณยุกต์ไทยไว้ (\\w ของ Python ไม่นับเครื่องหมายกำกับ Mn เช่น ั ิ ี ุ ่ ้
    ทำให้ 'ปรับ' กลายเป็น 'ปร_บ') ; ตัดเฉพาะอักขระที่ Windows ห้าม + ช่องว่าง + สัญลักษณ์"""
    import unicodedata
    s = unicodedata.normalize('NFC', str(s))
    out = []
    for ch in s:
        cat = unicodedata.category(ch)
        out.append(ch if (ch.isalnum() or ch in '-_' or cat in ('Mn', 'Mc')) else '_')
    s = re.sub(r'_+', '_', ''.join(out)).strip('_')
    s = s[:n].rstrip('_')
    return s or 'out'


def new_out_dir(base, op, name, params):
    """โฟลเดอร์ใหม่ทุกครั้ง: <วันเวลา>_<งาน>_<ชื่อ>_<hash ค่าที่ตั้ง> — กันบั๊ก "ผลเก่าค้าง" """
    h = hashlib.sha1(json.dumps(params, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:8]
    d = Path(base) / f'{datetime.now():%Y%m%d_%H%M%S}_{op}_{slug(name)}_{h}'
    d.mkdir(parents=True, exist_ok=False)
    return d


def qml_paletted(entries):
    """entries = [(ค่า, '#rrggbb', ป้ายชื่อ)] — ป้ายชื่อต้อง escape (เช่น '<300') ไม่อย่างนั้น QGIS โหลดสีไม่ได้เงียบ ๆ"""
    ents = ''.join(f'<paletteEntry value="{v}" color="{c}" alpha="255" label={quoteattr(lbl)}/>' for v, c, lbl in entries)
    return ('<!DOCTYPE qgis PUBLIC \'http://mrcc.com/qgis.dtd\' \'SYSTEM\'>\n'
            '<qgis version="3.28" styleCategories="AllStyleCategories">\n <pipe>\n'
            '  <rasterrenderer type="paletted" band="1" opacity="1" alphaBand="-1" nodataColor="">\n'
            f'   <colorPalette>{ents}</colorPalette>\n  </rasterrenderer>\n </pipe>\n</qgis>\n')


def write_lineage(out_dir, operation, inputs, params, outputs, stats_summary=None, warnings=None):
    d = dict(id=Path(out_dir).name, created_at=datetime.now().isoformat(timespec='seconds'), operation=operation,
             app_version=APP_VERSION, inputs=inputs, params=params, outputs=[str(o) for o in outputs],
             stats_summary=stats_summary or {}, warnings=warnings or [])
    p = Path(out_dir) / 'lineage.json'
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding='utf-8')
    return p


def lineage_input(ds):
    return dict(dataset_id=ds.get('id'), name=ds.get('name'), path=ds.get('path'), read_path=ds.get('read_path'),
                fingerprint=ds.get('fingerprint'), value_type=ds.get('value_type'), nodata_as=ds.get('nodata_as'), exclude_values=ds.get('exclude_values'),
                band=ds.get('band') or 1)


def write_csv(path, header, rows):
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


# ---------- legend ----------
def _font(size):
    from PIL import ImageFont
    for f in ('tahoma.ttf', 'LeelawUI.ttf', 'leelawad.ttf', 'arial.ttf'):
        p = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts', f)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def legend_png(path, nx, ny, colors, x_name, y_name, x_labels, y_labels, highlight=()):
    """ตาราง nx×ny : แกน X ซ้าย→ขวา, แกน Y ล่าง→บน ; ช่องเขตเน้นมีกรอบหนา"""
    from PIL import Image, ImageDraw
    f, fb = _font(13), _font(15)
    cell = int(max([56] + [f.getlength(s) + 10 for s in x_labels]))
    lw = max([f.getlength(s) for s in y_labels] + [60]) + 24
    W = int(max(lw + nx * cell + 30, fb.getlength(y_name) + 16, lw + fb.getlength(x_name) + 40))
    H = int(30 + ny * cell + 30 + 18 * 2 + 20)
    im = Image.new('RGB', (W, max(H, 200)), 'white')
    d = ImageDraw.Draw(im)
    gx, gy = int(lw), 30
    d.text((8, 6), y_name, fill='black', font=fb)
    for y in range(ny):
        for x in range(nx):
            code = y * nx + x + 1
            X0, Y0 = gx + x * cell, gy + (ny - 1 - y) * cell
            d.rectangle([X0, Y0, X0 + cell - 2, Y0 + cell - 2], fill=colors[code - 1])
            if code in highlight:
                d.rectangle([X0, Y0, X0 + cell - 2, Y0 + cell - 2], outline='black', width=3)
            h = colors[code - 1].lstrip('#')
            lum = 0.299 * int(h[0:2], 16) + 0.587 * int(h[2:4], 16) + 0.114 * int(h[4:6], 16)
            d.text((X0 + 5, Y0 + 4), str(code), fill='#222222' if lum > 110 else '#ffffff', font=_font(10))
        lbl = y_labels[y]
        d.text((gx - 8 - f.getlength(lbl), gy + (ny - 1 - y) * cell + cell / 2 - 8), lbl, fill='black', font=f)
    yb = gy + ny * cell + 4
    for x in range(nx):
        lbl = x_labels[x]
        d.text((gx + x * cell + cell / 2 - f.getlength(lbl) / 2, yb), lbl, fill='black', font=f)
    d.text((gx, yb + 22), x_name + '  →', fill='black', font=fb)
    im.save(path)
    return path


def class_labels(clf_cfg, unit=''):
    """ป้ายช่วงของแต่ละคลาสจากเกณฑ์ ; ค่าเท่าเกณฑ์อยู่ชั้นบน"""
    n = int(clf_cfg.get('n', 3))
    if clf_cfg.get('method') == 'degurba':
        d = clf_cfg.get('degurba') or {}
        dn, mp = d.get('dens', [300, 1500]), d.get('minpop', [5000, 50000])
        return ['ชนบท', f'กลุ่มเมือง (≥{dn[0]:,}, รวม ≥{mp[0]:,})', f'ศูนย์กลางเมือง (≥{dn[1]:,}, รวม ≥{mp[1]:,})']
    b = clf_cfg.get('breaks', [])
    if n == 1:
        return ['ทั้งหมด']

    def fm(v):
        return f'{v:,.0f}' if float(v).is_integer() else f'{v:,.4g}'
    out = [f'<{fm(b[0])}']
    for i in range(1, n - 1):
        out.append(f'{fm(b[i - 1])}–<{fm(b[i])}')
    out.append(f'≥{fm(b[-1])}')
    names = clf_cfg.get('class_names') or []
    return [f'{names[i]} {out[i]}' if i < len(names) and names[i] else out[i] for i in range(n)]
