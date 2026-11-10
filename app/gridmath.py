# -*- coding: utf-8 -*-
"""ความละเอียดแบบค่าแม่นยำ + กลุ่มกริด + พื้นที่พิกเซล

ความละเอียดของ CRS องศาเก็บเป็น "ฟิลิปดา (arc-second)" แบบเศษส่วน เช่น 8.3333333e-05° = 3/10″
ความละเอียดของ CRS เมตรเก็บเป็นเมตรแบบเศษส่วน
ไฟล์จริงเก็บทศนิยมไม่ตรงกัน (8.3333333e-05 กับ 8.3333332999999994e-05) → เทียบแบบมี tolerance"""
import math
from fractions import Fraction

import numpy as np

from .config import KM_PER_DEG

REL_TOL = 1e-6          # ความคลาดเคลื่อนสัมพัทธ์ที่ยอมให้ถือว่าเป็นค่าเดียวกัน


def exact_res(res, geographic):
    """ขนาดพิกเซล (หน่วยของ CRS) → Fraction (ฟิลิปดา หรือ เมตร) ; None ถ้าหาเศษส่วนง่าย ๆ ไม่ได้"""
    v = res * 3600 if geographic else res
    for den in (1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 25, 32, 40, 50, 60, 64, 100, 120, 128, 200, 256, 1000):
        f = Fraction(round(v * den), den)
        if f > 0 and abs(float(f) - v) <= REL_TOL * v:
            return f
    # กริดไทล์ WGS84 (ภาพดาวเทียมจากบริการไทล์) ขนาดพิกเซล = 180°/(512·2^z) → เศษส่วนฐานสองแท้
    # ตัวส่วนใหญ่จับค่าสุ่มได้ง่าย → ยอมรับเฉพาะที่ตรงเกือบเป๊ะ (float แทนเศษส่วนฐานสองได้แม่นอยู่แล้ว)
    for k in range(9, 21):
        den = 2 ** k
        f = Fraction(round(v * den), den)
        if f > 0 and abs(float(f) - v) <= 1e-12 * v:
            return f
    return None


def frac_str(f):
    return str(f.numerator) if f.denominator == 1 else f'{f.numerator}/{f.denominator}'


def parse_frac(s):
    return Fraction(s)


def fmt_num(x):
    s = f'{x:.6f}'.rstrip('0').rstrip('.')
    return s


def res_label(f, geographic, lat=None):
    """'3″ (≈ 93 × 93 ม. ที่ 14°N)' — แสดง 2 หน่วยเสมอ"""
    if f is None:
        return 'ไม่ทราบ'
    if geographic:
        sec = float(f)
        main = f'{fmt_num(sec)}″' if sec < 60 else (f'{fmt_num(sec / 60)}′' if sec < 3600 else f'{fmt_num(sec / 3600)}°')
        deg = sec / 3600
        la = 14.0 if lat is None else lat
        dx = deg * KM_PER_DEG * math.cos(math.radians(la)) * 1000
        dy = deg * KM_PER_DEG * 1000
        return f'{main} (≈ {_len(dx)} × {_len(dy)} ที่ {abs(la):.0f}°{"N" if la >= 0 else "S"})'
    m = float(f)
    return _len(m)


def _len(m):
    if m >= 1000:
        return f'{fmt_num(round(m / 1000, 2))} กม.'
    if m >= 10:
        return f'{m:.0f} ม.'
    return f'{fmt_num(round(m, 2))} ม.'


def res_to_units(f, geographic):
    """Fraction (ฟิลิปดา/เมตร) → ขนาดพิกเซลในหน่วยของ CRS (float)"""
    return float(f) / 3600 if geographic else float(f)


def row_area_km2(res_deg, lat):
    """พื้นที่พิกเซล (ตร.กม.) = (ขนาด° × 111.32)² × cos(ละติจูดกึ่งกลางแถว) — สูตรที่ใช้ทำไฟล์เดิม"""
    return (res_deg * KM_PER_DEG) ** 2 * np.cos(np.radians(lat))


def pixel_area_rows(geographic, res_x, res_y, y0, row0, nrows):
    """พื้นที่พิกเซลรายแถว (ตร.กม.) ของแถว row0 … row0+nrows-1 ; y0 = ขอบบนของกริด"""
    if geographic:
        lat = y0 - abs(res_y) * (row0 + np.arange(nrows) + 0.5)
        return row_area_km2(abs(res_x), lat) if abs(abs(res_x) - abs(res_y)) <= REL_TOL * abs(res_x) \
            else (abs(res_x) * KM_PER_DEG) * (abs(res_y) * KM_PER_DEG) * np.cos(np.radians(lat))
    return np.full(nrows, abs(res_x * res_y) / 1e6)


def ratio(a, b):
    """a / b แบบเศษส่วน (a, b เป็น Fraction)"""
    return Fraction(a) / Fraction(b)


def family_key(meta):
    """กลุ่มกริด = CRS + มุมเริ่ม (ปัดตามความละเอียด) ; ความละเอียดที่เป็นพหุคูณกันอยู่กลุ่มเดียวกัน"""
    if meta.get('kind') != 'raster' or not meta.get('crs_key'):
        return None
    t = meta['transform']
    q = 1e7 if meta.get('geographic') else 1e3
    return f"{meta['crs_key']}|{round(t[2] * q) / q}|{round(t[5] * q) / q}"


def same_origin(ma, mb):
    """มุมเริ่มตรงกันภายใน 1/1000 ของพิกเซลที่ละเอียดกว่า"""
    ta, tb = ma['transform'], mb['transform']
    tol = min(abs(ta[0]), abs(tb[0])) * 1e-3
    return ma.get('crs_key') == mb.get('crs_key') and abs(ta[2] - tb[2]) <= tol and abs(ta[5] - tb[5]) <= tol


def int_ratio(r):
    """r (Fraction) → ('same',1) / ('up',k) ถ้า r=k / ('down',m) ถ้า r=1/m / None ถ้าไม่ใช่จำนวนเต็ม"""
    if r == 1:
        return ('same', 1)
    if r > 1 and r.denominator == 1:
        return ('up', r.numerator)       # ต้นทางหยาบกว่าเป้าหมาย k เท่า → แตกพิกเซล
    if r < 1 and r.numerator == 1:
        return ('down', r.denominator)   # ต้นทางละเอียดกว่า m เท่า → รวมพิกเซล
    return None
