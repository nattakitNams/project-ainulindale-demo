# -*- coding: utf-8 -*-
"""รวมคำแปล tools/i18n/b*_th.txt + b*_en_NNN.txt (บรรทัดตรงกัน) → web/i18n_en.js

    python tools/i18n_build.py
แต่ละชุด bN: b{N}_th.txt (ไทย บรรทัดละชิ้น) + b{N}_en_<บรรทัดเริ่ม>.txt (อังกฤษ เรียงตามบรรทัด เว้นว่าง = ไม่แปล)
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / 'tools' / 'i18n'


def load():
    out, issues = {}, []
    for th in sorted(D.glob('b*_th.txt')):
        b = th.stem.split('_')[0]
        keys = th.read_text(encoding='utf-8').split('\n')
        en = [None] * len(keys)
        for f in sorted(D.glob(f'{b}_en_*.txt'), key=lambda p: int(p.stem.split('_')[-1])):
            start = int(f.stem.split('_')[-1]) - 1
            lines = f.read_text(encoding='utf-8').rstrip('\n').split('\n')
            for i, s in enumerate(lines):
                if start + i < len(en):
                    en[start + i] = s
        for k, v in zip(keys, en):
            k = k.strip()
            if not k or v is None:
                continue
            v = v.strip()
            if not v or len(k) < 2:
                continue
            if re.search(r'[฀-๿]', v) and not re.search(r'GISTDA|กรม', v):
                issues.append(f'ยังมีอักษรไทยในคำแปล: {k} → {v}')
            out[k] = v
        missing = sum(1 for v in en if v is None)
        print(f'{b}: {len(keys):,} ชิ้น · ยังไม่มีคำแปล {missing:,}')
    return out, issues


if __name__ == '__main__':
    d, issues = load()
    for i in issues[:20]:
        print('  !', i)
    js = '// คำแปลภาษาอังกฤษ (สร้างด้วย tools/i18n_build.py — แก้ที่ tools/i18n/ ไม่ใช่ที่ไฟล์นี้)\nwindow.I18N_EN = ' + json.dumps(d, ensure_ascii=False, indent=0) + ';\n'
    (ROOT / 'web' / 'i18n_en.js').write_text(js, encoding='utf-8')
    print(f'web/i18n_en.js: {len(d):,} คำแปล · {len(js) / 1024:.0f} KB')
