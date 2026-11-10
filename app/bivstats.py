# -*- coding: utf-8 -*-
"""สถิติความสัมพันธ์ของแผนที่ไบแวเรียต — ใช้ค่าชุดเดียวกับที่แผนที่ใช้จัดชั้น (กริด ความละเอียด พื้นที่ศึกษา "ค่าที่ใช้" เดียวกัน)

สุ่มพิกเซลจากไทล์แบบสุ่มทั่วพื้นที่ (ไม่ใช่แค่มุมเดียว) → ค่า X, Y (หลังแปลง metric เช่น คน/ตร.กม.) + รหัสชั้นจากไฟล์แผนที่จริง แล้วคิด:
- ความสัมพันธ์: Pearson r (+ช่วงเชื่อมั่น 95%), Spearman ρ, OLS Y~X (ความชัน R²) · ถ้าเบ้มาก คิดบน log1p ด้วย
- ตารางไขว้ชั้น: สัดส่วนพิกเซล/พื้นที่แต่ละช่อง · χ² + Cramér's V · อัตราส่วนสังเกต/คาดหวัง (ช่องไหนเกิดบ่อยกว่าที่ควรถ้าไม่สัมพันธ์กัน)
- เปรียบเทียบ Y ระหว่างชั้น X: ANOVA (F, η²) + Kruskal–Wallis (H, ε²) เพราะข้อมูลภูมิศาสตร์มักไม่ปกติ/ความแปรปรวนไม่เท่ากัน · สถิติรายชั้น
- Moran's I ของ X, Y และส่วนเหลือ (เพื่อนบ้าน 4 ทิศ ในกริดเดียวกัน) → ขนาดตัวอย่างประสิทธิผล → ค่า p ที่ปรับแล้ว
  (พิกเซลติดกันไม่อิสระต่อกัน — p จากสูตรปกติเล็กเกินจริงมาก ต้องเตือนผู้ใช้)
- กราฟ: กระจายความหนาแน่น (hexbin) + เส้นแบ่งชั้น + เส้นถดถอย · ตารางไขว้แบบสีพาเลท · กล่อง Y ตามชั้น X
ผลเก็บที่ <โฟลเดอร์ผลลัพธ์>/stats/ (json, csv, png, md) — คิดครั้งเดียว เรียกซ้ำใช้แคช"""
import json
import math
import time
from fractions import Fraction
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

from . import db, engine, export
from .engine import EngineError, Source

N_SAMPLE = 200_000
TIME_LIMIT = 45


def _lineage(d):
    j = db.get('jobs', d['job_id']) if d.get('job_id') else None
    if not j or j['kind'] != 'bivariate' or not j.get('out_dir'):
        raise EngineError('วิเคราะห์ได้เฉพาะแผนที่ไบแวเรียตแบบกริดที่สร้างในแอป')
    lin = json.loads((Path(j['out_dir']) / 'lineage.json').read_text(encoding='utf-8'))
    return j, lin


def _fisher_ci(r, n):
    if r is None or n is None or n < 4 or abs(r) >= 1:
        return None
    z, se = math.atanh(r), 1 / math.sqrt(n - 3)
    return [math.tanh(z - 1.96 * se), math.tanh(z + 1.96 * se)]


def _p_from_r(r, n):
    from scipy import stats
    if r is None or n is None or n < 4 or abs(r) >= 1:
        return None
    t = r * math.sqrt((n - 2) / (1 - r * r))
    return float(2 * stats.t.sf(abs(t), n - 2))


def _strength(r):
    a = abs(r or 0)
    return 'แทบไม่มี' if a < 0.1 else 'อ่อน' if a < 0.3 else 'ปานกลาง' if a < 0.5 else 'ค่อนข้างแรง' if a < 0.7 else 'แรง'


def sample(d, log=lambda m: None):
    """สุ่มค่า X, Y, รหัสชั้น จากไทล์สุ่ม + ผลรวมเพื่อนบ้านสำหรับ Moran's I"""
    from .ops import setup_aoi
    j, lin = _lineage(d)
    p = lin['params']
    dsx, dsy = db.get('datasets', p['x']['dataset_id']), db.get('datasets', p['y']['dataset_id'])
    if not dsx or not dsy:
        raise EngineError('ชุดข้อมูลต้นทางของแผนที่นี้ถูกลบไปแล้ว')
    sx, sy = Source(dsx), Source(dsy)
    grid = engine.make_grid([sx, sy], Fraction(p['target_res']))
    tie, cdv = p.get('tie', 'high'), p.get('count_down_valid', 'positive')
    ogx, ogy = engine.OnGrid(sx, grid, cdv, tie), engine.OnGrid(sy, grid, cdv, tie)
    masker, mf, aoi = setup_aoi(p, grid, [ogx, ogy], log)
    T = engine.tile_size([ogx, ogy], False, mf)
    tiles = list(engine.iter_tiles(grid, T))
    rng = np.random.default_rng(42)
    order = rng.permutation(len(tiles))
    mx, my = p['x'].get('metric', 'value'), p['y'].get('metric', 'value')
    roff, coff = grid.win[0], grid.win[1]
    xs, ys, cs = [], [], []
    mor = {k: [0.0, 0.0, 0.0] for k in ('x', 'y')}               # Σ z_i z_j (เพื่อนบ้าน), จำนวนคู่, ใช้คิดทีหลังเมื่อรู้ค่าเฉลี่ย
    pairs = {'x': [], 'y': []}
    t0, used = time.time(), 0
    with rasterio.open(d.get('read_path') or d['path']) as mp:
        for k in order:
            r0, c0, h, w = tiles[k]
            vx, okx = ogx.values(r0, c0, h, w)
            vy, oky = ogy.values(r0, c0, h, w)
            ok = okx & oky
            if masker is not None:
                ok &= masker(r0, c0, h, w)
            used += 1
            if ok.any():
                ar = grid.area_rows(r0, h)
                ax = engine.metric_of(dsx['value_type'], mx, vx.astype('float64'), ar)
                ay = engine.metric_of(dsy['value_type'], my, vy.astype('float64'), ar)
                code = mp.read(1, window=Window(c0 - coff, r0 - roff, w, h), boundless=True, fill_value=0)
                ok &= code > 0
                xs.append(ax[ok]); ys.append(ay[ok]); cs.append(code[ok])
                # คู่เพื่อนบ้าน (ขวา + ล่าง) ภายในไทล์ — เก็บคู่ค่าไว้ คิด Moran's I ด้วยค่าเฉลี่ยรวมทีหลัง
                for ax_, key in ((ax, 'x'), (ay, 'y')):
                    for a1, a2, k1, k2 in ((ax_[:, :-1], ax_[:, 1:], ok[:, :-1], ok[:, 1:]), (ax_[:-1], ax_[1:], ok[:-1], ok[1:])):
                        m2 = k1 & k2
                        if m2.any():
                            sel = np.flatnonzero(m2.ravel())
                            if sel.size > 20000:
                                sel = rng.choice(sel, 20000, replace=False)
                            pairs[key].append(np.stack([a1.ravel()[sel], a2.ravel()[sel]], 1))
            n = sum(x.size for x in xs)
            if n >= N_SAMPLE * 3 or time.time() - t0 > TIME_LIMIT:
                break
    sx.close(); sy.close()
    if not xs or not sum(x.size for x in xs):
        raise EngineError('ไม่มีพิกเซลที่มีค่าทั้งสองแกน')
    X, Y, C = np.concatenate(xs), np.concatenate(ys), np.concatenate(cs).astype('int32')
    if X.size > N_SAMPLE:
        sel = rng.choice(X.size, N_SAMPLE, replace=False)
        X, Y, C = X[sel], Y[sel], C[sel]
    P = {k: (np.concatenate(v) if v else np.zeros((0, 2))) for k, v in pairs.items()}
    return dict(lin=lin, p=p, dsx=dsx, dsy=dsy, grid=grid, aoi=aoi, X=X, Y=Y, C=C, pairs=P,
                tiles_used=used, tiles_total=len(tiles), seconds=time.time() - t0)


def _moran(pairs, v):
    """Moran's I แบบเพื่อนบ้าน 4 ทิศ (น้ำหนักเท่ากัน) จากคู่เพื่อนบ้านที่สุ่ม + ค่าเฉลี่ย/ความแปรปรวนรวม"""
    if pairs.shape[0] < 100 or v.size < 100:
        return None
    allv = pairs.ravel()                                       # ค่าเฉลี่ย/ความแปรปรวนจากชุดค่าเดียวกับคู่เพื่อนบ้าน → I อยู่ในช่วงที่ถูกต้อง
    m, s2 = float(allv.mean()), float(allv.var())
    if s2 <= 0:
        return None
    return float(((pairs[:, 0] - m) * (pairs[:, 1] - m)).mean() / s2)


def compute(did, force=False, log=lambda m: None):
    from scipy import stats
    d = db.get('datasets', int(did))
    if d is None:
        raise EngineError('ไม่พบชุดข้อมูล')
    j, lin = _lineage(d)
    out_dir = Path(j['out_dir']) / 'stats'
    cache = out_dir / 'biv_stats.json'
    if cache.exists() and not force:
        return json.loads(cache.read_text(encoding='utf-8'))
    S = sample(d, log)
    p, X, Y, C = S['p'], S['X'], S['Y'], S['C']
    nx, ny = int(p['x']['n']), int(p['y']['n'])
    xi, yi = (C - 1) % nx, (C - 1) // nx
    n = int(X.size)
    xname = p['x'].get('label') or S['dsx']['name']
    yname = p['y'].get('label') or S['dsy']['name']
    res = dict(dataset_id=d['id'], name=d['name'], x=dict(name=xname, metric=p['x'].get('metric', 'value'), dataset_id=S['dsx']['id']),
               y=dict(name=yname, metric=p['y'].get('metric', 'value'), dataset_id=S['dsy']['id']),
               sample=dict(n=n, tiles_used=S['tiles_used'], tiles_total=S['tiles_total'], seconds=round(S['seconds'], 1),
                           note='สุ่มจากไทล์แบบสุ่มทั่วพื้นที่' + ('' if S['tiles_used'] == S['tiles_total'] else f' ({S["tiles_used"]:,}/{S["tiles_total"]:,} ไทล์)')),
               resolution=S['grid'].describe()['res_label'], aoi=(S['aoi'] or {}).get('name'))
    warns = []
    # ---- ความสัมพันธ์ ----
    const = X.std() == 0 or Y.std() == 0
    r = None if const else float(np.corrcoef(X, Y)[0, 1])
    rho = None if const else float(stats.spearmanr(X, Y).statistic)
    lr = None if const else stats.linregress(X, Y)
    skew_x, skew_y = float(stats.skew(X)), float(stats.skew(Y))
    logr = None
    if not const and (abs(skew_x) > 2 or abs(skew_y) > 2) and X.min() >= 0 and Y.min() >= 0:
        lx, ly = np.log1p(X), np.log1p(Y)
        if lx.std() > 0 and ly.std() > 0:
            logr = float(np.corrcoef(lx, ly)[0, 1])
    # ---- Moran's I + ขนาดตัวอย่างประสิทธิผล (แบบหยาบ: n_eff = n (1 − Ix·Iy) / (1 + Ix·Iy)) ----
    Ix, Iy = _moran(S['pairs']['x'], X), _moran(S['pairs']['y'], Y)
    neff = None
    if Ix is not None and Iy is not None:
        k = max(min(Ix * Iy, 0.999), 0)
        neff = max(4, int(n * (1 - k) / (1 + k)))
    res['correlation'] = dict(pearson_r=r, pearson_ci95=_fisher_ci(r, n), spearman_rho=rho, strength=_strength(rho if rho is not None else r),
                              p_naive=_p_from_r(r, n), n_effective=neff, p_adjusted=_p_from_r(r, neff) if neff else None,
                              log_pearson_r=logr, skew=dict(x=skew_x, y=skew_y),
                              ols=dict(slope=lr.slope, intercept=lr.intercept, r2=lr.rvalue ** 2) if lr else None)
    res['spatial'] = dict(moran_x=Ix, moran_y=Iy, note='Moran\'s I เพื่อนบ้าน 4 ทิศที่ความละเอียดผลลัพธ์ · ใกล้ 1 = ค่าเกาะกลุ่มมาก (พิกเซลไม่อิสระต่อกัน)')
    if Ix is not None and Iy is not None and min(Ix, Iy) > 0.3:
        warns.append(f'ค่าเกาะกลุ่มเชิงพื้นที่สูง (Moran\'s I X {Ix:.2f} · Y {Iy:.2f}) — พิกเซลไม่อิสระต่อกัน ค่า p แบบปกติเล็กเกินจริง '
                     f'ใช้ p ที่ปรับด้วยขนาดตัวอย่างประสิทธิผล (~{neff:,}) แทน')
    if abs(skew_x) > 2 or abs(skew_y) > 2:
        warns.append(f'ข้อมูลเบ้มาก (skew X {skew_x:.1f} · Y {skew_y:.1f}) — Pearson ไวต่อค่าสุดโต่ง ให้ดู Spearman ρ' + (f' และ r บน log1p = {logr:.3f}' if logr is not None else ''))
    # ---- ตารางไขว้ ----
    tab = np.zeros((ny, nx), 'int64')
    np.add.at(tab, (yi, xi), 1)
    exp = tab.sum(1, keepdims=True) * tab.sum(0, keepdims=True) / max(tab.sum(), 1)
    chi = stats.chi2_contingency(tab + (tab.sum(0, keepdims=True) == 0) + (tab.sum(1, keepdims=True) == 0), correction=False) if nx > 1 and ny > 1 else None
    cv = math.sqrt(chi.statistic / (n * (min(nx, ny) - 1))) if chi is not None and min(nx, ny) > 1 else None
    res['crosstab'] = dict(counts=tab.tolist(), share=(tab / max(tab.sum(), 1)).tolist(),
                           obs_exp=np.where(exp > 0, tab / np.where(exp > 0, exp, 1), 0).round(3).tolist(),
                           chi2=float(chi.statistic) if chi is not None else None, dof=int(chi.dof) if chi is not None else None, cramers_v=cv,
                           note='แถว = ชั้น Y (ล่าง→บน) · คอลัมน์ = ชั้น X (ซ้าย→ขวา) · obs/exp > 1 = ช่องนี้เกิดบ่อยกว่าที่คาดถ้า X กับ Y ไม่สัมพันธ์กัน')
    # ---- Y ตามชั้น X ----
    groups = [Y[xi == k] for k in range(nx)]
    ok_g = [g for g in groups if g.size >= 2]
    anova = kw = None
    if len(ok_g) >= 2:
        f = stats.f_oneway(*ok_g)
        ssb = sum(g.size * (g.mean() - Y.mean()) ** 2 for g in ok_g)
        sst = ((Y - Y.mean()) ** 2).sum()
        anova = dict(F=float(f.statistic), p_naive=float(f.pvalue), eta2=float(ssb / sst) if sst > 0 else None)
        h = stats.kruskal(*ok_g)
        kw = dict(H=float(h.statistic), p_naive=float(h.pvalue), epsilon2=float(h.statistic / ((n * n - 1) / (n + 1))) if n > 1 else None)
    res['by_x_class'] = dict(anova=anova, kruskal=kw, classes=[
        dict(x_class=k + 1, n=int(g.size), mean=float(g.mean()) if g.size else None, median=float(np.median(g)) if g.size else None,
             q1=float(np.percentile(g, 25)) if g.size else None, q3=float(np.percentile(g, 75)) if g.size else None) for k, g in enumerate(groups)],
        note='η² / ε² = สัดส่วนความแปรปรวนของ Y ที่อธิบายด้วยชั้น X (0.01 เล็ก · 0.06 กลาง · 0.14 ใหญ่) · ใช้ Kruskal–Wallis เป็นหลักเมื่อข้อมูลเบ้')
    res['warnings'] = warns + ['ความสัมพันธ์ระดับพื้นที่ ≠ ความสัมพันธ์ระดับบุคคล (ecological fallacy) และผลขึ้นกับความละเอียด/ขอบเขต (MAUP) — ลองเทียบหลายความละเอียด']
    res['interpretation'] = _interpret(res, xname, yname)
    out_dir.mkdir(parents=True, exist_ok=True)
    res['charts'] = _charts(out_dir, S, res, xname, yname)
    _write(out_dir, res)
    cache.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding='utf-8')
    return res


def _interpret(res, xn, yn):
    c = res['correlation']
    L = []
    rr = c['spearman_rho'] if c['spearman_rho'] is not None else c['pearson_r']
    if rr is not None:
        L.append(f'"{xn}" กับ "{yn}" สัมพันธ์{"ทางบวก" if rr > 0 else "ทางลบ"}ระดับ{c["strength"]} (Spearman ρ = {rr:.2f}'
                 + (f', Pearson r = {c["pearson_r"]:.2f}' if c['pearson_r'] is not None else '') + ')')
    if c.get('p_adjusted') is not None:
        L.append(f'หลังคิดการเกาะกลุ่มเชิงพื้นที่ ขนาดตัวอย่างประสิทธิผล ~{c["n_effective"]:,} พิกเซล → p {"< 0.0001" if c["p_adjusted"] < 1e-4 else "≈ " + format(c["p_adjusted"], ".2g")}'
                 + ((' (มีนัยสำคัญทางสถิติ แต่ขนาดผลแทบเป็นศูนย์ — ไม่มีความหมายในทางปฏิบัติ)' if c['strength'] == 'แทบไม่มี' else ' (มีนัยสำคัญที่ 0.05)')
                    if c['p_adjusted'] < 0.05 else ' (ยังไม่มีนัยสำคัญที่ 0.05)'))
    ct = res['crosstab']
    if ct.get('cramers_v') is not None:
        oe = np.array(ct['obs_exp'])
        yy, xx = np.unravel_index(oe.argmax(), oe.shape)
        L.append(f'ตารางไขว้: Cramér\'s V = {ct["cramers_v"]:.2f} · ช่องที่เกิดบ่อยเกินคาดที่สุด = Y ชั้น {yy + 1} × X ชั้น {xx + 1} ({oe[yy, xx]:.1f} เท่าของที่คาด)')
    a = res['by_x_class']
    if a.get('kruskal') and a['kruskal'].get('epsilon2') is not None:
        e2 = a['kruskal']['epsilon2']
        L.append(f'ค่า "{yn}" ต่างกันระหว่างชั้นของ "{xn}" ขนาดผล ε² = {e2:.3f} ({"เล็ก" if e2 < 0.06 else "กลาง" if e2 < 0.14 else "ใหญ่"})')
    return L


def _charts(out_dir, S, res, xn, yn):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for f in ('Tahoma', 'Leelawadee UI', 'Leelawadee', 'TH Sarabun New', 'Noto Sans Thai'):
        if any(f == x.name for x in font_manager.fontManager.ttflist):
            plt.rcParams['font.family'] = f
            break
    p, X, Y, C = S['p'], S['X'], S['Y'], S['C']
    nx, ny = int(p['x']['n']), int(p['y']['n'])
    bx, by = p['x'].get('resolved_breaks') or p['x'].get('breaks') or [], p['y'].get('resolved_breaks') or p['y'].get('breaks') or []
    colors = p.get('colors') or ['#888888'] * (nx * ny)
    out = {}
    # 1) กระจาย (hexbin) — แกน log ถ้าเบ้มาก
    lg = res['correlation']['log_pearson_r'] is not None
    fig, ax = plt.subplots(figsize=(6.4, 5.2), dpi=150)
    xv, yv = (np.log1p(X), np.log1p(Y)) if lg else (X, Y)
    hb = ax.hexbin(xv, yv, gridsize=70, bins='log', mincnt=1, cmap='viridis')
    fig.colorbar(hb, ax=ax, label='จำนวนพิกเซล (log)')
    for b in bx:
        ax.axvline(np.log1p(b) if lg else b, color='#ff7f50', lw=1, ls='--')
    for b in by:
        ax.axhline(np.log1p(b) if lg else b, color='#ff7f50', lw=1, ls='--')
    ols = res['correlation'].get('ols')
    if ols and not lg:
        xx = np.linspace(xv.min(), xv.max(), 50)
        ax.plot(xx, ols['intercept'] + ols['slope'] * xx, color='white', lw=1.6)
    ax.set_xlabel(xn + (' (log1p)' if lg else '')); ax.set_ylabel(yn + (' (log1p)' if lg else ''))
    c = res['correlation']
    ax.set_title(f'ρ = {c["spearman_rho"]:.2f} · r = {c["pearson_r"]:.2f} · n = {X.size:,}' if c['pearson_r'] is not None else f'n = {X.size:,}', fontsize=10)
    fig.tight_layout(); fig.savefig(out_dir / 'scatter.png'); plt.close(fig)
    out['scatter'] = 'scatter.png'
    # 2) ตารางไขว้ (สัดส่วน %) ในสีพาเลทจริง
    share = np.array(res['crosstab']['share']) * 100
    oe = np.array(res['crosstab']['obs_exp'])
    fig, ax = plt.subplots(figsize=(1.1 * nx + 2.2, 1.1 * ny + 1.4), dpi=150)
    for yy in range(ny):
        for xx in range(nx):
            col = colors[yy * nx + xx]
            ax.add_patch(plt.Rectangle((xx, yy), 1, 1, color=col))
            h_ = col.lstrip('#')
            lum = (0.299 * int(h_[0:2], 16) + 0.587 * int(h_[2:4], 16) + 0.114 * int(h_[4:6], 16)) / 255
            tc = 'black' if lum > 0.55 else 'white'
            ax.text(xx + .5, yy + .58, f'{share[yy, xx]:.1f}%', ha='center', va='center', fontsize=9, color=tc)
            ax.text(xx + .5, yy + .3, f'×{oe[yy, xx]:.1f}', ha='center', va='center', fontsize=7, color=tc)
    ax.set_xlim(0, nx); ax.set_ylim(0, ny); ax.set_aspect('equal')
    ax.set_xticks(np.arange(nx) + .5, [str(i + 1) for i in range(nx)]); ax.set_yticks(np.arange(ny) + .5, [str(i + 1) for i in range(ny)])
    ax.set_xlabel(f'{xn} →'); ax.set_ylabel(f'{yn} →')
    ax.set_title('สัดส่วนพิกเซล · ×เท่าของที่คาดถ้าไม่สัมพันธ์', fontsize=9)
    fig.tight_layout(); fig.savefig(out_dir / 'crosstab.png'); plt.close(fig)
    out['crosstab'] = 'crosstab.png'
    # 3) กล่อง Y ตามชั้น X
    fig, ax = plt.subplots(figsize=(6.4, 4.2), dpi=150)
    xi = (C - 1) % nx
    data = [Y[xi == k] for k in range(nx)]
    ax.boxplot([g if g.size else [np.nan] for g in data], showfliers=False, patch_artist=True,
               boxprops=dict(facecolor='#9ee8d4', alpha=.6), medianprops=dict(color='#333'))
    if res['correlation']['skew']['y'] > 2 and Y.min() > 0:
        ax.set_yscale('log')
    ax.set_xticks(range(1, nx + 1), [f'X ชั้น {k + 1}' for k in range(nx)])
    ax.set_ylabel(yn)
    kw = res['by_x_class'].get('kruskal')
    ax.set_title(f'{yn} ตามชั้นของ {xn}' + (f' · ε² = {kw["epsilon2"]:.3f}' if kw and kw.get('epsilon2') is not None else ''), fontsize=10)
    fig.tight_layout(); fig.savefig(out_dir / 'box.png'); plt.close(fig)
    out['box'] = 'box.png'
    return out


def _write(out_dir, res):
    c, ct, a = res['correlation'], res['crosstab'], res['by_x_class']
    rows = [['n (สุ่ม)', res['sample']['n']], ['Pearson r', c['pearson_r']], ['r ช่วงเชื่อมั่น 95%', c['pearson_ci95']], ['Spearman ρ', c['spearman_rho']],
            ['r บน log1p', c['log_pearson_r']], ['OLS ความชัน', (c['ols'] or {}).get('slope')], ['OLS R²', (c['ols'] or {}).get('r2')],
            ["Moran's I X", res['spatial']['moran_x']], ["Moran's I Y", res['spatial']['moran_y']], ['n ประสิทธิผล', c['n_effective']],
            ['p (ปกติ)', c['p_naive']], ['p (ปรับการเกาะกลุ่ม)', c['p_adjusted']], ['χ²', ct['chi2']], ["Cramér's V", ct['cramers_v']],
            ['ANOVA F', (a['anova'] or {}).get('F')], ['η²', (a['anova'] or {}).get('eta2')], ['Kruskal–Wallis H', (a['kruskal'] or {}).get('H')],
            ['ε²', (a['kruskal'] or {}).get('epsilon2')]]
    export.write_csv(out_dir / 'biv_stats.csv', ['สถิติ', 'ค่า'], rows)
    md = [f'# สถิติความสัมพันธ์: {res["name"]}', '', f'X = {res["x"]["name"]} · Y = {res["y"]["name"]} · {res["resolution"]}' + (f' · {res["aoi"]}' if res.get('aoi') else ''), '',
          '## สรุป', *[f'- {x}' for x in res['interpretation']], '', '## ข้อควรระวัง', *[f'- {w}' for w in res['warnings']], '',
          '## ค่าสถิติ', '| สถิติ | ค่า |', '|---|---|', *[f'| {k} | {v} |' for k, v in rows], '',
          '![กระจาย](scatter.png) ![ตารางไขว้](crosstab.png) ![กล่อง](box.png)']
    (out_dir / 'biv_stats.md').write_text('\n'.join(md), encoding='utf-8')


def chart_path(did, name):
    d = db.get('datasets', int(did))
    j, _ = _lineage(d)
    f = Path(j['out_dir']) / 'stats' / name
    if name not in ('scatter.png', 'crosstab.png', 'box.png', 'biv_stats.md', 'biv_stats.csv') or not f.exists():
        raise EngineError('ไม่พบไฟล์')
    return f
