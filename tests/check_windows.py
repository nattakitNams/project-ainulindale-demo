# -*- coding: utf-8 -*-
"""ทดสอบเร็ว: คำนวณรหัสไบแวเรียตด้วย engine บนหน้าต่างตัวอย่าง แล้วเทียบกับไฟล์เดิมทีละพิกเซล
รัน:  python -m tests.check_windows   (จากโฟลเดอร์ p_Ainulindale)"""
import os
import sys
from fractions import Fraction

import numpy as np
import rasterio
from rasterio.windows import Window

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import dsinfo, engine  # noqa: E402
from tests.refdata import BIV, FLOOD, POP  # noqa: E402


def src(path, vt, nodata_as=None, name=''):
    rp, _ = dsinfo.fix_vrt(path, 'test')
    return engine.Source(dict(path=path, read_path=rp, meta=dsinfo.raster_meta(path, rp), value_type=vt,
                              nodata_as=nodata_as, name=name or os.path.basename(path)))


def main():
    sp = src(POP, 'count', name='pop')
    sf = src(FLOOD, 'class', nodata_as=0, name='flood')
    clx = engine.Classifier(dict(n=3, method='breaks', breaks=[300, 1500], metric='density'))
    cly = engine.Classifier(dict(n=3, method='breaks', breaks=[1, 5], metric='value'))
    clx_deg = engine.Classifier(dict(n=3, method='degurba', metric='density'))
    bad = 0
    # หน้าต่างตัวอย่าง (หน่วย: พิกเซลแม่ 100 ม.) — กรุงเทพฯ, อยุธยา/สิงห์บุรี, เชียงใหม่, หาดใหญ่
    wins = [(7900, 3650, 300, 300), (6600, 3550, 400, 400), (1900, 1900, 200, 200), (16050, 3650, 200, 200)]
    for res, f in (('3/10', 10), ('3', 1)):
        g = engine.make_grid([sp, sf], Fraction(res))
        ox, oy = engine.OnGrid(sp, g), engine.OnGrid(sf, g)
        ref = rasterio.open(BIV[res])
        for (r, c, h, w) in wins:
            R, C, H, W = r * f, c * f, h * f, w * f
            if f == 10:
                R, C = R // 10 * 10, C // 10 * 10
            cx = ox.classes(clx, R, C, H, W)
            cy = oy.classes(cly, R, C, H, W)
            ok = (cx >= 0) & (cy >= 0)
            code = np.where(ok, cy * 3 + cx + 1, 0)
            exp = ref.read(1, window=Window(C, R, W, H))
            n = int((code != exp).sum())
            bad += n
            print(f'{res}″ หน้าต่าง {r},{c}: พิกเซล {code.size:,} · ไม่ตรง {n:,} · รหัส>0 {int((exp > 0).sum()):,}')
    # 1 กม. ทั้งประเทศ (DEGURBA + majority จาก 10 ม. — อ่านน้ำท่วมทั้งประเทศ จึงทำเฉพาะเมื่อสั่ง --1km)
    if '--1km' in sys.argv:
        g = engine.make_grid([sp, sf], Fraction(30))
        ox, oy = engine.OnGrid(sp, g), engine.OnGrid(sf, g)
        deg = engine.degurba_classes(ox, g, clx_deg)
        ref = rasterio.open(BIV['30']).read(1)
        code = np.zeros(ref.shape, 'uint8')
        for (r0, c0, h, w) in engine.iter_tiles(g, 50):
            cy = oy.classes(cly, r0, c0, h, w)
            cx = deg[r0:r0 + h, c0:c0 + w]
            ok = (cx >= 0) & (cy >= 0)
            code[r0:r0 + h, c0:c0 + w] = np.where(ok, cy * 3 + cx + 1, 0)
        n = int((code != ref).sum())
        bad += n
        print(f'1 กม. ทั้งประเทศ: ไม่ตรง {n:,} จาก {ref.size:,}')
    print('ผล:', 'ผ่าน ✔' if bad == 0 else f'ไม่ผ่าน ✘ ({bad:,} พิกเซล)')
    return bad


if __name__ == '__main__':
    sys.exit(1 if main() else 0)
