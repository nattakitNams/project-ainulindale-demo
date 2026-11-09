# -*- coding: utf-8 -*-
"""เปลี่ยนเลขเวอร์ชันแอปทุกจุดที่ต้องตรงกัน — แทนเฉพาะรูปแบบของแอปเอง ไม่แตะ URL ไลบรารี (เช่น leaflet-draw@1.0.4)

    python tools/bump_version.py 1.0.6
"""
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES = [
    ('app/config.py', r"(APP_VERSION = ')[\d.]+(')"),
    ('web/app.js', r"(const UI_VERSION = ')[\d.]+(')"),
    ('web/index.html', r'(<meta name="ainu-version" content=")[\d.]+(")'),
    ('web/index.html', r'(href="(?:style|report)\.css\?v=)[\d.]+(")'),
    ('web/index.html', r'(src="(?:config|palette|report|app|ai|hub|i18n|i18n_en)\.js\?v=)[\d.]+(")'),
    ('web/config.js', r"('setup\.js\?v=)[\d.]+(')"),
]


def main(v):
    assert re.fullmatch(r'\d+\.\d+\.\d+', v), 'รูปแบบเวอร์ชัน x.y.z'
    for f, pat in RULES:
        p = ROOT / f
        t = p.read_text(encoding='utf-8')
        t2, n = re.subn(pat, lambda m: m.group(1) + v + m.group(2), t)
        assert n, f'{f}: ไม่พบ {pat}'
        p.write_text(t2, encoding='utf-8')
        print(f'{f}: {n} จุด')
    # ไลบรารีภายนอกต้องโหลดได้จริง (กันพลาดแบบ leaflet-draw@1.0.5 ที่ไม่มีอยู่)
    html = (ROOT / 'web/index.html').read_text(encoding='utf-8')
    for u in re.findall(r'(?:src|href)="(https://unpkg\.com/[^"]+)"', html):
        code = urllib.request.urlopen(urllib.request.Request(u, method='HEAD'), timeout=20).status
        print(('✔' if code == 200 else '✘'), code, u)
        assert code == 200, u


if __name__ == '__main__':
    main(sys.argv[1])
