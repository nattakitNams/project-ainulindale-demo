# -*- coding: utf-8 -*-
"""รันชุดทดสอบผ่าน API ทั้งหมดตามลำดับ (test_smoke ต้องรันก่อน — เป็นตัวเพิ่มข้อมูลทดสอบเข้าคลัง)

    python tests/api/run_all.py
ตั้งค่าดู tests/api/common.py · ข้อที่ขาดข้อมูล (เช่น ไม่ได้ตั้ง AINU_TEST_VECTORS) จะขึ้น "ข้าม" ไม่นับว่าล้ม
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORDER = ['test_smoke.py', 'test_hex.py', 'test_trash.py', 'test_folders.py', 'test_rasterize.py', 'test_extent.py', 'test_tools.py', 'test_satellite.py', 'test_ai_agent.py', 'test_ai_knowledge.py', 'test_ai_conv.py', 'test_ai.py', 'test_ai_tools.py', 'test_ai_data.py']

res = {}
for f in ORDER:
    print(f'\n========== {f}')
    r = subprocess.run([sys.executable, str(HERE / f)], capture_output=True, text=True, encoding='utf-8', errors='replace')
    out = (r.stdout or '') + (r.stderr or '')
    lines = [l for l in out.splitlines() if l.startswith(('✔', '✘', 'ผล:', 'ข้าม:'))]
    print('\n'.join(lines) or out[-1500:])
    res[f] = 'ข้าม' if any(l.startswith('ข้าม:') for l in lines) else ('ผ่าน' if r.returncode == 0 else 'ล้ม')
print('\n========== สรุป')
for f, s in res.items():
    print(f'{s:5} {f}')
sys.exit(1 if 'ล้ม' in res.values() else 0)
