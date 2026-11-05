// ================= จัดหน้าแผนที่แบบแคนวาส (ใช้ร่วม: ตัวแก้ในแอป + หน้าพิมพ์ของ Edge headless) =================
// หน่วยทั้งหมดเป็น มม. (ตำแหน่ง/ขนาด) และ pt (ตัวอักษร) → หน้าจอ = PDF
(function (G) {
  const RPT = {};
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const PT = 0.3528;                                                  // 1 pt = 0.3528 มม.
  RPT.PAPERS = { A4: [210, 297], A3: [297, 420], A5: [148, 210], LETTER: [215.9, 279.4] };
  RPT.FONTS = {
    'Sarabun': 'Sarabun — สารบรรณ (แบบเดียวกับ TH Sarabun ของหนังสือราชการ)',
    'Noto Sans Thai': 'Noto Sans Thai — เรียบ อ่านง่าย',
    'IBM Plex Sans Thai': 'IBM Plex Sans Thai — ทันสมัย',
    'Anuphan': 'Anuphan — ไม่มีหัว ทันสมัย',
    'Kanit': 'Kanit — หัวเรื่องหนักแน่น',
    'Prompt': 'Prompt — กลม อินโฟกราฟิก',
  };
  RPT.fontHref = fs => 'https://fonts.googleapis.com/css2?' + [...new Set(fs)].map(f => `family=${f.replace(/ /g, '+')}:wght@300;400;500;600;700`).join('&') + '&display=block';
  RPT.size = doc => {
    const p = doc.paper || {};
    if (p.size === 'custom') return [+p.w, +p.h];
    const [a, b] = RPT.PAPERS[p.size || 'A4'] || RPT.PAPERS.A4;
    return p.orient === 'portrait' ? [a, b] : [b, a];
  };
  const today = () => { const d = new Date(); return `${d.getDate()}/${d.getMonth() + 1}/${d.getFullYear() + 543}`; };
  const fmtN = (v, d = 0) => v == null || isNaN(v) ? '–' : Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: 0 });
  const big = v => Math.abs(v) >= 1e6 ? fmtN(v / 1e6, 1) + ' ล้าน' : fmtN(v, 0);

  // ข้อความที่มีตัวแทน {title} {org} ... — บรรทัดที่ตัวแทนว่างทั้งหมดจะถูกตัดทิ้ง
  RPT.META = { title: 'ชื่อแผนที่', subtitle: 'คำอธิบายรอง', org: 'หน่วยงาน', author: 'ผู้จัดทำ', map_no: 'หมายเลขแผนที่', date: 'วันที่', note: 'หมายเหตุ', caption: 'คำบรรยายภาพ' };
  RPT.fill = (t, doc) => {
    const m = Object.assign({ date: today() }, doc.meta || {});
    if (!m.date) m.date = today();
    return String(t ?? '').split('\n').map(line => {
      let any = false, empty = true;
      const out = line.replace(/\{(\w+)\}/g, (_, k) => { any = true; const v = m[k] ?? ''; if (String(v).trim()) empty = false; return v; });
      return any && empty ? null : out;
    }).filter(x => x !== null).join('\n');
  };

  // ---------- ชนิดองค์ประกอบ ----------
  RPT.TYPES = {
    map: { name: 'แผนที่หลัก', p: { fw: .35, fc: '#1d2233', bg: '#ffffff', grid: 'lines', gridColor: '#5d6478', gridOp: .35, gridLabels: 'lb', gfs: 6, labels: true, declutter: true, lfs: 6.5, lcolor: '#1d2233', halo: '#ffffff', view: null } },
    inset: { name: 'แผนที่แสดงตำแหน่ง', p: { title: 'แผนที่แสดงตำแหน่ง', fw: .3, fc: '#1d2233', rc: '#d6303c', basemap: 'esri_light', zoom: 1, fs: 6 } },
    legend: { name: 'คำอธิบายสัญลักษณ์', p: { title: 'คำอธิบายสัญลักษณ์', fs: 8, tfs: 10, color: '#1d2233', bg: '', bc: '', bw: 0, pad: 0, r: 0, cols: 1, skip: [], names: {} } },
    scalebar: { name: 'มาตราส่วน', p: { style: 'alt', seg: 4, ratio: true, fs: 7, color: '#1d2233', bg: '', align: 'left' } },
    north: { name: 'ลูกศรทิศเหนือ', p: { style: 'classic', color: '#1d2233' } },
    text: { name: 'ข้อความ', p: { text: 'ข้อความ', fs: 11, fw: 400, color: '#1d2233', align: 'left', valign: 'top', bg: '', bc: '', bw: 0, pad: 0, r: 0, lh: 1.3, ls: 0, italic: false, upper: false } },
    rect: { name: 'สี่เหลี่ยม/แถบสี', p: { fill: '#1f3a5f', stroke: '', sw: 0, r: 0, op: 1 } },
    line: { name: 'เส้น', p: { color: '#1d2233', width: .4, dash: false } },
    image: { name: 'รูปภาพ/โลโก้', p: { src: '', fit: 'contain' } },
    kpi: { name: 'การ์ดตัวเลข', p: { fs: 15, lfs: 7, color: '#1f3a5f', bg: '#ffffff', bc: '#dde1ea', r: 1.5, gap: 2.5 } },
    chart: { name: 'กราฟแท่งต่อรหัส', p: { title: 'auto', fs: 7, tfs: 8.5, color: '#1d2233', bg: '', pad: 0 } },
    prov: { name: 'ข้อมูลและวิธีการ', p: { title: 'ข้อมูลและวิธีการ', fs: 6.5, tfs: 7.5, color: '#4a5166', note: true } },
    credits: { name: 'เครดิต/ที่มา', p: { fs: 6, color: '#5d6478', align: 'left', extra: '', note: true, crs: true, author: true } },
  };

  // ---------- วาดหน้า ----------
  RPT.render = (root, doc, data, opt = {}) => {
    const [W, H] = RPT.size(doc);
    root.classList.add('rpt-page');
    Object.assign(root.style, { width: W + 'mm', height: H + 'mm', background: doc.bg || '#ffffff', fontFamily: `'${doc.font || 'Sarabun'}', 'Sarabun', sans-serif` });
    root.innerHTML = '';
    [...doc.els].sort((a, b) => (a.z || 0) - (b.z || 0)).forEach(e => {
      if (e.hidden && !opt.editor) return;
      const n = document.createElement('div');
      n.dataset.id = e.id;
      root.appendChild(n);
      RPT.draw(n, e, doc, data, opt);
    });
  };
  RPT.draw = (n, e, doc, data, opt = {}) => {
    n.className = `rpt-el rpt-t-${e.type}${e.hidden ? ' rpt-hidden' : ''}`;
    Object.assign(n.style, { left: e.x + 'mm', top: e.y + 'mm', width: e.w + 'mm', height: e.h + 'mm', zIndex: 10 + (e.z || 0) });
    const f = R[e.type];
    try { n.innerHTML = f ? f(e, e.p || {}, doc, data || {}, opt) : ''; } catch (er) { n.innerHTML = opt.editor ? `<div class="rpt-ph">${esc(er.message)}</div>` : ''; console.error(er); }
  };
  const abs = u => (window.ENGINE && /^\/api\//.test(u || '')) ? window.ENGINE + u : u;   // v1: ภาพอยู่ที่ตัวประมวลผลในเครื่อง
  const ph = (opt, t) => opt.editor ? `<div class="rpt-ph">${t}</div>` : '';
  const mapOf = (e, data) => (data.maps || {})[e.p?.link] || Object.values(data.maps || {})[0];

  // ระยะกริดพิกัดที่อ่านง่าย (องศา)
  const STEPS = [1 / 60, 2 / 60, 5 / 60, 10 / 60, 15 / 60, .5, 1, 2, 5, 10, 15, 30];
  const gstep = span => STEPS.find(s => span / s <= 5) || 30;
  const deg = (v, step, ax) => {
    const h = ax === 'x' ? (v >= 0 ? 'E' : 'W') : (v >= 0 ? 'N' : 'S');
    v = Math.abs(v);
    if (step >= 1 - 1e-9) return `${Math.round(v)}°${h}`;
    let d = Math.floor(v + 1e-9), mn = Math.round((v - d) * 60);
    if (mn === 60) { d += 1; mn = 0; }
    return `${d}°${String(mn).padStart(2, '0')}′${h}`;
  };

  const R = {};
  R.map = (e, p, doc, data, opt) => {
    const m = (data.maps || {})[e.id];
    let h = `<div class="rpt-mapbox" style="background:${p.bg || 'transparent'}">`;
    if (m) {
      h += `<img class="rpt-mapimg" src="${abs(m.src)}" alt="" draggable="false">`;
      const [x0, y0, x1, y1] = m.ext, W = e.w, H = e.h;
      const X = v => (v - x0) / (x1 - x0) * W, Y = v => (y1 - v) / (y1 - y0) * H;
      if (p.grid && p.grid !== 'none') {
        const st = gstep(y1 - y0), sx = gstep(x1 - x0);
        const step = Math.max(st, sx);
        let s = `<svg class="rpt-ov" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">`;
        const xs = [], ys = [];
        for (let v = Math.ceil(x0 / step) * step; v < x1; v += step) xs.push(v);
        for (let v = Math.ceil(y0 / step) * step; v < y1; v += step) ys.push(v);
        if (p.grid === 'lines') {
          xs.forEach(v => s += `<line x1="${X(v)}" y1="0" x2="${X(v)}" y2="${H}" stroke="${p.gridColor}" stroke-opacity="${p.gridOp}" stroke-width=".15" stroke-dasharray="1 .8"/>`);
          ys.forEach(v => s += `<line x1="0" y1="${Y(v)}" x2="${W}" y2="${Y(v)}" stroke="${p.gridColor}" stroke-opacity="${p.gridOp}" stroke-width=".15" stroke-dasharray="1 .8"/>`);
        }
        const tk = 1.4;                                              // ขีดที่ขอบกรอบ
        xs.forEach(v => s += `<line x1="${X(v)}" y1="0" x2="${X(v)}" y2="${tk}" stroke="${p.fc}" stroke-width=".25"/><line x1="${X(v)}" y1="${H - tk}" x2="${X(v)}" y2="${H}" stroke="${p.fc}" stroke-width=".25"/>`);
        ys.forEach(v => s += `<line x1="0" y1="${Y(v)}" x2="${tk}" y2="${Y(v)}" stroke="${p.fc}" stroke-width=".25"/><line x1="${W - tk}" y1="${Y(v)}" x2="${W}" y2="${Y(v)}" stroke="${p.fc}" stroke-width=".25"/>`);
        h += s + '</svg>';
        const gl = p.gridLabels || '', fs = (p.gfs || 6) + 'pt';
        const lab = (cls, style, t) => `<span class="rpt-glab ${cls}" style="font-size:${fs};color:${p.fc};${style}">${t}</span>`;
        if (gl.includes('b')) xs.forEach(v => h += lab('gb', `left:${X(v) / W * 100}%`, deg(v, step, 'x')));
        if (gl.includes('t')) xs.forEach(v => h += lab('gt', `left:${X(v) / W * 100}%`, deg(v, step, 'x')));
        if (gl.includes('l')) ys.forEach(v => h += lab('gl', `top:${Y(v) / H * 100}%`, deg(v, step, 'y')));
        if (gl.includes('r')) ys.forEach(v => h += lab('gr', `top:${Y(v) / H * 100}%`, deg(v, step, 'y')));
        if (gl.includes('i')) {                                       // ป้ายด้านในกรอบ
          xs.forEach(v => h += lab('gi gib', `left:${X(v) / W * 100}%`, deg(v, step, 'x')));
          ys.forEach(v => h += lab('gi gil', `top:${Y(v) / H * 100}%`, deg(v, step, 'y')));
        }
      }
      if (p.labels && m.labels?.length) {
        let labs = m.labels.filter(l => l.x > x0 && l.x < x1 && l.y > y0 && l.y < y1);
        if (p.declutter !== false) {                                  // ซ่อนป้ายที่ทับกัน (ประมาณขนาดจากจำนวนตัวอักษร)
          const fmm = (p.lfs || 6.5) * PT, boxes = [];
          const wOf = s => [...s].filter(c => !/[\u0E31\u0E34-\u0E3A\u0E47-\u0E4E]/.test(c)).length * fmm * .56 + fmm * .4;
          labs = labs.map(l => ({ ...l, cx: X(l.x), cy: Y(l.y), w: wOf(l.t), h: fmm * 1.25 })).sort((a, b) => a.w - b.w).filter(l => {
            const b = [l.cx - l.w / 2, l.cy - l.h / 2, l.cx + l.w / 2, l.cy + l.h / 2];
            if (b[0] < 0 || b[2] > W || b[1] < 0 || b[3] > H) return false;
            if (boxes.some(o => b[0] < o[2] && b[2] > o[0] && b[1] < o[3] && b[3] > o[1])) return false;
            boxes.push(b); return true;
          });
        }
        const halo = p.halo ? `text-shadow:${[[-1, 0], [1, 0], [0, -1], [0, 1], [-.7, -.7], [.7, .7], [-.7, .7], [.7, -.7]].map(([a, b]) => `${a * .25}mm ${b * .25}mm 0 ${p.halo}`).join(',')};` : '';
        h += `<div class="rpt-labels" style="font-size:${p.lfs}pt;color:${p.lcolor};${halo}">` + labs.map(l => `<span style="left:${X(l.x) / W * 100}%;top:${Y(l.y) / H * 100}%">${esc(l.t)}</span>`).join('') + '</div>';
      }
    } else h += ph(opt, opt.loading ? 'กำลังวาดแผนที่…' : 'แผนที่');
    h += `<div class="rpt-frame" style="border:${p.fw || 0}mm solid ${p.fc}"></div></div>`;
    return h;
  };

  R.inset = (e, p, doc, data, opt) => {
    const ins = (data.insets || {})[e.id], m = mapOf(e, data);
    let h = `<div class="rpt-mapbox" style="background:#e9edf3">`;
    if (ins && m) {
      const [x0, y0, x1, y1] = ins.ext, [a0, b0, a1, b1] = m.ext, W = e.w, H = e.h;
      const X = v => (v - x0) / (x1 - x0) * W, Y = v => (y1 - v) / (y1 - y0) * H;
      const rw = Math.max(X(a1) - X(a0), 1.2), rh = Math.max(Y(b0) - Y(b1), 1.2);
      h += `<img class="rpt-mapimg" src="${abs(ins.src)}" alt="" draggable="false"><svg class="rpt-ov" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
        <rect x="${X(a0)}" y="${Y(b1)}" width="${rw}" height="${rh}" fill="${p.rc}" fill-opacity=".18" stroke="${p.rc}" stroke-width=".45"/></svg>`;
    } else h += ph(opt, 'แผนที่แสดงตำแหน่ง');
    if (p.title) h += `<div class="rpt-institle" style="font-size:${p.fs}pt">${esc(p.title)}</div>`;
    return h + `<div class="rpt-frame" style="border:${p.fw || 0}mm solid ${p.fc}"></div></div>`;
  };

  R.north = (e, p) => {
    const c = p.color || '#1d2233';
    const S = {
      classic: `<path d="M50 12 L66 82 L50 70 Z" fill="${c}"/><path d="M50 12 L34 82 L50 70 Z" fill="none" stroke="${c}" stroke-width="2.5" stroke-linejoin="round"/>`,
      compass: `<circle cx="50" cy="56" r="28" fill="none" stroke="${c}" stroke-width="1.6"/><path d="M50 16 L57 56 L50 52 L43 56 Z" fill="${c}"/><path d="M50 96 L57 56 L50 60 L43 56 Z" fill="none" stroke="${c}" stroke-width="1.6"/><path d="M90 56 L50 63 L54 56 L50 49 Z" fill="none" stroke="${c}" stroke-width="1.2"/><path d="M10 56 L50 63 L46 56 L50 49 Z" fill="none" stroke="${c}" stroke-width="1.2"/>`,
      simple: `<path d="M50 14 L50 92" stroke="${c}" stroke-width="3.5"/><path d="M50 12 L64 40 L50 33 L36 40 Z" fill="${c}"/>`,
      star: `<path d="M50 12 L58 50 L50 92 L42 50 Z" fill="none" stroke="${c}" stroke-width="2"/><path d="M50 12 L58 50 L50 50 Z" fill="${c}"/><path d="M50 92 L42 50 L50 50 Z" fill="${c}"/>`,
    };
    const ny = { classic: 9, compass: 13, simple: 9, star: 9 }[p.style] ?? 9;
    return `<svg viewBox="0 -10 100 110" preserveAspectRatio="xMidYMid meet" class="rpt-fill">${S[p.style] || S.classic}
      <text x="50" y="${ny}" text-anchor="middle" font-size="20" font-weight="700" fill="${c}" font-family="inherit">N</text></svg>`;
  };

  // มาตราส่วน: คิดจากกรอบแผนที่ที่ผูกไว้ (ระยะจริงต่อ มม. ที่ละติจูดกลาง)
  RPT.kmPerMm = m => (m.ext[2] - m.ext[0]) * 111.32 * Math.cos((m.ext[1] + m.ext[3]) / 2 * Math.PI / 180) / m.w;
  const niceDown = x => { const e = 10 ** Math.floor(Math.log10(x)); for (const k of [5, 2.5, 2, 1]) if (k * e <= x) return k * e; return e; };
  const niceRatio = r => { const e = 10 ** (Math.floor(Math.log10(r)) - 1); return Math.round(r / e) * e; };
  R.scalebar = (e, p, doc, data, opt) => {
    const m = mapOf(e, data);
    if (!m) return ph(opt, 'มาตราส่วน');
    const kpm = RPT.kmPerMm(m), fs = (p.fs || 7) * PT, c = p.color || '#1d2233';
    const ratioH = p.ratio ? fs * 1.5 : 0;
    const L = niceDown(Math.max((e.w - fs * 4) * kpm, 1e-6));
    const n = Math.max(1, +p.seg || 4), len = L / kpm, seg = len / n;
    const meters = L < 1, lab = v => meters ? fmtN(v * 1000, 0) : fmtN(v, v < 10 ? 1 : 0);
    const x0 = p.align === 'center' ? (e.w - len - fs * 3) / 2 : p.align === 'right' ? e.w - len - fs * 3.2 : fs * .8;
    const by = fs * 1.6, bh = Math.max(Math.min(e.h - by - ratioH - .5, 1.6), .8);
    let s = `<svg viewBox="0 0 ${e.w} ${e.h}" class="rpt-fill" font-family="inherit">`;
    if (p.style === 'line') {
      s += `<line x1="${x0}" y1="${by + bh}" x2="${x0 + len}" y2="${by + bh}" stroke="${c}" stroke-width=".35"/>`;
      for (let i = 0; i <= n; i++) s += `<line x1="${x0 + i * seg}" y1="${by + bh - (i % n === 0 ? bh : bh * .6)}" x2="${x0 + i * seg}" y2="${by + bh}" stroke="${c}" stroke-width=".3"/>`;
    } else {
      for (let i = 0; i < n; i++) {
        s += `<rect x="${x0 + i * seg}" y="${by}" width="${seg}" height="${bh}" fill="${i % 2 ? '#ffffff' : c}" stroke="${c}" stroke-width=".2"/>`;
        if (p.style === 'double') s += `<rect x="${x0 + i * seg}" y="${by + bh}" width="${seg}" height="${bh}" fill="${i % 2 ? c : '#ffffff'}" stroke="${c}" stroke-width=".2"/>`;
      }
    }
    const marks = n % 2 === 0 ? [0, n / 2, n] : [0, n];
    marks.forEach(i => s += `<text x="${x0 + i * seg}" y="${by - fs * .35}" font-size="${fs}" text-anchor="middle" fill="${c}">${lab(L * i / n)}</text>`);
    s += `<text x="${x0 + len + fs * .5}" y="${by + bh * (p.style === 'double' ? 1 : .5) + fs * .35}" font-size="${fs}" fill="${c}">${meters ? 'ม.' : 'กม.'}</text>`;
    if (p.ratio) {
      const yy = by + bh * (p.style === 'double' ? 2 : 1) + fs * 1.25;
      s += `<text x="${x0 + len / 2}" y="${yy}" font-size="${fs}" text-anchor="middle" fill="${c}">มาตราส่วน 1:${fmtN(niceRatio(kpm * 1e6), 0)}</text>`;
    }
    return `<div class="rpt-fill" style="background:${p.bg || 'transparent'}">${s}</svg></div>`;
  };

  R.text = (e, p, doc) => {
    const t = p.bind ? (doc.meta?.[p.bind] ?? '') : RPT.fill(p.text, doc);
    const jc = { top: 'flex-start', middle: 'center', bottom: 'flex-end' }[p.valign || 'top'];
    return `<div class="rpt-txt" style="font-size:${p.fs}pt;font-weight:${p.fw};color:${p.color};text-align:${p.align};justify-content:${jc};
      background:${p.bg || 'transparent'};border:${p.bw || 0}mm solid ${p.bc || 'transparent'};border-radius:${p.r || 0}mm;padding:${p.pad || 0}mm;
      line-height:${p.lh || 1.3};letter-spacing:${p.ls || 0}em;font-style:${p.italic ? 'italic' : 'normal'};text-transform:${p.upper ? 'uppercase' : 'none'}"><div class="rpt-tx">${esc(t).replace(/\n/g, '<br>')}</div></div>`;
  };
  R.rect = (e, p) => `<div class="rpt-fill" style="background:${p.fill || 'transparent'};border:${p.sw || 0}mm solid ${p.stroke || 'transparent'};border-radius:${p.r || 0}mm;opacity:${p.op ?? 1}"></div>`;
  R.line = (e, p) => {
    const v = e.h > e.w;
    return `<svg viewBox="0 0 ${e.w} ${e.h}" class="rpt-fill"><line x1="${v ? e.w / 2 : 0}" y1="${v ? 0 : e.h / 2}" x2="${v ? e.w / 2 : e.w}" y2="${v ? e.h : e.h / 2}"
      stroke="${p.color}" stroke-width="${p.width}" ${p.dash ? 'stroke-dasharray="1.5 1"' : ''}/></svg>`;
  };
  R.image = (e, p, doc, data, opt) => p.src ? `<img src="${p.src}" class="rpt-fill" style="object-fit:${p.fit || 'contain'}" draggable="false">` : ph(opt, 'รูปภาพ / โลโก้<br><small>เลือกไฟล์ในแผงขวา</small>');

  // คำอธิบายสัญลักษณ์
  R.legend = (e, p, doc, data, opt) => {
    const items = (data.info?.legend || []).filter(it => !(p.skip || []).includes(it.name));
    if (!items.length) return ph(opt, 'คำอธิบายสัญลักษณ์');
    const fs = p.fs || 8;
    let h = `<div class="rpt-leg" style="font-size:${fs}pt;color:${p.color};background:${p.bg || 'transparent'};border:${p.bw || 0}mm solid ${p.bc || 'transparent'};border-radius:${p.r || 0}mm;padding:${p.pad || 0}mm">`;
    if (p.title) h += `<div class="rpt-leg-t" style="font-size:${p.tfs || fs + 2}pt">${esc(p.title)}</div>`;
    h += `<div class="rpt-leg-b" style="column-count:${p.cols || 1}">`;
    const nm = it => (p.names || {})[it.name] || it.name;            // ชื่อที่ตั้งใหม่สำหรับรายงาน
    for (const it of items) {
      h += `<div class="rpt-leg-i">`;
      if (it.type !== 'patch' && it.type !== 'line' && nm(it) !== '-') h += `<div class="rpt-leg-n">${esc(nm(it))}</div>`;
      if (it.type === 'biv') {
        const cell = Math.max(3.2, Math.min(7, fs * .75));
        let g = `<div class="rpt-biv"><div class="rpt-biv-y">${esc(it.yn)} →</div><div><div class="rpt-biv-g" style="grid-template-columns:auto repeat(${it.nx},${cell}mm)">`;
        for (let y = it.ny - 1; y >= 0; y--) {
          g += `<span class="rpt-biv-yl">${esc(it.yl[y])}</span>`;
          for (let x = 0; x < it.nx; x++) { const code = y * it.nx + x + 1; g += `<i style="background:${it.colors[code - 1]};height:${cell}mm" class="${(it.hl || []).includes(code) ? 'hl' : ''}"></i>`; }
        }
        g += `<span></span>` + Array.from({ length: it.nx }, (_, x) => `<span class="rpt-biv-xl">${esc(it.xl[x])}</span>`).join('');
        h += g + `</div><div class="rpt-biv-x">${esc(it.xn)} →</div></div></div>`;
        if ((it.hl || []).length) h += `<div class="rpt-leg-r"><i class="sw" style="background:#fff;border:.35mm solid #1d2233"></i>กรอบเข้ม = เขตเน้น (รหัส ${it.hl.join(', ')})</div>`;
      } else if (it.type === 'ramp') {
        h += `<div class="rpt-ramp" style="background:linear-gradient(90deg,${it.items.map(x => x.color).join(',')})"></div>
          <div class="rpt-ramp-l"><span>${esc(it.items[0]?.label ?? '')}</span><span>${esc(it.items.at(-1)?.label ?? '')}${it.unit ? ' ' + esc(it.unit) : ''}</span></div>`;
      } else if (it.type === 'list') {
        h += it.items.map(x => `<div class="rpt-leg-r"><i class="sw" style="background:${x.color}"></i>${esc(x.label ?? x.value)}</div>`).join('');
        if (it.more) h += `<div class="rpt-leg-m">… อีก ${it.more} รายการ</div>`;
        if (it.unit) h += `<div class="rpt-leg-m">(${esc(it.unit)})</div>`;
      } else if (it.type === 'patch') {
        h += `<div class="rpt-leg-r"><i class="sw" style="background:${it.useColor ? 'linear-gradient(135deg,#e8e8e8,#574249)' : it.fill};border:.3mm solid ${it.stroke}"></i>${esc(nm(it))}</div>`;
      } else if (it.type === 'line') {
        h += `<div class="rpt-leg-r"><i class="sw ln" style="border-top:${Math.max(it.width * .3, .25)}mm solid ${it.color}"></i>${esc(nm(it))}</div>`;
      } else h += `<div class="rpt-leg-m">${esc(it.text || '')}</div>`;
      h += '</div>';
    }
    return h + '</div></div>';
  };

  R.kpi = (e, p, doc, data, opt) => {
    const k = data.info?.stats?.kpi || [];
    if (!k.length) return ph(opt, 'การ์ดตัวเลข<br><small>ชั้นหลักไม่มีสถิติ</small>');
    return `<div class="rpt-kpi" style="gap:${p.gap}mm">` + k.map(([v, l]) => `<div style="background:${p.bg};border:.25mm solid ${p.bc};border-radius:${p.r}mm">
      <b style="font-size:${p.fs}pt;color:${p.color}">${esc(v)}</b><span style="font-size:${p.lfs}pt">${esc(l)}</span></div>`).join('') + '</div>';
  };

  R.chart = (e, p, doc, data, opt) => {
    const st = data.info?.stats, b = st?.bars || [];
    if (!b.length) return ph(opt, 'กราฟแท่ง<br><small>ชั้นหลักไม่มีสถิติรายรหัส</small>');
    const fs = (p.fs || 7) * PT, tfs = (p.tfs || 8.5) * PT, title = p.title === 'auto' ? (st.bar_title || '') : p.title;
    const W = e.w, H = e.h, top = title ? tfs * 1.9 : 1, left = fs * 2.6, right = fs * 5.5, bot = 1;
    const rowH = (H - top - bot) / b.length, mx = Math.max(...b.map(x => x[1]), 1e-9);
    let s = `<svg viewBox="0 0 ${W} ${H}" class="rpt-fill" font-family="inherit">`;
    if (title) s += `<text x="0" y="${tfs}" font-size="${tfs}" font-weight="700" fill="${p.color}">${esc(title)}</text>`;
    b.forEach(([code, v, c], i) => {
      const y = top + i * rowH, bw = (W - left - right) * v / mx;
      s += `<text x="${left - fs * .6}" y="${y + rowH / 2 + fs * .35}" font-size="${fs}" text-anchor="end" fill="${p.color}">${code}</text>
        <rect x="${left}" y="${y + rowH * .14}" width="${Math.max(bw, .2)}" height="${rowH * .72}" fill="${c}" stroke="#00000033" stroke-width=".1" rx=".3"/>
        <text x="${left + bw + fs * .5}" y="${y + rowH / 2 + fs * .35}" font-size="${fs}" fill="#5d6478">${big(v)}</text>`;
    });
    return `<div class="rpt-fill" style="background:${p.bg || 'transparent'}">${s}</svg></div>`;
  };

  R.prov = (e, p, doc, data, opt) => {
    const lines = data.info?.prov || [];
    const note = p.note && doc.meta?.note ? `<div style="margin-bottom:1mm">${esc(doc.meta.note)}</div>` : '';
    if (!lines.length && !note) return ph(opt, 'ข้อมูลและวิธีการ');
    return `<div class="rpt-prov" style="font-size:${p.fs}pt;color:${p.color}">${p.title ? `<div class="rpt-prov-t" style="font-size:${p.tfs}pt">${esc(p.title)}</div>` : ''}${note}${lines.map(l => `<div>${esc(l)}</div>`).join('')}</div>`;
  };

  R.credits = (e, p, doc, data) => {
    const i = data.info || {}, m = doc.meta || {};
    const L = [];
    if (p.extra) L.push(esc(RPT.fill(p.extra, doc)));
    if (p.note && m.note) L.push('หมายเหตุ: ' + esc(m.note));
    if (i.sources?.length) L.push('แหล่งข้อมูล: ' + esc(i.sources.join(', ')));
    if (i.basemap_attrib) L.push('แผนที่พื้นหลัง: ' + esc(i.basemap_attrib));
    L.push([p.author && m.author ? 'จัดทำโดย ' + esc(m.author) : '', m.org ? esc(m.org) : '', 'วันที่ ' + esc(m.date || today()),
      p.crs ? 'ระบบพิกัดภูมิศาสตร์ WGS 84 (EPSG:4326)' : '', `Ainulindalë ${esc(i.version || '')}`].filter(Boolean).join(' · '));
    return `<div class="rpt-cred" style="font-size:${p.fs}pt;color:${p.color};text-align:${p.align}">${L.map(x => `<div>${x}</div>`).join('')}</div>`;
  };

  // ---------- เทมเพลต (ออกแบบตามแบบแผนที่งานราชการ/สากล) ----------
  let seq = 0;
  RPT.uid = () => 'e' + Date.now().toString(36) + (seq++).toString(36);
  const E = (type, x, y, w, h, p = {}, extra = {}) => ({ id: RPT.uid(), type, x, y, w, h, z: 0, p: Object.assign(JSON.parse(JSON.stringify(RPT.TYPES[type].p)), p), ...extra });
  const T = (type, x, y, w, h, text, p = {}) => E('text', x, y, w, h, Object.assign({ text }, p));
  const NAVY = '#1b2a4a', INK = '#1d2233', MUTED = '#5d6478';
  RPT.TEMPLATES = {
    gov_l: {
      name: 'ราชการ A4 แนวนอน', desc: 'กรอบเส้นคู่ · แผงข้อมูลขวา (ชื่อเรื่อง คำอธิบาย มาตราส่วน แผนที่ตำแหน่ง) แบบแผนที่หน่วยงานรัฐ',
      paper: { size: 'A4', orient: 'landscape' },
      build: c => [
        E('rect', 5, 5, 287, 200, { fill: '', stroke: NAVY, sw: .6 }),
        E('rect', 6.2, 6.2, 284.6, 197.6, { fill: '', stroke: NAVY, sw: .2 }),
        E('map', 16, 12, 191, 186, { gridLabels: 'lb' }),
        E('rect', 213, 6.2, 77.8, 197.6, { fill: '#f4f6f9', stroke: '', sw: 0 }),
        E('line', 213, 6.2, .4, 197.6, { color: NAVY, width: .3 }),
        T('text', 218, 11, 68, 6, '{org}', { fs: 9, fw: 600, color: NAVY }),
        T('text', 218, 17, 68, 22, '{title}', { fs: 17, fw: 700, color: NAVY, lh: 1.15 }),
        T('text', 218, 39, 68, 11, '{subtitle}', { fs: 9.5, color: '#3d4458', lh: 1.25 }),
        E('line', 218, 51, 68, 1, { color: NAVY, width: .35 }),
        E('legend', 218, 55, 68, 72, { fs: 8, tfs: 9.5 }),
        E('line', 218, 129, 68, 1, { color: '#c3c8d4', width: .25 }),
        E('north', 218, 132, 13, 18, { style: 'classic' }),
        E('scalebar', 234, 133, 53, 16, { align: 'left' }),
        E('inset', 218, 153, 68, 30),
        E('credits', 218, 185, 68, 17, { fs: 5.4, extra: 'แผนที่หมายเลข {map_no}' }),
      ],
    },
    gov_p: {
      name: 'ราชการ A4 แนวตั้ง', desc: 'หัวเรื่องบน · แผนที่ใหญ่กลางหน้า · แถบข้อมูลล่าง (คำอธิบาย / ตำแหน่ง / มาตราส่วน)',
      paper: { size: 'A4', orient: 'portrait' },
      build: c => [
        E('rect', 5, 5, 200, 287, { fill: '', stroke: NAVY, sw: .6 }),
        E('rect', 6.2, 6.2, 197.6, 284.6, { fill: '', stroke: NAVY, sw: .2 }),
        T('text', 12, 11, 120, 6, '{org}', { fs: 9, fw: 600, color: NAVY }),
        T('text', 130, 11, 68, 6, 'แผนที่หมายเลข {map_no}', { fs: 8, color: MUTED, align: 'right' }),
        T('text', 12, 17, 186, 13, '{title}', { fs: 20, fw: 700, color: NAVY, lh: 1.15 }),
        T('text', 12, 30, 186, 8, '{subtitle}', { fs: 10, color: '#3d4458' }),
        E('line', 12, 39.5, 186, 1, { color: NAVY, width: .45 }),
        E('map', 19, 44, 179, 170, { gridLabels: 'lb' }),
        E('rect', 6.2, 221, 197.6, 69.8, { fill: '#f4f6f9' }),
        E('line', 6.2, 221, 197.6, .4, { color: NAVY, width: .3 }),
        E('legend', 12, 225, 80, 62, { fs: 7.5, tfs: 9 }),
        E('inset', 97, 227, 48, 38),
        E('north', 151, 226, 11, 15),
        E('scalebar', 150, 243, 48, 15, { align: 'left' }),
        E('credits', 97, 268, 101, 20, { fs: 5.4 }),
      ],
    },
    ocha: {
      name: 'สากลงานมนุษยธรรม (OCHA)', desc: 'หัวแถบน้ำเงิน · แผนที่เต็มหน้า · คำอธิบายและแผนที่ตำแหน่งลอยบนแผนที่ · ข้อความปฏิเสธความรับผิดชอบ',
      paper: { size: 'A4', orient: 'landscape' },
      build: c => [
        E('rect', 0, 0, 297, 21, { fill: '#007CBB' }),
        T('text', 8, 3.2, 210, 10, '{title}', { fs: 18, fw: 700, color: '#ffffff' }),
        T('text', 8, 13, 210, 6, '{subtitle}', { fs: 9, color: '#dcefff' }),
        T('text', 215, 4, 74, 7, '{org}', { fs: 10, fw: 700, color: '#ffffff', align: 'right' }),
        T('text', 215, 12.5, 74, 6, 'Map No. {map_no}\n{date}', { fs: 7.5, color: '#dcefff', align: 'right', lh: 1.2 }),
        E('map', 0, 21, 297, 172, { fw: 0, grid: 'none', gridLabels: '' }),
        E('legend', 7, 108, 62, 78, { fs: 7.5, tfs: 9, bg: '#ffffffee', bc: '#cfd6de', bw: .25, pad: 3, r: 1 }),
        E('inset', 247, 26, 44, 34, { title: '' }),
        E('north', 279, 64, 10, 14, { style: 'simple' }),
        E('scalebar', 230, 181, 62, 9, { bg: '#ffffffd9', align: 'right', ratio: false }),
        E('rect', 0, 193, 297, 17, { fill: '#f1f4f8' }),
        E('credits', 7, 194.5, 283, 14.5, { fs: 5.4, extra: 'ขอบเขตและชื่อที่แสดงบนแผนที่นี้ไม่ได้แสดงการรับรองอย่างเป็นทางการ · The boundaries and names shown and the designations used on this map do not imply official endorsement or acceptance.' }),
      ],
    },
    journal: {
      name: 'ภาพประกอบบทความวิชาการ', desc: 'ขนาดกว้างหน้ากระดาษวารสาร (174×140 มม.) · กริดพิกัด · คำอธิบายในกรอบ · คำบรรยายภาพใต้รูป',
      paper: { size: 'custom', w: 174, h: 140 },
      build: c => [
        E('map', 12, 4, 158, 108, { fw: .3, fc: '#222222', gridLabels: 'lb', gfs: 6.5 }),
        E('legend', 125, 62, 42, 47, { fs: 6.5, tfs: 7.5, bg: '#ffffffee', bc: '#999999', bw: .2, pad: 2 }),
        E('north', 158, 7, 8, 12, { style: 'simple' }),
        E('scalebar', 15, 100, 50, 10, { style: 'line', ratio: false }),
        T('text', 12, 118, 158, 11, '{caption}', { fs: 9, color: '#111111', lh: 1.35 }),
        E('credits', 12, 129.5, 158, 9.5, { fs: 5.5, crs: false, author: false, note: false }),
      ],
    },
    poster_a3: {
      name: 'โปสเตอร์ A3 แนวตั้ง', desc: 'หัวเรื่องใหญ่พร้อมแถบสี · แผนที่เต็มความกว้าง · ด้านล่าง 3 คอลัมน์: คำอธิบาย / ตำแหน่ง / ตัวเลขสำคัญ',
      paper: { size: 'A3', orient: 'portrait' },
      build: c => [
        E('rect', 16, 15, 4, 25, { fill: '#2b59c3' }),
        T('text', 25, 12, 200, 19, '{title}', { fs: 32, fw: 700, color: INK, lh: 1.1 }),
        T('text', 25, 31, 200, 10, '{subtitle}', { fs: 13, color: MUTED }),
        T('text', 200, 14, 81, 16, '{org}\n{date}', { fs: 11, fw: 600, color: INK, align: 'right', lh: 1.4 }),
        E('line', 16, 45, 265, 1, { color: INK, width: .5 }),
        E('map', 24, 51, 257, 246, { gridLabels: 'lb', gfs: 7.5, lfs: 7.5 }),
        E('legend', 16, 308, 86, 92, { fs: 10, tfs: 13 }),
        E('inset', 110, 312, 80, 58, { fs: 7 }),
        E('north', 110, 376, 13, 18),
        E('scalebar', 127, 378, 63, 16, { fs: 8 }),
        ...(c.hasStats && c.hasBars ? [E('kpi', 198, 308, 83, 30, { fs: 14, lfs: 7.5 }), E('chart', 198, 343, 83, 57, { fs: 8, tfs: 10 })]
          : c.hasStats ? [E('kpi', 198, 308, 83, 30, { fs: 14, lfs: 7.5 }), E('prov', 198, 344, 83, 56, { fs: 8.5, tfs: 10.5 })]
            : [E('prov', 198, 308, 83, 92, { fs: 9, tfs: 11 })]),
        E('line', 16, 404, 265, 1, { color: '#c3c8d4', width: .3 }),
        E('credits', 16, 406, 265, 12, { fs: 7, note: false }),
      ],
    },
    dashboard: {
      name: 'Dashboard / อินโฟกราฟิก A4', desc: 'การ์ดพื้นขาวบนพื้นเทา · แผนที่ซ้าย · ตัวเลขสำคัญ + กราฟ + คำอธิบายด้านขวา',
      paper: { size: 'A4', orient: 'landscape' }, bg: '#f3f5fa',
      build: c => {
        const card = (x, y, w, h) => E('rect', x, y, w, h, { fill: '#ffffff', stroke: '#e1e5ee', sw: .25, r: 2.5 });
        const els = [
          T('text', 10, 7, 200, 11, '{title}', { fs: 19, fw: 700, color: INK }),
          T('text', 10, 18, 200, 6, '{subtitle}', { fs: 9.5, color: MUTED }),
          T('text', 200, 8, 87, 14, '{org}\n{date}', { fs: 9, fw: 600, color: INK, align: 'right', lh: 1.45 }),
          card(10, 27, 168, 173), E('map', 13, 30, 162, 167, { fw: 0, grid: 'none', gridLabels: '' }),
          E('north', 163, 34, 9, 13, { style: 'simple' }),
          E('scalebar', 16, 185, 52, 10, { bg: '#ffffffd9', ratio: false }),
        ];
        if (c.hasStats && !c.hasBars) {
          els.push(E('kpi', 183, 27, 104, 27, { fs: 14, lfs: 6.5 }), card(183, 58, 104, 90), E('legend', 188, 62, 94, 82, { fs: 8, tfs: 10 }),
            E('inset', 183, 152, 50, 48, { title: '' }), E('credits', 238, 152, 49, 48, { fs: 5.6 }));
        } else if (c.hasStats) {
          els.push(E('kpi', 183, 27, 104, 27, { fs: 14, lfs: 6.5 }), card(183, 58, 104, 64), E('chart', 187, 61, 96, 58),
            card(183, 126, 62, 74), E('legend', 187, 129, 55, 68, { fs: 7, tfs: 8.5 }), E('inset', 249, 126, 38, 46, { title: '' }), E('credits', 249, 175, 38, 25, { fs: 5 }));
        } else {
          els.push(card(183, 27, 104, 110), E('legend', 188, 31, 94, 102, { fs: 8, tfs: 10 }), E('inset', 183, 141, 50, 59, { title: '' }), E('credits', 238, 141, 49, 59, { fs: 5.6 }));
        }
        return els;
      },
    },
  };
  RPT.fromTemplate = (key, ctx, prev = {}) => {
    const t = RPT.TEMPLATES[key];
    const els = t.build(ctx);
    els.forEach((e, i) => { e.z = i; if (e.type === 'rect') e.lock = true; if (e.type === 'map') e.p.auto = true; });
    return Object.assign({}, prev, { v: 2, template: key, paper: { ...t.paper }, bg: t.bg || '#ffffff', els });
  };

  G.RPT = RPT;
})(window);
