# -*- coding: utf-8 -*-
"""เทียบผลไบแวเรียตที่แอปสร้าง กับไฟล์เดิมทีละพิกเซล + ตัวเลข PROJECT_BRIEF 2.4
รัน:  python -m tests.compare_output <โฟลเดอร์ผลลัพธ์ใน workspace/maps> <3/10 | 3 | 30>"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.refdata import BIV, EXPECT, EXPECT_BY_CODE_10M  # noqa: E402


def main(out_dir, res):
    out_dir = Path(out_dir)
    tif = next(p for p in out_dir.glob('*.tif'))
    lin = json.loads((out_dir / 'lineage.json').read_text(encoding='utf-8'))
    s = lin['stats_summary']
    fails = 0
    a, b = rasterio.open(tif), rasterio.open(BIV[res])
    if (a.width, a.height) != (b.width, b.height):
        print(f'✘ ขนาดไม่ตรง {a.width}×{a.height} กับ {b.width}×{b.height}')
        return 1
    print(f'ขนาด {a.width:,} × {a.height:,} ✔ · transform ต่างกันสูงสุด {max(abs(x - y) for x, y in zip(a.transform, b.transform)):.2e}')
    bad = 0
    B = 5120
    n = 0
    for r0 in range(0, a.height, B):
        for c0 in range(0, a.width, B):
            w = Window(c0, r0, min(B, a.width - c0), min(B, a.height - r0))
            x, y = a.read(1, window=w), b.read(1, window=w)
            bad += int((x != y).sum())
            n += 1
        print(f'  แถว {r0:,}/{a.height:,} · ไม่ตรงสะสม {bad:,}', flush=True)
    print(('✔' if bad == 0 else '✘') + f' พิกเซลไม่ตรง {bad:,}')
    fails += bad > 0
    e = EXPECT[res]
    wc = s['weight_by_code']
    got = dict(total=s['weight_total'], flooded=sum(wc[str(c)] for c in range(4, 10)), red=sum(wc[str(c)] for c in (8, 9)))
    for k in ('total', 'flooded', 'red'):
        ok = abs(got[k] - e[k]) < 0.02
        fails += not ok
        print(f'{"✔" if ok else "✘"} {k}: {got[k]:,.2f} (คาด {e[k]:,.2f})')
    if res == '3/10':
        for c, v in EXPECT_BY_CODE_10M.items():
            ok = abs(wc[str(c)] - v) < 1
            fails += not ok
            print(f'{"✔" if ok else "✘"} รหัส {c}: {wc[str(c)]:,.0f} (คาด {v:,})')
    print('ผล:', 'ผ่าน ✔' if not fails else f'ไม่ผ่าน ✘ ({fails})')
    return fails


if __name__ == '__main__':
    sys.exit(1 if main(sys.argv[1], sys.argv[2]) else 0)
