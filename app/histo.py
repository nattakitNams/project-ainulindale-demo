# -*- coding: utf-8 -*-
"""ฮิสโทแกรมสำหรับหน้าเว็บ — เลือกแกนตามข้อมูล (ใช้ร่วม: /api/classes-preview, ตาราง attribute)

- เชิงเส้น: ข้อมูลไม่เบ้
- log: ค่าบวกล้วน เบ้ขวามาก (p99 / มัธยฐาน > 20) — ค่า ≤ 0 นับแยก (zeros)
- symlog: มีทั้งค่าลบและบวก (เช่น ประชากรเปลี่ยนแปลง −91 … +8.6 กองอยู่ใกล้ 0) → log ทั้งสองฝั่ง ช่วงใกล้ 0 เป็นเชิงเส้น
  T(v) = sign(v) · log10(1 + |v| / c) · c = ค่า |v| ระดับ p10 (ช่วงเชิงเส้น) — ก่อน 1.0.44 ค่าลบหายจากกราฟทั้งหมด
แกนเชิงเส้นตัดหางที่ p0.5–p99.5 (นับส่วนที่ตัดไว้ใน under/over) ไม่ให้ค่าสุดโต่งไม่กี่พิกเซลบีบกราฟทั้งหมด"""
import numpy as np


def symlog(v, c):
    return np.sign(v) * np.log10(1 + np.abs(v) / c)


def symexp(t, c):
    return np.sign(t) * c * (10 ** np.abs(t) - 1)


def hist(v, bins=40, kind=None):
    """→ dict(scale=linear|log|symlog, log=bool (เข้ากับหน้าเว็บรุ่นก่อน), edges, counts, zeros, under, over, c)"""
    v = np.asarray(v, 'float64')
    v = v[np.isfinite(v)]
    if not v.size:
        return dict(scale='linear', log=False, edges=[0, 1], counts=[0], zeros=0)
    neg, pos = v[v < 0], v[v > 0]
    if kind != 'class' and neg.size >= max(3, 0.01 * v.size) and pos.size >= max(3, 0.01 * v.size):
        a = np.abs(v[v != 0])
        c = float(max(np.quantile(a, 0.10), 1e-9))
        t = symlog(v, c)
        lo, hi = float(t.min()), float(t.max())
        m = max(abs(lo), abs(hi))
        # สมมาตรรอบ 0 ถ้าสองฝั่งพอ ๆ กัน (อ่านง่ายกว่า) · ไม่งั้นใช้ช่วงจริง
        if min(abs(lo), abs(hi)) > 0.4 * m:
            lo, hi = -m, m
        te = np.linspace(lo, hi, bins + 1)
        counts, _ = np.histogram(t, te)
        return dict(scale='symlog', log=False, c=c, edges=symexp(te, c).tolist(), counts=counts.tolist(), zeros=0,
                    neg=int(neg.size), pos=int(pos.size))
    if kind != 'class' and pos.size > 10 and v.min() >= 0 and np.quantile(pos, 0.99) > 20 * max(float(np.quantile(pos, 0.5)), 1e-12):
        lo, hi = float(pos.min()), float(pos.max())
        edges = np.geomspace(max(lo, 1e-9), hi if hi > lo else lo * 10, bins + 1)
        counts, _ = np.histogram(pos, edges)
        return dict(scale='log', log=True, edges=edges.tolist(), counts=counts.tolist(), zeros=int((v <= 0).sum()))
    lo, hi = float(v.min()), float(v.max())
    under = over = 0
    if kind != 'class' and v.size > 200:
        q0, q1 = (float(x) for x in np.quantile(v, [0.005, 0.995]))
        if q1 > q0 and (hi - lo) > 4 * (q1 - q0):              # หางยาวมาก → ตัดไว้นับแยก
            under, over = int((v < q0).sum()), int((v > q1).sum())
            lo, hi = q0, q1
    counts, edges = np.histogram(v, bins, (lo, hi if hi > lo else lo + 1))
    return dict(scale='linear', log=False, edges=edges.tolist(), counts=counts.tolist(), zeros=0, under=under, over=over)
