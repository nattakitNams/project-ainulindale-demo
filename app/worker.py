# -*- coding: utf-8 -*-
"""รันงานหนึ่งงาน: python -m app.worker <job_id>"""
import os
import sys
import time

# GDAL ใช้ทุกคอร์: overview เร็วขึ้น ~3.6 เท่า (วัดจริง 143 → 40 วินาที ที่ 0.3″ ทั้งประเทศ)
os.environ.setdefault('GDAL_NUM_THREADS', 'ALL_CPUS')
import traceback
from datetime import datetime

from . import db, ops, ops3, ops_hex
from .config import ensure_workspace


def _timing_to_lineage(out_dir, timing):
    """บันทึกเวลาประมวลผลลง lineage.json ของผลลัพธ์ (รอคิว / เริ่ม / เสร็จ / ใช้เวลา)"""
    import json
    from pathlib import Path
    if not out_dir:
        return
    p = Path(out_dir) / 'lineage.json'
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding='utf-8'))
            d['timing'] = timing
            p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding='utf-8')
        except (ValueError, OSError):
            pass


def main(jid):
    ensure_workspace()
    job = db.get('jobs', jid)
    logf = open(job['log_path'], 'a', encoding='utf-8')

    def log(msg):
        logf.write(f'[{datetime.now():%H:%M:%S}] {msg}\n')
        logf.flush()

    last = [0.0, None]
    t0 = time.time()

    def progress(frac, msg=None):
        now = time.time()
        if frac is None:
            frac = last[1] if last[1] is not None else 0
        last[1] = frac
        if now - last[0] < 1.0 and frac < 1:
            return
        last[0] = now
        el = now - t0
        eta = el / frac * (1 - frac) if frac > 0 and (frac >= 0.02 or el >= 8) else None          # เวลาที่เหลือโดยประมาณ (ตามอัตราที่ผ่านมา)
        db.update('jobs', jid, progress=float(frac), message=msg, elapsed_s=el, eta_s=eta)
        if msg:
            log(msg)
        st = db.get('jobs', jid)['status']
        if st == 'cancelling':
            raise ops.Cancelled()

    log(f'เริ่มงาน #{jid} {job["kind"]} · {job["title"]}')
    if job.get('out_dir'):
        log(f'โฟลเดอร์ผลลัพธ์: {job["out_dir"]}')
    try:
        res = {**ops.OPS, **ops3.OPS3, **ops_hex.OPS_HEX}[job['kind']](job, progress, log)
        run_s = time.time() - t0
        fin = db.now()
        timing = dict(queued_at=job.get('created_at'), started_at=datetime.fromtimestamp(t0).isoformat(timespec='seconds'),
                      finished_at=fin, run_s=round(run_s, 1))
        try:
            timing['wait_s'] = round((datetime.fromtimestamp(t0) - datetime.fromisoformat(job['created_at'])).total_seconds(), 1)
        except (TypeError, ValueError):
            pass
        if isinstance(res, dict):
            res['timing'] = timing
        _timing_to_lineage(job.get('out_dir'), timing)
        db.update('jobs', jid, status='done', progress=1.0, result=res, message='เสร็จ', error=None, finished_at=fin, eta_s=0, elapsed_s=run_s)
        log(f'เสร็จ · ใช้เวลาประมวลผล {run_s:,.1f} วินาที' + (f' (รอคิว {timing["wait_s"]:,.0f} วินาที)' if timing.get('wait_s') else ''))
    except ops.Cancelled:
        db.update('jobs', jid, status='cancelled', message='ยกเลิกแล้ว', finished_at=db.now())
        log('ยกเลิกโดยผู้ใช้')
    except Exception as e:
        tb = traceback.format_exc()
        log(tb)
        db.update('jobs', jid, status='failed', error=str(e), message=str(e)[:300], finished_at=db.now())
    finally:
        logf.close()


if __name__ == '__main__':
    main(int(sys.argv[1]))
