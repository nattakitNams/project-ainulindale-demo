# -*- coding: utf-8 -*-
"""ค่าตั้งของแอป — path ของ workspace, พอร์ต, เวอร์ชัน

v1: ทุกอย่างอยู่ในโฟลเดอร์แอปโฟลเดอร์เดียว (ลบทิ้งทีเดียวจบ)
    ROOT/settings.json  ← ตัวช่วยติดตั้งเขียน (ที่เก็บผลลัพธ์ที่ผู้ใช้เลือก)
    ROOT/workspace/     ← ค่าเริ่มต้นของที่เก็บผลลัพธ์ แคช log โทเคน
"""
import json
import os
from pathlib import Path

APP_NAME = 'project_Ainulindale'
APP_VERSION = '1.0.35'

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = ROOT / 'settings.json'


def load_settings():
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_settings(**kw):
    s = load_settings()
    s.update(kw)
    SETTINGS_PATH.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding='utf-8')
    return s


WORKSPACE = Path(os.environ.get('AINU_WORKSPACE') or load_settings().get('workspace') or ROOT / 'workspace')
DB_PATH = WORKSPACE / 'catalog.db'
DIRS = {k: WORKSPACE / k for k in ('database', 'derived', 'maps', 'aoi', 'cache', 'logs')}
STATIC = ROOT / 'web'                       # หน้าเว็บ (deploy แยกได้ · ตัวประมวลผลเสิร์ฟสำรองที่ /ui/)
PORT = int(os.environ.get('AINU_PORT', 41217))   # พอร์ตแปลก ไม่ชนโปรแกรมอื่น · ต่ำกว่าช่วงพอร์ตชั่วคราวของ Windows (49152+)

# ไม่เขียนอะไรนอกโฟลเดอร์แอป: matplotlib ปกติเก็บแคชฟอนต์ที่ ~/.matplotlib
os.environ.setdefault('MPLCONFIGDIR', str(WORKSPACE / 'cache' / 'matplotlib'))

KM_PER_DEG = 111.32                 # สูตรพื้นที่พิกเซลเดียวกับโปรเจกต์เดิม (ตรวจทานแล้ว)
PREVIEW_MAX_PX = 200_000_000        # สำเนาพรีวิวไม่เกินกี่พิกเซล (ใหญ่กว่านี้ → ย่อ)
PREVIEW_NEED_PX = 4_000_000         # raster ใหญ่กว่านี้และไม่มี overview → สร้างสำเนาพรีวิว
SAMPLE_N = 200_000                  # จำนวนค่าสุ่มเก็บไว้คำนวณควอนไทล์ / ฮิสโทแกรม
INMEM_OUT_PX = 64_000_000           # ผลลัพธ์เล็กกว่านี้ → เก็บทั้งภาพในหน่วยความจำแล้วเขียนทีเดียว


def ensure_workspace():
    for d in DIRS.values():
        d.mkdir(parents=True, exist_ok=True)
