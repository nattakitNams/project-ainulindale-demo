# -*- coding: utf-8 -*-
"""ที่อยู่ข้อมูลอ้างอิง + ตัวเลขที่ตรวจทานแล้ว (PROJECT_BRIEF 2.4) — ใช้ทดสอบทุกเวอร์ชัน"""
import os

from app.dsinfo import find_mydrive

DRIVE = find_mydrive() or r'E:\My Drive'
PROJ = os.environ.get('AINU_REF_PROJECT', os.path.join(DRIVE, 'Gistda', 'p_watePop_v2'))
POP = os.path.join(PROJ, 'raw', 'tha_pop_2024_CN_100m_R2025A_v1.tif')
FLOOD = os.path.join(PROJ, 'raw', 'hr_years_flooded.vrt')
_B = os.path.join(PROJ, 'output', 'bivariate', 'bivariate_ghsl_often5_majority_{}')
BIV = {'3/10': _B.format('10m.vrt'), '3': _B.format('100m.tif'), '30': _B.format('1km.tif')}

# คนทั้งหมด / คนในพื้นที่เคยท่วม (รหัส 4–9) / คนในเขตแดง (8–9)
EXPECT = {
    '3/10': dict(total=71_689_208.10, flooded=15_032_492.83, red=47_719.56),
    '3': dict(total=71_689_208.11, flooded=15_148_932.68, red=36_499.00),
    '30': dict(total=71_689_208.11, flooded=15_527_028.21, red=45_239.26),
}
EXPECT_BY_CODE_10M = {1: 10_241_942, 2: 12_814_699, 3: 33_600_074, 4: 1_914_332, 5: 2_549_788,
                      6: 10_342_758, 7: 177_896, 8: 42_668, 9: 5_051}
