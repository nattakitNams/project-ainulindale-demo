# -*- coding: utf-8 -*-
"""คิวงาน: งานยาวรันใน process แยก (python -m app.worker <id>) ทีละงาน — หน้าจอไม่ค้าง
ความคืบหน้า/ข้อความ/ผลลัพธ์ เก็บในตาราง jobs ; log เต็มอยู่ที่ workspace/logs/job_<id>.log"""
import os
import subprocess
import sys
import threading
import time

from . import db, export
from .config import DIRS, ROOT

OUT_BASE = dict(resample='derived', bivariate='maps', rasterize='derived', vgrid='derived',
                download='database', zonal='maps', change='derived', sensitivity='maps', hex='derived', hexbiv='maps',
                calc='derived', trend='derived', mosaic='derived', vmerge='derived')
_lock = threading.Lock()
_procs = {}


def submit(kind, params, title):
    out_dir = None
    if kind in OUT_BASE:
        out_dir = str(export.new_out_dir(DIRS[OUT_BASE[kind]], kind, params.get('name') or title, params))
    jid = db.insert('jobs', kind=kind, title=title, params=params, status='queued', created_at=db.now(), out_dir=out_dir)
    db.update('jobs', jid, log_path=str(DIRS['logs'] / f'job_{jid}.log'))
    kick()
    return jid


def pid_alive(pid):
    if not pid:
        return False
    if os.name == 'nt':
        import ctypes
        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        h = k32.OpenProcess(0x1000, False, int(pid))                      # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            # เปิดไม่ได้เพราะ "ไม่มีสิทธิ์" (5) = process ยังอยู่ (เช่น เริ่มจากเซิร์ฟเวอร์ตัวก่อน) ; 87 = ไม่มี pid นี้แล้ว
            return ctypes.get_last_error() == 5
        code = ctypes.c_ulong()
        k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return code.value == 259                                          # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def recover():
    """ตอนเปิดแอป: งานที่ค้างสถานะ running แต่ process ตายแล้ว → failed"""
    for j in db.query("SELECT * FROM jobs WHERE status IN ('running','cancelling')"):
        if not pid_alive(j['pid']):
            db.update('jobs', j['id'], status='failed', error='แอปถูกปิดหรือ process หยุดระหว่างทำงาน', finished_at=db.now())


def kick():
    """เริ่มงานถัดไปถ้าไม่มีงานที่กำลังรัน"""
    with _lock:
        running = db.query("SELECT * FROM jobs WHERE status IN ('running','cancelling')")
        running = [j for j in running if pid_alive(j['pid']) or j['id'] in _procs and _procs[j['id']].poll() is None]
        if running:
            return
        q = db.query("SELECT * FROM jobs WHERE status='queued' ORDER BY id LIMIT 1")
        if not q:
            return
        j = q[0]
        flags = 0x08000000 if os.name == 'nt' else 0                           # CREATE_NO_WINDOW
        pr = subprocess.Popen([sys.executable, '-m', 'app.worker', str(j['id'])], cwd=str(ROOT), creationflags=flags,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _procs[j['id']] = pr
        db.update('jobs', j['id'], status='running', pid=pr.pid, started_at=db.now())


FORCE_AFTER = 15          # วินาที — worker ไม่ตอบรับการยกเลิก (เช่น ติดอยู่ใน GDAL สร้าง overview) → บังคับหยุด


def _kill(jid, pid, why):
    import signal
    try:
        os.kill(int(pid), signal.SIGTERM)                                  # Windows = TerminateProcess
    except OSError:
        pass
    _procs.pop(jid, None)
    db.update('jobs', jid, status='cancelled', message=why, finished_at=db.now())


def cancel(jid, force=False):
    """ยกเลิก: ขอให้ worker หยุดเอง (ตรวจทุกครั้งที่รายงานความคืบหน้า) ; ไม่หยุดใน FORCE_AFTER วินาที หรือ force → ฆ่า process"""
    j = db.get('jobs', jid)
    if j is None:
        return False
    if j['status'] == 'queued':
        db.update('jobs', jid, status='cancelled', finished_at=db.now())
    elif j['status'] in ('running', 'cancelling'):
        if force:
            _kill(jid, j['pid'], 'ยกเลิกแล้ว (บังคับหยุด)')
            return True
        db.update('jobs', jid, status='cancelling')

        def watch():
            for _ in range(FORCE_AFTER * 2):
                time.sleep(0.5)
                jj = db.get('jobs', jid)
                if not jj or jj['status'] != 'cancelling' or not pid_alive(jj['pid']):
                    if jj and jj['status'] == 'cancelling':          # process ตายไปแล้วแต่สถานะค้าง
                        db.update('jobs', jid, status='cancelled', finished_at=db.now())
                    return
            _kill(jid, j['pid'], f'ยกเลิกแล้ว (บังคับหยุดหลังรอ {FORCE_AFTER} วินาที — ตอนนั้นอยู่ในขั้นที่หยุดกลางทางไม่ได้)')
        threading.Thread(target=watch, daemon=True).start()
    return True


def dispatcher():
    while True:
        try:
            for jid, pr in list(_procs.items()):
                if pr.poll() is not None:
                    _procs.pop(jid, None)
                    j = db.get('jobs', jid)
                    if j and j['status'] in ('running', 'cancelling'):
                        db.update('jobs', jid, status='failed', error=f'process จบโดยไม่รายงานผล (exit {pr.returncode})',
                                  finished_at=db.now())
            kick()
        except Exception as e:
            print('[คิวงาน]', e)
        time.sleep(1.5)


def start_dispatcher():
    recover()
    threading.Thread(target=dispatcher, daemon=True).start()


def log_tail(j, n=60):
    p = j.get('log_path')
    if not p or not os.path.exists(p):
        return []
    with open(p, encoding='utf-8', errors='replace') as f:
        return f.read().splitlines()[-n:]
