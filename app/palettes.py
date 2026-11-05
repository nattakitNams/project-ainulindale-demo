# -*- coding: utf-8 -*-
"""พาเลทไบแวเรียต 3×3 จำนวน 10 แบบ (ลำดับสี = รหัส 1→9 ; ตำแหน่ง = x + 3y, x = แกน X ซ้าย→ขวา, y = แกน Y ล่าง→บน)
ที่มา: R package pals (R/bivariate.R) รวม Joshua Stevens, US Census Bureau, Tolochko, ColorBrewer
ขนาดอื่นที่ไม่ใช่ 3×3 → ไล่สีแบบ bilinear ใน OKLab (ทำทั้งฝั่งหน้าเว็บ static/palette.js และที่นี่ให้ผลเท่ากัน)"""
import numpy as np

PALETTES = [
    dict(id='traffic', name='traffic (ไฟล์เดิม)', source='โน้ตบุ๊กเดิม', cb_safe=False, gradient=False,
         colors='#eeeeee #a1d99b #238b45 #c6dbef #fdd49e #fc8d59 #2171b5 #ef3b2c #99000d'),
    dict(id='bluered', name='bluered', source='Joshua Stevens', cb_safe=True, gradient=True,
         colors='#e8e8e8 #e4acac #c85a5a #b0d5df #ad9ea5 #985356 #64acbe #627f8c #574249'),
    dict(id='pinkblue', name='pinkblue', source='Joshua Stevens', cb_safe=True, gradient=True,
         colors='#e8e8e8 #ace4e4 #5ac8c8 #dfb0d6 #a5add3 #5698b9 #be64ac #8c62aa #3b4994'),
    dict(id='greenblue', name='greenblue', source='Joshua Stevens', cb_safe=True, gradient=True,
         colors='#e8e8e8 #b5c0da #6c83b5 #b8d6be #90b2b3 #567994 #73ae80 #5a9178 #2a5a5b'),
    dict(id='purplegold', name='purplegold', source='Joshua Stevens', cb_safe=True, gradient=True,
         colors='#e8e8e8 #e4d9ac #c8b35a #cbb8d7 #c8ada0 #af8e53 #9972af #976b82 #804d36'),
    dict(id='pinkgreen', name='pinkgreen', source='Joshua Stevens', cb_safe=True, gradient=True,
         colors='#f3f3f3 #c2f1ce #8be2af #eac5dd #9ec6d3 #7fc6b1 #e6a3d0 #bc9fce #7b8eaf'),
    dict(id='blueyellow', name='blueyellow', source='US Census Bureau', cb_safe=True, gradient=True,
         colors='#fffdef #fef3a9 #efd100 #e6f1df #bedebc #4eb87b #d2e4f6 #a1c8ea #007fc4'),
    dict(id='redblue', name='redblue', source='Tolochko', cb_safe=True, gradient=True,
         colors='#dddddd #7bb3d1 #016eae #dd7c8a #8d6c8f #4a4779 #cc0024 #8a274a #4b264d'),
    dict(id='seqseq1', name='seqseq1', source='ColorBrewer', cb_safe=True, gradient=True,
         colors='#e8e6f2 #b5d3e7 #4fadd0 #e5b4d9 #b8b3d8 #3983bb #de4fa6 #b03598 #2a1a8a'),
    dict(id='seqseq2', name='seqseq2', source='ColorBrewer', cb_safe=True, gradient=True,
         colors='#f3f3f3 #b4d3e1 #509dc2 #f3e6b3 #b3b3b3 #376387 #f3b300 #b36600 #000000'),
]
for p in PALETTES:
    p['colors'] = p['colors'].split()
DEFAULT_PALETTE = 'bluered'
BY_ID = {p['id']: p for p in PALETTES}


# ---------- OKLab (Björn Ottosson 2020) ----------
def _lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _gam(c):
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(np.clip(c, 0, None), 1 / 2.4) - 0.055)


def hex2rgb(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])


def rgb2hex(c):
    c = np.clip(np.round(np.asarray(c) * 255), 0, 255).astype(int)
    return '#%02x%02x%02x' % tuple(c)


def to_oklab(h):
    r, g, b = _lin(hex2rgb(h))
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l, m, s = np.cbrt([l, m, s])
    return np.array([0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
                     1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
                     0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s])


def from_oklab(L):
    l_ = L[0] + 0.3963377774 * L[1] + 0.2158037573 * L[2]
    m_ = L[0] - 0.1055613458 * L[1] - 0.0638541728 * L[2]
    s_ = L[0] - 0.0894841775 * L[1] - 1.2914855480 * L[2]
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    rgb = np.array([4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
                    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
                    -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s])
    return rgb2hex(_gam(np.clip(rgb, 0, 1)))


def interpolate(colors9, nx, ny):
    """ขยาย/ย่อพาเลท 3×3 เป็น nx×ny : bilinear บนตาราง 3×3 ใน OKLab ; แกนที่มี 1 คลาส ใช้ตำแหน่งกลาง"""
    if nx == 3 and ny == 3:
        return list(colors9)
    lab = np.array([to_oklab(c) for c in colors9]).reshape(3, 3, 3)   # [y][x][lab]
    out = []
    for y in range(ny):
        v = 1.0 if ny == 1 else 2.0 * y / (ny - 1)
        for x in range(nx):
            u = 1.0 if nx == 1 else 2.0 * x / (nx - 1)
            x0, y0 = min(int(u), 1), min(int(v), 1)
            fu, fv = u - x0, v - y0
            c = (lab[y0, x0] * (1 - fu) * (1 - fv) + lab[y0, x0 + 1] * fu * (1 - fv)
                 + lab[y0 + 1, x0] * (1 - fu) * fv + lab[y0 + 1, x0 + 1] * fu * fv)
            out.append(from_oklab(c))
    return out
