# -*- coding: utf-8 -*-
"""จุดเริ่ม (Ainulindale.bat เรียก): ติดตั้งแล้ว → ตัวประมวลผล · ยังไม่ได้ติดตั้ง → ตัวช่วยติดตั้ง"""
import os
import site
import subprocess
import sys

from .config import ROOT


def installed():
    if not (ROOT / '.installed.json').exists():
        return False
    try:
        import flask  # noqa: F401
        import rasterio  # noqa: F401
        return True
    except ImportError:
        return False


def main():
    # ห้ามใช้แพ็กเกจจาก Python ของผู้ใช้ (%APPDATA%\Python\…) — ปนกับของแอปแล้วพังแบบหาสาเหตุยาก
    # Ainulindale.bat ตั้ง PYTHONNOUSERSITE=1 ให้แล้ว · ถ้าถูกเรียกตรงๆ ให้รันตัวเองใหม่แบบปิด user site
    if site.ENABLE_USER_SITE and os.environ.get('PYTHONNOUSERSITE') != '1':
        os.environ['PYTHONNOUSERSITE'] = '1'
        sys.exit(subprocess.call([sys.executable, '-m', 'app.launch', *sys.argv[1:]]))
    if installed():
        from . import server
        server.main()
    else:
        from . import setup_server
        setup_server.main()


if __name__ == '__main__':
    main()
