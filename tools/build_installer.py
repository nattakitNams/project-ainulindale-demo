# -*- coding: utf-8 -*-
"""สร้างตัวติดตั้งจิ๋ว dist/Ainulindale-setup.zip

ใน zip:  Ainulindale.bat · uninstall.bat · python/ (Python แบบพกพาจาก python.org) · app/ · web/
         installer/ (requirements.lock.txt + get-pip.py) · engine.json · README.txt
ผู้ใช้แตก zip → ดับเบิลคลิก Ainulindale.bat → ตัวช่วยติดตั้งในหน้าเว็บดาวน์โหลดแพ็กเกจที่เหลือลงโฟลเดอร์เดียวกัน

ขั้นตอน (ต้องมีอินเทอร์เน็ตตอน build):
  1) ล็อกเวอร์ชัน + SHA-256 ของทุกแพ็กเกจ (รวมแพ็กเกจย่อย) สำหรับ Windows/Python เดียวกับ python ที่แพ็ก
     ด้วย `pip install --dry-run --report` (อ่าน metadata จาก PyPI ไม่ติดตั้งจริง)
  2) แตก Python embeddable · เปิด site-packages · ให้ import โฟลเดอร์แอป (แก้ไฟล์ ._pth)
  3) zip + SHA-256 ของ zip
ใช้:  python tools/build_installer.py --embed <python-x.y.z-embed-amd64.zip> --getpip <get-pip.py> [--web-url URL] [--origin URL ...]
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.config import APP_VERSION  # noqa: E402


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def lock(py_ver, out):
    """requirements.in → requirements.lock.txt (ทุกแพ็กเกจ + hash) สำหรับ win_amd64 / CPython เวอร์ชันเดียวกับที่แพ็ก"""
    tmp = Path(tempfile.mkdtemp())
    rep = tmp / 'report.json'
    cmd = [sys.executable, '-m', 'pip', 'install', '--dry-run', '--ignore-installed', '--quiet', '--no-cache-dir', '--report', str(rep),
           '--only-binary=:all:', '--platform', 'win_amd64', '--python-version', py_ver, '--implementation', 'cp',
           '--target', str(tmp / 't'), '--index-url', 'https://pypi.org/simple', '-r', str(ROOT / 'installer' / 'requirements.in')]
    print('ล็อกเวอร์ชัน:', ' '.join(cmd[3:12]), '…')
    subprocess.run(cmd, check=True)
    items = json.loads(rep.read_text(encoding='utf-8'))['install']
    lines = ['# สร้างโดย tools/build_installer.py — ห้ามแก้มือ · pip ตรวจ SHA-256 ของทุกไฟล์ตอนติดตั้ง (--require-hashes)',
             f'# Windows x64 · CPython {py_ver} · {len(items)} แพ็กเกจ']
    for it in sorted(items, key=lambda i: i['metadata']['name'].lower()):
        md, ai = it['metadata'], it['download_info'].get('archive_info', {})
        h = (ai.get('hashes') or {}).get('sha256') or ai.get('hash', '').split('=')[-1]
        lines.append(f"{md['name']}=={md['version']} --hash=sha256:{h}")
    out.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    shutil.rmtree(tmp, ignore_errors=True)
    print(f'  → {out} ({len(items)} แพ็กเกจ)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--embed', required=True, help='python-x.y.z-embed-amd64.zip จาก python.org')
    ap.add_argument('--getpip', required=True, help='get-pip.py จาก bootstrap.pypa.io')
    ap.add_argument('--web-url', default='', help='ที่อยู่หน้าเว็บที่ deploy (ว่าง = หน้าสำรองในเครื่อง /ui/)')
    ap.add_argument('--origin', action='append', default=[], help='origin ของหน้าเว็บที่อนุญาต (ใส่ได้หลายครั้ง)')
    a = ap.parse_args()
    embed = Path(a.embed)
    py_ver = '.'.join(embed.name.split('-')[1].split('.')[:2])          # python-3.13.x-embed-amd64.zip → 3.13
    dist = ROOT / 'dist'
    out = dist / 'Ainulindale'
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # 1) ล็อกแพ็กเกจ
    (out / 'installer').mkdir()
    lock(py_ver, out / 'installer' / 'requirements.lock.txt')
    shutil.copy2(a.getpip, out / 'installer' / 'get-pip.py')

    # 2) Python แบบพกพา
    with zipfile.ZipFile(embed) as z:
        z.extractall(out / 'python')
    pth = next((out / 'python').glob('python3*._pth'))
    body = [ln for ln in pth.read_text().splitlines() if ln.strip() and not ln.startswith('#')]
    body += ['Lib\\site-packages', '..', 'import site']               # site-packages ของแอป + โฟลเดอร์แอป (import app)
    pth.write_text('\n'.join(body) + '\n')
    (out / 'python' / 'Lib' / 'site-packages').mkdir(parents=True)

    # 3) โค้ด + หน้าเว็บ + สคริปต์
    ign = shutil.ignore_patterns('__pycache__', '*.pyc')
    shutil.copytree(ROOT / 'app', out / 'app', ignore=ign)
    shutil.copytree(ROOT / 'web', out / 'web', ignore=shutil.ignore_patterns('__pycache__', 'download'))
    for f in ('Ainulindale.bat', 'uninstall.bat'):
        shutil.copy2(ROOT / f, out / f)
    origins = a.origin or ([a.web_url.split('/', 3)[0] + '//' + a.web_url.split('/', 3)[2]] if a.web_url else [])
    (out / 'engine.json').write_text(json.dumps(dict(
        _help='หน้าเว็บที่อนุญาตให้สั่งงานตัวประมวลผลเครื่องนี้ · web_url = หน้าที่เปิดให้ตอนเริ่ม (ว่าง = หน้าสำรอง http://127.0.0.1:41217/ui/)',
        web_url=a.web_url, allowed_origins=origins), ensure_ascii=False, indent=1), encoding='utf-8')
    (out / 'README.txt').write_text(
        f'Ainulindale {APP_VERSION}\r\n\r\n1) ดับเบิลคลิก Ainulindale.bat\r\n2) ทำตามตัวช่วยติดตั้งในหน้าเว็บ (ครั้งแรกเท่านั้น ~180 MB จาก PyPI)\r\n'
        '3) ครั้งต่อไปเปิด Ainulindale.bat แล้วใช้งานผ่านหน้าเว็บ\r\n\r\nทุกอย่างอยู่ในโฟลเดอร์นี้ · ถอนการติดตั้ง = รัน uninstall.bat หรือลบโฟลเดอร์นี้\r\n'
        'ไม่ใช้สิทธิ์ admin · ไม่แก้ registry · ไม่แตะ Python ของเครื่อง\r\n', encoding='utf-8-sig')

    # 4) zip + SHA-256
    zp = dist / 'Ainulindale-setup.zip'                               # ชื่อคงที่ → ลิงก์ releases/latest/download ใช้ได้ทุกเวอร์ชัน
    if zp.exists():
        zp.unlink()
    with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(out.rglob('*')):
            if f.is_file():
                z.write(f, Path('Ainulindale') / f.relative_to(out))
    h = sha256(zp)
    (dist / 'SHA256.txt').write_text(f'{h}  {zp.name}\n', encoding='utf-8')
    print(f'\n✔ {zp}  ({zp.stat().st_size / 1e6:.1f} MB)\n  SHA-256 {h}')


if __name__ == '__main__':
    main()
