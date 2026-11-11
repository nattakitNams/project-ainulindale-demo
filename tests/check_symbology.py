# -*- coding: utf-8 -*-
"""ตรวจการจัดชั้นสัญลักษณ์ (symbology) — ไม่ต้องเปิดตัวประมวลผล ไม่ใช้ไฟล์จริง

    python -m tests.check_symbology

ครอบคลุม: บัก 1.0.42 (ข้อมูลจำนวนเต็ม 0–14 ตั้งเป็น "จำนวนนับ" ได้ชุดเกณฑ์ประชากร 10–3,000 ตายตัว + ป้ายมั่ว)
และอัลกอริทึมแบ่งชั้นทุกตัว: เลขกลม · ลอการิทึม · Jenks · head/tail · SD · ป้ายจำนวนเต็ม"""
import math
import xml.dom.minidom

import numpy as np

from app import ops, symbology as S

FAIL = []


def check(name, cond, detail=''):
    print(('ok   ' if cond else 'FAIL ') + name + (f'  [{detail}]' if detail else ''))
    if not cond:
        FAIL.append(name)


def fake(vt, sample, stats=None):
    """ชุดข้อมูลปลอม + แทน sample_values ให้คืนค่าที่กำหนด (density = ค่าเดียวกัน)"""
    S.sample_values = lambda ds, metric: np.asarray(sample, 'float64')
    return dict(id=1, name='test', value_type=vt, meta=dict(has_colormap=False), stats=stats or {}, exclude_values=[])


rng = np.random.default_rng(0)

# ---------- 1) บัก: จำนวนปีท่วม 0–14 แต่ตั้งเป็น "จำนวนนับ" ----------
years = rng.integers(0, 15, 20000)
st = S.default_style(fake('count', years, dict(min=0.0, max=14.0)))
check('จำนวนเต็ม 0–14 (count) → แสดงทีละค่า', st['type'] == 'paletted', st['type'])
check('ครบ 15 ค่า 0–14', [e['value'] for e in st['entries']] == list(range(15)))
check('ใช้ค่าดิบ ไม่ใช่ความหนาแน่น', st.get('metric') == 'value')
check('ซ่อน 0 (ไม่เคยท่วม) ไว้ก่อน', st['hide_values'] == [0] and not st['entries'][0]['visible'])
check('มีคำแนะนำให้ตั้งเป็น "ชั้น"', 'ชั้น' in st.get('note', ''))
check('ไม่มีเกณฑ์ประชากรตายตัวเหลือในโมดูล', not hasattr(S, 'DENS_BINS'))

# ---------- 2) ประชากร (เบ้ขวามาก) → ลอการิทึมเลขกลม จากข้อมูลจริง ----------
pop = np.concatenate([np.zeros(5000), rng.lognormal(3.5, 1.6, 30000)])
st = S.default_style(fake('count', pop))
labels = [s['label'] for s in st['stops']]
check('ประชากร → pseudocolor ลอการิทึม', st['type'] == 'pseudocolor' and st['mode'] == 'log', st.get('mode'))
vals = [s['value'] for s in st['stops'] if not math.isinf(s['value'])]
check('เกณฑ์เป็นเลขกลมชุด 1-3-10 / 1-2-5', all(float(f'{v:.1g}') == v for v in vals), vals)
check('ชั้นแรกเริ่มที่ 0', labels[0].startswith('0 – '), labels[0])
check('ชั้นสุดท้ายเปิด (> ค่า)', labels[-1].startswith('> '), labels[-1])
check('ซ่อน 0 (ไม่มีคน)', st['hide_values'] == [0])

# ---------- 3) ค่าต่อเนื่องไม่เบ้ (count) → เลขกลมช่วงเท่ากัน ----------
st = S.default_style(fake('count', rng.normal(500, 80, 20000).clip(1)))
check('ไม่เบ้ → เลขกลม', st['mode'] == 'pretty', st.get('mode'))

# ---------- 4) อัลกอริทึมเดี่ยว ----------
check('pretty 0–14 จำนวนเต็ม', S.pretty_breaks(0, 14, 5, True) == [2, 4, 6, 8, 10, 12], S.pretty_breaks(0, 14, 5, True))
check('pretty 0–3000 ได้ 500 ทีละขั้น', S.pretty_breaks(0, 3000, 6) == [500, 1000, 1500, 2000, 2500], S.pretty_breaks(0, 3000, 6))
lb = S.log_breaks(1.2, 3000, 7)
check('log 1.2–3000 7 ชั้น = 3,10,30,…,1000', lb == [3, 10, 30, 100, 300, 1000], lb)
clusters = np.concatenate([rng.normal(10, 1, 3000), rng.normal(50, 2, 3000), rng.normal(120, 3, 3000)])
jb = S.jenks_breaks(clusters, 3)
check('Jenks แยก 3 กลุ่มได้ (เกณฑ์อยู่ในช่องว่างระหว่างกลุ่ม)', len(jb) == 2 and 15 < jb[0] < 44 and 57 < jb[1] < 110, jb)
ht = S.headtail_breaks(rng.pareto(1.2, 50000), 6)
check('Head/tail กับข้อมูลหางยาว ได้หลายชั้น เพิ่มขึ้นเรื่อย ๆ', len(ht) >= 3 and ht == sorted(ht), [round(x, 2) for x in ht])
try:
    S.mode_breaks('headtail', rng.uniform(0, 1, 5000), 0, 1, 5)
    check('Head/tail กับข้อมูลสม่ำเสมอ → แจ้งว่าใช้ไม่ได้', False)
except ValueError:
    check('Head/tail กับข้อมูลสม่ำเสมอ → แจ้งว่าใช้ไม่ได้', True)
sd = S.stddev_breaks(rng.normal(0, 1, 20000), -10, 10)
check('SD: 6 เกณฑ์รอบค่าเฉลี่ย', len(sd) == 6 and abs(sd[2] + 0.5) < 0.05 and abs(sd[3] - 0.5) < 0.05, [round(x, 2) for x in sd])
check('tidy ปัดเลขให้อ่านง่าย', S.tidy([12.37, 48.91, 1437.8]) == [12, 49, 1400], S.tidy([12.37, 48.91, 1437.8]))

# ---------- 5) ป้าย ----------
check('ป้ายจำนวนเต็ม', S.class_labels([4.0, 9.0, math.inf], 1.0, 'discrete', True) == ['1–4', '5–9', '≥ 10'],
      S.class_labels([4.0, 9.0, math.inf], 1.0, 'discrete', True))
check('ป้ายจำนวนเต็มชั้นเดียวค่าเดียว', S.class_labels([1.0, 2.0, math.inf], 1.0, 'discrete', True) == ['1', '2', '≥ 3'])
check('ป้ายทศนิยม', S.class_labels([3.0, 10.0, math.inf], 0.0, 'discrete') == ['0 – 3', '3 – 10', '> 10'],
      S.class_labels([3.0, 10.0, math.inf], 0.0, 'discrete'))

# ---------- 6) classify ทุกวิธี ไม่พัง และเกณฑ์เรียงถูก ----------
ds = fake('density', rng.lognormal(2, 1, 20000))
for mode in S.CLASS_MODES:
    for interp in ('discrete', 'linear'):
        try:
            o = S.classify(ds, dict(type='pseudocolor', mode=mode, interp=interp, classes=5, ramp='viridis'))
            v = [s['value'] for s in o['stops']]
            check(f'classify {mode}/{interp}', len(v) >= 2 and v == sorted(v) and len(set(v)) == len(v), f'{len(v)} จุด')
        except ValueError as e:
            check(f'classify {mode}/{interp}', mode == 'headtail', str(e))
ds = fake('class', years)
o = S.classify(ds, dict(type='pseudocolor', mode='equal', interp='discrete', classes=3, ramp='viridis', min=0, max=14))
check('equal กับจำนวนเต็ม → ป้าย 0–4 แบบจำนวนเต็ม', o['stops'][0]['label'] == '0–4', [s['label'] for s in o['stops']])

# ---------- 7) แกนไบแวเรียต: Jenks ได้ n−1 เกณฑ์พอดี ----------
b = ops.jenks_exact(clusters, 3)
check('jenks_exact 3 ชั้น = 2 เกณฑ์', len(b) == 2, b)
try:
    ops.jenks_exact(np.array([1, 1, 2, 2.0]), 4)
    check('jenks_exact ค่าน้อยกว่าชั้น → แจ้งชัด', False)
except Exception as e:
    check('jenks_exact ค่าน้อยกว่าชั้น → แจ้งชัด', 'ไม่ครบ' in str(e), str(e))

# ---------- 8) QML ยัง valid XML (ป้าย < >) ----------
ds = dict(fake('density', clusters), meta=dict(has_colormap=False, transform=[1, 0, 0, 0, -1, 0]))
o = S.classify(ds, dict(type='pseudocolor', mode='jenks', interp='discrete', classes=3, ramp='viridis'))
o['stops'][0]['label'] = '< 15 & น้อย'
try:
    xml.dom.minidom.parseString(S.qml(ds, o))
    check('QML ยังเป็น XML ถูกต้อง', True)
except Exception as e:
    check('QML ยังเป็น XML ถูกต้อง', False, str(e))

# ---------- 9) 1.0.44 ข้อมูลเพิ่ม/ลด (ประชากรเปลี่ยนแปลง −91…+8.6 กองใกล้ 0) → สองขั้วแยกที่ 0 ----------
from app import histo  # noqa: E402
chg = np.concatenate([np.zeros(60000), rng.laplace(0.01, 0.05, 120000), -rng.lognormal(0, 1.5, 2000), rng.lognormal(-1, 1, 3000)])
ds = fake('count', chg)
o = S.default_style(ds)
vals = [st['value'] for st in o['stops']]
check('ข้อมูลมีทั้งลบ/บวก → สไตล์เริ่มต้นสองขั้ว RdBu แยกที่ 0', o.get('center') == 0 and o['ramp'] == 'RdBu' and 0 in vals, [st['label'] for st in o['stops']])
neg = [v for v in vals if isinstance(v, (int, float)) and v < 0]
check('ฝั่งลบมีชั้นของตัวเอง (ไม่หายเพราะเบ้)', len(neg) >= 2, len(neg))
check('ค่า 0 พอดีเยอะ → ซ่อน (= ไม่เปลี่ยน)', o['hide_values'] == [0])
cols = [st['color'] for st in o['stops']]
r0, b0, r1, b1 = int(cols[0][1:3], 16), int(cols[0][5:7], 16), int(cols[-1][1:3], 16), int(cols[-1][5:7], 16)
check('สีปลายลบแดง ปลายบวกน้ำเงิน', r0 > b0 and b1 > r1, (cols[0], cols[-1]))
for m in ('quantile', 'jenks', 'equal', 'log', 'pretty'):
    q = S.classify(ds, dict(type='pseudocolor', ramp='RdBu', mode=m, interp='discrete', classes=6, center=0, metric='value'))
    v = [st['value'] for st in q['stops']]
    fin = [x for x in v if not math.isinf(x)]
    check(f'จุดกลาง 0 + {m}: 0 เป็นเกณฑ์ ทั้งสองฝั่งมีชั้น', 0 in v and any(x < 0 for x in fin) and any(x > 0 for x in fin) or (0 in v and math.isinf(v[-1]) and any(x < 0 for x in fin)),
          [st['label'] for st in q['stops']])
q = S.classify(ds, dict(type='pseudocolor', ramp='RdBu', mode='continuous', interp='linear', classes=5, center=0, metric='value'))
check('จุดกลาง + ไล่สี: ช่วงสมมาตร 0 อยู่กลาง', abs(q['min'] + q['max']) < 1e-9 and q['stops'][len(q['stops']) // 2]['value'] == 0)
q = S.classify(ds, dict(type='pseudocolor', ramp='RdBu', mode='quantile', interp='discrete', classes=6, center=0.5, metric='value'))
check('จุดกลางไม่ใช่ 0 ได้', 0.5 in [st['value'] for st in q['stops']])
h = histo.hist(chg)
check('ฮิสโทแกรมมีทั้งลบ/บวก → symlog (ค่าลบไม่หาย)', h['scale'] == 'symlog' and h['edges'][0] < 0 < h['edges'][-1] and sum(h['counts']) == chg.size, h['scale'])
h = histo.hist(rng.lognormal(0, 2, 5000))
check('บวกล้วนเบ้มาก → log เหมือนเดิม', h['scale'] == 'log' and h['log'])
h = histo.hist(np.concatenate([rng.normal(0, 1, 5000) + 10, [1e6]]))
check('หางยาวมากเชิงเส้น → ตัดหาง นับแยก', h['scale'] == 'linear' and h['over'] >= 1 and h['edges'][-1] < 100, h['edges'][-1])
s0 = fake('density', rng.uniform(-1, 1, 5000))
ntl = np.concatenate([rng.normal(0, 0.15, 3000), rng.lognormal(1, 1.2, 13000)])
check('night light มีค่าลบรบกวน (−0.3 กับ +60) → ไม่ใช่สองขั้ว', S.default_style(dict(fake('density', ntl), name='vnl_edge')).get('center') is None)
dem = np.concatenate([rng.uniform(-5, 0, 400), rng.lognormal(5, 1, 9600)])
check('DEM ต่ำกว่าระดับทะเลนิดหน่อย → ไม่ใช่สองขั้ว', S.default_style(dict(fake('density', dem), name='dem')).get('center') is None)
check('NDVI คงสี RdYlGn เดิม (ไม่บังคับสองขั้ว)', S.default_style(dict(fake('density', rng.uniform(-1, 1, 5000)), name='ndvi_2024')).get('center') is None)
check('NDVI ผลต่างสองปี → สองขั้ว', S.default_style(dict(fake('density', rng.uniform(-1, 1, 5000)), name='ndvi_change_2015_2024')).get('center') == 0)

print('\nผ่านทั้งหมด' if not FAIL else f'\nไม่ผ่าน {len(FAIL)} ข้อ: {FAIL}')
raise SystemExit(1 if FAIL else 0)
