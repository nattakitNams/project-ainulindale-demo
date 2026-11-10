# -*- coding: utf-8 -*-
"""ค่าที่ใช้ร่วมกันของชุดทดสอบผ่าน API (ทดสอบกับตัวประมวลผลที่รันอยู่จริง)

ตั้งค่าด้วย environment variable — ไม่ฝัง path ของเครื่องใดไว้ในโค้ด:
  AINU_TEST_ENGINE   ที่อยู่ตัวประมวลผลสำหรับทดสอบ (ค่าเริ่มต้น http://127.0.0.1:41299)
                     แนะนำรันแยกจากของจริง: set AINU_PORT=41299 & set AINU_WORKSPACE=<โฟลเดอร์ทดสอบ> & python -m app.server --no-browser
  AINU_TEST_DATA     โฟลเดอร์ข้อมูลทดสอบ raster: wp_bkk.tif (WorldPop ตัดกทม., count), ndvi_bkk.tif (NDVI), vnl_edge.tif (night light จำลอง)
  AINU_TEST_NTL      ไฟล์ night light จริง (VIIRS VNL ทั้งโลก int16 scale ×10) — ไม่มี = ข้ามข้อที่ต้องใช้
  AINU_TEST_VECTORS  โฟลเดอร์เวกเตอร์ทดสอบ: building/Building 23_16.shp (อาคาร 1 feature หลายหมื่นส่วน)
                     และ เชียงใหม่2553/การใช้ที่ดิน/LU_CMI_2553.shp (ฟิลด์ไทย TIS-620) — ไม่มี = ข้าม
"""
import os
import time
from pathlib import Path

import requests

ENGINE = os.environ.get('AINU_TEST_ENGINE', 'http://127.0.0.1:41299').rstrip('/')
DATA = Path(os.environ['AINU_TEST_DATA']) if os.environ.get('AINU_TEST_DATA') else None
NTL = Path(os.environ['AINU_TEST_NTL']) if os.environ.get('AINU_TEST_NTL') else None
VECTORS = Path(os.environ['AINU_TEST_VECTORS']) if os.environ.get('AINU_TEST_VECTORS') else None

session = requests.Session()
session.headers['Origin'] = ENGINE          # หน้าของตัวประมวลผลเอง (same-origin) → ไม่ต้องใช้โทเคนจับคู่


def wait_engine(sec=30):
    for _ in range(sec):
        try:
            session.get(ENGINE + '/api/engine/hello', timeout=2)
            return True
        except requests.RequestException:
            time.sleep(1)
    raise SystemExit(f'ติดต่อตัวประมวลผลที่ {ENGINE} ไม่ได้ — เปิดตัวประมวลผลทดสอบก่อน (ดู README หัวข้อการทดสอบ)')


def need(path, what):
    if path is None or not Path(path).exists():
        raise SystemExit(f'ข้าม: ต้องตั้ง {what} (ดู tests/api/common.py)')
    return Path(path)


class Results:
    def __init__(self):
        self.ok = []

    def check(self, name, cond, extra=''):
        self.ok.append(bool(cond))
        print(('✔' if cond else '✘'), name, extra)

    def done(self):
        print(f'\nผล: ผ่าน {sum(self.ok)}/{len(self.ok)}')
        return 0 if all(self.ok) else 1
