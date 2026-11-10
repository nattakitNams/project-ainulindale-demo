// Ainulindalë — หน้าเว็บ (หน้าเดียว, เส้นทาง #hash) · V2
'use strict';
const UI_VERSION = '1.0.41';          // ต้องตรงกับ APP_VERSION ฝั่งเซิร์ฟเวอร์ — ไม่ตรง = run.bat ยังรันโค้ดเก่า
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pxLabel = n => n >= 1e6 ? `${(n / 1e6).toLocaleString('th-TH', { maximumFractionDigits: 1 })} ล้านพิกเซล` : `${Math.round(n).toLocaleString('th-TH')} พิกเซล`;
const fmt = (v, d = 2) => v == null || Number.isNaN(+v) ? '–'
  : (+v !== 0 && Math.abs(+v) < 1) ? Number(v).toLocaleString('th-TH', { maximumSignificantDigits: Math.max(3, d) })   // ค่า 0–1 ละเอียด ไม่ปัดเป็น 0
    : Number(v).toLocaleString('th-TH', { maximumFractionDigits: d });
const bytes = b => b == null ? '–' : b < 1024 ** 2 ? (b / 1024).toFixed(0) + ' KB' : b < 1024 ** 3 ? (b / 1024 ** 2).toFixed(1) + ' MB' : (b / 1024 ** 3).toFixed(2) + ' GB';
const attr = s => esc(JSON.stringify(s));
const VT = { count: 'จำนวนนับ (เช่น คน/พิกเซล)', density: 'ความหนาแน่น / ค่าต่อเนื่อง', class: 'ชั้น / หมวดหมู่' };
const VT_SHORT = { count: 'จำนวนนับ', density: 'ต่อเนื่อง', class: 'ชั้น' };
const VT_RULE = {
  count: 'เพิ่มความละเอียด = หารเท่ากัน ÷k² · ลด = ผลรวม',
  density: 'เพิ่มความละเอียด = ทำซ้ำค่า · ลด = ค่าเฉลี่ยถ่วงพื้นที่',
  class: 'เพิ่มความละเอียด = ทำซ้ำค่า · ลด = เสียงข้างมาก (majority)'
};
const VT_CARDS = [
  { k: 'count', c: 'var(--peach)', t: 'จำนวนนับ', ex: 'คน/พิกเซล · จำนวนอาคาร · จำนวนต้นไม้', rule: 'รวมพิกเซล → บวกกัน · แตกพิกเซล → หารแบ่งเท่า ๆ' },
  { k: 'density', c: 'var(--sky)', t: 'ต่อเนื่อง / ความหนาแน่น', ex: 'คน/ตร.กม. · ความสูง · อุณหภูมิ · NDVI', rule: 'รวมพิกเซล → เฉลี่ย (ถ่วงพื้นที่) · แตกพิกเซล → ค่าเดิม' },
  { k: 'class', c: 'var(--mint)', t: 'ชั้น / หมวดหมู่', ex: 'ชั้นน้ำท่วม · land cover · จำนวนปีที่ท่วม · รหัสจังหวัด', rule: 'รวมพิกเซล → เสียงข้างมาก · แตกพิกเซล → ค่าเดิม' },
];
const ROLE = { input: 'นำเข้า', derived: 'แปลงแล้ว', map: 'แผนที่' };
const ROLE_C = { input: 'var(--sky)', derived: 'var(--peach)', map: 'var(--rose)' };

// ---------- ไอคอน (เส้น 1.8px) ----------
const P = d => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
const IC = {
  calc: P('<rect x="4.5" y="3.5" width="15" height="17" rx="2"/><path d="M8 8h8M8.5 13.5h2M8.5 17h2M13.5 13.5h2M13.5 17h2"/>'),
  chat: P('<path d="M5 5.5h14a1.5 1.5 0 0 1 1.5 1.5v8.5A1.5 1.5 0 0 1 19 17h-8l-4.5 3.5V17H5a1.5 1.5 0 0 1-1.5-1.5V7A1.5 1.5 0 0 1 5 5.5z"/>'),
  lock: P('<rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5"/>'),
  unlock: P('<rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8 10.5V8a4 4 0 0 1 7.6-1.7"/>'),
  send: P('<path d="M4 12 20 4l-6 16-3-7z"/><path d="m11 13 9-9"/>'),
  minus: P('<path d="M6 12h12"/>'),
  ext: P('<path d="M14 4.5h5.5V10M19.5 4.5 11 13M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10"/>'),
  eye: P('<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.8"/>'),
  eyeOff: P('<path d="M4 4l16 16M10 6a9.5 9.5 0 0 1 2-.5c6 0 9.5 6.5 9.5 6.5a16 16 0 0 1-2.6 3.4M6.5 7.5C4 9.2 2.5 12 2.5 12S6 18.5 12 18.5c1.6 0 3-.5 4.2-1.1"/>'),
  copy: P('<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5.5A1.5 1.5 0 0 0 14.5 4h-9A1.5 1.5 0 0 0 4 5.5v9A1.5 1.5 0 0 0 5.5 16H8"/>'),
  db: P('<ellipse cx="12" cy="5.5" rx="7.5" ry="3"/><path d="M4.5 5.5v13c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-13"/><path d="M4.5 12c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3"/>'),
  grid: P('<rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/>'),
  target: P('<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r="1"/>'),
  pulse: P('<path d="M3 12h4l2.5-6 5 12 2.5-6H21"/>'),
  raster: P('<rect x="3.5" y="3.5" width="17" height="17" rx="3"/><path d="M3.5 9.5h17M3.5 14.5h17M9.5 3.5v17M14.5 3.5v17"/>'),
  vector: P('<path d="M5 18 9 6l6 9 4-7"/><circle cx="5" cy="18" r="1.8"/><circle cx="9" cy="6" r="1.8"/><circle cx="15" cy="15" r="1.8"/><circle cx="19" cy="8" r="1.8"/>'),
  map: P('<path d="m3.5 6.5 5.5-2.5 6 2.5 5.5-2.5v13.5l-5.5 2.5-6-2.5-5.5 2.5z"/><path d="M9 4v13.5M15 6.5V20"/>'),
  plus: P('<path d="M12 5v14M5 12h14"/>'), folder: P('<path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2.5h7a2 2 0 0 1 2 2v7.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>'),
  upload: P('<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v2.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V16"/>'),
  edit: P('<path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z"/>'), trash: P('<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12.5a1.5 1.5 0 0 0 1.5 1.5h7a1.5 1.5 0 0 0 1.5-1.5L18 7M9 7V4.5h6V7"/>'),
  refresh: P('<path d="M20 11a8 8 0 0 0-14.5-4.5M4 4v4h4M4 13a8 8 0 0 0 14.5 4.5M20 20v-4h-4"/>'),
  play: P('<path d="M7 4.5v15l12-7.5z"/>'), check: P('<path d="m5 12.5 4.5 4.5L19 7.5"/>'), x: P('<path d="M6 6l12 12M18 6 6 18"/>'),
  link: P('<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>'),
  palette: P('<path d="M12 3.5a8.5 8.5 0 1 0 0 17c1.4 0 2-1 1.5-2.2-.6-1.4.3-2.8 1.8-2.8h1.7a3.5 3.5 0 0 0 3.5-3.5c0-4.7-3.8-8.5-8.5-8.5z"/><circle cx="7.5" cy="11" r="1.2"/><circle cx="10.5" cy="7.5" r="1.2"/><circle cx="15" cy="7.8" r="1.2"/>'),
  layers: P('<path d="m12 3.5 8.5 4.5-8.5 4.5-8.5-4.5z"/><path d="m3.5 12 8.5 4.5 8.5-4.5M3.5 16l8.5 4.5 8.5-4.5"/>'),
  gear: P('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>'),
  pdf: P('<path d="M14 3.5H7a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8.5z"/><path d="M14 3.5v5h5M9 13h6M9 16.5h4"/>'),
  hex: P('<path d="M12 3 19.8 7.5v9L12 21l-7.8-4.5v-9z"/>'),
  globe: P('<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.5 2.6 3.7 5.4 3.7 8.5s-1.2 5.9-3.7 8.5c-2.5-2.6-3.7-5.4-3.7-8.5s1.2-5.9 3.7-8.5z"/>'),
  download: P('<path d="M12 4v12M7 11l5 5 5-5"/><path d="M4 18v1.5A1.5 1.5 0 0 0 5.5 21h13a1.5 1.5 0 0 0 1.5-1.5V18"/>'),
};
const ic = k => `<span class="ic">${IC[k] || ''}</span>`;
// ---------- หกเหลี่ยม ----------
const isHex = d => !!(d && d.meta && d.meta.hex);
const niceKm = x => { const p = 10 ** Math.floor(Math.log10(x)); return [1, 2, 5, 10].map(k => k * p).find(v => v >= x) || 10 * p; };
const frac = s => { const [a, b] = String(s).split('/'); return +a / (+b || 1); };
const pxKm = m => m.res_exact ? (m.geographic ? frac(m.res_exact) / 3600 * 111.32 : frac(m.res_exact) / 1000) : null;
const hexFields = d => (d.meta.hex?.fields || []).flatMap(f => Object.entries(f.columns || {}).map(([c, t]) => ({ c, t, name: f.name, vt: f.value_type, main: c === f.main })));
function hexCard(d, all, aoiOpts) {
  const m = d.meta, px = d.kind === 'raster' ? pxKm(m) : null;
  const size = px ? niceKm(Math.max(px * 3, 0.1)) : 1;
  const others = all.filter(x => x.id !== d.id && !isHex(x) && ((x.kind === 'raster' && x.value_type_confirmed) || x.kind === 'vector'));
  return `<div class="card"><div class="card-head"><h2><span class="dot" style="background:var(--lav);color:var(--lav)"></span>แปลงเป็นหกเหลี่ยม (hex)</h2></div>
    <p class="small muted" style="margin-top:0">ช่องหกเหลี่ยมพื้นที่เท่ากัน + ค่าของแต่ละชุด (GeoPackage) — ${d.kind === 'raster' ? 'นับ = ผลรวม · ต่อเนื่อง = เฉลี่ยถ่วงพื้นที่ · ชั้น = ค่าที่กินพื้นที่มากสุด' : 'โพลิกอน = % พื้นที่ที่ทับ · เส้น = ความยาว กม. · จุด = จำนวน'} · คิดที่ความละเอียดต้นทาง (ไม่แตกพิกเซล)</p>
    <div class="grid-form">
      <label class="field"><span>ขนาด (กม. ระหว่างศูนย์กลาง)</span><input type="number" id="hxSize" min="0.01" step="any" value="${size}"><span class="tiny muted" id="hxArea"></span></label>
      <label class="field"><span>พื้นที่ศึกษา</span><select id="hxAoi">${aoiOpts}</select></label>
      <div class="field full"><span>ใส่ค่าจากชุดอื่นด้วย</span><div class="checklist" id="hxMore">${others.map(x => `<label><input type="checkbox" value="${x.id}"><span>#${x.id} ${esc(x.name)} <span class="tiny muted">${x.kind === 'raster' ? esc(VT_SHORT[x.value_type] || '') + ' · ' + esc((x.meta.res_label || '').split(' (')[0]) : esc(x.meta.geometry_type || 'vector')}</span></span></label>`).join('') || '<div class="tiny muted" style="padding:6px 8px">ไม่มีชุดอื่น</div>'}</div></div>
      <label class="row small full"><input type="checkbox" id="hxDrop" checked> ตัดช่องที่ว่าง/เป็น 0 ทุกชุดออก</label>
      <label class="field full"><span>ชื่อผลลัพธ์</span><input type="text" id="hxName" placeholder="เว้นว่าง = ตั้งให้"></label>
    </div>
    <div class="tiny muted" style="margin:8px 0">${px ? `พิกเซลข้อมูลกว้าง ≈ ${fmt(px, 3)} กม. — ช่องควรกว้างกว่าพิกเซลหลายเท่า (ค่าเริ่มต้น ≈ 3 เท่า)` : ''} · ทำ hex แล้วนำไปทำไบแวเรียตหกเหลี่ยม หรือแปลงกลับเป็นราสเตอร์ได้</div>
    <button id="hxRun" class="mint">${IC.hex}สร้างหกเหลี่ยม</button></div>`;
}
function hexCardBind(d) {
  const area = () => { const s = +$('#hxSize').value; $('#hxArea').textContent = s > 0 ? `≈ ${fmt(Math.sqrt(3) / 2 * s * s, 3)} ตร.กม./ช่อง` : ''; };
  $('#hxSize').oninput = area; area();
  $('#hxRun').onclick = () => runJob('hex', { dataset_ids: [d.id, ...$$('#hxMore input:checked').map(o => +o.value)], size_km: +$('#hxSize').value,
    aoi_id: +$('#hxAoi').value || null, drop_empty: $('#hxDrop').checked, name: $('#hxName').value.trim() || null }, () => location.hash = '#/jobs');
}

let STATE = null, PALS = { builtin: [], custom: [] };
let maps = [];

async function api(url, opt = {}) {
  if (opt.json !== undefined) { opt.body = JSON.stringify(opt.json); opt.headers = { 'Content-Type': 'application/json' }; opt.method = opt.method || 'POST'; }
  const r = await fetch(url, opt);
  const t = await r.text();
  let d; try { d = JSON.parse(t); } catch { d = { error: t.slice(0, 300) }; }
  if (!r.ok) throw new Error(d.error || r.statusText);
  return d;
}
function toast(msg, err = false, ms = 5000) {
  const d = document.createElement('div'); d.textContent = msg; if (err) d.className = 'err';
  $('#toast').appendChild(d); setTimeout(() => d.remove(), ms);
}
const ui = {
  // หน้าต่างถาม-ตอบแทน confirm()/prompt() ของเบราว์เซอร์
  open(title, body, buttons) {
    return new Promise(res => {
      $('#mTitle').textContent = title; $('#mBody').innerHTML = body;
      $('#mActions').innerHTML = buttons.map((b, i) => `<button data-i="${i}" class="${b.cls || ''}">${b.label}</button>`).join('');
      $('#modal').classList.remove('hide');
      const done = v => { $('#modal').classList.add('hide'); res(v); };
      $$('#mActions button').forEach(b => b.onclick = () => done(buttons[+b.dataset.i].value(done)));
      $('#modal').onclick = e => { if (e.target.id === 'modal') done(null); };
      setTimeout(() => $('#mBody input')?.focus(), 30);
    });
  },
  confirm(title, body, ok = 'ตกลง') { return ui.open(title, body, [{ label: 'ยกเลิก', cls: 'ghost', value: () => false }, { label: ok, cls: 'primary', value: () => true }]); },
  prompt(title, value = '', hint = '') {
    return ui.open(title, `${hint ? `<p class="muted small">${esc(hint)}</p>` : ''}<input type="text" id="mIn" value="${esc(value)}">`,
      [{ label: 'ยกเลิก', cls: 'ghost', value: () => null }, { label: 'บันทึก', cls: 'primary', value: () => $('#mIn').value.trim() || null }]);
  },
};
async function openFolder(p) { try { await api(ENGINE + '/api/open-folder', { json: { path: p } }); } catch (e) { toast(e.message, true); } }
window.openFolder = openFolder;
async function browseOne() { const r = await api(ENGINE + '/api/browse', { json: {} }); return r.paths[0]; }

// ---------------- เส้นทาง ----------------
async function route() {
  window._routeGen = (window._routeGen || 0) + 1;       // หน้าเก่าที่ยังมีงาน async ค้าง เช็คเลขนี้ก่อนวาด/บันทึก (กันหน้าเก่าทับหน้าใหม่)
  maps.forEach(m => m.remove()); maps = [];
  clearInterval(window._poll);
  const h = location.hash || '#/';
  const r = ['viewer', 'report', 'biv', 'change', 'tools', 'aoi', 'hub', 'jobs', 'system', 'trash'].find(k => h.startsWith('#/' + k)) || 'home';
  $$('#nav a, .side-trash').forEach(a => a.classList.toggle('on', a.dataset.r === r));
  const v = $('#view');
  v.innerHTML = '<p class="muted">กำลังโหลด…</p>';
  window.scrollTo(0, 0);
  try {
    if (h.startsWith('#/ds/')) { const d = await api(ENGINE + '/api/datasets/' + h.split('/')[2]); d.kind === 'link' ? await pageLink(d) : await pageDataset(d.id); }
    else if (r === 'biv') await pageBiv();
    else if (r === 'aoi') await pageAoi(new URLSearchParams(h.split('?')[1] || ''));
    else if (r === 'jobs') await pageJobs();
    else if (r === 'trash') await pageTrash();
    else if (r === 'hub') await pageHub(h.startsWith('#/hub/') ? decodeURIComponent(h.slice(6)) : null);
    else if (r === 'viewer') await pageViewer();
    else if (r === 'report') await pageReport(new URLSearchParams(h.split('?')[1] || ''));
    else if (r === 'change') await pageChange();
    else if (r === 'tools') await pageTools(new URLSearchParams(h.split('?')[1] || ''));
    else if (r === 'system') await pageSystem();
    else await pageHome();
  } catch (e) { v.innerHTML = `<div class="note err">${esc(e.message)}</div>`; console.error(e); }
  enhanceAoiSelects();
  if (r !== 'trash') trashBadge();
}
window.addEventListener('hashchange', route);
async function jobBadge() {
  try {
    const js = await api(ENGINE + '/api/jobs');
    const n = js.filter(j => ['queued', 'running', 'cancelling'].includes(j.status)).length;
    const b = $('#jobBadge'); b.textContent = n; b.classList.toggle('hide', !n);
    const run = js.find(j => j.status === 'running');
    const sj = $('#sideJob');
    if (run) {
      const pct = Math.round((run.progress || 0) * 100);
      sj.innerHTML = `<a href="#/jobs"><div class="tiny" style="color:var(--text-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(run.title)}</div>
        <div class="bar run" style="min-width:0;margin:6px 0 4px"><div style="width:${pct}%"></div></div>
        <div class="tiny muted">${pct}% · ${run.eta_s != null ? 'เหลือ ~' + fmtDur(run.eta_s) : 'กำลังประเมิน…'}</div></a>`;
      sj.classList.remove('hide');
    } else sj.classList.add('hide');
  } catch { }
}
const head = (eyebrow, title, sub = '', actions = '') => `<div class="page-head"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1>${sub ? `<div class="sub">${sub}</div>` : ''}</div><div class="row">${actions}</div></div>`;

// ================= คลังข้อมูล =================
async function pageHome() {
  const [all, fr] = await Promise.all([api(ENGINE + '/api/datasets'), api(ENGINE + '/api/folders')]);
  const FOL = fr.folders;
  let cur = +new URLSearchParams(location.hash.split('?')[1] || '').get('f') || null;
  if (cur && !FOL.some(f => f.id === cur)) cur = null;               // โฟลเดอร์ถูกลบไปแล้ว → ราก
  window._libFolder = cur;
  const inF = d => (d.folder_id || null) === cur;
  const list = all.filter(inF);                                    // ชุดข้อมูลในโฟลเดอร์ที่เปิดอยู่ (หมวดย่อยแบบเดิม)
  const by = r => list.filter(d => d.role === r && d.kind !== 'link');
  const byAll = r => all.filter(d => d.role === r && d.kind !== 'link');
  const lks = list.filter(d => d.kind === 'link' && !d.meta?.builtin);
  const base = list.filter(d => d.kind === 'link' && d.meta?.builtin);
  const kids = FOL.filter(f => (f.parent_id || null) === cur);
  const pathTo = id => { const out = []; let f = FOL.find(x => x.id === id); while (f) { out.unshift(f); f = FOL.find(x => x.id === f.parent_id); } return out; };
  const sub = id => { const s = new Set([id]); let grew = true; while (grew) { grew = false; FOL.forEach(f => { if (s.has(f.parent_id) && !s.has(f.id)) { s.add(f.id); grew = true; } }); } return s; };
  const countIn = id => { const s = sub(id); return all.filter(d => s.has(d.folder_id)).length; };
  const crumbs = [{ id: null, name: 'คลังข้อมูล' }, ...pathTo(cur)];
  let bd = null; try { bd = await api(ENGINE + '/api/basedata'); } catch { }
  const bdMissing = (bd?.items || []).filter(i => !i.present);
  const jobs = await api(ENGINE + '/api/jobs');
  const running = jobs.filter(j => ['queued', 'running'].includes(j.status)).length;
  const v = $('#view');
  v.innerHTML = head('Library', 'คลังข้อมูล', 'เพิ่มชุดข้อมูลแล้วแอปจำไว้ — ข้อมูลนำเข้า ผลแปลง และแผนที่ แยกเก็บคนละหมวด')
    + `<div class="stats">
      <div class="stat" style="--c:var(--sky)"><b>${byAll('input').length}</b><span>ข้อมูลนำเข้า</span></div>
      <div class="stat" style="--c:var(--peach)"><b>${byAll('derived').length}</b><span>ข้อมูลที่แปลงแล้ว</span></div>
      <div class="stat" style="--c:var(--rose)"><b>${byAll('map').length}</b><span>แผนที่ไบแวเรียต</span></div>
      <div class="stat" style="--c:var(--mint)"><b>${running}</b><span>งานที่กำลังทำ/รอคิว</span></div></div>
    <div class="lib-bar">
      <nav class="crumbs">${crumbs.map((c, i) => `${i ? '<span class="sep">›</span>' : ''}<a href="#/${c.id ? '?f=' + c.id : ''}" class="crumb ${i === crumbs.length - 1 ? 'on' : ''}" data-drop="${c.id ?? ''}" ${c.id ? 'translate="no"' : ''}>${i ? IC.folder : IC.db}${esc(c.name)}</a>`).join('')}</nav>
      <span class="spacer"></span><span class="tiny muted">ลากการ์ดไปวางบนโฟลเดอร์เพื่อย้าย</span>
      <button class="sm" id="fNew">${IC.plus}โฟลเดอร์ใหม่</button></div>
    ${kids.length ? `<div class="folder-grid">${kids.map(f => `<a class="folder" href="#/?f=${f.id}" data-drop="${f.id}" data-fid="${f.id}" draggable="true">
      <span class="ico">${IC.folder}</span><span class="fn" translate="no">${esc(f.name)}</span><span class="tiny muted">${countIn(f.id)} ชุด</span>
      <span class="fa"><button class="ghost sm" data-fren="${f.id}" title="แก้ชื่อโฟลเดอร์">${IC.edit}</button><button class="ghost sm" data-fmv="${f.id}" title="ย้ายโฟลเดอร์">${IC.folder}</button><button class="ghost sm danger" data-fdel="${f.id}" title="ลบโฟลเดอร์ (ของข้างในย้ายขึ้นไปโฟลเดอร์แม่)">${IC.trash}</button></span></a>`).join('')}</div>` : ''}
    ${!list.length && !kids.length && cur ? '<div class="empty">โฟลเดอร์ว่าง — เพิ่มชุดข้อมูลด้านบน (จะเข้าโฟลเดอร์นี้) หรือลากการ์ดจากที่อื่นมาวางบนชื่อโฟลเดอร์ในแถบด้านบน</div>' : ''}
    <div class="card">
      <div class="card-head"><h2><span class="dot"></span>เพิ่มชุดข้อมูล</h2>
        <label class="switch"><input type="checkbox" id="copy"><i></i><span class="small">ก๊อปไฟล์เข้า database ของแอป</span></label></div>
      <div class="cols2">
        <div id="drop" class="drop">${IC.upload}<div><b>ลากไฟล์มาวาง</b></div><div class="small muted">จะก๊อปเข้า database เสมอ (เบราว์เซอร์ไม่บอก path จริง) · shapefile ลาก .shp .shx .dbf .prj พร้อมกัน</div></div>
        <div class="stack">
          <div class="row"><button id="browse" class="primary">${IC.folder}เลือกไฟล์จากเครื่อง…</button><span class="small muted">ได้ path จริง · ไม่ติ๊กก๊อป = จำ path</span></div>
          <textarea id="paths" placeholder="หรือวาง path เต็ม บรรทัดละไฟล์ — E:\\My Drive\\…\\pop_2024.tif"></textarea>
          <div class="row"><button id="addPaths">${IC.plus}เพิ่มจาก path</button><span class="small muted">GeoTIFF · VRT · GeoPackage · Shapefile · GeoJSON · zip</span></div>
        </div>
      </div>
      <div id="addMsg"></div>
    </div>
    <div class="card">
      <div class="card-head"><h2><span class="dot" style="background:var(--lav);color:var(--lav)"></span>เพิ่มแผนที่จากลิงก์</h2><span class="tiny muted">XYZ · WMTS · WMS · WFS · ArcGIS REST · GeoJSON · COG</span></div>
      <div class="row"><input type="text" id="lkUrl" placeholder="วางลิงก์ เช่น https://…/arcgis/rest/services/…/MapServer  หรือ  https://…/{z}/{x}/{y}.png" style="flex:1;min-width:280px">
        <select id="lkSec" style="max-width:200px"><option value="">ไม่ใช้โทเคน</option></select><button class="sm ghost" id="lkSecAdd" title="เพิ่มโทเคน (เก็บเข้ารหัส)">${IC.plus}โทเคน</button>
        <button id="lkGo" class="primary">${IC.link}ตรวจลิงก์</button></div>
      <div id="lkRes"></div>
    </div>
    ${['input', 'derived', 'map'].filter(r => !cur || by(r).length).map(r => `<div class="section-title"><span class="dot" style="background:${ROLE_C[r]};color:${ROLE_C[r]}"></span><h2>${{ input: 'ข้อมูลนำเข้า', derived: 'ข้อมูลที่แปลงแล้ว', map: 'แผนที่ไบแวเรียต' }[r]}</h2><span class="count">${by(r).length}</span></div>
      <div class="ds-grid">${by(r).map(cardHtml).join('') || `<div class="empty">${cur ? 'ไม่มีในโฟลเดอร์นี้' : r === 'input' ? 'ยังไม่มี — เพิ่มชุดข้อมูลด้านบน' : r === 'derived' ? 'ผลจากการปรับความละเอียด / แปลงเป็นราสเตอร์ / ทำกริด จะอยู่ที่นี่' : 'สร้างจากเมนู "สร้างไบแวเรียต"'}</div>`}</div>`).join('')}
    ${cur && !base.length ? '' : `<div class="section-title"><span class="dot" style="background:var(--butter);color:var(--butter)"></span><h2>ข้อมูลพื้นฐาน</h2><span class="count">${base.length}</span>
      <span class="tiny muted">ขอบเขตการปกครองจาก GISTDA · ใช้เป็นเส้นขอบเขต พื้นที่ศึกษา และไบแวเรียตรายพื้นที่ได้ทันที</span>
      ${bdMissing.length && !cur ? `<button class="sm ghost" id="bdRestore" style="margin-left:auto">${IC.plus}เพิ่มกลับ ${bdMissing.length} ชุด (${bdMissing.map(i => esc(i.name)).join(', ')})</button>` : ''}</div>
    <div class="ds-grid">${base.map(cardHtml).join('') || `<div class="empty">${cur ? 'ไม่มีในโฟลเดอร์นี้' : bd?.status?.state === 'running' ? 'กำลังเชื่อมต่อบริการ GISTDA…' : 'ยังไม่มี — ต้องต่ออินเทอร์เน็ตครั้งแรก แล้วกด "เพิ่มกลับ"'}</div>`}</div>`}
    ${cur && !lks.length ? '' : `<div class="section-title"><span class="dot" style="background:var(--lav);color:var(--lav)"></span><h2>ลิงก์แผนที่</h2><span class="count">${lks.length}</span></div>
    <div class="ds-grid">${lks.map(cardHtml).join('') || `<div class="empty">${cur ? 'ไม่มีในโฟลเดอร์นี้' : 'ยังไม่มี — วางลิงก์บริการแผนที่ด้านบน'}</div>`}</div>`}`;
  // ---- โฟลเดอร์: สร้าง / แก้ชื่อ / ลบ / ย้าย / ลากวาง ----
  const reload = () => pageHome();
  const folderPick = async (title, exclude = new Set()) => {
    const opts = [{ id: '', name: 'คลังข้อมูล (ราก)' }, ...FOL.filter(f => !exclude.has(f.id)).map(f => ({ id: f.id, name: pathTo(f.id).map(x => x.name).join(' › ') }))]
      .sort((a, b) => (a.id === '' ? -1 : b.id === '' ? 1 : a.name.localeCompare(b.name, 'th')));
    return ui.open(title, `<select id="fPick" style="width:100%">${opts.map(o => `<option value="${o.id}" ${o.id === (cur ?? '') ? 'selected' : ''} translate="no">${esc(o.name)}</option>`).join('')}</select>`,
      [{ label: 'ยกเลิก', cls: 'ghost', value: () => undefined }, { label: 'ย้าย', cls: 'primary', value: () => $('#fPick').value }]);
  };
  const moveTo = async (body, to) => {
    try { await api(ENGINE + '/api/folders/move', { json: { ...body, to: to === '' || to == null ? null : +to } }); reload(); } catch (e) { toast(e.message, true); }
  };
  $('#fNew').onclick = async () => {
    const n = await ui.prompt('โฟลเดอร์ใหม่', '', cur ? `ใน "${pathTo(cur).map(x => x.name).join(' › ')}"` : 'ที่ราก ของคลังข้อมูล'); if (!n) return;
    try { await api(ENGINE + '/api/folders', { json: { name: n, parent_id: cur } }); reload(); } catch (e) { toast(e.message, true); }
  };
  $$('[data-fren]').forEach(b => b.onclick = async e => {
    e.preventDefault(); e.stopPropagation();
    const f = FOL.find(x => x.id == b.dataset.fren);
    const n = await ui.prompt('แก้ชื่อโฟลเดอร์', f.name); if (!n) return;
    try { await api(`${ENGINE}/api/folders/${f.id}`, { method: 'PATCH', json: { name: n } }); reload(); } catch (er) { toast(er.message, true); }
  });
  $$('[data-fdel]').forEach(b => b.onclick = async e => {
    e.preventDefault(); e.stopPropagation();
    const f = FOL.find(x => x.id == b.dataset.fdel), n = countIn(f.id);
    if (!await ui.confirm('ลบโฟลเดอร์?', `<p>"${esc(f.name)}"${n ? ` — ชุดข้อมูล ${n} ชุดและโฟลเดอร์ย่อยข้างในจะย้ายขึ้นไปที่ "${esc(crumbs.at(-1).name)}"` : ''}</p><p class="small muted">ไม่มีข้อมูลหาย (โฟลเดอร์เป็นแค่การจัดหมวดในแอป ไม่ได้ย้ายไฟล์จริง)</p>`, 'ลบโฟลเดอร์')) return;
    try { await api(`${ENGINE}/api/folders/${f.id}`, { method: 'DELETE' }); reload(); } catch (er) { toast(er.message, true); }
  });
  $$('[data-fmv]').forEach(b => b.onclick = async e => {
    e.preventDefault(); e.stopPropagation();
    const to = await folderPick('ย้ายโฟลเดอร์ไปที่…', sub(+b.dataset.fmv));
    if (to !== undefined && to !== null) moveTo({ folder_ids: [+b.dataset.fmv] }, to);
  });
  $$('[data-mv]').forEach(b => b.onclick = async e => {
    e.stopPropagation();
    const to = await folderPick('ย้ายชุดข้อมูลไปที่…');
    if (to !== undefined && to !== null) moveTo({ dataset_ids: [+b.dataset.mv] }, to);
  });
  // ลากการ์ดชุดข้อมูล / โฟลเดอร์ ไปวางบนโฟลเดอร์หรือแถบเส้นทาง
  $$('.ds').forEach(el => { el.draggable = true; el.ondragstart = e => { e.dataTransfer.setData('text/ainu', JSON.stringify({ d: +el.dataset.id })); e.dataTransfer.effectAllowed = 'move'; }; });
  $$('.folder').forEach(el => el.ondragstart = e => { e.dataTransfer.setData('text/ainu', JSON.stringify({ f: +el.dataset.fid })); e.dataTransfer.effectAllowed = 'move'; });
  $$('[data-drop]').forEach(el => {
    el.ondragover = e => { if ([...e.dataTransfer.types].includes('text/ainu')) { e.preventDefault(); el.classList.add('over'); } };
    el.ondragleave = () => el.classList.remove('over');
    el.ondrop = e => {
      e.preventDefault(); el.classList.remove('over');
      let x; try { x = JSON.parse(e.dataTransfer.getData('text/ainu')); } catch { return; }
      const to = el.dataset.drop === '' ? null : +el.dataset.drop;
      if (x.f && (x.f === to || (to && sub(x.f).has(to)))) return toast('ย้ายโฟลเดอร์เข้าไปในตัวเองไม่ได้', true);
      moveTo(x.d ? { dataset_ids: [x.d] } : { folder_ids: [x.f] }, to);
    };
  });
  linkAdder();
  $('#bdRestore') && ($('#bdRestore').onclick = async () => {
    $('#bdRestore').disabled = true; $('#bdRestore').textContent = 'กำลังเชื่อมต่อบริการ GISTDA…';
    try { const r = await api(ENGINE + '/api/basedata', { json: {} }); if (r.status.failed.length) toast('เพิ่มไม่ได้: ' + r.status.failed.join(' · '), true); } catch (e) { toast(e.message, true); }
    pageHome();
  });
  if (bd?.status?.state === 'running') setTimeout(() => { if (location.hash === '#/' || location.hash === '') pageHome(); }, 3000);
  $$('.ds').forEach(el => el.onclick = e => { if (!e.target.closest('button')) location.hash = '#/ds/' + el.dataset.id; });
  $$('[data-ren]').forEach(b => b.onclick = async () => {
    const d = list.find(x => x.id == b.dataset.ren);
    const n = await ui.prompt('แก้ชื่อชุดข้อมูล', d.name); if (!n) return;
    await api(ENGINE + '/api/datasets/' + d.id, { method: 'PATCH', json: { name: n } }); pageHome();
  });
  $$('[data-del]').forEach(b => b.onclick = async () => {
    const d = list.find(x => x.id == b.dataset.del);
    if (!await ui.confirm('ย้ายไปถังขยะ?', `<p>"${esc(d.name)}" จะหายจากรายการ — กู้คืนได้จากถังขยะ (มุมล่างของแถบซ้าย)</p>`, 'ย้ายไปถังขยะ')) return;
    const r = await api(ENGINE + '/api/datasets/' + d.id, { method: 'DELETE' }); toast(r.note); trashBadge(r.trash); pageHome();
  });
  const showRes = r => {
    $('#addMsg').innerHTML = (r.added.length ? `<div class="note ok">เพิ่มแล้ว ${r.added.length} ชุด — กำลังเตรียมสถิติ/พรีวิวในแท็บงาน</div>` : '')
      + r.warnings.map(w => `<div class="note warn">${esc(w)}</div>`).join('') + r.errors.map(w => `<div class="note err">${esc(w)}</div>`).join('');
    if (r.added.length) setTimeout(pageHome, 1400);
  };
  $('#browse').onclick = async () => {
    $('#browse').disabled = true;
    try {
      const r = await api(ENGINE + '/api/browse', { json: {} });
      if (r.paths.length) showRes(await api(ENGINE + '/api/datasets', { json: { paths: r.paths, copy: $('#copy').checked, folder_id: cur } }));
    } catch (e) { toast(e.message, true); } finally { $('#browse').disabled = false; }
  };
  $('#addPaths').onclick = async () => {
    const ps = $('#paths').value.split(/\r?\n/).map(s => s.trim().replace(/^"|"$/g, '')).filter(Boolean);
    if (ps.length) try { showRes(await api(ENGINE + '/api/datasets', { json: { paths: ps, copy: $('#copy').checked, folder_id: cur } })); } catch (e) { toast(e.message, true); }
  };
  const dz = $('#drop');
  dz.ondragover = e => { if ([...e.dataTransfer.types].includes('text/ainu')) return; e.preventDefault(); dz.classList.add('over'); };
  dz.ondragleave = () => dz.classList.remove('over');
  dz.ondrop = async e => {
    e.preventDefault(); dz.classList.remove('over');
    const fd = new FormData();
    for (const f of e.dataTransfer.files) fd.append('files', f, f.name);
    if (cur) fd.append('folder_id', cur);
    dz.querySelector('b').textContent = 'กำลังอัปโหลด…';
    try { showRes(await api(ENGINE + '/api/upload', { method: 'POST', body: fd })); } catch (er) { toast(er.message, true); }
  };
}

function cardHtml(d) {
  const m = d.meta || {};
  const c = d.role === 'map' ? 'var(--rose)' : d.role === 'derived' ? 'var(--peach)' : d.kind === 'vector' ? 'var(--mint)' : 'var(--sky)';
  if (d.kind === 'link') {
    return `<div class="ds" data-id="${d.id}" style="--c:var(--lav)">
      <div class="acts"><button class="ghost sm" data-mv="${d.id}" title="ย้ายไปโฟลเดอร์…">${IC.folder}</button><button class="ghost sm" data-ren="${d.id}" title="แก้ชื่อ">${IC.edit}</button><button class="ghost sm danger" data-del="${d.id}" title="ย้ายไปถังขยะ">${IC.trash}</button></div>
      <div class="t"><div class="ico">${IC.link}</div><div style="min-width:0;padding-right:84px"><div class="name">${esc(d.name)}</div><div class="path" title="${esc(d.path)}">${esc(d.path)}</div></div></div>
      ${m.description ? `<div class="tiny muted" style="margin:-2px 0 8px">${esc(m.description)}</div>` : ''}
      <div class="chips">${m.builtin ? '<span class="chip" style="color:var(--butter);border-color:#f6e3a155">ข้อมูลพื้นฐาน</span>' : ''}<span class="chip">${esc(m.type_label || d.format)}</span>${m.view ? '<span class="chip">ดูอย่างเดียว</span>' : '<span class="chip ok">ดาวน์โหลดได้</span>'}${m.secret_id ? `<span class="chip">${IC.lock}โทเคน</span>` : ''}</div>
      <div class="foot"><span class="status-dot"></span>ลิงก์<span class="spacer"></span>#${d.id}</div></div>`;
  }
  const icon = d.role === 'map' ? 'map' : d.kind === 'vector' ? 'vector' : 'raster';
  const vt = d.kind === 'raster' ? (d.value_type_confirmed ? `<span class="chip">${esc(VT_SHORT[d.value_type] || d.value_type)}</span>` : `<span class="chip warn">${esc(VT_SHORT[d.value_type] || '?')} · ยังไม่ยืนยัน</span>`) : '';
  const res = d.kind === 'raster' ? esc((m.res_label || '').split(' (')[0]) : `${fmt(m.features, 0)} feature`;
  return `<div class="ds" data-id="${d.id}" style="--c:${c}">
    <div class="acts"><button class="ghost sm" data-mv="${d.id}" title="ย้ายไปโฟลเดอร์…">${IC.folder}</button><button class="ghost sm" data-ren="${d.id}" title="แก้ชื่อ">${IC.edit}</button><button class="ghost sm danger" data-del="${d.id}" title="ย้ายไปถังขยะ">${IC.trash}</button></div>
    <div class="t"><div class="ico">${IC[icon]}</div><div style="min-width:0;padding-right:84px"><div class="name">${esc(d.name)}</div><div class="path" title="${esc(d.path)}">${esc(d.path)}</div></div></div>
    <div class="chips"><span class="chip ${d.kind}">${d.kind}</span>${vt}<span class="chip">${res}</span>${d.copied ? '<span class="chip">ก๊อปแล้ว</span>' : ''}</div>
    <div class="foot"><span class="status-dot ${d.status}"></span>${d.status === 'ok' ? 'พร้อมใช้' : d.status === 'missing' ? 'ไม่พบไฟล์' : 'ไฟล์เปลี่ยน'}<span class="spacer"></span>${bytes(m.file_bytes)} · #${d.id}</div></div>`;
}

// ================= หน้าชุดข้อมูล =================
async function pageDataset(id) {
  const [d, all, aois, fr] = await Promise.all([api(ENGINE + '/api/datasets/' + id), api(ENGINE + '/api/datasets'), api(ENGINE + '/api/aoi'), api(ENGINE + '/api/folders').catch(() => ({ folders: [] }))]);
  const m = d.meta, isR = d.kind === 'raster', st = d.stats || {}, g = m.value_type_guess || {};
  const v = $('#view');
  const kv = rows => `<table class="kv">${rows.filter(Boolean).map(([k, x]) => `<tr><td>${k}</td><td>${x}</td></tr>`).join('')}</table>`;
  const fileRow = ['ไฟล์', `<div class="mono">${esc(d.path)}</div><button class="sm" style="margin-top:6px" onclick='openFolder(${attr(d.path)})'>${IC.folder}เปิดโฟลเดอร์</button>`];
  const info = isR ? [fileRow,
    d.read_path && d.read_path !== d.path ? ['อ่านจริงจาก', `<span class="mono">${esc(d.read_path)}</span>`] : null,
    d.copied ? ['ต้นฉบับก่อนก๊อป', `<span class="mono">${esc(d.source_path)}</span>`] : null,
    ['รูปแบบ', `${esc(m.driver)} · ${esc(d.format)}${m.vrt ? ` · ${fmt(m.vrt.sources, 0)} ไฟล์ย่อย` : ''}`],
    ['CRS', esc(m.crs_name)],
    ['ความละเอียด', `<b>${esc(m.res_label)}</b><div class="tiny muted">ค่าในไฟล์ ${m.res.map(x => x.toPrecision(10)).join(' × ')} ${m.geographic ? '°' : 'ม.'} · ค่าแม่นยำ ${esc(m.res_exact)} ${m.res_unit === 'arcsec' ? 'ฟิลิปดา' : 'ม.'}</div>`],
    ['ขนาด', `${fmt(m.width, 0)} × ${fmt(m.height, 0)} (${pxLabel(m.pixels)}) · ${m.count} แบนด์ · ${esc(m.dtypes.join(', '))}`],
    ['nodata ในไฟล์', esc(m.nodata ?? 'ไม่มี')],
    ['ขอบเขต (WGS84)', m.bounds_wgs84 ? m.bounds_wgs84.map(x => x.toFixed(4)).join(', ') : '–'],
    ['มุมเริ่มกริด', `<span class="mono">${m.transform[2]}, ${m.transform[5]}</span>`],
    ['กลุ่มกริด', `<span class="mono">${esc(m.grid_family)}</span>`],
    ['overview', m.overviews.length ? m.overviews.join(', ') : 'ไม่มี' + (d.preview_path ? ' (แอปทำสำเนาพรีวิวให้แล้ว)' : '')],
    ['ขนาดไฟล์', bytes(m.file_bytes)],
    st.valid != null ? ['สถิติ', `มีค่า ${fmt(st.valid, 0)} · nodata ${fmt(st.nodata, 0)}<br>min ${fmt(st.min, 4)} · max ${fmt(st.max, 4)} · เฉลี่ย ${fmt(st.mean, 4)}<br><b>ผลรวม ${fmt(st.sum, 2)}</b>`]
      : d.role !== 'map' ? ['สถิติ', '<span class="muted">กำลังคำนวณ (ดูแท็บงาน)</span>'] : null,
  ] : [fileRow, ['ชั้น (layer)', esc(d.layer || '–')], ['รูปแบบ', esc(m.driver)], ['CRS', esc(m.crs_name)],
    ['ชนิดเรขาคณิต', esc(m.geometry_type)], ['จำนวน feature', fmt(m.features, 0)],
    ['ขอบเขต (WGS84)', m.bounds_wgs84 ? m.bounds_wgs84.map(x => x.toFixed(4)).join(', ') : '–'], ['ขนาดไฟล์', bytes(m.file_bytes)],
    ['ฟิลด์', m.fields.map(f => `${esc(f.name)} <span class="tiny muted">${esc(f.type)}</span>`).join(' · ')],
    d.format === 'shp' ? ['การเข้ารหัสข้อความ', `<div class="row"><select id="encSel">${Object.entries(d.encodings || {}).map(([k, v]) => `<option value="${k}" ${(m.encoding_manual ? m.encoding : '') === k ? 'selected' : ''}>${esc(v)}${!k && m.encoding_auto ? ' → ' + esc(m.encoding_auto) : ''}</option>`).join('')}</select></div>
      <div class="tiny muted">ภาษาไทยเพี้ยน (เช่น Í.à©ÅÔÁ) → เลือก TIS-620 · ถ้าเป็น "?????" แปลว่าเสียมาจากไฟล์ต้นทาง เลือกอะไรก็กู้ไม่ได้</div>`] : null];
  const rasters = all.filter(x => x.kind === 'raster');
  const aoiOpts = `<option value="">ทั้งขอบเขตข้อมูล</option>` + aoiOptions(aois);
  v.innerHTML = head(`${ROLE[d.role]} · ${d.kind}`, `${esc(d.name)} <span class="edit" id="ren" title="แก้ชื่อ">${IC.edit}</span>`,
    `<span class="chip ${d.kind}">${d.kind}</span> ${d.role !== 'input' ? `<span class="chip ${d.role}">${ROLE[d.role]}</span>` : ''} ${isR ? `<span class="chip">${esc((m.res_label || '').split(' (')[0])}</span>` : ''}`,
    `<button id="toViewer">${IC.layers}เปิดในแผนที่ซ้อนชั้น</button><a class="btn" href="#/report?ds=${d.id}">${IC.pdf}ออกแบบรายงาน</a><a class="btn" href="#/">← คลังข้อมูล</a>`)
    + (d.status !== 'ok' ? `<div class="card" style="border-color:rgba(255,154,168,.3)"><div class="card-head"><h2><span class="dot" style="background:var(--coral);color:var(--coral)"></span>${d.status === 'missing' ? 'ไม่พบไฟล์ที่ path นี้' : 'ไฟล์เปลี่ยนไปจากตอนนำเข้า'}</h2></div>
      <p class="small muted">ไฟล์ถูกย้าย/เปลี่ยนชื่อ? ชี้ไปที่ไฟล์ใหม่ได้ (relink) — การตั้งค่าและประวัติยังอยู่</p>
      <div class="row"><input type="text" id="rlPath" placeholder="path ใหม่" style="flex:1"><button id="rlBrowse">${IC.folder}เลือก…</button><button id="rlGo" class="primary">${IC.link}ชี้ไฟล์ใหม่</button></div></div>` : '')
    + (m.warnings || []).map(w => `<div class="note warn">${esc(w)}</div>`).join('')
    + (d.source_changed?.length ? `<div class="note warn">ต้นทางเปลี่ยนหลังสร้างผลนี้: ${d.source_changed.map(esc).join(' · ')} — ควร<a href="#/jobs"> รันซ้ำ</a></div>` : '')
    + `<div class="cols"><div>
      ${isR ? `<div class="card" id="vtPanel">
        <div class="card-head"><h2><span class="dot"></span>ประเภทค่า</h2>${d.value_type_confirmed ? '<span class="chip ok">ยืนยันแล้ว</span>' : '<span class="chip warn">ยังไม่ยืนยัน — ต้องยืนยันก่อนคำนวณ</span>'}</div>
        <div class="vt-cards">${VT_CARDS.map(c => `<label class="vt-card ${c.k === d.value_type ? 'on' : ''}" style="--c:${c.c}"><input type="radio" name="vt" value="${c.k}" ${c.k === d.value_type ? 'checked' : ''}>
          <b>${c.t}</b><span class="ex">${c.ex}</span><span class="rule">${c.rule}</span>${g.value_type === c.k ? '<em>แอปเดา</em>' : ''}</label>`).join('')}</div>
        <div class="vt-help">วิธีแยกเร็ว ๆ: ถ้า<b>รวม 4 พิกเซลเป็น 1 พิกเซล</b> ค่าควร… <span>“บวกกัน”</span> → จำนวนนับ · <span>“เฉลี่ย”</span> → ต่อเนื่อง · <span>“เอาค่าที่มีมากที่สุด”</span> → ชั้น</div>
        ${g.reason ? `<div class="tiny muted">แอปเดา: ${esc(VT[g.value_type])} — ${esc(g.reason)}</div>` : ''}
        <div class="row" style="margin-top:10px"><button id="vtOk" class="primary">${IC.check}ยืนยันประเภทค่า</button></div>
        <h3>nodata และค่าที่ไม่นับ <span class="tiny muted">(มีผลกับการคำนวณ)</span></h3>
        <div class="grid-form">
          <label class="field"><span>นับ nodata เป็นค่า</span><input type="text" id="ndas" value="${d.nodata_as ?? ''}" placeholder="ว่าง = ไม่มีข้อมูล"></label>
          <label class="field"><span>ค่าที่ไม่นับ (ถือเป็นไม่มีข้อมูล)</span><input type="text" id="exv" value="${(d.exclude_values || []).join(', ')}" placeholder="เช่น 0 หรือ 0, 255"></label>
        </div>
        <div class="row" style="margin-top:8px"><button id="ndOk">บันทึก</button><span class="tiny muted">ซ่อนค่าแค่บนแผนที่ (ไม่กระทบการคำนวณ) ใช้ "ซ่อนค่า" ในสัญลักษณ์ด้านล่าง</span></div>
        ${m.nodata === 0 && d.value_type === 'class' && d.role === 'input' ? '<div class="note warn small">ไฟล์นี้ใช้ 0 เป็น nodata — ถ้า 0 แปลว่า "ไม่มีเหตุการณ์" (เช่น ไม่เคยท่วม) ให้ใส่ 0 ในช่อง "นับ nodata เป็นค่า"</div>' : ''}
        ${m.count > 1 ? `<h3>แบนด์ที่ใช้</h3><select id="band">${Array.from({ length: m.count }, (_, i) => `<option ${i + 1 == d.band ? 'selected' : ''}>${i + 1}</option>`).join('')}</select>` : ''}
      </div>` : ''}
      ${isR && d.role !== 'map' ? '<div class="card" id="symPanel"></div>' : ''}
      ${d.role === 'map' && isR ? '<div class="card" id="mapPal"></div><div class="card" id="bivStats"></div>' : ''}
      ${d.role === 'map' && !isR && d.lineage?.params?.x ? zonalLegend(d) : ''}
      ${isR ? `<div class="card"><div class="card-head"><h2><span class="dot" style="background:var(--peach);color:var(--peach)"></span>ปรับความละเอียด / ตัดพื้นที่</h2></div>
        <div class="grid-form">
          <label class="field full"><span>ความละเอียดใหม่</span><select id="rsRes"></select></label>
          <label class="field"><span>พื้นที่ศึกษา</span><select id="rsAoi">${aoiOpts}</select></label>
          <label class="field"><span>กติกาตัดพื้นที่</span><select id="rsRule"><option value="center">ศูนย์กลางพิกเซล</option><option value="touch">แตะ</option></select></label>
          ${d.value_type === 'class' ? '<label class="field"><span>เสมอกันใน majority</span><select id="rsTie"><option value="high">ค่ามากกว่า</option><option value="low">ค่าน้อยกว่า</option></select></label>' : ''}
        </div>
        <div class="tiny muted" style="margin:8px 0">กติกาตามประเภทค่า: ${esc(VT_RULE[d.value_type] || '')} · ผลลง workspace/derived/ โฟลเดอร์ใหม่ทุกครั้ง</div>
        <button id="rsRun" class="primary">${IC.play}สร้าง</button></div>
        <div class="card"><div class="card-head"><h2><span class="dot" style="background:var(--mint);color:var(--mint)"></span>ทำเป็นกริดเวกเตอร์</h2></div>
        <p class="small muted" style="margin-top:0">ช่องสี่เหลี่ยม + ค่า (GeoPackage) สำหรับวิชวลไลซ์ — ช่องว่าง/ค่า 0 ถูกตัดทิ้ง · สูงสุด 2 ล้านช่อง</p>
        <div class="grid-form">
          <label class="field"><span>ขนาดช่อง</span><select id="vgRes"></select></label>
          <label class="field"><span>พื้นที่ศึกษา</span><select id="vgAoi">${aoiOpts}</select></label>
          <div class="field full"><span>ใส่ค่าจากชุดอื่นด้วย (กริดเดียวกัน)</span><div class="checklist" id="vgMore">${rasters.filter(x => x.id !== d.id && x.meta.grid_family === m.grid_family && x.value_type_confirmed).map(x => `<label><input type="checkbox" value="${x.id}"><span>#${x.id} ${esc(x.name)} <span class="tiny muted">${esc(VT_SHORT[x.value_type] || '')} · ${esc((x.meta.res_label || '').split(' (')[0])}</span></span></label>`).join('') || '<div class="tiny muted" style="padding:6px 8px">ไม่มีชุดอื่นในกริดเดียวกัน</div>'}</div></div>
        </div>
        <button id="vgRun" class="mint" style="margin-top:10px">${IC.grid}สร้างกริด</button></div>
        ${d.role !== 'map' ? hexCard(d, all, aoiOpts) : ''}` : `
        <div class="card"><div class="card-head"><h2><span class="dot" style="background:var(--sky);color:var(--sky)"></span>แปลงเป็นราสเตอร์</h2></div>
        <div class="grid-form">
          <div class="field full"><span>กริดผลลัพธ์</span><div class="seg" id="rzGrid"><button data-g="own">กำหนดเอง (พิกัด + ความละเอียด)</button><button data-g="ref" ${rasters.length ? '' : 'disabled title="ยังไม่มี raster ในคลัง"'}>จับกริดกับ raster ในคลัง</button></div></div>
          <div class="field full rzRef"><span>raster อ้างอิง — พิกเซลจะตรงกับชุดนี้ (ใช้ไบแวเรียตต่อได้ทันที)</span><select id="rzRef">${rasters.map(x => `<option value="${x.id}">#${x.id} ${esc(x.name)} · ${esc((x.meta.res_label || '').split(' (')[0])}</option>`).join('')}</select></div>
          <label class="field rzRef"><span>ความละเอียด</span><select id="rzRes"></select></label>
          <label class="field rzOwn"><span>ระบบพิกัด</span><select id="rzCrs"><option value="">ของไฟล์นี้ (${esc((m.crs_name || '').split(' · ')[0])})</option><option value="EPSG:32647">UTM โซน 47N (EPSG:32647)</option><option value="EPSG:32648">UTM โซน 48N (EPSG:32648)</option><option value="EPSG:4326">WGS 84 องศา (EPSG:4326)</option></select></label>
          <label class="field rzOwn"><span>ความละเอียด <b id="rzUnit"></b></span><select id="rzResSel"></select><input type="number" id="rzResOwn" class="hide" min="0" step="any" value="30" placeholder="พิมพ์ความละเอียด" style="margin-top:6px"></label>
          <div class="field full"><span>พื้นที่ผลลัพธ์</span><select id="rzExt"></select></div>
          <label class="field"><span>วิธีแปลง</span><select id="rzMode"><option value="presence">มี / ไม่มี (1 / 0)</option><option value="attribute">ค่าจากฟิลด์</option><option value="majority">ค่าจากฟิลด์ — ที่กินพื้นที่มากสุดในพิกเซล</option><option value="fraction">สัดส่วนพื้นที่ที่ทับ (0–1)</option></select></label>
          <label class="field rzF"><span>ฟิลด์ที่ใช้เป็นค่า</span><select id="rzField"><option value="">— เลือกฟิลด์ —</option>${m.fields.map(f => { const num = /int|float|double|real/i.test(f.type); return `<option value="${esc(f.name)}" data-num="${num ? 1 : 0}">${esc(f.name)} · ${num ? 'ตัวเลข' : 'ข้อความ'}</option>`; }).join('')}<option value="__index__">ลำดับ feature (1, 2, 3…)</option></select></label>
          <label class="field"><span>พิกเซลไหนนับ</span><select id="rzRule"><option value="center">จุดกึ่งกลางพิกเซลอยู่ในรูป</option><option value="touch">แตะรูปนิดเดียวก็นับ (all touched)</option></select></label>
        </div>
        <div class="note info small" id="rzHelp" style="margin:8px 0"></div>
        <button id="rzRun" class="primary">${IC.raster}แปลง</button>
        ${isHex(d) ? '<div class="tiny muted" style="margin-top:8px">ชุดหกเหลี่ยม → ราสเตอร์: เลือก "ค่าจากฟิลด์" แล้วเลือกคอลัมน์ค่า</div>' : ''}</div>
        ${isHex(d) ? `<div class="card"><div class="card-head"><h2><span class="dot" style="background:var(--lav);color:var(--lav)"></span>หกเหลี่ยม</h2></div>
          <table class="kv"><tr><td>ขนาด</td><td>${fmt(m.hex.d_km, 3)} กม. · ${fmt(m.hex.area_km2, 4)} ตร.กม./ช่อง</td></tr><tr><td>พิกัดฉาย</td><td>${esc(m.hex.crs_label || m.hex.crs)}</td></tr>
          ${(m.hex.fields || []).map(f => `<tr><td>${esc(f.name)}</td><td>${Object.entries(f.columns || {}).map(([c, x]) => `<code>${esc(c)}</code> <span class="tiny muted">${esc(x)}</span>`).join('<br>')}<div class="tiny muted">${esc(f.rule || '')}</div></td></tr>`).join('')}</table>
          ${d.role !== 'map' ? `<a class="btn" style="margin-top:10px" href="#/biv?hex=${d.id}">${IC.grid}ใช้ทำไบแวเรียตหกเหลี่ยม</a>` : ''}</div>` : (d.role !== 'map' && /Polygon|Line|Point/i.test(m.geometry_type || '') ? hexCard(d, all, aoiOpts) : '')}
        ${/Polygon/.test(m.geometry_type || '') ? `<div class="card"><div class="card-head"><h2><span class="dot" style="background:var(--lav)"></span>ใช้เป็นพื้นที่ศึกษา</h2></div><p class="small muted" style="margin-top:0">เลือกจังหวัด / อำเภอ / ตำบล จากชั้นนี้</p><a class="btn" href="#/aoi?ds=${d.id}">${IC.target}เลือกพื้นที่จากชั้นนี้</a></div>` : ''}`}
      <div class="card"><div class="card-head"><h2><span class="dot" style="background:var(--muted);color:var(--muted)"></span>รายละเอียด</h2></div>${kv(info)}
      ${isR && st.valid != null && d.role !== 'map' ? '<h3>ฮิสโทแกรม (ค่าสุ่ม)</h3><canvas class="hist" id="hist"></canvas><div class="tiny muted" id="histNote"></div>' : ''}</div>
      <div class="card" id="profCard"><div class="card-head"><h2><span class="dot" style="background:var(--butter);color:var(--butter)"></span>ประวัติชุดข้อมูล</h2>
        <div class="row">${d.lineage ? `<button class="sm" id="rerun">${IC.refresh}รันซ้ำ</button><button class="sm" onclick='openFolder(${attr(d.out_dir)})'>${IC.folder}โฟลเดอร์ผล</button>` : ''}
          <a class="btn sm ghost" href="${ENGINE}/api/datasets/${d.id}/profile.md">${IC.download}.md</a></div></div>
        <div id="profBody" class="small muted">กำลังโหลด…</div>
        ${d.lineage ? `<details class="tiny" style="margin-top:10px"><summary>lineage.json (ข้อมูลดิบ)</summary><pre class="log">${esc(JSON.stringify(d.lineage, null, 1))}</pre></details>` : ''}</div>
    </div>
    <div class="card sticky">
      <div class="mapbar">
        <div class="seg" id="bm"><button data-k="gh">ดาวเทียม</button><button data-k="osm">แผนที่</button><button data-k="none">ไม่มี</button></div>
        <label class="row small" title="ความทึบของชั้นข้อมูล">ข้อมูล <input type="range" id="op" min="0" max="1" step="0.05" value="0.85"></label>
        ${isR ? `<label class="row small" title="ตัดการแสดงผลตามรูปพื้นที่ศึกษา — แสดงผลเท่านั้น ไฟล์ไม่เปลี่ยน">แสดง <select id="clipSel" class="sm"><option value="">ทั้งกรอบข้อมูล</option>${aoiOptions(aois, { text: a => esc(a.name) })}</select></label>` : ''}
        <span class="tiny muted" id="mapNote"></span>
      </div>
      <div id="map" class="mapbox"></div>
      <div id="pt" class="pt small muted">คลิกบนแผนที่เพื่อดูค่า</div>
    </div></div>`;

  $('#ren').onclick = async () => { const n = await ui.prompt('แก้ชื่อชุดข้อมูล', d.name); if (n) { await api(ENGINE + '/api/datasets/' + id, { method: 'PATCH', json: { name: n } }); route(); } };
  $('#toViewer').onclick = () => { viewerAdd([vLayerFromDs(d)]); location.hash = '#/viewer'; };
  if ($('#encSel')) $('#encSel').onchange = async () => { await api(ENGINE + '/api/datasets/' + id, { method: 'PATCH', json: { encoding: $('#encSel').value } }); toast('เปลี่ยนการเข้ารหัสแล้ว'); route(); };
  if ($('#rlGo')) {
    $('#rlBrowse').onclick = async () => { const p = await browseOne(); if (p) $('#rlPath').value = p; };
    $('#rlGo').onclick = async () => {
      try { const r = await api(`${ENGINE}/api/datasets/${id}/relink`, { json: { path: $('#rlPath').value } }); toast('ชี้ไฟล์ใหม่แล้ว' + (r.warnings.length ? ' — ' + r.warnings.join(' · ') : '')); route(); }
      catch (e) { toast(e.message, true); }
    };
  }
  if ($('#rerun')) $('#rerun').onclick = async () => {
    if (!await ui.confirm('รันซ้ำ?', '<p>ใช้ค่าที่ตั้งเดิมทั้งหมด ผลลงโฟลเดอร์ใหม่ (ไม่ทับของเดิม)</p>', 'รันซ้ำ')) return;
    try { const r = await api(`${ENGINE}/api/jobs/${d.job_id}/rerun`, { json: {} }); toast(`เริ่มงาน #${r.job}`); } catch (e) { toast(e.message, true); }
  };
  if (isR) {
    $$('.vt-card input').forEach(r => r.onchange = () => $$('.vt-card').forEach(c => c.classList.toggle('on', c.querySelector('input').checked)));
    $('#vtOk').onclick = async () => {
      const vt = $('.vt-card input:checked').value;
      await api(ENGINE + '/api/datasets/' + id, { method: 'PATCH', json: { value_type: vt } });
      if (vt !== d.value_type && d.style) await api(`${ENGINE}/api/datasets/${id}/style`, { json: { style: null } });   // ประเภทเปลี่ยน → สไตล์เริ่มต้นใหม่
      toast('บันทึกประเภทค่าแล้ว'); route();
    };
    $('#ndOk').onclick = async () => {
      try { await api(ENGINE + '/api/datasets/' + id, { method: 'PATCH', json: { nodata_as: $('#ndas').value.trim(), exclude_values: $('#exv').value } }); toast('บันทึกแล้ว'); route(); }
      catch (e) { toast(e.message, true); }
    };
    if ($('#band')) $('#band').onchange = async () => { await api(ENGINE + '/api/datasets/' + id, { method: 'PATCH', json: { band: +$('#band').value } }); route(); };
    const opts = d.res_options || [];
    const optHtml = (list, mark) => list.map(o => `<option value="${o.value}">${esc(o.label)} · ${pxLabel(o.px)}${o.is_source.includes(d.id) ? ' · เท่าเดิม' : mark && o.px > m.pixels ? ' · ละเอียดขึ้น' : ''}</option>`).join('');
    $('#rsRes').innerHTML = optHtml(opts, true);
    const coarser = opts.find(o => o.px < m.pixels);
    $('#rsRes').value = coarser ? coarser.value : opts[0]?.value;
    const vgo = opts.filter(o => o.px <= m.pixels);
    $('#vgRes').innerHTML = optHtml(vgo, false);
    $('#vgRes').value = (vgo.find(o => o.px < 2e6) || vgo.at(-1))?.value;
    $('#rsRun').onclick = () => runJob('resample', { dataset_id: id, target_res: $('#rsRes').value, tie: $('#rsTie')?.value || 'high', aoi_id: +$('#rsAoi').value || null, aoi_rule: $('#rsRule').value });
    $('#vgRun').onclick = () => runJob('vgrid', { dataset_ids: [id, ...$$('#vgMore input:checked').map(o => +o.value)], target_res: $('#vgRes').value, aoi_id: +$('#vgAoi').value || null });
    if ($('#hxRun')) hexCardBind(d);
    if (st.valid != null && d.role !== 'map') drawHist(id);
    if (d.role === 'map') { mapPalette(d); if (isR) bivStatsCard(d); }
  } else {
    const loadRz = async () => {
      try {
        const r = await api(ENGINE + '/api/res-options?ids=' + $('#rzRef').value);
        $('#rzRes').innerHTML = r.options.map(o => `<option value="${o.value}">${esc(o.label.split(' (')[0])} · ${fmt(o.px / 1e6, 1)} ล้าน${o.is_source.length ? ' · = กริดอ้างอิง' : ''}</option>`).join('');
        $('#rzRes').value = r.options.find(o => o.is_source.length)?.value;
      } catch (e) { toast(e.message, true); }
    };
    // กริด: กำหนดเอง (ไม่ต้องมี raster) หรือจับกับ raster ในคลัง · ขอบเขตผลลัพธ์ = ของ vector นี้ (หรือพื้นที่ศึกษา) เสมอ
    let rzGrid = 'own', rzExtTouched = false;
    // ความละเอียด (กริดกำหนดเอง): ค่าสำเร็จรูปตามหน่วย + "พิมพ์เอง…"
    const RZ_PRESET = { geo: [[1, '1″ (≈ 30 ม.)'], [3, '3″ (≈ 90 ม.)'], [7.5, '7.5″ (≈ 250 ม.)'], [15, '15″ (≈ 500 ม.)'], [30, '30″ (≈ 1 กม.)']],
      m: [[10, '10 ม.'], [30, '30 ม.'], [100, '100 ม.'], [250, '250 ม.'], [500, '500 ม.'], [1000, '1 กม.']] };
    const rzGeo = () => $('#rzCrs').value === 'EPSG:4326' || (!$('#rzCrs').value && m.geographic);
    const rzFillRes = () => {
      const ps = RZ_PRESET[rzGeo() ? 'geo' : 'm'];
      $('#rzResSel').innerHTML = ps.map(([v, l]) => `<option value="${v}">${l}</option>`).join('') + '<option value="custom">พิมพ์เอง…</option>';
      $('#rzResSel').value = rzGeo() ? 1 : 30;
      $('#rzResOwn').value = $('#rzResSel').value;
      $('#rzResOwn').classList.add('hide');
    };
    $('#rzResSel').onchange = () => {
      const c = $('#rzResSel').value === 'custom';
      $('#rzResOwn').classList.toggle('hide', !c);
      if (c) $('#rzResOwn').focus(); else $('#rzResOwn').value = $('#rzResSel').value;
    };
    // ขอบเขต: จับกริดกับ raster → ค่าเริ่มต้นครอบทั้งผืนเท่าชุดนั้น (นอกรูป = 0 ไบแวเรียตได้ทั้งพื้นที่) จนกว่าผู้ใช้เลือกเอง
    const rzExtDefault = () => { if (!rzExtTouched) $('#rzExt').value = rzGrid === 'ref' ? $('#rzRef').value : ''; };
    $('#rzExt').onchange = () => {
      rzExtTouched = true;
      rzSync();
    };
    const rzSync = () => {
      $$('#rzGrid button').forEach(b => b.classList.toggle('on', b.dataset.g === rzGrid));
      $$('.rzRef').forEach(e => e.classList.toggle('hide', rzGrid !== 'ref'));
      $$('.rzOwn').forEach(e => e.classList.toggle('hide', rzGrid !== 'own'));
      $('#rzUnit').textContent = rzGeo() ? '(ฟิลิปดา ″ · 1″ ≈ 30 ม.)' : '(เมตร)';
      const md = $('#rzMode').value, fo = $('#rzField').selectedOptions[0];
      $('.rzF').classList.toggle('hide', md === 'presence' || md === 'fraction');
      const fld = fo && fo.value ? (fo.value === '__index__' ? 'ลำดับ feature' : `ฟิลด์ "${fo.value}"`) : 'ฟิลด์ที่เลือก';
      const txt = fo && fo.value && fo.value !== '__index__' && fo.dataset.num === '0';
      $('#rzHelp').innerHTML = ({
        presence: 'พิกเซลที่ทับรูป = 1 ไม่ทับ = 0 (เช่น มีอาคาร / ไม่มีอาคาร)',
        attribute: `พิกเซลได้ค่าของ ${fld}${txt ? ' — <b>ข้อความ</b> จะแปลงเป็นรหัส 1, 2, 3… พร้อมไฟล์ตารางรหัส (_codes.csv)' : ''} · รูปที่ซ้อนกัน ตัวหลังทับตัวก่อน`,
        majority: `พิกเซลได้ค่าของ ${fld}ที่กินพื้นที่มากที่สุดในพิกเซลนั้น (แตกพิกเซลละเอียดขึ้น 10 เท่าเพื่อนับ — ช้ากว่า)${txt ? ' · ข้อความแปลงเป็นรหัส + _codes.csv' : ''}`,
        fraction: 'สัดส่วนพื้นที่พิกเซลที่ถูกรูปทับ 0–1 (เช่น ร้อยละพื้นที่อาคาร) · แตกพิกเซลละเอียดขึ้น 10 เท่าเพื่อนับ',
      })[md] + '<br><span class="tiny">' + ($('#rzExt').value.startsWith('aoi:')
        ? 'พื้นที่ผลลัพธ์ = พื้นที่ศึกษาที่เลือก — ในพื้นที่นอกรูปเวกเตอร์ได้ 0 · นอกพื้นที่ (เช่น ทะเล เพื่อนบ้าน) = ไม่มีข้อมูล'
        : $('#rzExt').value
        ? 'พื้นที่ผลลัพธ์ = ทั้งผืนของ raster ที่เลือก — นอกรูปเวกเตอร์ได้ 0 (ไบแวเรียตกับชุดนั้นได้ครบทั้งพื้นที่)'
        : 'พื้นที่ผลลัพธ์ = กรอบของเวกเตอร์ชุดนี้ — ถ้าจะไบแวเรียตกับข้อมูลทั้งประเทศ (เช่น ประชากร) ให้เลือกพื้นที่ศึกษา "ประเทศไทย" หรือ raster ชุดนั้น ไม่งั้นแผนที่จะได้แค่ส่วนที่ทับกัน') + '</span>';
    };
    $$('#rzGrid button').forEach(b => b.onclick = () => { if (b.disabled) return; rzGrid = b.dataset.g; if (rzGrid === 'ref' && !$('#rzRes').options.length) loadRz(); rzExtDefault(); rzSync(); });
    $('#rzRef').onchange = () => { loadRz(); rzExtDefault(); rzSync(); };
    $('#rzCrs').onchange = () => { rzFillRes(); rzSync(); };
    $('#rzMode').onchange = rzSync;
    $('#rzField').onchange = () => { if ($('#rzField').value && $('#rzMode').value === 'presence') $('#rzMode').value = 'attribute'; rzSync(); };
    const rasOpt = tail => x => `<option value="${x.id}">#${x.id} ${esc(x.name)} · ${tail(x)}</option>`;
    dsPicker($('#rzRef'), rasters, fr.folders || [], rasOpt(x => esc((x.meta.res_label || '').split(' (')[0])), null);
    // ขอบเขตผลลัพธ์: กรอบเวกเตอร์ · หมวดพื้นที่ศึกษา (พื้นฐานขึ้นก่อน) · หมวด raster ในคลัง
    dsPicker($('#rzExt'), rasters, fr.folders || [], rasOpt(x => esc((x.meta.res_label || '').split(' (')[0])), 'กรอบของชุดนี้ (bbox ของเวกเตอร์)',
      aoiOptions(aois, { val: a => 'aoi:' + a.id }), 'raster ในคลัง — ครอบทั้งผืนเท่ากับชุดนี้');
    rzFillRes();
    rzSync();
    if ($('#hxRun')) hexCardBind(d);
    $('#rzRun').onclick = () => {
      const md = $('#rzMode').value;
      if ((md === 'attribute' || md === 'majority') && !$('#rzField').value) return toast('เลือกฟิลด์ที่จะใช้เป็นค่าก่อน', true);
      const g = rzGrid === 'ref' ? { grid: 'ref', ref_dataset_id: +$('#rzRef').value, target_res: $('#rzRes').value } : { grid: 'own', crs: $('#rzCrs').value || null, target_res: $('#rzResOwn').value };
      if (!(+g.target_res > 0) && !String(g.target_res).includes('/')) return toast('ใส่ความละเอียด', true);
      // ช่องเดียว: พื้นที่ศึกษา = ขอบเขต + ตัดตามรูป (เดิมสองช่องทำหน้าที่ซ้อนกัน) · raster = ครอบทั้งผืนชุดนั้น · ว่าง = กรอบเวกเตอร์
      const ev = $('#rzExt').value, ext = ev.startsWith('aoi:') ? { extent_aoi_id: +ev.slice(4), aoi_id: +ev.slice(4) } : { extent_dataset_id: +ev || null, aoi_id: null };
      runJob('rasterize', { dataset_id: id, ...g, ...ext, mode: md, field: md === 'presence' || md === 'fraction' ? null : $('#rzField').value, rule: $('#rzRule').value });
    };
  }
  initMap(d);
  if ($('#symPanel')) symPanel(d);
  profileCard(d);
}

// ประวัติชุดข้อมูล: โน้ต (ผู้ใช้ / ผู้ช่วย AI) · ไฟล์อะไร · มาจากไหน · สร้างโดยงานอะไร (ชุดต้นทาง + ค่าที่ตั้ง) · ชุดที่ทำต่อ
// สถิติความสัมพันธ์ของแผนที่ไบแวเรียต (ค่าชุดเดียวกับที่แผนที่ใช้) — คิดครั้งเดียว เก็บแคชในโฟลเดอร์ผลลัพธ์
async function bivStatsCard(d, force = false) {
  const el = $('#bivStats');
  if (!el) return;
  const head = `<div class="card-head"><h2><span class="dot" style="background:var(--lav);color:var(--lav)"></span>สถิติความสัมพันธ์</h2>`;
  if (!force && !d._statsAsked) {
    el.innerHTML = head + `<button class="sm" id="bsGo">${IC.pulse}วิเคราะห์</button></div><div class="small muted">ความสัมพันธ์ระหว่างแกน X กับ Y จากค่าจริงทุกพิกเซล (สุ่ม): สหสัมพันธ์, ตารางไขว้, ANOVA / Kruskal–Wallis, การเกาะกลุ่มเชิงพื้นที่ และกราฟ</div>`;
    $('#bsGo').onclick = () => { d._statsAsked = true; bivStatsCard(d); };
    return;
  }
  el.innerHTML = head + '</div><div class="small muted">กำลังสุ่มค่าและคำนวณ… (ไม่เกินราว 1 นาที)</div>';
  let r;
  try { r = await api(`${ENGINE}/api/datasets/${d.id}/bivstats`, { json: { force } }); }
  catch (e) { el.innerHTML = head + `</div><div class="note err">${esc(e.message)}</div>`; return; }
  const c = r.correlation, ct = r.crosstab, a = r.by_x_class, f4 = v => v == null ? '–' : fmt(v, Math.abs(v) < 0.01 && v !== 0 ? 4 : 3);
  const pf = v => v == null ? '–' : v < 1e-4 ? '< 0.0001' : fmt(v, 4);
  const img = n => `${ENGINE}/api/datasets/${d.id}/bivstats/${n}?t=${Date.now()}`;
  el.innerHTML = head + `<button class="sm ghost" id="bsRe" title="สุ่มใหม่ / คิดใหม่">${IC.refresh}</button></div>
    <div class="bs-int">${r.interpretation.map(x => `<div class="small">• <span translate="no">${esc(x)}</span></div>`).join('')}</div>
    <div class="bs-imgs"><img src="${img('scatter.png')}" alt="กราฟกระจาย"><img src="${img('crosstab.png')}" alt="ตารางไขว้"><img src="${img('box.png')}" alt="กล่อง"></div>
    <table class="kv tiny"><tr><td>ตัวอย่าง</td><td>${fmt(r.sample.n, 0)} พิกเซล · ${esc(r.sample.note)} · ${esc(r.resolution.split(' (')[0])}${r.aoi ? ' · ' + esc(r.aoi) : ''}</td></tr>
      <tr><td>Pearson r</td><td>${f4(c.pearson_r)}${c.pearson_ci95 ? ` (95% CI ${f4(c.pearson_ci95[0])} – ${f4(c.pearson_ci95[1])})` : ''}${c.log_pearson_r != null ? ` · บน log1p ${f4(c.log_pearson_r)}` : ''}</td></tr>
      <tr><td>Spearman ρ</td><td>${f4(c.spearman_rho)} · ${esc(c.strength)}</td></tr>
      <tr><td>OLS Y = a + bX</td><td>${c.ols ? `b = ${f4(c.ols.slope)} · R² = ${f4(c.ols.r2)}` : '–'}</td></tr>
      <tr><td>Moran's I (X / Y)</td><td>${f4(r.spatial.moran_x)} / ${f4(r.spatial.moran_y)} · n ประสิทธิผล ~${c.n_effective ? fmt(c.n_effective, 0) : '–'}</td></tr>
      <tr><td>ค่า p</td><td>ปรับการเกาะกลุ่ม ${pf(c.p_adjusted)} <span class="muted">(สูตรปกติ ${pf(c.p_naive)} — เล็กเกินจริง)</span></td></tr>
      <tr><td>ตารางไขว้</td><td>χ² = ${f4(ct.chi2)} (df ${ct.dof ?? '–'}) · Cramér's V = ${f4(ct.cramers_v)}</td></tr>
      <tr><td>Y ตามชั้น X</td><td>ANOVA F = ${f4(a.anova?.F)} · η² = ${f4(a.anova?.eta2)} · Kruskal–Wallis H = ${f4(a.kruskal?.H)} · ε² = ${f4(a.kruskal?.epsilon2)}</td></tr></table>
    ${r.warnings.map(w => `<div class="note warn small" style="margin-top:6px">${esc(w)}</div>`).join('')}
    <div class="row" style="margin-top:8px"><a class="btn sm ghost" href="${img('biv_stats.csv')}" download>${IC.download}CSV</a><a class="btn sm ghost" href="${img('biv_stats.md')}" target="_blank">${IC.download}รายงาน .md</a></div>`;
  $('#bsRe').onclick = () => bivStatsCard(d, true);
}

async function profileCard(d) {
  const el = $('#profBody'); if (!el) return;
  let p; try { p = await api(`${ENGINE}/api/datasets/${d.id}/profile`); } catch (e) { el.textContent = e.message; return; }
  if (!document.body.contains(el)) return;
  const kv = rows => `<table class="kv">${rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td translate="no">${/^https?:\/\//.test(String(v)) ? `<a href="${esc(v)}" target="_blank" rel="noopener">${esc(v)}</a>` : esc(v)}</td></tr>`).join('')}</table>`;
  const dsLink = x => `<a href="#/ds/${x.id}" translate="no">#${x.id} ${esc(x.name)}</a>${x.exists === false ? ' <span class="muted">(ถูกลบแล้ว)</span>' : ''}`;
  const ai = p.notes.ai, mb = p.made_by;
  el.className = 'small';
  el.innerHTML = `
    <div class="prof-note"><div class="row" style="justify-content:space-between"><b>โน้ต</b><button class="sm ghost" id="noteEdit">${IC.edit}${p.notes.user ? 'แก้' : 'เขียนโน้ต'}</button></div>
      <div class="prof-text ${p.notes.user ? '' : 'muted'}" ${p.notes.user ? 'translate="no"' : ''}>${p.notes.user ? esc(p.notes.user) : 'ยังไม่มีโน้ต — บันทึกได้ว่าข้อมูลนี้คืออะไร ใช้ทำอะไร ข้อควรระวัง'}</div></div>
    ${ai ? `<div class="prof-note ai"><div class="row" style="justify-content:space-between"><b>${IC.chat}โน้ตจากผู้ช่วย AI</b><button class="sm ghost danger" id="noteAiDel" title="ลบโน้ตของผู้ช่วย">${IC.trash}</button></div>
      <div class="prof-text" translate="no">${esc(ai.text)}</div><div class="tiny muted">${esc(ai.model || '')} · ${esc(ai.at || '')}</div></div>` : ''}
    <h3>ไฟล์อะไร / รูปแบบสำคัญ</h3>${kv(p.facts)}
    ${p.origin.length ? `<h3>มาจากไหน</h3>${kv(p.origin)}` : ''}
    ${mb ? `<h3>สร้างโดยงาน: ${esc(mb.operation_th)}</h3><div class="tiny muted">${esc(mb.created_at || '')} · แอป v${esc(mb.app_version || '')}</div>
      <div style="margin:6px 0"><b>ชุดต้นทาง:</b> ${mb.parents.map(dsLink).join(' · ') || '—'}</div>${kv(mb.settings)}
      ${Object.keys(mb.summary || {}).length ? `<details class="tiny"><summary>สรุปผล</summary>${kv(Object.entries(mb.summary))}</details>` : ''}` : ''}
    ${p.children.length ? `<h3>ชุดที่ทำต่อจากชุดนี้</h3><div>${p.children.map(c => dsLink(c) + ` <span class="tiny muted">${esc(c.operation_th)}</span>`).join('<br>')}</div>` : ''}`;
  $('#noteEdit').onclick = async () => {
    const t = await ui.open('โน้ตของชุดข้อมูล', `<p class="muted small">เช่น ข้อมูลนี้คืออะไร หน่วยของค่า ใช้ทำอะไร ข้อควรระวัง</p><textarea id="noteTxt" rows="6" style="width:100%">${esc(p.notes.user || '')}</textarea>`,
      [{ label: 'ยกเลิก', cls: 'ghost', value: () => null }, { label: 'บันทึก', cls: 'primary', value: () => $('#noteTxt').value }]);
    if (t === null) return;
    await api(`${ENGINE}/api/datasets/${d.id}/note`, { json: { text: t } }); profileCard(d);
  };
  if ($('#noteAiDel')) $('#noteAiDel').onclick = async () => { await api(`${ENGINE}/api/datasets/${d.id}/note`, { json: { clear_ai: true } }); profileCard(d); };
}

// ================= สัญลักษณ์ (Symbology แบบ QGIS) =================
const RTYPE = { paletted: 'Paletted / Unique values (ค่าเฉพาะ)', pseudocolor: 'Singleband pseudocolor (ไล่สี)', gray: 'Singleband gray (ขาวดำ)' };
const rampCss = (name, inv) => { const s = STATE.ramps[name] || []; const c = inv ? [...s].reverse() : s; return STATE.categorical.includes(name) ? `linear-gradient(90deg,${c.map((x, i) => `${x} ${i / c.length * 100}% ${(i + 1) / c.length * 100}%`).join(',')})` : `linear-gradient(90deg,${c.join(',')})`; };
const vstr = v => v === 'inf' || v === Infinity ? '∞' : v;
const vnum = s => { s = String(s).trim(); return s === '∞' || /^inf/i.test(s) ? 'inf' : parseFloat(s); };

// o.viewer = ใช้ในหน้าแผนที่ซ้อนชั้น: สไตล์เป็นของชั้นในหน้านั้นเท่านั้น (ไม่บันทึกลงชุดข้อมูล)
//   o = { el, viewer: true, style (สไตล์ที่ปรับไว้ หรือ null), onStyle(sty), onReset(), onClose() }
async function symPanel(d, o = {}) {
  const el = o.el || $('#symPanel');
  const r = o.style ? { style: o.style, saved: false } : await api(`${ENGINE}/api/datasets/${d.id}/style`);
  let sty = JSON.parse(JSON.stringify(r.style || { type: 'pseudocolor', stops: [] }));
  let saved = r.saved, pvTimer = null, override = !!o.style;
  if (!o.viewer && d.kind === 'raster' && window._rasterLayer) {   // ความทึบตั้งต้นตามสไตล์ (night light = 100% แบบ QGIS)
    const op0 = sty.opacity ?? .85;
    window._rasterLayer.setOpacity(op0);
    if ($('#op')) $('#op').value = op0;
  }
  const legend = s => o.viewer ? o.onStyle?.(s) : setMapLegend(s);
  const isCount = d.value_type === 'count';
  const items = () => sty.type === 'paletted' ? (sty.entries ||= []) : (sty.stops ||= []);
  // แผนที่ไบแวเรียต: เลือกพาเลท 2 มิติ (nX×nY) ได้ตรงนี้ — รหัส = ชั้นY × nX + ชั้นX + 1 → สีที่ตำแหน่ง รหัส−1 ของพาเลท
  let biv = null;
  if (d.role === 'map') {
    try {
      const L = d.lineage || (await api(`${ENGINE}/api/datasets/${d.id}`)).lineage;
      const bp = L?.params;
      if (bp?.x?.n && bp?.y?.n) {
        biv = { nx: +bp.x.n, ny: +bp.y.n };
        if (!PALS.builtin.length) await loadPals();
      }
    } catch { }
  }
  const preview = () => {
    clearTimeout(pvTimer);
    pvTimer = setTimeout(async () => {
      if (o.viewer) { if (!override) { override = true; draw(); } o.onStyle(sty); return; }
      const t = await api(ENGINE + '/api/style-preview', { json: { dataset_id: d.id, style: sty } });
      window._rasterSt = t.token; window._rasterLayer?.setUrl(rTileUrl(d, t.token));
      window._rasterLayer?.setOpacity(sty.opacity ?? .85);
      setMapLegend(sty);
    }, 250);
  };
  const draw = () => {
    const T = sty.type;
    el.innerHTML = (o.viewer
      ? `<div class="card-head"><h2 style="font-size:15px;min-width:0"><span class="dot" style="background:var(--butter);color:var(--butter)"></span><span class="vname" title="${esc(d.name)}">สัญลักษณ์ · ${esc(d.name)}</span></h2>
        <div class="row">${override ? '<span class="chip ok">ปรับเฉพาะแผนที่นี้</span>' : '<span class="chip">ตามชุดข้อมูล</span>'}<button class="sm ghost" id="sClose" title="ปิด">✕</button></div></div>`
      : `<div class="card-head"><h2><span class="dot" style="background:var(--butter);color:var(--butter)"></span>สัญลักษณ์ <span class="tiny muted th-only">Symbology</span></h2>
      <div class="row">${saved ? '<span class="chip ok">บันทึกแล้ว</span>' : '<span class="chip">ค่าเริ่มต้น</span>'}<a class="btn sm ghost" href="${ENGINE}/api/datasets/${d.id}/style.qml" title="ไฟล์สไตล์สำหรับ QGIS">${IC.download}.qml</a></div></div>`) + `
      <div class="grid-form">
        <label class="field full"><span>Render type</span><select id="sType">${Object.entries(RTYPE).map(([k, t]) => `<option value="${k}" ${k === T ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
        ${isCount && T !== 'paletted' ? `<label class="field full"><span>ค่าที่แสดง</span><select id="sMetric"><option value="density" ${sty.metric === 'density' ? 'selected' : ''}>ความหนาแน่น (ต่อ ตร.กม.) — เทียบได้ทุกความละเอียด</option><option value="value" ${sty.metric !== 'density' ? 'selected' : ''}>ค่าต่อพิกเซล (ค่าดิบ)</option></select></label>` : ''}
        ${T === 'gray' ? `<div class="field full"><span>Color ramp <span class="tiny muted">— เลือกพาเลท = เปลี่ยนเป็นไล่สี (pseudocolor) ใช้ Min/Max เดิม</span></span><div class="ramp-pick"><button type="button" id="rampBtn" class="ramp-btn"><i style="background:linear-gradient(90deg,#000,#fff)"></i><span>ขาวดำ</span>▾</button>
          <div class="ramp-list hide" id="rampList">${Object.keys(STATE.ramps).filter(k => !STATE.categorical.includes(k)).map(k => `<div data-r="${esc(k)}"><i style="background:${rampCss(k)}"></i>${esc(k)}</div>`).join('')}</div></div></div>` : ''}
        ${T !== 'gray' ? `<div class="field full"><span>Color ramp</span><div class="ramp-pick"><button type="button" id="rampBtn" class="ramp-btn"><i style="background:${rampCss(sty.ramp || 'viridis', sty.invert)}"></i><span>${esc(sty.ramp || 'viridis')}</span>▾</button>
          <label class="row small"><input type="checkbox" id="sInv" ${sty.invert ? 'checked' : ''}> กลับด้าน</label>
          <div class="ramp-list hide" id="rampList">${Object.keys(STATE.ramps).map(k => `<div data-r="${esc(k)}"><i style="background:${rampCss(k)}"></i>${esc(k)}</div>`).join('')}</div></div></div>` : ''}
        ${biv && T === 'paletted' ? `<div class="field full"><span>พาเลทไบแวเรียต ${biv.nx}×${biv.ny} <span class="tiny muted">— แทนสีทุกรหัสตามตาราง 2 มิติ</span></span><div class="pals" id="sBivPal"></div></div>` : ''}
        ${T === 'pseudocolor' ? `
          <label class="field"><span>Min</span><input type="number" step="any" id="sMin" value="${sty.min ?? ''}"></label>
          <label class="field"><span>Max</span><input type="number" step="any" id="sMax" value="${sty.max ?? ''}"></label>
          <label class="field"><span>Interpolation</span><select id="sInterp">${[['discrete', 'Discrete (เป็นช่วง)'], ['linear', 'Linear (ไล่สี)'], ['exact', 'Exact (ค่าตรง)']].map(([k, t]) => `<option value="${k}" ${sty.interp === k ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
          <label class="field"><span>Mode</span><select id="sMode">${[['continuous', 'Continuous'], ['equal', 'Equal Interval'], ['quantile', 'Quantile']].map(([k, t]) => `<option value="${k}" ${sty.mode === k ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
          <label class="field"><span>Classes</span><input type="number" min="2" max="64" id="sN" value="${sty.classes || 5}"></label>
          <div class="field"><span>&nbsp;</span><button id="sMinMax" class="sm ghost" title="ตัด 2%–98% ของค่าสุ่ม">ใช้ช่วง 2–98%</button></div>` : ''}
        ${T === 'gray' ? `<label class="field"><span>Min</span><input type="number" step="any" id="sMin" value="${sty.min ?? 0}"></label>
          <label class="field"><span>Max</span><input type="number" step="any" id="sMax" value="${sty.max ?? 1}"></label>
          <label class="row small"><input type="checkbox" id="sInv" ${sty.invert ? 'checked' : ''}> กลับด้าน (ขาว → ดำ)</label>
          <div class="field"><button id="sMinMax" class="sm ghost" title="ตัด 2%–98% ของค่าสุ่ม (ศูนย์กองเยอะ → คิดจากพิกเซลที่มีค่า)">ใช้ช่วง 2–98%</button></div>` : ''}
      </div>
      ${T !== 'gray' ? `<div class="sym-wrap"><table class="sym"><thead><tr><th title="แสดง/ซ่อน">${IC.eye}</th><th>${T === 'pseudocolor' && sty.interp === 'discrete' ? 'ค่า ≤' : 'ค่า'}</th><th>สี</th><th>ป้ายชื่อ</th><th></th></tr></thead><tbody>
        ${items().map((e, i) => `<tr class="${e.visible === false ? 'off' : ''}"><td><input type="checkbox" data-vis="${i}" ${e.visible === false ? '' : 'checked'}></td>
          <td><input type="text" data-val="${i}" value="${esc(vstr(e.value))}"></td>
          <td><label class="sw" style="background:${e.color}"><input type="color" data-col="${i}" value="${e.color}"></label></td>
          <td><input type="text" data-lbl="${i}" value="${esc(e.label ?? '')}"></td>
          <td><button class="sm ghost danger" data-rm="${i}" title="ลบแถว">✕</button></td></tr>`).join('') || '<tr><td colspan="5" class="muted small">ยังไม่มีรายการ — กด Classify</td></tr>'}
      </tbody></table></div>
      <div class="row" style="margin-top:8px"><button id="sClassify" class="mint">${IC.refresh}Classify</button><button id="sAdd" class="sm">${IC.plus}เพิ่มแถว</button><button id="sClear" class="sm ghost danger">ลบทั้งหมด</button>
        <span class="spacer"></span><span class="tiny muted">${items().length} รายการ</span></div>` : ''}
      <h3>ตัวกรองการแสดงผล</h3>
      <div class="grid-form">
        <label class="field"><span>ซ่อนค่า (คั่นด้วย ,)</span><input type="text" id="sHide" value="${(sty.hide_values || []).join(', ')}" placeholder="เช่น 0"></label>
        <div class="field"><span>แสดงเฉพาะช่วง</span><div class="row" style="flex-wrap:nowrap"><input type="number" step="any" id="sLo" value="${sty.range?.[0] ?? ''}" placeholder="ต่ำสุด" style="width:50%"><input type="number" step="any" id="sHi" value="${sty.range?.[1] ?? ''}" placeholder="สูงสุด" style="width:50%"></div></div>
        ${o.viewer ? '' : `<label class="field full"><span>ความทึบ <b id="opv">${Math.round((sty.opacity ?? .85) * 100)}%</b></span><input type="range" id="sOp" min="0" max="1" step="0.05" value="${sty.opacity ?? .85}"></label>`}
      </div>
      ${o.viewer
        ? `<div class="tiny muted">ปรับแล้วมีผลทันทีเฉพาะชั้นนี้ในแผนที่ซ้อนชั้น (และรายงานที่ดึงจากหน้านี้) · สไตล์ของชุดข้อมูลไม่ถูกแก้ · ความทึบใช้แถบของชั้น</div>
      <div class="row" style="margin-top:12px"><button id="sReset" class="ghost" ${override ? '' : 'disabled'}>คืนเป็นสไตล์ของชุดข้อมูล</button><a class="btn sm ghost" href="#/ds/${d.id}">แก้สไตล์ของชุดข้อมูล →</a></div>`
        : `<div class="tiny muted">ตัวกรองนี้มีผลแค่บนแผนที่ · ถ้าไม่ให้นับในการคำนวณ ใช้ "ค่าที่ไม่นับ" ในการ์ดประเภทค่า</div>
      <div class="row" style="margin-top:14px"><button id="sSave" class="primary">${IC.check}บันทึกสไตล์</button><button id="sReset" class="ghost">คืนค่าเริ่มต้น</button>
        ${d.role === 'derived' ? '<span class="tiny muted">บันทึกแล้วเขียน .qml คู่ไฟล์ให้ QGIS เปิดแล้วสีขึ้นเอง</span>' : '<span class="tiny muted">ไฟล์ต้นฉบับไม่ถูกแก้ — ดาวน์โหลด .qml ได้จากปุ่มด้านบน</span>'}</div>`}`;
    const num = id => { const v = $(id)?.value; return v === '' || v == null ? null : parseFloat(v); };
    $('#sType').onchange = async () => {
      const prev = sty.type;
      sty.type = $('#sType').value;
      if (sty.type === 'gray') { draw(); preview(); return; }
      if (!await reclass()) { sty.type = prev; draw(); }        // เปลี่ยนไม่ได้ (เช่น ค่าไม่ซ้ำเกิน 256) → กลับเป็นแบบเดิม ไม่ให้หน้าจอค้างไม่ตรงกับแผนที่
    };
    $('#sMetric') && ($('#sMetric').onchange = async () => { sty.metric = $('#sMetric').value; sty.min = sty.max = null; await reclass(); });
    if ($('#rampBtn')) {
      $('#rampBtn').onclick = () => $('#rampList').classList.toggle('hide');
      $$('#rampList div').forEach(x => x.onclick = async () => {
        sty.ramp = x.dataset.r;
        if (sty.type !== 'gray') return recolor();
        Object.assign(sty, { type: 'pseudocolor', mode: 'continuous', interp: 'linear', classes: sty.classes || 5 });   // ขาวดำ → ไล่สี ช่วงเดิม
        if (!await reclass()) { sty.type = 'gray'; draw(); }
      });
    }
    if ($('#sBivPal')) palGallery($('#sBivPal'), biv.nx, biv.ny, sty.biv_pal || null, pp => {
      sty.biv_pal = pp.key;
      items().forEach(e => { const c = pp.colors[Math.round(+e.value) - 1]; if (c) e.color = c; });
      draw(); preview();
    });
    $('#sInv') && ($('#sInv').onchange = () => { sty.invert = $('#sInv').checked; sty.type === 'gray' ? (draw(), preview()) : recolor(); });
    ['#sMin', '#sMax'].forEach(k => $(k) && ($(k).onchange = () => { sty.min = num('#sMin'); sty.max = num('#sMax'); if (sty.type === 'gray') { draw(); preview(); } }));
    $('#sInterp') && ($('#sInterp').onchange = () => { sty.interp = $('#sInterp').value; reclass(); });
    $('#sMode') && ($('#sMode').onchange = () => { sty.mode = $('#sMode').value; });
    $('#sN') && ($('#sN').onchange = () => { sty.classes = +$('#sN').value; });
    $('#sMinMax') && ($('#sMinMax').onclick = () => { sty.min = sty.max = null; reclass(); });
    $('#sClassify') && ($('#sClassify').onclick = () => reclass());
    $('#sAdd') && ($('#sAdd').onclick = () => { const it = items(); const last = it.at(-1); it.push({ value: last ? (last.value === 'inf' ? 0 : +last.value + 1) : 0, color: '#c3b6ff', label: '', visible: true }); draw(); preview(); });
    $('#sClear') && ($('#sClear').onclick = () => { items().length = 0; draw(); preview(); });
    $$('[data-vis]', el).forEach(c => c.onchange = () => { items()[+c.dataset.vis].visible = c.checked; c.closest('tr').classList.toggle('off', !c.checked); preview(); });
    if (sty.type === 'paletted') $$('[data-vis]', el).forEach(c => c.closest('tr').oncontextmenu = ev => {     // คลิกขวาแถว = ความทึบเฉพาะค่านั้น
      if (ev.target.matches('input[type=text], input[type=number]')) return;
      const e = items()[+c.dataset.vis];
      opacityMenu(ev, e, `${e.value} · ${e.label || ''}`, () => { c.checked = true; c.closest('tr').classList.remove('off'); c.closest('tr').style.opacity = (e.opacity ?? 1) < 1 ? Math.max(.4, e.opacity) : ''; preview(); });
    });
    $$('[data-val]', el).forEach(c => c.onchange = () => { items()[+c.dataset.val].value = vnum(c.value); preview(); });
    $$('[data-col]', el).forEach(c => c.oninput = () => { items()[+c.dataset.col].color = c.value; c.parentElement.style.background = c.value; preview(); });
    $$('[data-lbl]', el).forEach(c => c.onchange = () => { items()[+c.dataset.lbl].label = c.value; o.viewer ? preview() : setMapLegend(sty); });
    $$('[data-rm]', el).forEach(c => c.onclick = () => { items().splice(+c.dataset.rm, 1); draw(); preview(); });
    $('#sHide').onchange = () => { sty.hide_values = $('#sHide').value.split(',').map(s => parseFloat(s)).filter(x => !isNaN(x)); preview(); };
    ['#sLo', '#sHi'].forEach(k => $(k).onchange = () => { const lo = num('#sLo'), hi = num('#sHi'); sty.range = lo == null && hi == null ? null : [lo, hi]; preview(); });
    $('#sOp') && ($('#sOp').oninput = () => { sty.opacity = +$('#sOp').value; $('#opv').textContent = Math.round(sty.opacity * 100) + '%'; window._rasterLayer?.setOpacity(sty.opacity); });
    $('#sClose') && ($('#sClose').onclick = () => o.onClose?.());
    if (o.viewer) {
      $('#sReset').onclick = async () => { clearTimeout(pvTimer); o.onReset?.(); sty = (await api(`${ENGINE}/api/datasets/${d.id}/style`)).style; override = false; draw(); };
      return;
    }
    $('#sSave').onclick = async () => { const r = await api(`${ENGINE}/api/datasets/${d.id}/style`, { json: { style: sty } }); saved = true; toast('บันทึกสไตล์แล้ว' + (r.qml ? ' · เขียน ' + r.qml.split(/[\\/]/).pop() : '')); draw(); };
    $('#sReset').onclick = async () => { await api(`${ENGINE}/api/datasets/${d.id}/style`, { json: { style: null } }); const r = await api(`${ENGINE}/api/datasets/${d.id}/style`); sty = r.style; saved = false; draw(); preview(); };
  };
  // Classify: คำนวณช่วง/ค่าเฉพาะใหม่ตาม mode/ramp/classes (เหมือนปุ่ม Classify ของ QGIS)
  const reclass = async () => {
    try {
      const req = { type: sty.type, ramp: sty.ramp || (sty.type === 'paletted' ? 'Set3 (หมวดหมู่)' : 'viridis'), invert: !!sty.invert, mode: sty.mode || 'continuous',
        interp: sty.interp || 'linear', classes: sty.classes || 5, min: sty.min ?? null, max: sty.max ?? null, metric: isCount ? (sty.metric || 'density') : 'value',
        hide_values: sty.hide_values || [], range: sty.range || null, opacity: sty.opacity ?? .85 };
      const r = await api(`${ENGINE}/api/datasets/${d.id}/classify`, { json: req });
      sty = r.style; draw(); preview();
      return true;
    } catch (e) { toast(e.message, true); return false; }
  };
  // เปลี่ยน ramp → ระบายสีรายการเดิมใหม่ (ไม่เปลี่ยนค่า)
  const recolor = () => {
    const it = items(), n = it.length, s = STATE.ramps[sty.ramp] || [];
    const st = sty.invert ? [...s].reverse() : s;
    const cat = STATE.categorical.includes(sty.ramp);
    it.forEach((e, i) => { e.color = cat ? st[i % st.length] : rampAt(st, n === 1 ? 0 : i / (n - 1)); });
    draw(); preview();
  };
  draw();
  if (o.viewer) return;
  setMapLegend(sty);
  if (sty.opacity != null) window._rasterLayer?.setOpacity(sty.opacity);
}
function rampAt(st, t) {
  const h2 = h => [1, 3, 5].map(i => parseInt(h.substr(i, 2), 16));
  const x = Math.min(Math.max(t, 0), 1) * (st.length - 1), i = Math.min(Math.floor(x), st.length - 2), f = x - i;
  const a = h2(st[i]), b = h2(st[i + 1]);
  return '#' + a.map((v, k) => Math.round(v * (1 - f) + b[k] * f).toString(16).padStart(2, '0')).join('');
}

// คำอธิบายสัญลักษณ์บนแผนที่ (มุมขวาล่าง)
function setMapLegend(sty) {
  const mp = window._mapObj; if (!mp || !sty) return;
  if (!mp._legend) { mp._legend = L.control({ position: 'bottomright' }); mp._legend.onAdd = () => L.DomUtil.create('div', 'map-legend'); mp._legend.addTo(mp); }
  const el = mp._legend.getContainer();
  const it = (sty.type === 'paletted' ? sty.entries : sty.stops || []) || [];
  if (sty.type === 'gray') { el.innerHTML = `<div class="ml-bar" style="background:linear-gradient(90deg,#000,#fff)"></div><div class="ml-mm"><span>${fmt(sty.min)}</span><span>${fmt(sty.max)}</span></div>`; return; }
  if (sty.type === 'pseudocolor' && sty.interp === 'linear') {
    el.innerHTML = `<div class="ml-bar" style="background:linear-gradient(90deg,${it.map(s => s.color).join(',')})"></div><div class="ml-mm"><span>${esc(it[0]?.label ?? '')}</span><span>${esc(it.at(-1)?.label ?? '')}</span></div>${sty.metric === 'density' ? '<div class="tiny muted">ต่อ ตร.กม.</div>' : ''}`;
    return;
  }
  const shown = it.slice(0, 14);
  el.innerHTML = shown.map(e => `<div class="ml-row ${e.visible === false ? 'off' : ''}"><i style="background:${e.color}"></i>${esc(e.label ?? e.value)}</div>`).join('')
    + (it.length > 14 ? `<div class="tiny muted">… อีก ${it.length - 14}</div>` : '') + (sty.metric === 'density' ? '<div class="tiny muted">ต่อ ตร.กม.</div>' : '');
}

// ไบแวเรียตรายพื้นที่: คำอธิบาย + ตาราง (อ่านอย่างเดียว)
function zonalLegend(d) {
  const lp = d.lineage.params, s = d.lineage.stats_summary || {};
  const nx = +lp.x.n, ny = +lp.y.n;
  const csv = (d.lineage.outputs || []).find(o => o.endsWith('_table.csv'));
  const ax = a => { const q = lp[a].stat_label || ({ density: 'ต่อ ตร.กม.', per_pixel: 'ต่อช่อง', value: '' }[lp[a].metric] ?? lp[a].metric) || lp[a].field || lp[a].stat || ''; return `${lp[a].label || a.toUpperCase()}${q ? ' (' + q + ')' : ''}`; };
  const hx = lp.hex;
  return `<div class="card"><div class="card-head"><h2><span class="dot" style="background:var(--rose);color:var(--rose)"></span>${hx ? `ไบแวเรียตหกเหลี่ยม ${fmt(hx.d_km, 3)} กม.` : 'ไบแวเรียตรายพื้นที่'}</h2>
    ${csv ? `<button class="sm ghost" onclick='openFolder(${attr(csv)})'>${IC.folder}ตาราง CSV</button>` : ''}</div>
    ${legendHtml(nx, ny, lp.colors, lp.highlight || [], ax('x'), ax('y'), false)}
    <table class="kv" style="margin-top:12px"><tr><td>เกณฑ์ X</td><td>${(lp.x.resolved_breaks || []).map(b => fmt(b, 3)).join(' / ') || '–'}</td></tr>
      <tr><td>เกณฑ์ Y</td><td>${(lp.y.resolved_breaks || []).map(b => fmt(b, 3)).join(' / ') || '–'}</td></tr>
      ${hx ? `<tr><td>ช่อง</td><td>${fmt(s.hexes, 0)} ช่อง · เขตเน้น <b style="color:var(--butter)">${fmt(s.hexes_highlight, 0)}</b> (${fmt(s.hexes_highlight * hx.area_km2, 1)} ตร.กม.)</td></tr>
        ${s.weight_total != null ? `<tr><td>${esc(s.weight_name || 'น้ำหนัก')}</td><td>รวม ${fmt(s.weight_total, 0)} · ในเขตเน้น <b style="color:var(--butter)">${fmt(s.weight_highlight, 0)}</b> (${fmt(s.weight_highlight / (s.weight_total || 1) * 100, 1)}%)</td></tr>` : ''}`
      : `<tr><td>พื้นที่</td><td>${fmt(s.zones, 0)} · มีรหัส ${fmt(s.zones_coded, 0)} · เขตเน้น <b style="color:var(--butter)">${fmt(s.zones_highlight, 0)}</b></td></tr>`}</table>
    <div class="tiny muted" style="margin-top:6px">คลิกพื้นที่บนแผนที่เพื่อดูค่า x_value / y_value ของพื้นที่นั้น</div></div>`;
}

// ประเมินขนาด → ถาม → ส่งงาน
async function runJob(kind, params, then) {
  try {
    const e = await api(ENGINE + '/api/estimate', { json: { kind, params } });
    if (!e.ok) throw new Error(e.error);
    const mode = o => !o ? '' : o.mode === 'same' ? 'เท่าเดิม' : o.mode === 'up' ? `แตกพิกเซล ×${o.factor}` : `รวมพิกเซล ${o.factor}×${o.factor}`;
    const body = `<table class="kv">
      <tr><td>ความละเอียด</td><td>${esc(e.grid.res_label)}</td></tr>
      ${e.hex ? `<tr><td>จำนวนช่อง</td><td>ประมาณ ${fmt(e.hex.n, 0)} ช่อง · ${esc(e.hex.crs)}</td></tr>` : `<tr><td>ขนาดผลลัพธ์</td><td>${fmt(e.grid.width, 0)} × ${fmt(e.grid.height, 0)} พิกเซล</td></tr>`}
      ${e.aoi ? `<tr><td>พื้นที่ศึกษา</td><td>${esc(e.aoi)}</td></tr>` : ''}
      ${e.mode ? `<tr><td>วิธี</td><td>${mode(e)}</td></tr>` : ''}${e.x ? `<tr><td>แกน X / Y</td><td>${mode(e.x)} / ${mode(e.y)}</td></tr>` : ''}
      ${e.cells_max ? `<tr><td>จำนวนช่องสูงสุด</td><td>${fmt(e.cells_max, 0)}</td></tr>` : ''}</table>`
      + e.warnings.map(w => `<div class="note warn">${esc(w)}</div>`).join('');
    if (!await ui.confirm('เริ่มงาน?', body, 'เริ่มงาน')) return;
    const r = await api(ENGINE + '/api/jobs', { json: { kind, params } });
    toast(`เริ่มงาน #${r.job} — ดูความคืบหน้าในแท็บงาน`);
    jobBadge(); if (then) then(r);
  } catch (er) { toast(er.message, true); }
}

async function drawHist(id) {
  try {
    const r = await api(ENGINE + '/api/classes-preview', { json: { dataset_id: id, cfg: { n: 1, method: 'breaks', breaks: [], metric: 'value' } } });
    histCanvas($('#hist'), r.hist);
    $('#histNote').textContent = `${fmt(r.n, 0)} ค่าสุ่ม · ${r.hist.log ? 'แกน X แบบ log (ข้อมูลเบ้มาก)' + (r.hist.zeros ? ` · ค่า ≤0 ${fmt(r.hist.zeros, 0)} ค่าไม่แสดง` : '') : 'แกน X เชิงเส้น'}`;
  } catch { }
}

function histCanvas(cv, h, breaks = [], colors = []) {
  const W = cv.width = cv.clientWidth * devicePixelRatio, H = cv.height = 96 * devicePixelRatio;
  const c = cv.getContext('2d'); c.clearRect(0, 0, W, H);
  const mx = Math.max(...h.counts, 1), n = h.counts.length;
  const e0 = h.edges[0], e1 = h.edges[n];
  const X = v => h.log ? (Math.log10(v) - Math.log10(e0)) / (Math.log10(e1) - Math.log10(e0)) * W : (v - e0) / (e1 - e0) * W;
  const cls = v => breaks.filter(b => v >= b).length;
  h.counts.forEach((k, i) => {
    const x0 = X(h.edges[i]), x1 = X(h.edges[i + 1]); const hh = k / mx * (H - 16);
    c.fillStyle = colors[cls((h.edges[i] + h.edges[i + 1]) / 2)] || '#c3b6ff';
    c.globalAlpha = .85; c.beginPath(); c.roundRect(x0, H - 14 - hh, Math.max(1, x1 - x0 - 2), hh, 3 * devicePixelRatio); c.fill();
  });
  c.globalAlpha = 1; c.fillStyle = '#ffc2a8';
  breaks.forEach(b => { if (b > e0 && b < e1) c.fillRect(X(b), 0, 2 * devicePixelRatio, H - 14); });
  c.fillStyle = '#8a90b0'; c.font = `${10.5 * devicePixelRatio}px Anuphan, sans-serif`;
  c.fillText(fmt(e0, 3), 2, H - 1); const t = fmt(e1, 3); c.fillText(t, W - c.measureText(t).width - 2, H - 1);
}

// ---------- แผนที่ ----------
function baseMap(el, opts = {}) {
  const mp = L.map(el, { preferCanvas: true, zoomControl: true, ...opts });
  maps.push(mp);
  const bms = {
    osm: L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap' }),
    gh: L.tileLayer('https://mt{s}.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', { subdomains: '0123', maxZoom: 21, attribution: 'Google' }),
  };
  let bop = 1; try { bop = +(localStorage.getItem('basemapOpacity') ?? 1); } catch { }
  mp._setBm = k => { Object.values(bms).forEach(l => mp.removeLayer(l)); if (bms[k]) bms[k].setOpacity(bop).addTo(mp).bringToBack(); try { localStorage.setItem('basemap', k); } catch { } };
  mp._setBmOpacity = v => { bop = v; Object.values(bms).forEach(l => l.setOpacity(v)); try { localStorage.setItem('basemapOpacity', v); } catch { } };
  mp._bmOpacity = () => bop;
  let cur = 'gh'; try { cur = localStorage.getItem('basemap') || 'gh'; } catch { }
  mp._setBm(cur); mp._bm = cur;
  return mp;
}
function bmSeg(mp, seg) {
  const set = k => { mp._setBm(k); $$('button', seg).forEach(b => b.classList.toggle('on', b.dataset.k === k)); rng.disabled = k === 'none'; };
  // ความโปร่งใสของแผนที่พื้นหลัง (จำค่าไว้ทุกหน้า) — ลดลงให้ข้อมูลเด่นขึ้น
  const lab = document.createElement('label');
  lab.className = 'row small bm-op'; lab.title = 'ความทึบของแผนที่พื้นหลัง';
  lab.innerHTML = `พื้นหลัง <input type="range" min="0" max="1" step="0.05" value="${mp._bmOpacity()}"><b>${Math.round(mp._bmOpacity() * 100)}%</b>`;
  seg.after(lab);
  const rng = $('input', lab);
  rng.oninput = () => { mp._setBmOpacity(+rng.value); $('b', lab).textContent = Math.round(rng.value * 100) + '%'; };
  $$('button', seg).forEach(b => b.onclick = () => set(b.dataset.k)); set(mp._bm);
}

// URL ไทล์ราสเตอร์ของหน้าชุดข้อมูล: st = สไตล์ชั่วคราว · clip = ตัดการแสดงผลตามพื้นที่ศึกษา (จำแยกต่อชุดในเบราว์เซอร์)
const clipKey = id => 'ainu-clip-' + id;
const getClip = id => { try { return localStorage.getItem(clipKey(id)) || ''; } catch { return ''; } };
function rTileUrl(d, st) {
  const c = getClip(d.id);
  return `${ENGINE}/api/datasets/${d.id}/tile/{z}/{x}/{y}.png?v=${encodeURIComponent(d.fingerprint || '')}${st ? '&st=' + st : ''}${c ? '&clip=' + c : ''}`;
}

function initMap(d) {
  const m = d.meta;
  const mp = baseMap('map');
  window._mapObj = mp;
  bmSeg(mp, $('#bm'));
  const b = m.bounds_wgs84;
  if (b) mp.fitBounds([[b[1], b[0]], [b[3], b[2]]]); else mp.setView([13.5, 100.5], 6);
  let layer;
  if (d.kind === 'raster') {
    window._rasterSt = null;                                    // token สไตล์ชั่วคราวของชุดก่อนหน้า ไม่ใช้ข้ามหน้า
    layer = L.tileLayer(rTileUrl(d), { maxZoom: 22, opacity: .85 }).addTo(mp);
    window._rasterLayer = layer;
    if ($('#clipSel')) {
      $('#clipSel').value = getClip(d.id);
      if ($('#clipSel').value !== getClip(d.id)) { try { localStorage.removeItem(clipKey(d.id)); } catch { } }   // พื้นที่ศึกษาถูกลบไปแล้ว
      $('#clipSel').onchange = () => {
        try { $('#clipSel').value ? localStorage.setItem(clipKey(d.id), $('#clipSel').value) : localStorage.removeItem(clipKey(d.id)); } catch { }
        layer.setUrl(rTileUrl(d, window._rasterSt));
      };
    }
    if (!d.preview_path && m.pixels > 4e6 && !m.overviews.length) $('#mapNote').textContent = 'ไฟล์ใหญ่ไม่มี overview — ซูมออกจะช้าจนกว่าเตรียมข้อมูลเสร็จ';
  } else {
    const hasColor = (m.fields || []).some(f => f.name === 'color');
    const stl = f => hasColor ? { color: '#ffffff', weight: .4, fillColor: f.properties.color, fillOpacity: +$('#op').value * .9 } : { color: '#f7a8cc', weight: 1.2, fillOpacity: .12 };
    layer = L.geoJSON(null, { style: stl, pointToLayer: (f, ll) => L.circleMarker(ll, { radius: 3, weight: 1 }) }).addTo(mp);
    layer.setStyle = layer.setStyle.bind(layer);
    const load = async () => {
      const bb = mp.getBounds();
      const q = [bb.getWest(), bb.getSouth(), bb.getEast(), bb.getNorth()].join(',');
      try {
        const r = await fetch(`${ENGINE}/api/datasets/${d.id}/features?bbox=${q}&z=${mp.getZoom()}${hasColor ? '&fields=color,code' : ''}`);
        const gj = await r.json(); layer.clearLayers(); layer.addData(gj);
        const hid = +r.headers.get('X-Hidden') || 0;
        $('#mapNote').textContent = (r.headers.get('X-Truncated') === '1' ? `แสดง ${r.headers.get('X-Count')} รูปแรก — ซูมเข้าเพื่อดูครบ` : `${r.headers.get('X-Count')} รูปในกรอบ`)
          + (hid ? ` · อีก ${fmt(hid, 0)} รูปเล็กกว่าพิกเซลที่ระดับนี้ — ซูมเข้าเพื่อดู` : '');
      } catch (e) { $('#mapNote').textContent = 'โหลด feature ไม่ได้: ' + e.message; }
    };
    mp.on('moveend', load); load();
  }
  $('#op').oninput = () => d.kind === 'vector' ? layer.eachLayer(l => l.setStyle?.({ fillOpacity: +$('#op').value * ((m.fields || []).some(f => f.name === 'color') ? .9 : .2) })) : layer.setOpacity(+$('#op').value);
  linkOverlay(mp, $('.mapbar'));
  let pxRect = null;
  mp.on('click', async e => {
    const { lat } = e.latlng, lng = e.latlng.wrap().lng;      // แผนที่วนรอบโลก → ลองจิจูดเกิน 180 (เช่น 459.9) ให้กลับเป็น −180…180
    try {
      const r = await api(`${ENGINE}/api/datasets/${d.id}/point?lon=${lng}&lat=${lat}&z=${mp.getZoom()}`);
      $('#pt').innerHTML = pointHtml(r);
      if (pxRect) mp.removeLayer(pxRect);
      if (r.kind === 'raster' && !r.outside && m.geographic) {
        const t = m.transform, x0 = t[2] + r.col * t[0], y0 = t[5] + r.row * t[4];
        pxRect = L.rectangle([[y0, x0], [y0 + t[4], x0 + t[0]]], { color: '#f6e3a1', weight: 2, fill: false }).addTo(mp);
      }
    } catch (er) { $('#pt').innerHTML = `<div class="note err">${esc(er.message)}</div>`; }
  });
}

function pointHtml(r) {
  const ll = `${r.lat.toFixed(6)}, ${r.lon.toFixed(6)}`;
  const box = (h) => `<div class="pt-card"><div class="mono muted" style="margin-bottom:4px">${ll}</div>${h}</div>`;
  if (r.kind === 'vector') {
    if (!r.features.length) return box('<span class="muted">ไม่พบ feature ใกล้จุดนี้</span>');
    return box(`${r.features.length} feature` + r.features.map(f => `<table class="kv">${Object.entries(f.attrs).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}</table>`).join('<hr style="border-color:var(--line)">'));
  }
  if (r.outside) return box('<span class="muted">อยู่นอกขอบเขตข้อมูล</span>');
  const rows = r.bands.map(b => [`แบนด์ ${b.band}${b.desc ? ' ' + esc(b.desc) : ''}`, b.nodata ? `nodata (${esc(b.value)})${r.nodata_as != null ? ` → นับเป็น ${r.nodata_as}` : ''}` : `<b style="color:var(--text);font-size:15px">${fmt(b.value, 6)}</b>${b.raw != null ? ` <span class="tiny muted">(ค่าดิบ ${fmt(b.raw, 6)} × scale ${b.scale}${b.offset ? ` + ${b.offset}` : ''})</span>` : ''}`]);
  rows.push(['พิกเซล (แถว, คอลัมน์)', `${fmt(r.row, 0)}, ${fmt(r.col, 0)}`]);
  rows.push(['พื้นที่พิกเซล', r.pixel_area_km2 < 0.01 ? `${fmt(r.pixel_area_km2 * 1e6, 1)} ตร.ม.` : `${fmt(r.pixel_area_km2, 4)} ตร.กม.`]);
  if (r.density != null) rows.push(['ความหนาแน่น', `${fmt(r.density, 2)} ต่อ ตร.กม.`]);
  if (r.color) rows.push(['สี', `<span style="display:inline-block;width:14px;height:14px;border-radius:4px;background:${r.color};vertical-align:middle"></span> ${r.color}`]);
  return box(`<table class="kv">${rows.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('')}</table>`);
}

// ---------- พาเลท ----------
async function loadPals() { PALS = await api(ENGINE + '/api/palettes'); return PALS; }
// รายการพาเลทที่ใช้กับขนาด nx×ny ได้: แบบสำเร็จรูป (ไล่สีจาก 3×3) + ที่บันทึกไว้ขนาดเดียวกัน
function palChoices(nx, ny) {
  return [...PALS.builtin.map(p => ({ key: 'b:' + p.id, name: p.name, colors: Pal.interpolate(p.colors, nx, ny), cb: p.cb_safe, grad: p.gradient, src: p.source })),
    ...PALS.custom.filter(p => p.nx === nx && p.ny === ny).map(p => ({ key: 'c:' + p.id, id: p.id, name: p.name, colors: p.colors, cb: null, custom: true, src: 'บันทึกเอง' }))];
}
function palGallery(el, nx, ny, curKey, onPick, onDelete) {
  const ch = palChoices(nx, ny);
  el.innerHTML = ch.map(p => `<div class="pal ${p.key === curKey ? 'on' : ''}" data-k="${p.key}" title="${esc(p.src || '')}">
    ${p.custom ? `<span class="x" data-del="${p.id}">✕</span>` : ''}
    <div class="mini" style="grid-template-columns:repeat(${nx},14px)">${Array.from({ length: ny }, (_, yy) => Array.from({ length: nx }, (_, x) => `<i style="background:${p.colors[(ny - 1 - yy) * nx + x]}"></i>`).join('')).join('')}</div>
    ${esc(p.name)}${p.cb === false ? ' ⚠' : ''}</div>`).join('');
  $$('.pal', el).forEach(e => e.onclick = ev => {
    if (ev.target.dataset.del) { onDelete?.(+ev.target.dataset.del); return; }
    const p = ch.find(c => c.key === e.dataset.k); onPick(p);
  });
  return ch;
}
function legendHtml(nx, ny, cols, hl, xname, yname, editable = true) {
  let h = `<div class="row" style="align-items:stretch;gap:10px;flex-wrap:nowrap"><div class="axis-y">${esc(yname || 'แกน Y')} →</div><div><div class="legend" style="grid-template-columns:repeat(${nx},52px)">`;
  for (let y = ny - 1; y >= 0; y--) for (let x = 0; x < nx; x++) {
    const i = y * nx + x;
    h += `<div class="cell ${hl.includes(i + 1) ? 'hl' : ''}" data-code="${i + 1}" style="background:${cols[i]}"><span>${i + 1}</span>${editable ? `<input type="color" data-i="${i}" value="${cols[i]}">` : ''}</div>`;
  }
  return h + `</div><div class="small" style="margin-top:6px;color:var(--text-2)">${esc(xname || 'แกน X')} →</div></div></div>`;
}
async function savePalette(nx, ny, colors) {
  const n = await ui.prompt('บันทึกพาเลท', `พาเลท ${nx}×${ny}`, 'ใช้ซ้ำได้ในงานถัดไป (ขนาดเดียวกัน)');
  if (!n) return false;
  await api(ENGINE + '/api/palettes', { json: { name: n, nx, ny, colors } }); await loadPals(); toast('บันทึกพาเลทแล้ว'); return true;
}
function exportPalette(nx, ny, colors, name = 'palette') {
  const blob = new Blob([JSON.stringify({ name, nx, ny, colors }, null, 1)], { type: 'application/json' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name.replace(/[^\w\-ก-๙]+/g, '_') + '.json'; a.click();
}
function importPalette() {
  return new Promise(res => {
    const inp = document.createElement('input'); inp.type = 'file'; inp.accept = '.json,application/json';
    inp.onchange = async () => {
      try {
        const p = JSON.parse(await inp.files[0].text());
        await api(ENGINE + '/api/palettes', { json: { name: p.name || inp.files[0].name, nx: p.nx, ny: p.ny, colors: p.colors } });
        await loadPals(); toast(`นำเข้าพาเลท ${p.nx}×${p.ny} แล้ว`); res(p);
      } catch (e) { toast('นำเข้าไม่ได้: ' + e.message, true); res(null); }
    };
    inp.click();
  });
}

// เมนูคลิกขวา: ปรับความทึบเฉพาะสีเดียว (ent.opacity 0–1) · onChange(ทุกครั้งที่ลาก) · ปิดเมื่อคลิกที่อื่น/Esc
function opacityMenu(ev, ent, title, onChange) {
  ev.preventDefault();
  $$('.op-menu').forEach(m => m.remove());
  const m = document.createElement('div');
  m.className = 'op-menu';
  const pct = () => Math.round((ent.opacity ?? 1) * 100);
  m.innerHTML = `<div class="small" style="margin-bottom:6px"><b translate="no">${esc(title)}</b></div>
    <div class="tiny muted">ความทึบเฉพาะสีนี้</div>
    <div class="row" style="gap:8px;margin-top:4px"><input type="range" min="0" max="100" step="5" value="${pct()}"><b class="small op-v">${pct()}%</b></div>
    <div class="row" style="gap:6px;margin-top:8px">${[25, 50, 75, 100].map(v => `<button class="sm ghost" data-v="${v}">${v}%</button>`).join('')}</div>
    <div class="tiny muted" style="margin-top:6px">${ent.visible === false ? 'สีนี้ถูกซ่อนอยู่ — ปรับแล้วจะแสดงกลับ' : 'ซ่อนทั้งสี = คลิกซ้าย'}</div>`;
  document.body.appendChild(m);
  const r = m.getBoundingClientRect();
  m.style.left = Math.min(ev.clientX, innerWidth - r.width - 8) + 'px';
  m.style.top = Math.min(ev.clientY, innerHeight - r.height - 8) + 'px';
  const set = v => { ent.opacity = v / 100; ent.visible = true; m.querySelector('input').value = v; m.querySelector('.op-v').textContent = v + '%'; onChange(); };
  m.querySelector('input').oninput = e => set(+e.target.value);
  m.querySelectorAll('[data-v]').forEach(b => b.onclick = () => set(+b.dataset.v));
  const close = e => { if (e.type === 'keydown' ? e.key === 'Escape' : !m.contains(e.target)) { m.remove(); document.removeEventListener('mousedown', close, true); document.removeEventListener('keydown', close, true); } };
  setTimeout(() => { document.addEventListener('mousedown', close, true); document.addEventListener('keydown', close, true); });
}

// แผนที่ไบแวเรียต: คลิกช่อง = แสดง/ซ่อนชั้นบนแผนที่ · คลิกขวา = ปรับความทึบเฉพาะสีนั้น · ปุ่ม "แก้ไขพาเลท" = เลือกพาเลท / แก้สีทีละช่อง
async function mapPalette(d) {
  const lp = d.lineage?.params; if (!lp) return;
  await loadPals();
  const nx = +lp.x.n, ny = +lp.y.n;
  let cols = (d.lineage.palette_edits?.at(-1)?.colors || lp.colors).slice();
  const sr = await api(`${ENGINE}/api/datasets/${d.id}/style`);
  let sty = sr.style && sr.style.type === 'paletted' ? sr.style : { type: 'paletted', entries: cols.map((c, i) => ({ value: i + 1, color: c, label: String(i + 1), visible: true })) };
  const vis = code => (sty.entries.find(e => +e.value === code) || {}).visible !== false;
  let key = null, editing = false, dirty = false;
  const el = $('#mapPal');
  const preview = async () => {
    sty.entries.forEach(e => { const c = cols[+e.value - 1]; if (c) e.color = c; });
    const t = await api(ENGINE + '/api/style-preview', { json: { dataset_id: d.id, style: sty } });
    window._rasterSt = t.token; window._rasterLayer?.setUrl(rTileUrl(d, t.token));
    setMapLegend(sty);
  };
  const draw = () => {
    let grid = `<div class="row" style="align-items:stretch;gap:10px;flex-wrap:nowrap"><div class="axis-y">${esc(lp.y.label || 'แกน Y')} →</div><div><div class="legend ${editing ? 'editing' : ''}" style="grid-template-columns:repeat(${nx},52px)">`;
    for (let y = ny - 1; y >= 0; y--) for (let x = 0; x < nx; x++) {
      const i = y * nx + x, code = i + 1, ent = sty.entries.find(e => +e.value === code);
      const op = ent?.opacity ?? 1;
      grid += `<div class="cell ${(lp.highlight || []).includes(code) ? 'hl' : ''} ${vis(code) ? '' : 'hidden'}" data-code="${code}" style="background:${cols[i]};${op < 1 && vis(code) ? `opacity:${Math.max(.25, op)}` : ''}" title="${esc(ent?.label || code)}">
        <span>${code}</span>${op < 1 && vis(code) ? `<em class="op-badge">${Math.round(op * 100)}%</em>` : ''}${editing ? `<input type="color" data-i="${i}" value="${cols[i]}">` : ''}</div>`;
    }
    grid += `</div><div class="small" style="margin-top:6px;color:var(--text-2)">${esc(lp.x.label || 'แกน X')} →</div></div></div>`;
    el.innerHTML = `<div class="card-head"><h2><span class="dot" style="background:var(--rose);color:var(--rose)"></span>สีแผนที่</h2>
        <div class="row"><button class="sm ${editing ? 'primary' : ''}" id="pEdit">${IC.palette}${editing ? 'เสร็จ' : 'แก้ไขพาเลท'}</button><a class="btn sm ghost" href="${ENGINE}/api/datasets/${d.id}/style.qml">${IC.download}.qml</a></div></div>
      <div class="small muted" style="margin-bottom:10px">${editing ? 'คลิกช่องเพื่อแก้สี หรือเลือกพาเลทด้านล่าง — แผนที่เปลี่ยนทันที' : 'คลิกช่องเพื่อ <b>แสดง/ซ่อน</b> · <b>คลิกขวา</b>เพื่อปรับความทึบเฉพาะสีนั้น (ไม่แก้ไฟล์)'}</div>
      ${grid}
      <div class="row" style="margin-top:10px"><button class="sm ghost" id="pAll">แสดงทั้งหมด</button><button class="sm ghost" id="pHl">แสดงเฉพาะเขตเน้น</button><span class="tiny muted" id="pVisN"></span></div>
      ${editing ? `<h3>พาเลท</h3><div class="pals" id="mpPals"></div>
        <div class="row" style="margin-top:10px"><button class="sm ghost" id="pSave">${IC.download}บันทึกเป็นพาเลท</button><button class="sm ghost" id="pExp">ส่งออก</button><button class="sm ghost" id="pImp">นำเข้า</button></div>` : ''}
      ${dirty ? `<div class="note warn small" style="margin-top:12px">สีเปลี่ยนแล้วแต่ยังไม่ได้บันทึกลงไฟล์</div>` : ''}
      <div class="row" style="margin-top:12px">${dirty ? `<button id="palSave" class="primary">${IC.check}บันทึกสีลงไฟล์ (tif + qml + legend)</button><button id="palUndo" class="ghost">ยกเลิก</button>` : ''}</div>`;
    $('#pVisN').textContent = `แสดง ${sty.entries.filter(e => e.visible !== false).length}/${nx * ny} ชั้น`;
    $('#pEdit').onclick = () => { editing = !editing; draw(); };
    $$('.cell', el).forEach(c => c.onclick = async ev => {
      if (editing) return;
      const code = +c.dataset.code, ent = sty.entries.find(e => +e.value === code);
      if (ent) ent.visible = !vis(code);
      draw(); await preview(); saveVis();
    });
    let opT;
    $$('.cell', el).forEach(c => c.oncontextmenu = ev => {
      if (editing) return;
      const code = +c.dataset.code, ent = sty.entries.find(e => +e.value === code);
      if (!ent) return;
      opacityMenu(ev, ent, `${code} · ${ent.label || ''}`, () => { clearTimeout(opT); opT = setTimeout(() => { draw(); preview(); saveVis(); }, 120); });
    });
    const setVis = f => { sty.entries.forEach(e => e.visible = f(+e.value)); draw(); preview(); saveVis(); };
    $('#pAll').onclick = () => { sty.entries.forEach(e => delete e.opacity); setVis(() => true); };
    $('#pHl').onclick = () => setVis(c => (lp.highlight || []).includes(c));
    $$('.cell input', el).forEach(inp => inp.oninput = () => { cols[+inp.dataset.i] = inp.value; inp.parentElement.style.background = inp.value; key = null; if (!dirty) { dirty = true; draw(); } preview(); });
    if (editing) {
      palGallery($('#mpPals'), nx, ny, key, p => { key = p.key; cols = p.colors.slice(); dirty = true; draw(); preview(); },
        async pid => { await api(ENGINE + '/api/palettes/' + pid, { method: 'DELETE' }); await loadPals(); draw(); });
      $('#pSave').onclick = async () => { if (await savePalette(nx, ny, cols)) draw(); };
      $('#pExp').onclick = () => exportPalette(nx, ny, cols, d.name);
      $('#pImp').onclick = async () => { if (await importPalette()) draw(); };
    }
    if ($('#palSave')) {
      $('#palSave').onclick = async () => { await api(`${ENGINE}/api/datasets/${d.id}/colors`, { json: { colors: cols } }); toast('บันทึกสีลงไฟล์แล้ว'); route(); };
      $('#palUndo').onclick = () => route();
    }
  };
  // แสดง/ซ่อน = สไตล์การแสดงผล (บันทึกทันที ไม่แก้ไฟล์)
  let visTimer;
  const saveVis = () => { clearTimeout(visTimer); visTimer = setTimeout(() => api(`${ENGINE}/api/datasets/${d.id}/style`, { json: { style: sty } }), 400); };
  draw(); setMapLegend(sty);
}
// ================= ไบแวเรียต =================
const BIV = {
  x: { dataset_id: null, n: 3, method: 'breaks', breaks: [300, 1500], metric: 'density', order: 'auto', label: '' },
  y: { dataset_id: null, n: 3, method: 'breaks', breaks: [1, 5], metric: 'value', order: 'auto', label: '' },
  pal: null, colors: null, highlight: [8, 9], tie: 'high', count_down_valid: 'positive', target_res: null, name: '', hlMode: false, out: 'raster', size_km: 1,
  aoi_id: null, aoi_rule: 'center', aoi_mask_res: '',
};

const TEXT_LOST = 'ข้อความในฟิลด์นี้เป็น "?" ตั้งแต่ไฟล์ต้นทาง — โปรแกรมที่บันทึกไฟล์แปลงอักษรไทยทิ้งไปแล้ว เลือกการเข้ารหัสไหนก็กู้ไม่ได้ · ใช้ฟิลด์รหัส (เช่น *_IDN) แทน, ใช้ชั้นขอบเขตพื้นฐาน GISTDA หรือส่งออกไฟล์ใหม่จากต้นฉบับเป็น UTF-8';

// ตัวเลือกพื้นที่ศึกษาแยกหมวด: พื้นฐาน (เช่น ประเทศไทย) ขึ้นก่อน แล้วค่อยที่ผู้ใช้สร้างเอง
function aoiOptions(aois, { val = a => a.id, text = a => `${esc(a.name)} · ${fmt(a.area_km2, 0)} ตร.กม.`, sel = null } = {}) {
  const o = a => `<option value="${val(a)}" ${sel != null && String(val(a)) === String(sel) ? 'selected' : ''}>${text(a)}</option>`;
  const b = aois.filter(a => a.builtin), u = aois.filter(a => !a.builtin);
  return (b.length ? `<optgroup label="พื้นที่ศึกษาพื้นฐาน">${b.map(o).join('')}</optgroup>` : '')
    + (u.length ? `<optgroup label="พื้นที่ศึกษาที่สร้างเอง" data-user="1">${u.map(o).join('')}</optgroup>` : '');
}

// ตัวเลือกชุดข้อมูลแบบดรอปดาวน์ค้นหาได้: กดแล้วเปิดกล่อง (ค้นหาชื่อ/#id + กรองโฟลเดอร์ รวมโฟลเดอร์ย่อย) → คลิก/Enter เลือก
//   <select> เดิมยังอยู่ (ซ่อน) เป็นที่เก็บค่า → โค้ดเดิมที่อ่าน sel.value / ฟัง change ใช้ได้เหมือนเดิม
//   blank = ข้อความตัวเลือกค่าว่าง (null = ไม่มีตัวเลือกว่าง) · extra = ตัวเลือกคงที่ (HTML) ต่อจากค่าว่าง · group = หัวหมวดของชุดข้อมูล
function dsPicker(sel, list, FOL, optFn, blank = '— เลือก —', extra = '', group = null) {
  const pathName = id => { const o = []; let f = FOL.find(x => x.id === id); while (f) { o.unshift(f.name); f = FOL.find(x => x.id === f.parent_id); } return o.join(' / '); };
  const sub = id => { const s = new Set([id]); let grew = true; while (grew) { grew = false; FOL.forEach(f => { if (s.has(f.parent_id) && !s.has(f.id)) { s.add(f.id); grew = true; } }); } return s; };
  const box = document.createElement('div');
  box.className = 'cbx';
  box.innerHTML = `<button type="button" class="cbx-btn"><span class="cbx-t"></span><span class="cbx-c">▼</span></button>
    <div class="cbx-pop hide"><div class="cbx-bar">${FOL.length ? '<select class="dsp-f" title="โฟลเดอร์"></select>' : ''}<input type="search" class="dsp-q" placeholder="ค้นหาชื่อชุดข้อมูล หรือ #id" autocomplete="off"></div>
    <div class="cbx-list" role="listbox"></div></div>`;
  sel.before(box);
  sel.classList.add('hide');
  const btn = box.querySelector('.cbx-btn'), pop = box.querySelector('.cbx-pop'), lst = box.querySelector('.cbx-list'), tx = box.querySelector('.cbx-t');
  const q = box.querySelector('.dsp-q'), fs = box.querySelector('.dsp-f');
  const desc = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value');
  const label = () => {
    const o = sel.options[sel.selectedIndex];
    tx.textContent = o ? o.textContent : (blank || '— เลือก —');
    tx.classList.toggle('muted', !o || !o.value);
    btn.disabled = sel.disabled;
  };
  // ตั้งค่าจากโค้ด (sel.value = …) หรือสร้างตัวเลือกใหม่ → ป้ายบนปุ่มตามทันที
  Object.defineProperty(sel, 'value', { configurable: true, get() { return desc.get.call(this); }, set(v) { desc.set.call(this, v); label(); } });
  new MutationObserver(label).observe(sel, { childList: true, subtree: true, attributes: true, attributeFilter: ['disabled'] });
  sel.addEventListener('change', label);
  const byName = (a, b) => a.name.localeCompare(b.name, 'th');
  const drawFolders = fv => {
    if (!fs) return;
    const id = fv && fv !== 'root' ? +fv : null, cur = FOL.find(f => f.id === id), par = cur ? FOL.find(f => f.id === cur.parent_id) : null;
    const kids = FOL.filter(f => (f.parent_id || null) === id).sort(byName);
    const nk = f => FOL.some(x => x.parent_id === f.id) ? ' ›' : '';
    fs.innerHTML = `<option value="">ทุกโฟลเดอร์</option>`
      + (cur ? (par ? `<option value="${par.id}" translate="no">↑ ${esc(pathName(par.id))}</option>` : '')
        + `<option value="${cur.id}" translate="no">▾ ${esc(pathName(cur.id))}</option>` : `<option value="root">นอกโฟลเดอร์ (ชั้นนอกสุด)</option>`)
      + kids.map(f => `<option value="${f.id}" translate="no">${cur ? '    ' : ''}${esc(f.name)}${nk(f)}</option>`).join('');
    fs.value = fv;
  };
  drawFolders('');
  let hi = -1;
  const items = () => [...lst.querySelectorAll('.cbx-it:not(.dis)')];
  const mark = i => {
    const it = items();
    hi = Math.max(0, Math.min(i, it.length - 1));
    it.forEach((x, k) => x.classList.toggle('on', k === hi));
    it[hi]?.scrollIntoView({ block: 'nearest' });
  };
  const it = o => `<div class="cbx-it${o.disabled ? ' dis' : ''}${o.value === sel.value && o.value ? ' cur' : ''}" data-v="${esc(o.value)}" translate="no">${esc(o.textContent)}</div>`;
  const apply = () => {
    const t = q.value.trim().toLowerCase(), fv = fs ? fs.value : '', cur = sel.value;
    drawFolders(fv);
    const inF = fv === '' ? null : fv === 'root' ? new Set([null]) : sub(+fv);
    const show = list.filter(d => String(d.id) === cur || ((!inF || inF.has(d.folder_id || null)) && (!t || d.name.toLowerCase().includes(t) || ('#' + d.id).includes(t))));
    const body = show.map(optFn).join('') + (show.length > (show.some(d => String(d.id) === cur) ? 1 : 0) ? '' : '<option disabled>ไม่พบชุดข้อมูลที่ตรงเงื่อนไข</option>');
    sel.innerHTML = (blank != null ? `<option value="">${blank}</option>` : '') + extra + (group ? `<optgroup label="${group}">${body}</optgroup>` : body);
    desc.set.call(sel, cur);
    // รายการในกล่องสร้างจาก <option> (ข้อความเดียวกับตัวเลือกเดิม) · หัวหมวดจาก <optgroup>
    lst.innerHTML = [...sel.children].map(n => n.tagName === 'OPTGROUP'
      ? `<div class="cbx-g">${esc(n.label)}</div>` + [...n.children].map(it).join('') : it(n)).join('');
    label();
    mark(Math.max(0, items().findIndex(x => x.dataset.v === cur)));
  };
  const outside = e => { if (!box.contains(e.target)) close(); };
  const close = () => { pop.classList.add('hide'); document.removeEventListener('mousedown', outside); };
  const open = () => {
    if (sel.disabled) return;
    q.value = '';
    apply();
    pop.classList.remove('hide');
    document.addEventListener('mousedown', outside);
    q.focus();
  };
  const choose = v => {
    const ch = v !== sel.value;
    desc.set.call(sel, v);
    label(); close(); btn.focus();
    if (ch) sel.dispatchEvent(new Event('change', { bubbles: true }));
  };
  btn.onclick = () => pop.classList.contains('hide') ? open() : close();
  btn.onkeydown = e => { if (['ArrowDown', 'Enter', ' '].includes(e.key)) { e.preventDefault(); open(); } };
  lst.onmousedown = e => { const x = e.target.closest('.cbx-it'); if (x && !x.classList.contains('dis')) { e.preventDefault(); choose(x.dataset.v); } };
  q.oninput = apply;
  if (fs) fs.onchange = () => { apply(); q.focus(); };
  q.onkeydown = e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); mark(hi + 1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); mark(hi - 1); }
    else if (e.key === 'Enter') { e.preventDefault(); const x = items()[hi]; if (x) choose(x.dataset.v); }
    else if (e.key === 'Escape') { e.preventDefault(); close(); btn.focus(); }
  };
  if (!sel.options.length) apply(); else label();        // <select> ว่าง → สร้างตัวเลือกครั้งแรก
}

// ช่องค้นหาในรายการติ๊กเลือก (กล่อง "เพิ่มชั้นข้อมูล"): <input class="cl-q"> วางก่อน .checklist → กรองตามชื่อ ซ่อนหัวหมวดที่ไม่เหลือรายการ
document.addEventListener('input', e => {
  if (!e.target.classList?.contains('cl-q')) return;
  const t = e.target.value.trim().toLowerCase(), cl = e.target.nextElementSibling;
  let head = null, any = false;
  const flush = () => { if (head) head.classList.toggle('hide', !any); };
  [...cl.children].forEach(n => {
    if (n.tagName === 'LABEL') { const ok = !t || n.textContent.toLowerCase().includes(t); n.classList.toggle('hide', !ok); any ||= ok; }
    else { flush(); head = n; any = false; }
  });
  flush();
});
const CL_Q = '<input type="search" class="cl-q" placeholder="ค้นหาชื่อชั้นข้อมูล" autocomplete="off" style="width:100%;margin-bottom:8px">';

async function pageBiv() {
  const [all, aois, , fr] = await Promise.all([api(ENGINE + '/api/datasets'), api(ENGINE + '/api/aoi'), loadPals(), api(ENGINE + '/api/folders').catch(() => ({ folders: [] }))]);
  const list = all.filter(d => d.kind === 'raster' || (isHex(d) && d.role !== 'map'));
  const qh = +new URLSearchParams(location.hash.split('?')[1] || '').get('hex');
  if (qh && list.some(d => d.id === qh)) { BIV.out = 'hex'; if (!isHex(list.find(d => d.id === BIV.x.dataset_id))) { BIV.x.dataset_id = qh; BIV.x.method = 'quantile'; } }
  if (!BIV.pal) BIV.pal = 'b:' + STATE.default_palette;
  const v = $('#view');
  const opt = (sel, arr = list) => arr.map(d => isHex(d) ? `<option value="${d.id}" ${d.id == sel ? 'selected' : ''}>⬡ #${d.id} ${esc(d.name)} · หกเหลี่ยม ${fmt(d.meta.hex.d_km, 3)} กม.</option>`
    : `<option value="${d.id}" ${d.id == sel ? 'selected' : ''}>#${d.id} ${esc(d.name)} · ${esc(d.meta.res_label.split(' (')[0])} · ${esc(VT_SHORT[d.value_type] || '')}${d.value_type_confirmed ? '' : ' (ยังไม่ยืนยัน)'}</option>`).join('');
  v.innerHTML = head('Bivariate', 'สร้างแผนที่ไบแวเรียต', 'ไขว้ข้อมูล 2 ชุด → ตาราง nX × nY สี · ผลเป็น GeoTIFF + QML + legend + สถิติ + lineage')
    + `<div class="steps">
    <div class="step"><div class="cols2">
      ${['x', 'y'].map(ax => `<div class="card axis" id="ax_${ax}" style="--c:${ax === 'x' ? 'var(--sky)' : 'var(--rose)'}">
        <div class="card-head"><h2>แกน ${ax.toUpperCase()} <span class="muted small">${ax === 'x' ? 'ซ้าย → ขวา' : 'ล่าง → บน'}</span></h2></div>
        <div class="grid-form">
          <div class="field full"><span>ชุดข้อมูล</span><select data-k="dataset_id"><option value="">— เลือก —</option>${opt(BIV[ax].dataset_id)}</select></div>
          <label class="field full hexF hide"><span>คอลัมน์ค่าในชุดหกเหลี่ยม</span><select data-k="field"></select></label>
          <label class="field"><span>ชื่อแกน</span><input type="text" data-k="label" value="${esc(BIV[ax].label)}" placeholder="เช่น ประชากร"></label>
          <label class="field"><span>จำนวนคลาส</span><select data-k="n">${[1, 2, 3, 4, 5].map(n => `<option ${n == BIV[ax].n ? 'selected' : ''}>${n}</option>`).join('')}</select></label>
          <label class="field"><span>วิธีแบ่ง</span><select data-k="method"><option value="breaks">กำหนดเกณฑ์เอง</option><option value="quantile">ควอนไทล์</option><option value="equal">ช่วงเท่ากัน</option><option value="degurba">DEGURBA กลุ่มช่อง (1 กม.)</option></select></label>
          <label class="field metricL"><span>ค่าที่ใช้</span><select data-k="metric"><option value="density">ความหนาแน่น (ต่อ ตร.กม.)</option><option value="per_pixel">ค่าต่อพิกเซล</option><option value="value">ค่าตามไฟล์</option></select></label>
          <div class="field full brk"></div>
          <label class="field full"><span>ลำดับเมื่อลดความละเอียด</span><select data-k="order"><option value="auto">อัตโนมัติตามประเภทค่า</option><option value="classify_first">จัดชั้นก่อน แล้ว majority</option></select></label>
        </div>
        <div class="info tiny muted" style="margin-top:8px"></div>
        <canvas class="hist"></canvas><div class="shares small"></div>
      </div>`).join('')}
    </div></div>
    <div class="step"><div class="card">
      <div class="card-head"><h2>สี</h2><div class="row"><button class="sm ghost" id="pSave">${IC.download}บันทึกพาเลท</button><button class="sm ghost" id="pExp">ส่งออก</button><button class="sm ghost" id="pImp">นำเข้า</button><button class="sm ghost" id="palReset">${IC.refresh}คืนสี</button></div></div>
      <div class="cols2" style="grid-template-columns:1.3fr 1fr">
        <div><div class="row"><div class="cur-pal" id="curPal"></div><button class="sm" id="palToggle">${IC.palette}เปลี่ยนพาเลท</button></div><div class="pals hide" id="pals" style="margin-top:12px"></div><div class="small" id="palNote" style="margin-top:10px"></div></div>
        <div><div id="legend"></div>
          <div class="row" style="margin-top:14px"><label class="switch"><input type="checkbox" id="hlMode"><i></i><span class="small">โหมดเลือกเขตเน้น</span></label><span class="small muted" id="hlText"></span></div>
          <div class="tiny muted" style="margin-top:4px">ปกติคลิกช่อง = แก้สี · เปิดโหมดเขตเน้นแล้วคลิกช่องที่ต้องการนับแยก</div></div>
      </div></div></div>
    <div class="step"><div class="card">
      <div class="card-head"><h2>พื้นที่และผลลัพธ์</h2><div class="seg" id="outSeg"><button data-o="raster">${IC.raster}กริดสี่เหลี่ยม (raster)</button><button data-o="hex">${IC.hex}หกเหลี่ยม (hex)</button></div></div>
      <div class="cols2">
        <div class="grid-form" style="align-content:start">
          <label class="field full hexOnly"><span>ขนาดหกเหลี่ยม (กม. ระหว่างศูนย์กลาง)</span><input type="number" id="hxSizeB" min="0.01" step="any" value="${BIV.size_km}"><span class="tiny muted" id="hxNoteB"></span></label>
          <label class="field full"><span>พื้นที่ศึกษา</span><select id="aoi"><option value="">ทั้งขอบเขตข้อมูล</option>${aoiOptions(aois)}</select></label>
          <label class="field rasOnly"><span>กติกาตัดพื้นที่</span><select id="aoiRule"><option value="center">ศูนย์กลางพิกเซล</option><option value="touch">แตะ</option></select></label>
          <label class="field rasOnly"><span>ตัดพื้นที่อิงพิกเซลขนาด</span><select id="aoiMask"></select></label>
          <label class="field full rasOnly"><span>ความละเอียดผลลัพธ์</span><select id="res"></select><span class="tiny muted" id="resNote"></span></label>
          <label class="field rasOnly"><span>เสมอกันใน majority</span><select id="tie"><option value="high">ชั้นที่สูงกว่า</option><option value="low">ชั้นที่ต่ำกว่า</option></select></label>
          <label class="field rasOnly"><span>ค่านับรวม = 0</span><select id="cdv"><option value="positive">ไม่ให้รหัส (แบบงานเดิม)</option><option value="any">ให้รหัสถ้ามีข้อมูล</option></select></label>
          <label class="field rasOnly"><span>น้ำหนักสถิติ</span><select id="wds"><option value="">อัตโนมัติ (แกนจำนวนนับ)</option>${list.filter(d => d.value_type === 'count').map(d => `<option value="${d.id}">#${d.id} ${esc(d.name)}</option>`).join('')}</select></label>
          <label class="field"><span>ชื่อผลลัพธ์</span><input type="text" id="bname" value="${esc(BIV.name)}" placeholder="flood_pop_10m"></label>
          <div class="full tiny muted"><a href="#/aoi">+ สร้างพื้นที่ศึกษา (จังหวัด / อำเภอ / ตำบล / วาดเอง)</a></div>
        </div>
        <div><div id="aoiMap" class="mapbox sm"></div><div class="tiny muted" style="margin-top:6px">พรีวิวขอบเขตบนภาพดาวเทียม</div></div>
      </div></div></div>
    <div class="step"><div class="card">
      <div class="card-head"><h2>ตรวจและสร้าง</h2></div>
      <div id="est" class="small muted">กด "ตรวจค่าที่ตั้ง" เพื่อดูขนาดผลลัพธ์ก่อนรัน</div>
      <div class="row" style="margin-top:14px"><button id="check">${IC.check}ตรวจค่าที่ตั้ง</button><button id="run" class="primary">${IC.play}สร้างแผนที่</button><span class="spacer"></span><button id="sensT" class="ghost rasOnly">${IC.layers}เทียบหลายค่าที่ตั้ง…</button></div>
      <div id="sens" class="hide" style="margin-top:16px;padding-top:14px;border-top:1px solid var(--line)">
        <h3 style="margin-top:0">เทียบหลายค่าที่ตั้ง <span class="tiny muted">ดูว่าตัวเลขเขตเน้นเปลี่ยนแค่ไหนเมื่อเปลี่ยนเกณฑ์/ความละเอียด (สถิติอย่างเดียว ไม่สร้างแผนที่)</span></h3>
        <div class="grid-form">
          <label class="field"><span>ชุดเกณฑ์แกน X (บรรทัดละชุด)</span><textarea id="sX" placeholder="300, 1500&#10;200, 1000"></textarea></label>
          <label class="field"><span>ชุดเกณฑ์แกน Y (บรรทัดละชุด)</span><textarea id="sY" placeholder="1, 5&#10;1, 3"></textarea></label>
          <div class="field full"><span>ความละเอียด</span><div class="checklist" id="sR" style="max-height:140px"></div></div>
        </div>
        <div class="row" style="margin-top:10px"><button id="sRun" class="mint">${IC.play}เริ่มเทียบ</button><span class="tiny muted" id="sN"></span></div></div>
    </div></div></div>`;

  const dsOf = id => list.find(d => d.id == id);
  const readAxis = ax => {
    const el = $('#ax_' + ax), c = BIV[ax];
    $$('[data-k]', el).forEach(i => { const k = i.dataset.k; if (k === 'field' && i.closest('.hide')) return; c[k] = ['n', 'dataset_id'].includes(k) ? (i.value === '' ? null : +i.value) : i.value; });
    c.breaks = $$('.brk input', el).map(i => parseFloat(i.value)).filter(x => !isNaN(x));
  };
  const axisColors = ax => BIV.colors ? (ax === 'x' ? Array.from({ length: BIV.x.n }, (_, i) => BIV.colors[i]) : Array.from({ length: BIV.y.n }, (_, i) => BIV.colors[i * BIV.x.n])) : [];
  const drawAxis = ax => {
    const el = $('#ax_' + ax), c = BIV[ax], d = dsOf(c.dataset_id);
    const hx = isHex(d);
    $('.hexF', el).classList.toggle('hide', !hx);
    if (hx) {
      const fs = hexFields(d);
      if (!fs.some(f => f.c === c.field)) c.field = (fs.find(f => f.main && f.vt === 'count' && fs.some(g => g.c === f.c + '_km2')) ? fs.find(f => f.main).c + '_km2' : fs.find(f => f.main)?.c) || fs[0]?.c;
      $('[data-k="field"]', el).innerHTML = fs.map(f => `<option value="${f.c}">${esc(f.name)} · ${esc(f.t)} (${esc(f.c)})</option>`).join('');
      if (c.method === 'degurba') c.method = 'quantile';
    }
    $$('[data-k]', el).forEach(i => { if (c[i.dataset.k] != null) i.value = c[i.dataset.k]; });
    $('.metricL', el).classList.toggle('hide', !(d && d.value_type === 'count') || hx);
    $('[data-k="order"]', el).closest('.field').classList.toggle('hide', hx || BIV.out === 'hex');
    $('[data-k="method"] option[value="degurba"]', el).disabled = BIV.out === 'hex';
    if (d && d.value_type !== 'count' && c.metric !== 'value') { c.metric = 'value'; }
    const need = c.method === 'breaks' ? c.n - 1 : 0;
    while (c.breaks.length < need) c.breaks.push((c.breaks.at(-1) || 0) + 1);
    c.breaks = c.breaks.slice(0, need);
    $('.brk', el).innerHTML = need ? `<span>เกณฑ์ (ค่าเท่าเกณฑ์ขึ้นชั้นบน)</span><div class="row">${c.breaks.map(b => `<input type="number" step="any" value="${b}" style="width:110px">`).join('')}</div>`
      : `<span class="tiny muted">${c.method === 'degurba' ? 'กลุ่มเมือง ≥300 ติดกัน 8 ทิศ รวม ≥5,000 · ศูนย์กลางเมือง ≥1,500 ติดกัน 4 ทิศ รวม ≥50,000' : c.n === 1 ? 'แกนนี้ไม่แบ่ง (แผนที่ตัวแปรเดียว)' : 'เกณฑ์คำนวณจากค่าสุ่มตอนรัน'}</span>`;
    $$('.brk input', el).forEach(i => i.onchange = () => { readAxis(ax); preview(ax); });
    $('.info', el).innerHTML = hx ? `ชุดหกเหลี่ยม ${fmt(d.meta.hex.d_km, 3)} กม. · ${esc(d.meta.hex.crs_label || '')} — อีกแกนเป็น raster ได้ (จะรวมค่าลงช่องเดียวกันให้)`
      : d ? `${esc(VT[d.value_type])} — ${esc(VT_RULE[d.value_type])}${d.value_type_confirmed ? '' : ' <b style="color:var(--coral)">· ยังไม่ยืนยันประเภทค่า</b>'}${d.meta.nodata != null ? ` · nodata ${d.meta.nodata}${d.nodata_as != null ? ' → นับเป็น ' + d.nodata_as : ''}` : ''}` : '';
  };
  const pvTimer = {};
  const preview = ax => {
    clearTimeout(pvTimer[ax]);
    pvTimer[ax] = setTimeout(async () => {
      const el = $('#ax_' + ax), c = BIV[ax];
      const cv = $('canvas', el), sh = $('.shares', el);
      if (!c.dataset_id || isHex(dsOf(c.dataset_id))) { sh.innerHTML = c.dataset_id ? '<span class="tiny muted">ชุดหกเหลี่ยม — เกณฑ์ควอนไทล์คำนวณจากค่าของช่องตอนรัน</span>' : ''; cv.getContext('2d').clearRect(0, 0, cv.width, cv.height); return; }
      try {
        const r = await api(ENGINE + '/api/classes-preview', { json: { dataset_id: c.dataset_id, cfg: c } });
        const cols = axisColors(ax);
        histCanvas(cv, r.hist, r.breaks, cols);
        const bar = (arr, t) => `<div class="tiny muted">${t}</div><div class="share">${arr.map((s, i) => `<div style="width:${s * 100}%;background:${cols[i] || '#c3b6ff'}" title="คลาส ${i + 1}: ${(s * 100).toFixed(1)}%">${s > .07 ? (s * 100).toFixed(1) + '%' : ''}</div>`).join('')}</div>`;
        sh.innerHTML = bar(r.pixel_share, 'สัดส่วนพิกเซลต่อคลาส') + (r.value_share ? bar(r.value_share, 'สัดส่วนค่านับ (เช่น คน) ต่อคลาส') : '')
          + `<div class="tiny muted">${fmt(r.n, 0)} ค่าสุ่ม ที่ความละเอียดต้นทาง · เกณฑ์ ${r.breaks.map(b => fmt(b, 4)).join(' / ') || '–'}${r.note ? ' · ' + esc(r.note) : ''}</div>`;
      } catch (e) { sh.innerHTML = `<span class="tiny muted">${esc(e.message)}</span>`; }
    }, 250);
  };
  const drawPal = (reset = false) => {
    const nx = BIV.x.n, ny = BIV.y.n;
    const ch = palChoices(nx, ny);
    let cur = ch.find(p => p.key === BIV.pal);
    if (!cur) { BIV.pal = 'b:' + STATE.default_palette; cur = ch.find(p => p.key === BIV.pal); reset = true; }
    if (reset || !BIV.colors || BIV.colors.length !== nx * ny) BIV.colors = cur.colors.slice();
    BIV.highlight = BIV.highlight.filter(c => c <= nx * ny);
    $('#curPal').innerHTML = `<div class="mini" style="grid-template-columns:repeat(${nx},14px)">${Array.from({ length: ny }, (_, yy) => Array.from({ length: nx }, (_, x) => `<i style="background:${BIV.colors[(ny - 1 - yy) * nx + x]}"></i>`).join('')).join('')}</div><span>${esc(cur.name)}</span>`;
    $('#pals').classList.toggle('hide', !BIV.showPals);
    $('#palToggle').classList.toggle('on', !!BIV.showPals);
    palGallery($('#pals'), nx, ny, BIV.pal, p => { BIV.pal = p.key; drawPal(true); },
      async pid => { await api(ENGINE + '/api/palettes/' + pid, { method: 'DELETE' }); await loadPals(); drawPal(); });
    $('#palNote').innerHTML = `${esc(cur.src || '')} ${cur.cb === true ? '<span class="chip ok">ปลอดภัยต่อตาบอดสี</span>' : cur.cb === false ? '<span class="chip warn">มีเขียว-แดง ไม่ปลอดภัยต่อตาบอดสี</span>' : ''}`
      + (cur.grad === false && (nx !== 3 || ny !== 3) ? ' <span class="chip warn">ไม่ใช่ไล่สีแท้ ขนาดอื่นอาจดูแปลก</span>' : '')
      + (nx * ny > 16 ? ' <span class="chip warn">เกิน 4×4 อ่านยาก</span>' : '') + ((nx !== 3 || ny !== 3) && !cur.custom ? ' <span class="tiny muted">· ไล่สีจาก 3×3 แบบ OKLab</span>' : '');
    $('#legend').innerHTML = legendHtml(nx, ny, BIV.colors, BIV.highlight, BIV.x.label || dsOf(BIV.x.dataset_id)?.name, BIV.y.label || dsOf(BIV.y.dataset_id)?.name, !BIV.hlMode);
    $$('#legend .cell input').forEach(inp => inp.oninput = () => { BIV.colors[+inp.dataset.i] = inp.value; inp.parentElement.style.background = inp.value; });
    $$('#legend .cell').forEach(c => c.onclick = () => {
      if (!BIV.hlMode) return;
      const k = +c.dataset.code; BIV.highlight = BIV.highlight.includes(k) ? BIV.highlight.filter(x => x !== k) : [...BIV.highlight, k].sort((a, b) => a - b); drawPal();
    });
    $('#hlText').textContent = 'เขตเน้น: ' + (BIV.highlight.join(', ') || 'ไม่มี');
    ['x', 'y'].forEach(preview);
  };
  let resOpts = [];
  const fillMask = () => {
    const tr = $('#res').value;
    const cur = resOpts.find(o => o.value === tr);
    const coarse = resOpts.filter(o => cur && o.px <= cur.px);
    $('#aoiMask').innerHTML = `<option value="">เท่าผลลัพธ์</option>` + coarse.filter(o => o.value !== tr).map(o => `<option value="${o.value}">${esc(o.label.split(' (')[0])}${o.is_source.length ? ' (= ข้อมูล #' + o.is_source.join(', #') + ')' : ''}</option>`).join('');
    $('#aoiMask').value = coarse.some(o => o.value === BIV.aoi_mask_res) ? BIV.aoi_mask_res : '';
  };
  const setOut = o => {
    if ([BIV.x, BIV.y].some(c => isHex(dsOf(c.dataset_id)))) o = 'hex';       // แกนเป็นชุดหกเหลี่ยม → ผลต้องเป็นหกเหลี่ยม
    BIV.out = o;
    $$('#outSeg button').forEach(b => b.classList.toggle('on', b.dataset.o === o));
    $$('.rasOnly').forEach(e => e.classList.toggle('hide', o === 'hex'));
    $$('.hexOnly').forEach(e => e.classList.toggle('hide', o !== 'hex'));
    const ref = [BIV.x, BIV.y].map(c => dsOf(c.dataset_id)).find(isHex);
    $('#hxSizeB').disabled = !!ref;
    if (ref) $('#hxSizeB').value = ref.meta.hex.d_km;
    const s = +$('#hxSizeB').value;
    $('#hxNoteB').textContent = ref ? `ใช้กริดของ "${ref.name}" (${fmt(ref.meta.hex.d_km, 3)} กม.)` : s > 0 ? `≈ ${fmt(Math.sqrt(3) / 2 * s * s, 3)} ตร.กม./ช่อง · ประชากร (นับ) รวมเป็นต่อ ตร.กม. ของช่อง` : '';
    ['x', 'y'].forEach(drawAxis);
  };
  const loadRes = async () => {
    setOut(BIV.out);
    if (BIV.out === 'hex') return;
    const ids = [BIV.x.dataset_id, BIV.y.dataset_id].filter(Boolean);
    const sel = $('#res');
    if (ids.length < 2) { sel.innerHTML = '<option value="">เลือกชุดข้อมูลทั้งสองแกนก่อน</option>'; $('#aoiMask').innerHTML = '<option value="">เท่าผลลัพธ์</option>'; return; }
    try {
      const r = await api(ENGINE + '/api/res-options?ids=' + ids.join(','));
      resOpts = r.options;
      const finer = r.options.filter(o => o.is_source.length).map(o => o.value)[0];
      sel.innerHTML = r.options.map(o => `<option value="${o.value}">${esc(o.label)} · ${pxLabel(o.px)}${o.is_source.length ? ' · = ข้อมูล #' + o.is_source.join(', #') : ''}</option>`).join('');
      sel.value = BIV.target_res && r.options.some(o => o.value === BIV.target_res) ? BIV.target_res : finer;
      $('#resNote').textContent = 'เสนอเฉพาะพหุคูณจำนวนเต็มของทั้งสองชุด (แม่-ลูกแม่นยำ)';
      fillMask();
    } catch (e) { sel.innerHTML = ''; $('#resNote').innerHTML = `<span style="color:var(--coral)">${esc(e.message)}</span>`; }
  };
  // เปลี่ยนชุดข้อมูล → เสนอเกณฑ์จากข้อมูลจริง (ควอนไทล์ที่ทนค่าซ้ำ ปัดเลขสวย) แทนเกณฑ์ประชากร 300/1500 ที่ไม่เข้ากับค่า 0–1
  const niceBreaks = bs => {
    for (let sig = 2; sig <= 6; sig++) {
      const r = bs.map(b => +Number(b).toPrecision(sig));
      if (r.every((v, i) => i === 0 || v > r[i - 1])) return r;
    }
    return bs;
  };
  const suggestBreaks = async ax => {
    const c = BIV[ax], d = dsOf(c.dataset_id);
    if (!d || c.n < 2) return;
    if (isHex(d)) { if (c.method === 'breaks') c.method = 'quantile'; return; }
    if (d.value_type === 'count') { c.metric = 'density'; if (c.method === 'breaks' && c.n === 3) c.breaks = [300, 1500]; if (c.method === 'breaks' && c.n === 3) return; }
    else c.metric = 'value';
    if (c.method !== 'breaks') return;
    try {
      const r = await api(ENGINE + '/api/classes-preview', { json: { dataset_id: d.id, cfg: { ...c, method: 'quantile' } } });
      if (r.breaks?.length === c.n - 1) c.breaks = niceBreaks(r.breaks);
    } catch (e) { toast(`${d.name}: ${e.message}`, true); }
  };
  // พรีวิวพื้นที่ศึกษา
  const amap = baseMap('aoiMap', { zoomControl: false, attributionControl: false });
  amap.setView([13.2, 100.9], 5);
  let aLayer = null;
  const showAoi = async () => {
    if (aLayer) { amap.removeLayer(aLayer); aLayer = null; }
    const id = $('#aoi').value;
    if (!id) { amap.setView([13.2, 100.9], 5); return; }
    const gj = await api(`${ENGINE}/api/aoi/${id}.geojson`);
    aLayer = L.geoJSON(gj, { style: { color: '#f6e3a1', weight: 2, fillColor: '#c3b6ff', fillOpacity: .15 } }).addTo(amap);
    amap.fitBounds(aLayer.getBounds(), { padding: [10, 10] });
  };

  ['x', 'y'].forEach(ax => {
    const el = $('#ax_' + ax);
    dsPicker($('[data-k="dataset_id"]', el), list, fr.folders || [], d => opt(null, [d]));
    $$('[data-k]', el).forEach(i => i.onchange = async () => {
      readAxis(ax);
      if (i.dataset.k === 'dataset_id' || (i.dataset.k === 'n' && BIV[ax].method === 'breaks')) await suggestBreaks(ax);
      drawAxis(ax); preview(ax);
      if (i.dataset.k === 'n') drawPal(true);
      if (i.dataset.k === 'dataset_id') loadRes();
      if (i.dataset.k === 'label') drawPal();
    });
    drawAxis(ax);
  });
  $('#hlMode').checked = BIV.hlMode;
  $('#hlMode').onchange = () => { BIV.hlMode = $('#hlMode').checked; drawPal(); };
  $('#palReset').onclick = () => drawPal(true);
  $('#palToggle').onclick = () => { BIV.showPals = !BIV.showPals; drawPal(); };
  $('#pSave').onclick = async () => { if (await savePalette(BIV.x.n, BIV.y.n, BIV.colors)) drawPal(); };
  $('#pExp').onclick = () => exportPalette(BIV.x.n, BIV.y.n, BIV.colors, BIV.name || 'palette');
  $('#pImp').onclick = async () => { const p = await importPalette(); if (p) { if (p.nx !== BIV.x.n || p.ny !== BIV.y.n) toast(`พาเลทนี้ ${p.nx}×${p.ny} — ปรับจำนวนคลาสให้ตรงเพื่อใช้`); drawPal(); } };
  $('#tie').value = BIV.tie; $('#cdv').value = BIV.count_down_valid; $('#aoi').value = BIV.aoi_id || ''; $('#aoiRule').value = BIV.aoi_rule;
  $('#aoi').onchange = () => { BIV.aoi_id = +$('#aoi').value || null; showAoi(); };
  $('#res').onchange = () => { BIV.target_res = $('#res').value; fillMask(); };
  $$('#outSeg button').forEach(b => b.onclick = () => { setOut(b.dataset.o); if (BIV.out === 'raster') loadRes(); });
  $('#hxSizeB').oninput = () => { BIV.size_km = +$('#hxSizeB').value; setOut(BIV.out); };
  const collect = () => {
    readAxis('x'); readAxis('y');
    Object.assign(BIV, { target_res: $('#res').value, tie: $('#tie').value, count_down_valid: $('#cdv').value, name: $('#bname').value.trim(),
      aoi_id: +$('#aoi').value || null, aoi_rule: $('#aoiRule').value, aoi_mask_res: $('#aoiMask').value });
    const ax = c => ({ dataset_id: c.dataset_id, n: c.n, method: c.method, breaks: c.breaks, metric: c.metric, order: c.order, label: c.label || dsOf(c.dataset_id)?.name,
      ...(isHex(dsOf(c.dataset_id)) ? { field: c.field } : {}) });
    if (BIV.out === 'hex') return { x: ax(BIV.x), y: ax(BIV.y), size_km: +$('#hxSizeB').value, aoi_id: BIV.aoi_id, colors: BIV.colors, palette: BIV.pal,
      highlight: BIV.highlight, name: BIV.name || null };
    return { x: ax(BIV.x), y: ax(BIV.y), target_res: BIV.target_res, tie: BIV.tie, count_down_valid: BIV.count_down_valid,
      colors: BIV.colors, palette: BIV.pal, highlight: BIV.highlight, name: BIV.name || null, weight_dataset_id: $('#wds').value ? +$('#wds').value : null,
      aoi_id: BIV.aoi_id, aoi_rule: BIV.aoi_rule, aoi_mask_res: BIV.aoi_mask_res || null };
  };
  $('#check').onclick = async () => {
    const p = collect();
    if (!p.x.dataset_id || !p.y.dataset_id) { $('#est').innerHTML = '<div class="note err">เลือกชุดข้อมูลทั้งสองแกน</div>'; return; }
    const e = await api(ENGINE + '/api/estimate', { json: { kind: BIV.out === 'hex' ? 'hexbiv' : 'bivariate', params: p } });
    if (!e.ok) { $('#est').innerHTML = `<div class="note err">${esc(e.error)}</div>`; return; }
    if (e.hex) { $('#est').innerHTML = `<div class="note info">${esc(e.grid.res_label)} · ประมาณ ${fmt(e.hex.n, 0)} ช่อง · ${esc(e.hex.crs)}${e.aoi ? ' · ' + esc(e.aoi) : ''}</div>` + e.warnings.map(w => `<div class="note warn">${esc(w)}</div>`).join(''); return; }
    const mode = o => o.mode === 'same' ? 'เท่าเดิม' : o.mode === 'up' ? `แตกพิกเซล ×${o.factor}` : `รวมพิกเซล ${o.factor}×${o.factor}`;
    $('#est').innerHTML = `<div class="note info">ผลลัพธ์ ${esc(e.grid.res_label)} · ${fmt(e.grid.width, 0)} × ${fmt(e.grid.height, 0)} พิกเซล${e.aoi ? ' · ' + esc(e.aoi) : ''}<br>X: ${mode(e.x)} · Y: ${mode(e.y)}</div>`
      + e.warnings.map(w => `<div class="note warn">${esc(w)}</div>`).join('');
  };
  $('#run').onclick = () => {
    const p = collect();
    if (!p.x.dataset_id || !p.y.dataset_id) return toast('เลือกชุดข้อมูลทั้งสองแกน', true);
    runJob(BIV.out === 'hex' ? 'hexbiv' : 'bivariate', p, () => location.hash = '#/jobs');
  };
  drawPal(false);
  loadRes();
  if (BIV.aoi_id) showAoi();
  // เทียบหลายค่าที่ตั้ง (3.5)
  const sets = s => s.split(/\r?\n/).map(l => l.split(',').map(parseFloat).filter(x => !isNaN(x))).filter(a => a.length);
  const sCount = () => { const n = Math.max(1, sets($('#sX').value).length) * Math.max(1, sets($('#sY').value).length) * Math.max(1, $$('#sR input:checked').length); $('#sN').textContent = `${n} ชุดค่า${n > 40 ? ' — เกิน 40' : ''}`; };
  $('#sensT').onclick = () => {
    $('#sens').classList.toggle('hide');
    if (!$('#sX').value) { readAxis('x'); readAxis('y'); $('#sX').value = BIV.x.breaks.join(', '); $('#sY').value = BIV.y.breaks.join(', '); }
    $('#sR').innerHTML = resOpts.filter(o => o.px < 3e10).map(o => `<label><input type="checkbox" value="${o.value}" ${o.value === $('#res').value ? 'checked' : ''}><span>${esc(o.label.split(' (')[0])} · ${fmt(o.px / 1e6, 1)} ล้าน</span></label>`).join('');
    $$('#sR input').forEach(i => i.onchange = sCount); sCount();
  };
  $('#sX').oninput = $('#sY').oninput = sCount;
  $('#sRun').onclick = () => {
    const base = collect();
    if (!base.x.dataset_id || !base.y.dataset_id) return toast('เลือกชุดข้อมูลทั้งสองแกน', true);
    runJob('sensitivity', { base, x_breaks_sets: base.x.method === 'degurba' ? null : sets($('#sX').value), y_breaks_sets: sets($('#sY').value),
      resolutions: $$('#sR input:checked').map(i => i.value), name: (base.name || 'เทียบค่าที่ตั้ง') }, () => location.hash = '#/jobs');
  };
}

// ================= พื้นที่ศึกษา =================
async function pageAoi(qs) {
  const [aois, all] = await Promise.all([api(ENGINE + '/api/aoi'), api(ENGINE + '/api/datasets')]);
  const vecs = all.filter(isPolySrc);
  const cur = () => vecs.find(x => x.id === dsId);
  const base = () => cur()?.kind === 'link' ? `${ENGINE}/api/links/${dsId}` : `${ENGINE}/api/datasets/${dsId}`;
  const v = $('#view');
  let dsId = +qs.get('ds') || vecs[0]?.id || null;
  v.innerHTML = head('Area of interest', 'พื้นที่ศึกษา', 'จังหวัด / อำเภอ / ตำบล จากชั้นขอบเขตใดก็ได้ในคลังข้อมูล หรือวาดโพลิกอนเอง — ใช้ตัดผลลัพธ์และคิดสถิติเฉพาะพื้นที่')
    + `<div class="cols"><div>
      <div class="card"><div class="card-head"><h2><span class="dot"></span>สร้างพื้นที่ศึกษา</h2><div class="seg" id="mode"><button data-k="ds" class="on">จากชั้นขอบเขต</button><button data-k="draw">วาดเอง</button><button data-k="coords">พิมพ์พิกัด</button></div></div>
        <div id="fromDs">
          ${vecs.length ? `<div class="grid-form">
            <label class="field full"><span>ชั้นขอบเขต</span><select id="aDs">${vecs.map(d => `<option value="${d.id}" ${d.id === dsId ? 'selected' : ''}>${srcLabel(d)}</option>`).join('')}</select></label>
            <label class="field"><span>ฟิลด์ชื่อพื้นที่</span><select id="aField"></select></label>
            <label class="field"><span>ค้นหา</span><input type="search" id="aQ" placeholder="พิมพ์ชื่อ…"></label>
          </div>
          <div class="row" style="margin:10px 0 6px"><span class="small muted" id="aCount"></span><span class="spacer"></span><button class="sm ghost" id="aAll">เลือกทั้งหมดที่ค้นเจอ</button><button class="sm ghost" id="aNone">ล้าง</button></div>
          <div class="checklist" id="aList"></div>` : `<div class="note info">ยังไม่มีชั้นขอบเขต — เพิ่มไฟล์ขอบเขต หรือ<b>ลิงก์</b> (เช่น ArcGIS FeatureServer ของ GISTDA: L05_Province / L05_Amphoe / L05_Tambon) ที่หน้าคลังข้อมูลก่อน</div>`}
        </div>
        <div id="fromCoords" class="hide">
          <textarea id="cTxt" rows="7" style="font-family:var(--mono);font-size:12.5px" placeholder="วางพิกัด บรรทัดละจุด เช่น
100.50 13.70
100.60 13.70
100.60 13.80
100.50 13.80
(หลายรูป: เว้นบรรทัดว่างคั่น · รับ WKT / GeoJSON / 100°30'15&quot;E 13°42'N / UTM ได้)"></textarea>
          <div class="grid-form" style="margin-top:8px">
            <label class="field"><span>ลำดับแกน</span><select id="cOrder"><option value="auto">อัตโนมัติ</option><option value="xy">ลองจิจูด, ละติจูด (X, Y)</option><option value="yx">ละติจูด, ลองจิจูด (Y, X)</option></select></label>
            <label class="field"><span>ระบบพิกัด</span><select id="cCrs"><option value="auto">อัตโนมัติ</option><option value="EPSG:4326">WGS 84 องศา</option><option value="EPSG:32647">UTM 47N (WGS 84)</option><option value="EPSG:32648">UTM 48N (WGS 84)</option><option value="EPSG:24047">UTM 47N (Indian 1975)</option><option value="EPSG:24048">UTM 48N (Indian 1975)</option></select></label>
          </div>
          <div id="cRes" class="small" style="margin-top:8px"><span class="muted">รูปจะแสดงบนแผนที่ทันทีที่พิมพ์ · ปิดรูปให้เอง</span></div>
        </div>
        <div id="fromDraw" class="hide"><p class="small muted" style="margin-top:0">ใช้เครื่องมือมุมซ้ายบนของแผนที่ วาดโพลิกอนหรือสี่เหลี่ยม (วาดหลายรูปได้ จะรวมเป็นพื้นที่เดียว)</p><div class="small" id="drawCount">ยังไม่ได้วาด</div></div>
        <div class="row" style="margin-top:14px"><input type="text" id="aName" placeholder="ชื่อพื้นที่ศึกษา เช่น สิงห์บุรี" style="flex:1"><button id="aSave" class="primary">${IC.check}บันทึก</button></div>
      </div>
      <div class="card"><div class="card-head"><h2><span class="dot" style="background:var(--mint);color:var(--mint)"></span>พื้นที่ที่บันทึกไว้</h2><span class="chip">${aois.length}</span></div>
        ${[['พื้นที่ศึกษาพื้นฐาน', aois.filter(a => a.builtin), 'var(--butter)'], ['พื้นที่ศึกษาที่สร้างเอง', aois.filter(a => !a.builtin), 'var(--mint)']].map(([t, xs, c]) => `
          <h3 class="aoi-sec" style="--c:${c}">${t} <span class="chip">${xs.length}</span></h3>
          ${xs.length ? `<table><tbody>${xs.map(a => `<tr data-a="${a.id}" style="cursor:pointer"><td><b translate="no">${esc(a.name)}</b><div class="tiny muted">${a.source?.type === 'base' ? esc(a.source.description || '') : a.source?.type === 'drawn' ? 'วาดเอง' : a.source?.type === 'coords' ? `พิมพ์พิกัด · ${a.source.points} จุด · ${esc(a.source.crs)}` : `<span translate="no">${esc(a.source?.dataset_name || '')} · ${esc(a.source?.field || '')} = ${esc((a.source?.values || []).slice(0, 4).join(', '))}${(a.source?.values || []).length > 4 ? ' …' : ''}</span>`}</div></td>
          <td class="small">${fmt(a.area_km2, 1)} ตร.กม.</td><td style="text-align:right"><button class="sm ghost danger" data-del="${a.id}">${IC.trash}</button></td></tr>`).join('')}</tbody></table>`
          : c === 'var(--butter)'
            ? `<div class="empty small">ยังไม่มี — สร้างจากชั้นขอบเขตจังหวัด GISTDA (ต้องต่ออินเทอร์เน็ต) <button class="sm" id="aBase">${IC.refresh}สร้างพื้นที่ศึกษาพื้นฐาน</button></div>`
            : '<div class="empty">ยังไม่มี</div>'}`).join('')}
      </div></div>
      <div class="card sticky"><div class="mapbar"><div class="seg" id="bm"><button data-k="gh">ดาวเทียม</button><button data-k="osm">แผนที่</button><button data-k="none">ไม่มี</button></div><span class="tiny muted" id="mapNote"></span></div>
        <div id="map" class="mapbox"></div></div></div>`;
  const mp = baseMap('map'); bmSeg(mp, $('#bm'));
  mp.setView([13.2, 100.9], 6);
  const drawn = new L.FeatureGroup().addTo(mp);
  const drawCtl = new L.Control.Draw({ draw: { polygon: { shapeOptions: { color: '#f6e3a1' } }, rectangle: { shapeOptions: { color: '#f6e3a1' } }, polyline: false, circle: false, marker: false, circlemarker: false }, edit: { featureGroup: drawn } });
  let mode = 'ds';
  const setMode = k => {
    mode = k; $$('#mode button').forEach(b => b.classList.toggle('on', b.dataset.k === k));
    $('#fromDs').classList.toggle('hide', k !== 'ds'); $('#fromDraw').classList.toggle('hide', k !== 'draw'); $('#fromCoords').classList.toggle('hide', k !== 'coords');
    if (cLayer && k !== 'coords') { mp.removeLayer(cLayer); cLayer = null; } else if (k === 'coords') parseCoords();
    if (k === 'draw') mp.addControl(drawCtl); else mp.removeControl(drawCtl);
  };
  $$('#mode button').forEach(b => b.onclick = () => setMode(b.dataset.k));
  if ($('#aBase')) $('#aBase').onclick = async () => {
    $('#aBase').disabled = true; toast('กำลังสร้างพื้นที่ศึกษาพื้นฐาน…');
    try { const r = await api(ENGINE + '/api/basedata', { json: {} }); if (r.status.failed.length) toast('สร้างไม่ได้: ' + r.status.failed.join(' · '), true); } catch (e) { toast(e.message, true); }
    route();
  };
  // พิมพ์พิกัด → เซิร์ฟเวอร์อ่าน/ตรวจ/แปลงเป็น WGS 84 → แสดงบนแผนที่ (บันทึกจริงเซิร์ฟเวอร์ตรวจซ้ำ)
  let cLayer = null, cOk = null, cT = null, cReq = 0;
  const parseCoords = () => {
    clearTimeout(cT);
    cT = setTimeout(async () => {
      const text = $('#cTxt').value, my = ++cReq;
      if (!text.trim()) { $('#cRes').innerHTML = '<span class="muted">รูปจะแสดงบนแผนที่ทันทีที่พิมพ์ · ปิดรูปให้เอง</span>'; cOk = null; if (cLayer) { mp.removeLayer(cLayer); cLayer = null; } return; }
      try {
        const r = await api(ENGINE + '/api/aoi/parse-coords', { json: { text, order: $('#cOrder').value, crs: $('#cCrs').value } });
        if (my !== cReq) return;
        cOk = r;
        if (cLayer) mp.removeLayer(cLayer);
        cLayer = L.geoJSON(r.geojson, { style: { color: '#f6e3a1', weight: 2.5, fillColor: '#f6e3a1', fillOpacity: .2 } }).addTo(mp);
        mp.fitBounds(cLayer.getBounds(), { padding: [30, 30], maxZoom: 15 });
        $('#cRes').innerHTML = `<div class="note ok" style="margin:0">✔ ${esc(r.info.format)} · ${esc(r.info.crs)}${r.info.order ? ' · ' + esc(r.info.order) : ''} · ${r.parts} รูป · <b>${fmt(r.area_km2, 2)} ตร.กม.</b>${r.info.closed ? '<div class="tiny muted">' + esc(r.info.closed) + '</div>' : ''}</div>`
          + r.warnings.map(w => `<div class="note warn" style="margin:6px 0 0">${esc(w)}</div>`).join('');
        if (!$('#aName').dataset.touched && !$('#aName').value) $('#aName').value = 'พื้นที่จากพิกัด';
      } catch (e) {
        if (my !== cReq) return;
        cOk = null; if (cLayer) { mp.removeLayer(cLayer); cLayer = null; }
        $('#cRes').innerHTML = `<div class="note err" style="margin:0">${esc(e.message)}</div>`;
      }
    }, 350);
  };
  $('#cTxt').oninput = parseCoords; $('#cOrder').onchange = parseCoords; $('#cCrs').onchange = parseCoords;
  mp.on(L.Draw.Event.CREATED, e => { drawn.addLayer(e.layer); $('#drawCount').textContent = `วาดแล้ว ${drawn.getLayers().length} รูป`; });
  // ชั้นขอบเขต + ไฮไลต์ที่เลือก
  const sel = new Set();
  let field = null, bLayer = null, shown = [];
  const style = f => sel.has(String(f.properties[field])) ? { color: '#f6e3a1', weight: 2, fillColor: '#c3b6ff', fillOpacity: .35 } : { color: '#f7a8cc', weight: .8, fillOpacity: .03 };
  const loadBoundary = async () => {
    if (!dsId || !field) return;
    const bb = mp.getBounds();
    const r = await fetch(`${base()}/features?bbox=${[bb.getWest(), bb.getSouth(), bb.getEast(), bb.getNorth()].map(v => v.toFixed(5)).join(',')}&z=${mp.getZoom()}&fields=${encodeURIComponent(field)}&limit=3000`);
    if (!r.ok) { $('#mapNote').textContent = 'ดึงขอบเขตไม่ได้: ' + ((await r.json()).error || r.status); return; }
    const gj = await r.json();
    if (bLayer) mp.removeLayer(bLayer);
    bLayer = L.geoJSON(gj, { style, onEachFeature: (f, l) => { l.bindTooltip(esc(f.properties[field]), { sticky: true }); l.on('click', () => toggle(String(f.properties[field]))); } }).addTo(mp);
    $('#mapNote').textContent = r.headers.get('X-Truncated') === '1' ? 'ซูมเข้าเพื่อดูขอบเขตครบ' : 'คลิกพื้นที่บนแผนที่เพื่อเลือก/ยกเลิก';
  };
  const refreshStyle = () => bLayer?.setStyle(style);
  // ติ๊กในรายการ → ซูมไปพื้นที่นั้น (ขอกรอบจากไฟล์/บริการ ; คำขอเก่าที่ตอบช้าไม่ทับคำขอใหม่)
  let zReq = 0;
  const zoomTo = async vals => {
    if (!vals.length) return;
    const my = ++zReq;
    try {
      const r = await api(`${base()}/extent`, { json: { field, values: vals.slice(0, 500) } });
      if (my !== zReq || !r.bounds) return;
      const [x0, y0, x1, y1] = r.bounds;
      mp.flyToBounds([[y0, x0], [y1, x1]], { padding: [30, 30], maxZoom: 13, duration: .8 });
    } catch (e) { $('#mapNote').textContent = 'ซูมไม่ได้: ' + e.message; }
  };
  const toggle = val => { sel.has(val) ? sel.delete(val) : sel.add(val); renderList(); refreshStyle(); };
  const renderList = () => {
    $('#aList').innerHTML = shown.map(x => `<label><input type="checkbox" value="${esc(x)}" ${sel.has(x) ? 'checked' : ''}>${esc(x)}</label>`).join('') || '<div class="tiny muted" style="padding:8px">ไม่พบ</div>';
    $$('#aList input').forEach(i => i.onchange = () => { i.checked ? sel.add(i.value) : sel.delete(i.value); refreshStyle(); updCount(); if (i.checked) zoomTo([i.value]); });
    updCount();
  };
  const updCount = () => { $('#aCount').textContent = `เลือก ${sel.size} พื้นที่`; if (sel.size && !$('#aName').dataset.touched) $('#aName').value = [...sel].slice(0, 3).join(' + ') + (sel.size > 3 ? ` และอีก ${sel.size - 3}` : ''); };
  let qTimer;
  const loadValues = async () => {
    $('#aCount').textContent = 'กำลังอ่านรายชื่อ…';
    const r = await api(`${base()}/field-values?field=${encodeURIComponent(field)}&q=${encodeURIComponent($('#aQ').value)}`);
    shown = r.values; renderList();
    if (r.total > r.values.length) $('#aCount').textContent += ` · แสดง ${r.values.length} จาก ${fmt(r.total, 0)} — พิมพ์ค้นหาเพื่อกรอง`;
    $$('.lostNote').forEach(e => e.remove());
    if (r.text_lost) $('#aCount').insertAdjacentHTML('afterend', `<div class="note warn small lostNote" style="margin:6px 0">${TEXT_LOST}</div>`);
  };
  const loadDs = async () => {
    if (!dsId) return;
    const d = cur();
    try { await ensureLinkFields(d); } catch (e) { $('#aCount').innerHTML = `<span style="color:var(--coral)">${esc(e.message)}</span>`; return; }
    const fs = fieldNames(d);
    const guess = guessNameField(fs);
    $('#aField').innerHTML = fs.map(f => `<option ${f === guess ? 'selected' : ''}>${esc(f)}</option>`).join('');
    field = guess; sel.clear();
    const b = d.meta.bounds_wgs84; if (b) mp.fitBounds([[b[1], b[0]], [b[3], b[2]]]);
    try { await loadValues(); } catch (e) { $('#aCount').innerHTML = `<span style="color:var(--coral)">อ่านรายชื่อไม่ได้: ${esc(e.message)}</span>`; }
    loadBoundary();
  };
  if (vecs.length) {
    $('#aDs').onchange = () => { dsId = +$('#aDs').value; loadDs(); };
    $('#aField').onchange = () => { field = $('#aField').value; sel.clear(); loadValues(); loadBoundary(); };
    $('#aQ').oninput = () => { clearTimeout(qTimer); qTimer = setTimeout(loadValues, 250); };
    $('#aAll').onclick = () => { shown.forEach(x => sel.add(x)); renderList(); refreshStyle(); zoomTo([...sel]); };
    $('#aNone').onclick = () => { sel.clear(); renderList(); refreshStyle(); };
    mp.on('moveend', loadBoundary);
    loadDs();
  }
  $('#aName').oninput = () => $('#aName').dataset.touched = 1;
  let aLayer = null;
  const showSaved = async id => {
    if (aLayer) mp.removeLayer(aLayer);
    aLayer = L.geoJSON(await api(`${ENGINE}/api/aoi/${id}.geojson`), { style: { color: '#9ee8d4', weight: 2.5, fillColor: '#9ee8d4', fillOpacity: .18 } }).addTo(mp);
    mp.fitBounds(aLayer.getBounds(), { padding: [20, 20] });
  };
  $$('tr[data-a]').forEach(tr => tr.onclick = e => { if (!e.target.closest('button')) showSaved(+tr.dataset.a); });
  $$('[data-del]').forEach(b => b.onclick = async () => {
    if (!await ui.confirm('ย้ายพื้นที่ศึกษาไปถังขยะ?', '<p>กู้คืนได้จากถังขยะ · ผลลัพธ์ที่สร้างไปแล้วไม่ได้รับผลกระทบ (lineage เก็บที่มาไว้)</p>', 'ย้ายไปถังขยะ')) return;
    await api(ENGINE + '/api/aoi/' + b.dataset.del, { method: 'DELETE' }); route();
  });
  $('#aSave').onclick = async () => {
    const name = $('#aName').value.trim();
    try {
      let r;
      if (mode === 'coords') {
        if (!cOk) return toast('พิกัดยังใช้ไม่ได้ — ดูข้อความใต้ช่องพิกัด', true);
        r = await api(ENGINE + '/api/aoi', { json: { name, coords: $('#cTxt').value, order: $('#cOrder').value, crs: $('#cCrs').value } });
      } else if (mode === 'draw') {
        if (!drawn.getLayers().length) return toast('ยังไม่ได้วาด', true);
        r = await api(ENGINE + '/api/aoi', { json: { name, geojson: drawn.toGeoJSON() } });
      } else {
        if (!sel.size) return toast('เลือกพื้นที่อย่างน้อย 1 รายการ', true);
        r = await api(ENGINE + '/api/aoi', { json: { name, [cur().kind === 'link' ? 'link_id' : 'dataset_id']: dsId, field, values: [...sel] } });
      }
      toast(`บันทึก "${r.aoi.name}" แล้ว · ${fmt(r.aoi.area_km2, 1)} ตร.กม.`); route();
    } catch (e) { toast(e.message, true); }
  };
}

// ================= งาน =================
const KIND = { prepare: ['เตรียมข้อมูล', 'db', 'var(--muted)'], resample: ['ปรับความละเอียด', 'layers', 'var(--peach)'], bivariate: ['ไบแวเรียต', 'map', 'var(--rose)'],
  rasterize: ['แปลงเป็นราสเตอร์', 'raster', 'var(--sky)'], vgrid: ['กริดเวกเตอร์', 'grid', 'var(--mint)'],
  hex: ['แปลงเป็นหกเหลี่ยม', 'hex', 'var(--lav)'], hexbiv: ['ไบแวเรียตหกเหลี่ยม', 'hex', 'var(--rose)'],
  calc: ['สูตรคำนวณ', 'calc', 'var(--sky)'], trend: ['อนุกรมเวลา', 'pulse', 'var(--peach)'], mosaic: ['รวมราสเตอร์', 'layers', 'var(--mint)'], vmerge: ['รวมเวกเตอร์', 'vector', 'var(--mint)'], satellite: ['ภาพดาวเทียม', 'globe', 'var(--sky)'] };
const fmtDur = s => s == null ? '–' : s < 60 ? `${Math.max(1, Math.round(s))} วินาที` : s < 3600 ? `${Math.floor(s / 60)} นาที ${Math.round(s % 60)} วินาที` : `${Math.floor(s / 3600)} ชม. ${Math.round(s % 3600 / 60)} นาที`;
const JOB_ST = { queued: 'รอคิว', running: 'กำลังทำ', cancelling: 'กำลังยกเลิก', done: 'เสร็จ', failed: 'ล้มเหลว', cancelled: 'ยกเลิกแล้ว' };
const JOB_CLS = { done: 'ok', failed: 'err', cancelled: 'warn', running: 'raster', queued: '' };
const isLive = j => ['queued', 'running', 'cancelling'].includes(j.status);

// แถวงานแต่ละแถวสร้างครั้งเดียว แล้วอัปเดตเฉพาะส่วนที่เปลี่ยน → หน้าไม่กระโดด, log ไม่เด้งขึ้นบน
async function pageJobs() {
  const v = $('#view');
  v.innerHTML = head('Jobs', 'งาน', 'งานยาวรันใน process แยกทีละงาน — ปิดหน้านี้ได้ งานยังทำต่อ') + '<div class="card" id="jobList"><p class="muted">กำลังโหลด…</p></div>';
  const list = $('#jobList');
  const rows = new Map(), open = new Set();
  const make = j => {
    const [kn, ki, kc] = KIND[j.kind] || [j.kind, 'pulse', 'var(--lav)'];
    const el = document.createElement('div');
    el.className = 'job'; el.dataset.id = j.id;
    el.innerHTML = `<div class="ico" style="--c:${kc}">${IC[ki]}</div>
      <div style="min-width:0"><div class="row" style="gap:8px"><b>${esc(j.title)}</b><span class="chip j-st"></span><span class="tiny muted">#${j.id} · ${kn}</span></div>
        <div class="j-prog"></div><div class="j-body"></div>
        <div class="tiny muted j-time"></div><div class="j-log hide" style="margin-top:8px"><div class="log"></div></div></div>
      <div class="row j-acts" style="justify-content:flex-end"></div>`;
    return el;
  };
  const update = (el, j) => {
    const sig = JSON.stringify([j.status, j.progress, j.message, j.eta_s != null && Math.round(j.eta_s / 5), j.error, !!j.result, j._queue]);
    if (el._sig === sig) return;
    el._sig = sig;
    const st = $('.j-st', el); st.className = `chip j-st ${JOB_CLS[j.status] || ''}`; st.textContent = JOB_ST[j.status] || j.status;
    const pct = Math.round((j.progress || 0) * 100);
    $('.j-prog', el).innerHTML = isLive(j) ? `<div class="prog"><div class="bar ${j.status === 'running' ? 'run' : ''}"><div style="width:${pct}%"></div></div><b>${pct}%</b></div>
      <div class="eta">${j.status === 'queued' ? (j._queue || 'รอคิว…') : j.status === 'cancelling' ? 'กำลังยกเลิก… ถ้างานอยู่ในขั้นที่หยุดกลางทางไม่ได้ ระบบจะบังคับหยุดใน 15 วินาที' : `ผ่านไป ${fmtDur(j.elapsed_s)} · ${j.eta_s != null ? `เหลือประมาณ <b>${fmtDur(j.eta_s)}</b>` : 'กำลังประเมินเวลา…'}`}</div>` : '';
    const s = j.result?.summary || {};
    $('.j-body', el).innerHTML = `<div class="tiny muted" style="margin-top:4px">${esc(j.message || '')}</div>`
      + (j.error ? `<div class="note err small">${esc(j.error)}</div>` : '')
      + (j.result?.warnings || []).map(w => `<div class="note warn small">${esc(w)}</div>`).join('')
      + (s.weight_total != null ? `<div class="small" style="margin-top:4px">น้ำหนักรวม <b>${fmt(s.weight_total)}</b> · มีรหัส ${fmt(s.weight_coded)} · เขตเน้น <b style="color:var(--butter)">${fmt(s.highlight_weight)}</b></div>` : '')
      + (s.sum != null ? `<div class="small" style="margin-top:4px">ผลรวมค่า <b>${fmt(s.sum)}</b></div>` : '') + (s.cells != null ? `<div class="small" style="margin-top:4px">${fmt(s.cells, 0)} ช่อง</div>` : '')
      + (s.zones != null ? `<div class="small" style="margin-top:4px">${fmt(s.zones, 0)} พื้นที่ · มีรหัส ${fmt(s.zones_coded, 0)} · เขตเน้น <b style="color:var(--butter)">${fmt(s.zones_highlight, 0)}</b> พื้นที่</div>` : '')
      + (s.diff != null ? `<div class="small" style="margin-top:4px">ก่อน ${fmt(s.sum_before)} → หลัง ${fmt(s.sum_after)} · <b>${s.diff >= 0 ? '+' : ''}${fmt(s.diff)}</b>${s.pct != null ? ` (${s.pct >= 0 ? '+' : ''}${fmt(s.pct)}%)` : ''}</div>` 
        + (s.pct_pixels_changed != null ? `<div class="tiny muted">พิกเซลที่ต่าง ${fmt(s.pct_pixels_changed, 2)}% (เพิ่ม ${fmt(s.pixels_up, 0)} · ลด ${fmt(s.pixels_down, 0)} · เท่าเดิม ${fmt(s.pixels_same, 0)}) · ต่างเฉลี่ย |Δ| ${fmt(s.mean_abs_diff, 4)} · สูงสุด ${fmt(s.max_abs_diff, 4)}${s.correlation != null ? ` · r = ${fmt(s.correlation, 4)}` : ''}</div>` : '') : '')
      + (s.results ? `<div class="small" style="margin-top:6px">เขตเน้น <b style="color:var(--butter)">${fmt(s.highlight_min)} – ${fmt(s.highlight_max)}</b> (มัธยฐาน ${fmt(s.highlight_median)}) จาก ${s.runs} ชุดค่า</div>
          <table class="sens"><tbody>${s.results.map(r => `<tr><td class="tiny">${esc(r.label)}</td><td style="text-align:right"><b>${fmt(r.highlight_weight)}</b></td><td style="width:40%"><div class="sbar"><div style="width:${s.highlight_max ? r.highlight_weight / s.highlight_max * 100 : 0}%"></div></div></td></tr>`).join('')}</tbody></table>` : '');
    const secs = (a, b) => a && b ? (new Date(b) - new Date(a)) / 1000 : null;
    const wait = secs(j.created_at, j.started_at), run = j.elapsed_s ?? secs(j.started_at, j.finished_at);
    const timing = j.finished_at && j.started_at
      ? `<div class="timing">⏱ ประมวลผล <b>${fmtDur(run)}</b>${wait > 1 ? ` · รอคิว ${fmtDur(wait)}` : ''} · รวม ${fmtDur(secs(j.created_at, j.finished_at))}
         <span class="tiny muted">(${esc(j.started_at.slice(11))} → ${esc(j.finished_at.slice(11))})</span></div>` : '';
    $('.j-time', el).innerHTML = timing + `<div>${esc((j.created_at || '').replace('T', ' '))}${j.out_dir ? ` · <span class="mono">${esc(j.out_dir)}</span>` : ''}</div>`;
    const acts = $('.j-acts', el);
    acts.innerHTML = `${j.result?.dataset_id ? `<a class="btn" href="#/ds/${j.result.dataset_id}">ดูผล</a>` : ''}
      ${j.out_dir ? `<button class="sm ghost" data-a="open" title="เปิดโฟลเดอร์">${IC.folder}</button>` : ''}
      ${!isLive(j) && j.kind !== 'prepare' ? `<button class="sm ghost" data-a="rerun" title="รันซ้ำ">${IC.refresh}</button>` : ''}
      <button class="sm ghost ${open.has(j.id) ? 'on' : ''}" data-a="log">log</button>
      ${['queued', 'running'].includes(j.status) ? `<button class="sm danger" data-a="cancel">ยกเลิก</button>` : ''}
      ${j.status === 'cancelling' ? `<button class="sm danger" data-a="force">บังคับหยุด</button>` : ''}`;
    $$('button', acts).forEach(b => b.onclick = async () => {
      const a = b.dataset.a;
      if (a === 'open') openFolder(j.out_dir);
      if (a === 'cancel') { await api(`${ENGINE}/api/jobs/${j.id}/cancel`, { json: {} }); tick(); }
      if (a === 'force') { if (await ui.confirm('บังคับหยุด?', '<p>หยุด process ทันที ไฟล์ผลลัพธ์ที่ยังไม่เสร็จจะไม่สมบูรณ์ (ลบได้ที่หน้า "ระบบ")</p>', 'บังคับหยุด')) { await api(`${ENGINE}/api/jobs/${j.id}/cancel`, { json: { force: true } }); tick(); } }
      if (a === 'rerun') {
        if (!await ui.confirm('รันซ้ำ?', '<p>ใช้ค่าที่ตั้งเดิม ผลลงโฟลเดอร์ใหม่</p>', 'รันซ้ำ')) return;
        try { const r = await api(`${ENGINE}/api/jobs/${j.id}/rerun`, { json: {} }); toast(`เริ่มงาน #${r.job}`); tick(); } catch (e) { toast(e.message, true); }
      }
      if (a === 'log') { open.has(j.id) ? open.delete(j.id) : open.add(j.id); el._sig = null; $('.j-log', el).classList.toggle('hide', !open.has(j.id)); b.classList.toggle('on'); if (open.has(j.id)) loadLog(el, j.id, true); }
    });
  };
  const loadLog = async (el, id, toBottom) => {
    const box = $('.j-log .log', el);
    const atBottom = box.scrollTop + box.clientHeight >= box.scrollHeight - 24;
    const top = box.scrollTop;
    const r = await api(ENGINE + '/api/jobs/' + id);
    const txt = r.log.join('\n');
    if (box.textContent !== txt) {
      box.textContent = txt;
      box.scrollTop = toBottom || atBottom ? box.scrollHeight : top;      // อยู่ล่างสุด → ตามบรรทัดใหม่ · เลื่อนขึ้นไปอ่าน → คงตำแหน่ง
    }
  };
  const tick = async () => {
    const js = await api(ENGINE + '/api/jobs');
    if (!js.length) { list.innerHTML = '<div class="empty">ยังไม่มีงาน</div>'; return; }
    if (!rows.size) list.innerHTML = '';
    // คิวทำทีละงาน → บอกงานที่รอว่ารอใคร ลำดับที่เท่าไร เหลือประมาณกี่นาที
    const run = js.find(j => ['running', 'cancelling'].includes(j.status));
    js.filter(j => j.status === 'queued').sort((a, b) => a.id - b.id).forEach((j, i) => {
      j._queue = `รอคิวลำดับที่ ${i + 1}${run ? ` · ทำทีละงาน กำลังทำ #${run.id}${run.eta_s != null ? ` (เหลือ ~${fmtDur(run.eta_s)})` : ''}` : ''}`;
    });
    let prev = null;
    for (const j of js) {
      let el = rows.get(j.id);
      if (!el) { el = make(j); rows.set(j.id, el); prev ? prev.after(el) : list.prepend(el); }
      update(el, j);
      if (open.has(j.id) && (isLive(j) || !el._logOnce)) { el._logOnce = true; loadLog(el, j.id); }
      prev = el;
    }
    jobBadge();
  };
  await tick();
  window._poll = setInterval(() => { if (!document.hidden && $('#modal').classList.contains('hide')) tick().catch(() => { }); }, 2000);
}
// ================= V3: ลิงก์ (3.1–3.3) =================
async function addSecret() {
  const r = await ui.open('เพิ่มโทเคน', `<p class="small muted">เก็บแบบเข้ารหัสด้วย Windows (DPAPI) — ถอดได้เฉพาะบัญชีนี้บนเครื่องนี้ · ไม่ลง lineage / log</p>
    <label class="field"><span>ชื่อ (ไว้จำ)</span><input type="text" id="sxName" placeholder="เช่น GISTDA ArcGIS"></label>
    <label class="field" style="margin-top:10px"><span>โทเคน</span><input type="password" id="sxVal" style="width:100%" autocomplete="off"></label>`,
    [{ label: 'ยกเลิก', cls: 'ghost', value: () => null }, { label: 'บันทึก', cls: 'primary', value: () => ({ name: $('#sxName').value, value: $('#sxVal').value }) }]);
  if (!r || !r.value) return null;
  const s = await api(ENGINE + '/api/secrets', { json: r });
  toast('บันทึกโทเคนแล้ว (เข้ารหัส)');
  return s.id;
}
async function fillSecrets(sel, cur) {
  const ss = await api(ENGINE + '/api/secrets');
  sel.innerHTML = '<option value="">ไม่ใช้โทเคน</option>' + ss.map(s => `<option value="${s.id}" ${s.id === cur ? 'selected' : ''}>${esc(s.name)}</option>`).join('');
}
function linkAdder() {
  fillSecrets($('#lkSec'));
  $('#lkSecAdd').onclick = async () => { const id = await addSecret(); if (id) fillSecrets($('#lkSec'), id); };
  $('#lkGo').onclick = async () => {
    const url = $('#lkUrl').value.trim(); if (!url) return;
    $('#lkGo').disabled = true; $('#lkRes').innerHTML = '<div class="small muted" style="margin-top:10px">กำลังตรวจ…</div>';
    try {
      const info = await api(ENGINE + '/api/links/inspect', { json: { url, secret_id: $('#lkSec').value || null } });
      const lay = info.layers?.length ? `<label class="field"><span>ชั้น</span><select id="lkLayer">${info.layers.map(l => `<option value="${esc(l.id)}" ${String(l.id) === String(info.layer) ? 'selected' : ''}>${esc(l.id)} · ${esc(l.name)}${l.geometry ? ' · ' + esc(l.geometry.replace('esriGeometry', '')) : ''}</option>`).join('')}</select></label>` : '';
      $('#lkRes').innerHTML = `<div class="note ${info.view ? 'info' : 'ok'}" style="margin-top:12px"><b>${esc(info.type_label)}</b> — ${info.view ? 'ภาพแผนที่ (ดูอย่างเดียว ไม่มีค่าให้คำนวณ)' : 'ข้อมูล (ดาวน์โหลดเข้า database แล้วใช้วิเคราะห์ได้)'}${info.note ? '<br>' + esc(info.note) : ''}</div>
        <div class="grid-form"><label class="field"><span>ชื่อ</span><input type="text" id="lkName" value="${esc(info.title || '')}"></label>${lay}</div>
        <div class="row" style="margin-top:10px"><button id="lkAdd" class="primary">${IC.plus}เพิ่มเข้าคลัง</button></div>`;
      $('#lkAdd').onclick = async () => {
        if ($('#lkLayer')) info.layer = isNaN(+$('#lkLayer').value) ? $('#lkLayer').value : +$('#lkLayer').value;
        const r = await api(ENGINE + '/api/links', { json: { info, name: $('#lkName').value, secret_id: $('#lkSec').value || null, folder_id: window._libFolder || null } });
        location.hash = '#/ds/' + r.id;
      };
    } catch (e) { $('#lkRes').innerHTML = `<div class="note err" style="margin-top:12px">${esc(e.message)}</div>`; }
    finally { $('#lkGo').disabled = false; }
  };
}

async function pageLink(d) {
  const m = d.meta;
  const aois = await api(ENGINE + '/api/aoi');
  const v = $('#view');
  const lay = m.layers?.length && ['wms', 'arcgis_feature', 'wfs'].includes(m.type)
    ? `<label class="field full"><span>ชั้นที่ใช้</span><select id="lkLayer">${m.layers.map(l => `<option value="${esc(l.id)}" ${String(l.id) === String(m.layer) ? 'selected' : ''}>${esc(l.id)} · ${esc(l.name)}</option>`).join('')}</select></label>` : '';
  const dynLayers = m.type === 'arcgis_dynamic' && m.layers?.length
    ? `<div class="field full"><span>ชั้นที่แสดง</span><div class="checklist" id="lkOn">${m.layers.map(l => `<label><input type="checkbox" value="${l.id}" ${!m.layers_on || m.layers_on.includes(l.id) ? 'checked' : ''}><span>${l.id} · ${esc(l.name)}</span></label>`).join('')}</div></div>` : '';
  v.innerHTML = head(`ลิงก์ · ${esc(m.type_label || d.format)}`, `${esc(d.name)} <span class="edit" id="ren">${IC.edit}</span>`,
    `<span class="chip">${m.view ? 'ดูอย่างเดียว' : 'ดาวน์โหลดได้'}</span>${m.secret_id ? ` <span class="chip">${IC.lock}โทเคน</span>` : ''}`, `<button id="toViewer">${IC.layers}เปิดในแผนที่ซ้อนชั้น</button><a class="btn" href="#/">← คลังข้อมูล</a>`)
    + (m.warnings || []).map(w => `<div class="note warn">${esc(w)}</div>`).join('')
    + `<div class="cols"><div>
      <div class="card"><div class="card-head"><h2><span class="dot"></span>ลิงก์</h2></div>
        <table class="kv"><tr><td>URL</td><td class="mono">${esc(d.path)}</td></tr><tr><td>ชนิด</td><td>${esc(m.type_label)}</td></tr>
          ${m.copyright ? `<tr><td>ลิขสิทธิ์</td><td class="small">${esc(m.copyright)}</td></tr>` : ''}${m.max_records ? `<tr><td>ดึงได้ต่อครั้ง</td><td>${fmt(m.max_records, 0)} รายการ (แอปดึงทีละชุดจนครบ)</td></tr>` : ''}
          ${m.width ? `<tr><td>ขนาด</td><td>${fmt(m.width, 0)} × ${fmt(m.height, 0)} · ${esc(m.crs)}</td></tr>` : ''}
          <tr><td>โทเคน</td><td><select id="lkSec"></select></td></tr></table>
        ${lay || dynLayers ? `<div class="grid-form" style="margin-top:12px">${lay}${dynLayers}</div><button id="lkSave" class="sm" style="margin-top:10px">บันทึก</button>` : ''}</div>
      ${!m.view ? `<div class="card"><div class="card-head"><h2><span class="dot" style="background:var(--mint);color:var(--mint)"></span>ดาวน์โหลดเข้า database</h2></div>
        <p class="small muted" style="margin-top:0">ข้อมูลจากลิงก์ต้องดาวน์โหลดก่อนใช้คำนวณ · บันทึก URL และวันที่ไว้ใน source.json (ไม่บันทึกโทเคน)</p>
        <div class="grid-form">
          <label class="field"><span>ตัดตามพื้นที่ศึกษา</span><select id="dlAoi"><option value="">ทั้งหมด</option>${aoiOptions(aois)}</select></label>
          <label class="field"><span>ชื่อชุดข้อมูล</span><input type="text" id="dlName" placeholder="${esc(d.name)}"></label>
          ${m.type === 'arcgis_feature' ? '<label class="field full"><span>เงื่อนไข (where)</span><input type="text" id="dlWhere" placeholder="1=1"></label>' : ''}
        </div><button id="dlGo" class="mint" style="margin-top:10px">${IC.download}ดาวน์โหลด</button></div>` : ''}
    </div>
    <div class="card sticky"><div class="mapbar"><div class="seg" id="bm"><button data-k="gh">ดาวเทียม</button><button data-k="osm">แผนที่</button><button data-k="none">ไม่มี</button></div>
      <label class="row small" title="ความทึบของชั้นข้อมูล">ข้อมูล <input type="range" id="op" min="0" max="1" step="0.05" value="0.9"></label></div>
      <div id="map" class="mapbox"></div>
      <div class="tiny muted" style="margin-top:8px"><span id="mapNote"></span> · ${m.view ? 'ไทล์ผ่านพร็อกซีของแอป (โทเคนไม่ถึงเบราว์เซอร์)' : 'พรีวิวจากบริการโดยตรง (เฉพาะกรอบที่มอง) — คลิก feature เพื่อดูค่า · ดาวน์โหลดเข้า database ก่อนใช้คำนวณ'}</div>
      <div id="pt" class="pt small"></div></div></div>`;
  $('#ren').onclick = async () => { const n = await ui.prompt('แก้ชื่อ', d.name); if (n) { await api(ENGINE + '/api/datasets/' + d.id, { method: 'PATCH', json: { name: n } }); route(); } };
  await fillSecrets($('#lkSec'), m.secret_id);
  $('#toViewer').onclick = () => { viewerAdd([vLayerFromDs(d)]); location.hash = '#/viewer'; };
  $('#lkSec').onchange = async () => { m.secret_id = $('#lkSec').value || null; await api(`${ENGINE}/api/links/${d.id}/layer`, { json: { secret_id: m.secret_id } }); ver++; show(); toast('เปลี่ยนโทเคนแล้ว'); };
  const mp = baseMap('map'); window._mapObj = mp; bmSeg(mp, $('#bm'));
  // ลิงก์ที่เพิ่มก่อน v3.1 ไม่มีขอบเขต/ฟิลด์ของชั้น → อ่านใหม่
  if (!m.view && m.type === 'arcgis_feature' && (!m.bounds_wgs84 || !m.fields)) {
    try { const r = await api(`${ENGINE}/api/links/${d.id}/refresh`, { json: {} }); m.bounds_wgs84 = r.bounds; m.fields = r.fields; } catch (e) { toast(e.message, true); }
  }
  const fit = () => { const b = m.bounds_wgs84; if (b) mp.fitBounds([[b[1], b[0]], [b[3], b[2]]]); else mp.setView([13.5, 100.5], 6); };
  fit();
  let layer = null, ver = 0, req = 0;
  const op = () => +$('#op').value;
  const loadFeats = async () => {
    const my = ++req, bb = mp.getBounds();
    const q = [bb.getWest(), bb.getSouth(), bb.getEast(), bb.getNorth()].map(v => v.toFixed(5)).join(',');
    $('#mapNote').textContent = 'กำลังดึง feature…';
    try {
      const r = await fetch(`${ENGINE}/api/links/${d.id}/features?bbox=${q}&z=${mp.getZoom()}&v=${ver}`);
      if (!r.ok) throw new Error((await r.json()).error);
      const gj = await r.json();
      if (my !== req) return;                                    // ผลของคำขอเก่า (เลื่อนแผนที่ไปแล้ว)
      layer.clearLayers(); layer.addData(gj);
      $('#mapNote').textContent = r.headers.get('X-Truncated') === '1' ? `แสดง ${r.headers.get('X-Count')} feature แรกในกรอบ — ซูมเข้าเพื่อดูครบ` : `${r.headers.get('X-Count')} feature ในกรอบ (ย่อรูปตามระดับซูม)`;
    } catch (e) { if (my === req) $('#mapNote').textContent = 'ดึง feature ไม่ได้: ' + e.message; }
  };
  const show = () => {
    if (layer) mp.removeLayer(layer);
    if (m.view) { layer = L.tileLayer(`${ENGINE}/api/links/${d.id}/tile/{z}/{x}/{y}.png?v=${ver}`, { maxZoom: 22, opacity: op() }).addTo(mp); return; }
    layer = L.geoJSON(null, {
      style: () => ({ color: '#c3b6ff', weight: 1.2, fillColor: '#c3b6ff', fillOpacity: op() * .18, opacity: op() }),
      pointToLayer: (f, ll) => L.circleMarker(ll, { radius: 4, weight: 1, color: '#c3b6ff' }),
      onEachFeature: (f, l) => l.on('click', () => {
        $('#pt').innerHTML = `<div class="pt-card"><table class="kv">${Object.entries(f.properties || {}).slice(0, 30).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}</table></div>`;
        layer.resetStyle(); l.setStyle({ color: '#f6e3a1', weight: 2.5 });
      }),
    }).addTo(mp);
    loadFeats();
  };
  if (!m.view) { let tm; mp.on('moveend', () => { clearTimeout(tm); tm = setTimeout(loadFeats, 250); }); }
  show();
  $('#op').oninput = () => m.view ? layer?.setOpacity(op()) : layer?.setStyle({ fillOpacity: op() * .18, opacity: op() });
  if ($('#lkSave')) $('#lkSave').onclick = async () => {
    const body = {};
    if ($('#lkLayer')) body.layer = isNaN(+$('#lkLayer').value) ? $('#lkLayer').value : +$('#lkLayer').value;
    if ($('#lkOn')) body.layers_on = $$('#lkOn input:checked').map(i => +i.value);
    await api(`${ENGINE}/api/links/${d.id}/layer`, { json: body }); Object.assign(m, body);
    if (m.type === 'arcgis_feature') { const r = await api(`${ENGINE}/api/links/${d.id}/refresh`, { json: {} }); m.bounds_wgs84 = r.bounds; m.fields = r.fields; fit(); }
    ver++; show(); toast('บันทึกแล้ว');
  };
  if ($('#dlGo')) $('#dlGo').onclick = () => runJob('download', { link_id: d.id, layer: $('#lkLayer') ? (isNaN(+$('#lkLayer').value) ? $('#lkLayer').value : +$('#lkLayer').value) : m.layer,
    aoi_id: +$('#dlAoi').value || null, name: $('#dlName').value.trim() || null, where: $('#dlWhere')?.value.trim() || null });
}

// ชั้นลิงก์ซ้อนบนแผนที่ใดก็ได้
async function linkOverlay(mp, bar) {
  const all = (await api(ENGINE + '/api/datasets')).filter(x => x.kind === 'link' && x.meta.view);
  if (!all.length) return;
  const sel = document.createElement('select'); sel.className = 'sm'; sel.style.maxWidth = '200px';
  sel.innerHTML = '<option value="">+ ซ้อนลิงก์…</option>' + all.map(x => `<option value="${x.id}">${esc(x.name)}</option>`).join('');
  bar.appendChild(sel);
  let lay = null;
  sel.onchange = () => { if (lay) mp.removeLayer(lay); lay = sel.value ? L.tileLayer(`${ENGINE}/api/links/${sel.value}/tile/{z}/{x}/{y}.png`, { maxZoom: 22, opacity: .8 }).addTo(mp) : null; };
}

// แหล่งโพลิกอน (ขอบเขต): ไฟล์ vector ในเครื่อง หรือ ลิงก์ Feature layer / WFS / GeoJSON
const isBoundaryLink = d => d.kind === 'link' && ['arcgis_feature', 'wfs', 'geojson'].includes(d.meta.type) && (!d.meta.geometry || /polygon/i.test(d.meta.geometry));
const isPolySrc = d => (d.kind === 'vector' && /Polygon/.test(d.meta.geometry_type || '')) || isBoundaryLink(d);
const fieldNames = d => (d.meta.fields || []).map(f => typeof f === 'string' ? f : f.name);
const guessNameField = fs => fs.find(f => /(_tn|_th|name_th|adm\d_th)$/i.test(f)) || fs.find(f => /th/i.test(f) && /name|adm/i.test(f)) || fs.find(f => /name/i.test(f)) || fs[0];
const srcLabel = d => d.kind === 'link' ? `🔗 ${esc(d.name)} · ${esc(d.meta.type_label || 'ลิงก์')}` : `#${d.id} ${esc(d.name)} · ${fmt(d.meta.features, 0)} feature`;
async function ensureLinkFields(d) {
  if (d.kind === 'link' && (!d.meta.fields || !d.meta.bounds_wgs84) && d.meta.type === 'arcgis_feature') {
    const r = await api(`${ENGINE}/api/links/${d.id}/refresh`, { json: {} }); d.meta.fields = r.fields; d.meta.bounds_wgs84 = r.bounds;
  }
}

// ================= ถังขยะ =================
// ลบ = ย้ายเข้าถัง (กู้คืนได้) · ลบในถัง = ลบถาวร: ไฟล์ใน workspace หายจริง ไฟล์ต้นฉบับนอก workspace ไม่ถูกแตะ
async function trashBadge(n) {
  try { if (n == null) n = (await api(ENGINE + '/api/trash')).count; } catch { return; }
  const b = $('#trashBadge'); if (!b) return;
  b.textContent = n; b.classList.toggle('hide', !n);
}
const fmtBytes = n => n >= 1e9 ? fmt(n / 1e9, 2) + ' GB' : n >= 1e6 ? fmt(n / 1e6, 1) + ' MB' : n >= 1e3 ? fmt(n / 1e3, 0) + ' KB' : n ? n + ' B' : '';
async function pageTrash() {
  const r = await api(ENGINE + '/api/trash');
  trashBadge(r.count);
  const v = $('#view');
  const KIND = { raster: 'raster', vector: 'vector', link: 'ลิงก์', aoi: 'พื้นที่ศึกษา' };
  const total = r.items.reduce((s, it) => s + (it.purge.bytes || 0), 0);
  v.innerHTML = head('Trash', 'ถังขยะ', 'ของที่ลบจะมาอยู่ที่นี่ก่อน — กู้คืนได้ · ลบในถังขยะ = ลบถาวร (ไฟล์ที่แอปเก็บใน workspace จะถูกลบจริง ไฟล์ต้นฉบับของคุณนอก workspace ไม่ถูกแตะ)',
    r.items.length ? `<button class="ghost danger" id="tEmpty">${IC.trash}ล้างถังขยะ${total ? ' · ' + fmtBytes(total) : ''}</button>` : '')
    + (r.items.length ? `<div class="card"><table class="tbl trash-tbl"><thead><tr><th>ชื่อ</th><th>ชนิด</th><th>ลบเมื่อ</th><th>ถ้าลบถาวร</th><th></th></tr></thead><tbody>
      ${r.items.map(it => `<tr><td><b>${esc(it.name)}</b></td><td class="small muted">${KIND[it.type] || it.type}${it.role === 'map' ? ' · แผนที่ไบแวเรียต' : it.role === 'derived' ? ' · ผลลัพธ์' : ''}</td>
        <td class="small muted">${esc(it.trashed_at.replace('T', ' '))}</td>
        <td class="small">${it.purge.action === 'delete' ? `<span style="color:var(--coral)" title="${esc(it.purge.path || '')}">${esc(it.purge.note)}</span>${it.purge.bytes ? ' · ' + fmtBytes(it.purge.bytes) : ''}` : `<span class="muted">${esc(it.purge.note)}</span>`}</td>
        <td><div class="row" style="justify-content:flex-end;flex-wrap:nowrap"><button class="sm" data-rs="${it.kind}:${it.id}">${IC.refresh}กู้คืน</button><button class="sm ghost danger" data-pg="${it.kind}:${it.id}">${IC.trash}ลบถาวร</button></div></td></tr>`).join('')}
      </tbody></table></div>`
      : `<div class="card"><p class="muted" style="margin:0">ถังขยะว่าง</p></div>`);
  const item = k => r.items.find(it => `${it.kind}:${it.id}` === k);
  $$('[data-rs]').forEach(b => b.onclick = async () => {
    const [k, id] = b.dataset.rs.split(':');
    await api(`${ENGINE}/api/trash/${k}/${id}/restore`, { json: {} }); toast(`กู้คืน "${item(b.dataset.rs).name}" แล้ว`); pageTrash();
  });
  $$('[data-pg]').forEach(b => b.onclick = async () => {
    const it = item(b.dataset.pg), [k, id] = b.dataset.pg.split(':');
    if (!await ui.confirm('ลบถาวร?', `<p>"${esc(it.name)}"</p><p>${it.purge.action === 'delete' ? `<b style="color:var(--coral)">${esc(it.purge.note)}</b>${it.purge.bytes ? ' (' + fmtBytes(it.purge.bytes) + ')' : ''} — <b>ย้อนกลับไม่ได้</b>` : esc(it.purge.note)}</p>`, 'ลบถาวร')) return;
    const x = await api(`${ENGINE}/api/trash/${k}/${id}`, { method: 'DELETE' }); toast('ลบถาวรแล้ว' + (x.freed ? ' · คืนพื้นที่ ' + fmtBytes(x.freed) : '')); pageTrash();
  });
  if ($('#tEmpty')) $('#tEmpty').onclick = async () => {
    const del = r.items.filter(it => it.purge.action === 'delete').length;
    if (!await ui.confirm('ล้างถังขยะ?', `<p>ลบถาวรทั้งหมด ${r.items.length} รายการ${del ? ` · ลบไฟล์ใน workspace ${del} รายการ (${fmtBytes(total)})` : ''} — <b>ย้อนกลับไม่ได้</b></p><p class="small muted">ไฟล์ต้นฉบับของคุณนอก workspace ไม่ถูกลบ</p>`, 'ล้างถังขยะ')) return;
    const x = await api(ENGINE + '/api/trash', { method: 'DELETE' }); toast(`ลบถาวร ${x.removed} รายการ` + (x.freed ? ' · คืนพื้นที่ ' + fmtBytes(x.freed) : '')); pageTrash();
  };
}

// ================= V3: เปรียบเทียบ 2 ช่วงเวลา (3.6) =================
async function pageChange() {
  const [all, aois] = await Promise.all([api(ENGINE + '/api/datasets'), api(ENGINE + '/api/aoi')]);
  const rs = all.filter(d => d.kind === 'raster' && d.value_type_confirmed);
  const v = $('#view');
  const opt = rs.map(d => `<option value="${d.id}">#${d.id} ${esc(d.name)} · ${esc((d.meta.res_label || '').split(' (')[0])} · ${esc(VT_SHORT[d.value_type] || '')}</option>`).join('');
  v.innerHTML = head('Change', 'เปรียบเทียบ 2 ช่วงเวลา', 'เช่น ประชากร 2015 → 2024 · ชั้นน้ำท่วมสองช่วง — ได้แผนที่ผลต่าง + ตารางสรุป')
    + `<div class="card" style="max-width:860px"><div class="grid-form">
      <label class="field"><span>ก่อน</span><select id="cA">${opt}</select></label>
      <label class="field"><span>หลัง</span><select id="cB">${opt}</select></label>
      <label class="field full"><span>วิธี</span><select id="cMode"><option value="diff">ผลต่าง (หลัง − ก่อน)</option><option value="pct">ร้อยละการเปลี่ยนแปลง</option><option value="ratio">อัตราส่วน (หลัง ÷ ก่อน)</option><option value="transition">การเปลี่ยนชั้น (ชั้น → ชั้น)</option></select></label>
      <label class="field"><span>ความละเอียด</span><select id="cRes"></select></label>
      <label class="field"><span>พื้นที่ศึกษา</span><select id="cAoi"><option value="">ทั้งขอบเขต</option>${aoiOptions(aois)}</select></label>
      <label class="field full"><span>ชื่อผลลัพธ์</span><input type="text" id="cName" placeholder="เช่น pop_2015_2024"></label></div>
      <div class="tiny muted" style="margin:10px 0">ค่าของแต่ละชุดปรับลงกริดเดียวกันตามประเภทค่าก่อนเทียบ (count รวม · density เฉลี่ย · class majority)</div>
      <button id="cRun" class="primary">${IC.play}เปรียบเทียบ</button></div>`;
  if (rs.length > 1) $('#cB').selectedIndex = 1;
  const loadRes = async () => {
    try {
      const r = await api(`${ENGINE}/api/res-options?ids=${$('#cA').value},${$('#cB').value}`);
      $('#cRes').innerHTML = r.options.map(o => `<option value="${o.value}">${esc(o.label.split(' (')[0])} · ${fmt(o.px / 1e6, 1)} ล้าน${o.is_source.length ? ' · = ข้อมูล' : ''}</option>`).join('');
      $('#cRes').value = r.options.filter(o => o.is_source.length).map(o => o.value)[0];
    } catch (e) { $('#cRes').innerHTML = `<option value="">${esc(e.message)}</option>`; }
  };
  $('#cA').onchange = $('#cB').onchange = loadRes; if (rs.length) loadRes();
  $('#cRun').onclick = () => runJob('change', { a_id: +$('#cA').value, b_id: +$('#cB').value, mode: $('#cMode').value, target_res: $('#cRes').value,
    aoi_id: +$('#cAoi').value || null, name: $('#cName').value.trim() || null }, () => location.hash = '#/jobs');
}

// ================= เครื่องมือข้อมูล: สูตรคำนวณ · อนุกรมเวลา · รวมราสเตอร์ · รวมเวกเตอร์ =================
const CALC_PRESETS = [
  { k: 'ndvi', t: 'NDVI (พืชพรรณ)', e: '(NIR - RED) / (NIR + RED)', v: ['NIR', 'RED'] },
  { k: 'ndwi', t: 'NDWI (น้ำ)', e: '(GREEN - NIR) / (GREEN + NIR)', v: ['GREEN', 'NIR'] },
  { k: 'ndbi', t: 'NDBI (สิ่งปลูกสร้าง)', e: '(SWIR - NIR) / (SWIR + NIR)', v: ['SWIR', 'NIR'] },
  { k: 'diff', t: 'ผลต่าง (B − A)', e: 'B - A', v: ['A', 'B'] },
  { k: 'ratio', t: 'อัตราส่วน (A ÷ B)', e: 'A / B', v: ['A', 'B'] },
  { k: 'thr', t: 'เกินเกณฑ์ → 1 / 0', e: 'where(A > 0.3, 1, 0)', v: ['A'] },
];
const TREND_STATS = { slope: 'แนวโน้มต่อปี (ความชันถดถอยเชิงเส้น)', change: 'เปลี่ยนแปลง (ปีท้าย − ปีแรก)', pct: 'เปลี่ยนแปลง % (เทียบปีแรก)', mean: 'ค่าเฉลี่ยทุกปี',
  std: 'ส่วนเบี่ยงเบนมาตรฐาน (ความผันผวน)', max_year: 'ปีที่ค่าสูงสุด', min_year: 'ปีที่ค่าต่ำสุด', count_above: 'จำนวนปีที่ค่า > เกณฑ์ (เช่น ความถี่น้ำท่วม)', count_below: 'จำนวนปีที่ค่า < เกณฑ์' };
const TOOLS = { tab: 'sat' };
async function pageTools(q) {
  const [all, aois, fr] = await Promise.all([api(ENGINE + '/api/datasets'), api(ENGINE + '/api/aoi'), api(ENGINE + '/api/folders').catch(() => ({ folders: [] }))]);
  if (q.get('t')) TOOLS.tab = q.get('t');
  const FOL = fr.folders || [];
  const rs = all.filter(d => d.kind === 'raster' && !d.trashed_at), vs = all.filter(d => d.kind === 'vector' && !d.trashed_at);
  const okR = rs.filter(d => d.value_type_confirmed);
  const opt = d => `<option value="${d.id}">#${d.id} ${esc(d.name)} · ${esc((d.meta.res_label || '').split(' (')[0])}${(d.meta.count || 1) > 1 ? ` · ${d.meta.count} แบนด์` : ''}${d.value_type ? ' · ' + esc(VT_SHORT[d.value_type] || '') : ''}</option>`;
  const aoiSel = id => `<label class="field"><span>พื้นที่ศึกษา</span><select id="${id}"><option value="">ทั้งขอบเขตที่ข้อมูลทับกัน</option>${aoiOptions(aois)}</select></label>`;
  const T = [['sat', 'ภาพดาวเทียม / SAR'], ['calc', 'สูตรคำนวณ'], ['trend', 'อนุกรมเวลา / ตรวจการเปลี่ยนแปลง'], ['mosaic', 'รวมราสเตอร์'], ['vmerge', 'รวมเวกเตอร์']];
  const v = $('#view');
  v.innerHTML = head('Tools', 'เครื่องมือข้อมูล', 'คำนวณด้วยสูตร (NDVI ฯลฯ) · เทียบอนุกรมเวลาหลายปี · ต่อไฟล์ราสเตอร์ · รวมชั้นเวกเตอร์ — ผลลัพธ์เข้าคลังพร้อมประวัติไฟล์ต้นทาง')
    + `<div class="seg" id="tTabs" style="margin-bottom:14px">${T.map(([k, t]) => `<button data-k="${k}" class="${TOOLS.tab === k ? 'on' : ''}">${t}</button>`).join('')}</div><div id="tBody"></div>`;
  $$('#tTabs button').forEach(b => b.onclick = () => { TOOLS.tab = b.dataset.k; location.hash = '#/tools?t=' + b.dataset.k; });
  const body = $('#tBody');
  const resFill = async (sel, ids) => {
    ids = ids.filter(Boolean);
    if (!ids.length) { sel.innerHTML = '<option value="">— เลือกข้อมูลก่อน —</option>'; return; }
    try {
      const r = await api(`${ENGINE}/api/res-options?ids=${ids.join(',')}`);
      const cur = sel.value;
      sel.innerHTML = r.options.map(o => `<option value="${o.value}">${esc(o.label.split(' (')[0])} · ${fmt(o.px / 1e6, 1)} ล้านพิกเซล${o.is_source.length ? ' · = ข้อมูล' : ''}</option>`).join('');
      sel.value = r.options.some(o => o.value === cur) ? cur : (r.options.filter(o => o.is_source.length).map(o => o.value)[0] || r.options[0]?.value);
    } catch (e) { sel.innerHTML = `<option value="">${esc(e.message)}</option>`; }
  };
  const done = () => location.hash = '#/jobs';
  const checklist = (list, id) => `<input type="search" class="dsp-q" id="${id}Q" placeholder="ค้นหาชื่อชุดข้อมูล" style="margin-bottom:6px">
    <div class="tool-list" id="${id}">${list.map(d => `<label class="tool-it" data-n="${esc(d.name.toLowerCase())}"><input type="checkbox" value="${d.id}"> <span>#${d.id} ${esc(d.name)}</span>
      <span class="tiny muted">${esc((d.meta.res_label || d.meta.crs_name || '').split(' (')[0])}${d.meta.features ? ' · ' + fmt(d.meta.features, 0) + ' feature' : ''}</span></label>`).join('') || '<div class="small muted">ยังไม่มีข้อมูลประเภทนี้ในคลัง</div>'}</div>`;
  const wireCheck = id => { $('#' + id + 'Q').oninput = e => { const t = e.target.value.trim().toLowerCase(); $$(`#${id} .tool-it`).forEach(x => x.classList.toggle('hide', !!t && !x.dataset.n.includes(t))); }; };
  const checked = id => $$(`#${id} input:checked`).map(x => +x.value);

  if (TOOLS.tab === 'sat') {
    const cat = await api(ENGINE + '/api/satellite/catalog');
    const st = TOOLS.sat || (TOOLS.sat = { collection: 'sentinel-2-l2a', bands: null, zoom: 9, date_from: '', date_to: '', cloud_max: 20, pick: '' });
    const today = new Date(), iso = d => d.toISOString().slice(0, 10);
    if (!st.date_to) { st.date_to = iso(today); st.date_from = iso(new Date(today - 90 * 864e5)); }
    const KIND_T = { optical: 'ภาพแสง', sar: 'เรดาร์ SAR', index: 'ดัชนี', dem: 'ความสูง', class: 'การใช้ที่ดิน' };
    body.innerHTML = `<div class="cols2"><div class="card" style="max-width:920px">
      <div class="small muted" style="margin-bottom:10px">ค้นภาพตามพื้นที่ + ช่วงวันที่ + เมฆ แล้วให้เซิร์ฟเวอร์ของ Microsoft Planetary Computer ทำภาพรวม (mosaic) ส่งมาเฉพาะผลลัพธ์ — เร็วกว่าโหลดภาพทั้งแผ่นหลายสิบเท่า · <b>ไม่ต้องมีบัญชี/โทเคน</b></div>
      <div class="grid-form">
        <label class="field full"><span>ข้อมูล</span><select id="saC">${Object.entries(KIND_T).map(([k, t]) => `<optgroup label="${t}">${cat.collections.filter(c => c.kind === k).map(c => `<option value="${c.id}">${esc(c.name)} · ${esc(c.years)}</option>`).join('')}</optgroup>`).join('')}</select></label>
        <div class="field full"><span>แบนด์</span><div id="saB" class="row" style="flex-wrap:wrap;gap:6px 14px"></div><div class="tiny muted" id="saNote"></div></div>
        <label class="field"><span>ตั้งแต่</span><input type="date" id="saF" value="${esc(st.date_from)}"></label>
        <label class="field"><span>ถึง</span><input type="date" id="saT" value="${esc(st.date_to)}"></label>
        <label class="field" id="saCF"><span>เมฆไม่เกิน (%)</span><input type="number" min="0" max="100" id="saCl" value="${esc(st.cloud_max)}"></label>
        <label class="field"><span>รวมหลายภาพแบบ</span><select id="saP"><option value="">ค่าแนะนำ</option><option value="median">ค่ามัธยฐาน (ตัดเมฆ/สัญญาณรบกวน)</option><option value="first">ภาพเมฆน้อยสุดก่อน</option><option value="mean">ค่าเฉลี่ย</option><option value="highest">ค่าสูงสุด</option><option value="lowest">ค่าต่ำสุด</option></select></label>
        <label class="field"><span>ความละเอียด</span><select id="saZ">${cat.zooms.map(z => `<option value="${z.zoom}">${esc(z.label)}</option>`).join('')}</select></label>
        ${aoiSel('saA').replace('<option value="">ทั้งขอบเขตที่ข้อมูลทับกัน</option>', '')}
        <label class="field full"><span>ชื่อผลลัพธ์</span><input type="text" id="saN" placeholder="เช่น Sentinel-2 ม.ค.–มี.ค. 2568 กรุงเทพฯ"></label></div>
      <div class="row" style="margin-top:12px"><button id="saS">${IC.target}ค้นภาพ</button><button id="saR" class="primary">${IC.download}ดึงเข้าคลัง</button></div>
      <div id="saOut" class="small" style="margin-top:10px"></div></div>
      <div class="card"><div class="card-head"><h2><span class="dot" style="background:var(--mint);color:var(--mint)"></span>Project Palantir</h2></div>
        <div class="small">แอปวิเคราะห์ดัชนีพืชพรรณ 22 แบบจาก Sentinel-2 (NDVI, EVI, SAVI, GCI …) วาดแปลงแล้วได้ผลทันที — ต้นแบบของวิธีดึงภาพในหน้านี้</div>
        <div class="row" style="margin-top:10px"><a class="btn sm" href="https://project-palantir.streamlit.app" target="_blank" rel="noopener">${IC.ext}เปิด Palantir</a></div>
        <div class="tiny muted" style="margin-top:8px">ในแอปนี้: ดึง Sentinel-2 แบนด์ที่ต้องใช้ → แท็บ "สูตรคำนวณ" ใส่สูตรดัชนี (มีสำเร็จรูป NDVI/NDWI/NDBI) → ไขว้กับข้อมูลอื่น / อนุกรมเวลา</div></div></div>`;
    const coll = () => cat.collections.find(c => c.id === $('#saC').value);
    const drawBands = () => {
      const c = coll(), sel = st.collection === c.id && st.bands ? st.bands : c.default;
      $('#saB').innerHTML = Object.entries(c.bands).map(([b, t]) => `<label class="small" title="${esc(t)}"><input type="checkbox" value="${esc(b)}" ${sel.includes(b) ? 'checked' : ''}> <b class="mono">${esc(b)}</b> <span class="muted">${esc(t)}</span></label>`).join('');
      $('#saNote').textContent = [c.note, `ต้นทาง ${c.native_m} ม. · ถ่ายซ้ำ ${c.revisit} · ${c.license}`].filter(Boolean).join(' · ');
      $('#saCF').classList.toggle('hide', !c.cloud);
    };
    $('#saC').value = st.collection; $('#saZ').value = st.zoom;
    if (!$('#saA').value) $('#saA').selectedIndex = 0;
    $('#saC').onchange = () => { st.collection = $('#saC').value; st.bands = null; drawBands(); };
    drawBands();
    const params = () => {
      const c = coll(), bands = $$('#saB input:checked').map(x => x.value);
      Object.assign(st, { collection: c.id, bands, zoom: +$('#saZ').value, date_from: $('#saF').value, date_to: $('#saT').value, cloud_max: $('#saCl').value, pick: $('#saP').value });
      return { collection: c.id, bands, zoom: st.zoom, date_from: st.date_from || null, date_to: st.date_to || null, cloud_max: c.cloud && st.cloud_max !== '' ? +st.cloud_max : null,
        pick: st.pick || null, aoi_id: +$('#saA').value || null, name: $('#saN').value.trim() || null };
    };
    $('#saS').onclick = async () => {
      $('#saOut').innerHTML = '<span class="muted">กำลังค้น…</span>';
      try {
        const r = await api(ENGINE + '/api/satellite/search', { json: params() });
        $('#saOut').innerHTML = r.n ? `<b>${fmt(r.n, 0)}${r.more ? '+' : ''} ภาพ</b> · ${esc(r.first)} – ${esc(r.last)}${r.cloud ? ` · เมฆ ${fmt(r.cloud.min, 0)}–${fmt(r.cloud.max, 0)}% (มัธยฐาน ${fmt(r.cloud.median, 0)}%)` : ''}
          <div class="tiny muted" style="margin-top:4px">วันที่มีภาพ: ${r.dates.map(esc).join(', ')}</div>` : '<span class="err">ไม่พบภาพ — ขยายช่วงวันที่ หรือเพิ่มเกณฑ์เมฆ</span>';
      } catch (e) { $('#saOut').innerHTML = `<span class="err">${esc(e.message)}</span>`; }
    };
    $('#saR').onclick = () => runJob('satellite', params(), done);
  } else if (TOOLS.tab === 'calc') {
    const st = TOOLS.calc || (TOOLS.calc = { expr: CALC_PRESETS[0].e, vars: CALC_PRESETS[0].v.map(k => ({ k, id: '', band: '' })) });
    body.innerHTML = `<div class="card" style="max-width:920px">
      <div class="grid-form"><label class="field full"><span>สูตรสำเร็จรูป</span><select id="cpPre"><option value="">— เขียนสูตรเอง —</option>${CALC_PRESETS.map(p => `<option value="${p.k}">${p.t} · ${esc(p.e)}</option>`).join('')}</select></label></div>
      <h3 style="margin:12px 0 6px">ตัวแปร</h3><div id="cpVars"></div><button class="sm" id="cpAdd">${IC.plus}เพิ่มตัวแปร</button>
      <div class="grid-form" style="margin-top:12px"><label class="field full"><span>สูตร</span><input type="text" id="cpExpr" class="mono" value="${esc(st.expr)}" spellcheck="false"></label></div>
      <div class="tiny muted" style="margin:4px 0 12px">ใช้ได้: ตัวแปรด้านบน ตัวเลข + − * / ** % · เปรียบเทียบ &lt; &gt; == (ได้ 1/0) · and or · ฟังก์ชัน where(เงื่อนไข, ค่าจริง, ค่าเท็จ) abs sqrt log log10 exp min max clip round floor ceil · พิกเซลที่ตัวแปรใดไม่มีค่า หรือหารด้วย 0 → ไม่มีข้อมูล</div>
      <div class="grid-form"><label class="field"><span>ความละเอียด</span><select id="cpRes"></select></label>${aoiSel('cpAoi')}
        <label class="field"><span>ประเภทค่าผลลัพธ์</span><select id="cpVt"><option value="density">ต่อเนื่อง (ดัชนี อัตราส่วน)</option><option value="count">จำนวนนับ</option><option value="class">ชั้น (เช่น ผล 1/0)</option></select></label>
        <label class="field"><span>ชื่อผลลัพธ์</span><input type="text" id="cpName" placeholder="เช่น NDVI 2024"></label></div>
      <div class="tiny muted" style="margin:10px 0">ทุกตัวแปรปรับลงกริดเดียวกันตามประเภทค่าของมันก่อนคำนวณ (ต้องระบบพิกัดเดียวกัน) · ผลเป็น float32</div>
      <button id="cpRun" class="primary">${IC.play}คำนวณ</button></div>`;
    const bands = i => {
      const x = st.vars[i], d = okR.find(r => r.id === x.id), n = d ? (d.meta.count || 1) : 1;
      const b = $(`[data-b="${i}"]`);
      b.innerHTML = Array.from({ length: n }, (_, j) => `<option value="${j + 1}">${j + 1}${d?.meta.descriptions?.[j] ? ' · ' + esc(d.meta.descriptions[j]) : ''}</option>`).join('');
      b.value = x.band || (d?.band || 1);
    };
    const draw = () => {
      $('#cpVars').innerHTML = st.vars.map((x, i) => `<div class="row tool-var">
        <label class="field" style="width:110px"><span>ชื่อ</span><input type="text" class="mono" data-k="${i}" value="${esc(x.k)}"></label>
        <label class="field" style="flex:1;min-width:220px"><span>ชุดข้อมูล</span><select data-d="${i}"></select></label>
        <label class="field" style="width:110px"><span>แบนด์</span><select data-b="${i}"></select></label>
        <button class="sm ghost danger" data-x="${i}" title="ลบตัวแปร">${IC.minus}</button></div>`).join('');
      st.vars.forEach((x, i) => {
        const s = $(`[data-d="${i}"]`);
        dsPicker(s, okR, FOL, opt);
        s.value = x.id; bands(i);
        s.onchange = () => { x.id = +s.value || ''; x.band = ''; bands(i); resFill($('#cpRes'), st.vars.map(y => y.id)); };
        $(`[data-k="${i}"]`).oninput = e => x.k = e.target.value.trim();
        $(`[data-b="${i}"]`).onchange = e => x.band = +e.target.value || '';
        $(`[data-x="${i}"]`).onclick = () => { st.vars.splice(i, 1); draw(); };
      });
    };
    draw();
    resFill($('#cpRes'), st.vars.map(y => y.id));
    $('#cpPre').onchange = e => {
      const p = CALC_PRESETS.find(x => x.k === e.target.value); if (!p) return;
      $('#cpExpr').value = st.expr = p.e;
      st.vars = p.v.map((k, i) => ({ k, id: st.vars[i]?.id || '', band: st.vars[i]?.band || '' })); draw();
    };
    $('#cpExpr').oninput = e => st.expr = e.target.value;
    $('#cpAdd').onclick = () => { const used = new Set(st.vars.map(x => x.k)); st.vars.push({ k: 'ABCDEFGHIJKL'.split('').find(c => !used.has(c)) || 'X', id: '', band: '' }); draw(); };
    $('#cpRun').onclick = () => {
      const vars = {};
      for (const x of st.vars) { if (!x.k || !x.id) return toast('ใส่ชื่อและเลือกชุดข้อมูลให้ครบทุกตัวแปร', true); vars[x.k] = { dataset_id: x.id, band: x.band || null }; }
      runJob('calc', { expr: $('#cpExpr').value.trim(), vars, target_res: $('#cpRes').value, aoi_id: +$('#cpAoi').value || null,
        value_type: $('#cpVt').value, name: $('#cpName').value.trim() || null }, done);
    };
  } else if (TOOLS.tab === 'trend') {
    const st = TOOLS.trend || (TOOLS.trend = { items: [] });
    const yearOf = d => (d.name.match(/(?:19|20)\d\d/g) || []).pop() || '';
    body.innerHTML = `<div class="card" style="max-width:920px">
      <div class="small muted" style="margin-bottom:10px">เลือกราสเตอร์ตัวแปรเดียวกันหลายปี (เช่น NDVI 2015–2024 · ประชากรทุก 5 ปี · ชั้นน้ำท่วมรายปี) แล้วใส่ปีของแต่ละชุด — ได้ราสเตอร์ 1 ชั้นตามสถิติที่เลือก</div>
      <div id="trItems"></div>
      <div class="row" style="margin:6px 0 14px"><select id="trPick"></select><button class="sm" id="trAdd">${IC.plus}เพิ่มปี</button></div>
      <div class="grid-form"><label class="field full"><span>สถิติ</span><select id="trStat">${Object.entries(TREND_STATS).map(([k, t]) => `<option value="${k}">${t}</option>`).join('')}</select></label>
        <label class="field" id="trThrF"><span>เกณฑ์</span><input type="number" step="any" id="trThr" placeholder="เช่น 0.5"></label>
        <label class="field"><span>ต้องมีค่าอย่างน้อย (ปี)</span><input type="number" min="2" id="trMin" placeholder="ทุกปี"></label>
        <label class="field"><span>ความละเอียด</span><select id="trRes"></select></label>${aoiSel('trAoi')}
        <label class="field full"><span>ชื่อผลลัพธ์</span><input type="text" id="trName" placeholder="เช่น แนวโน้ม NDVI 2015–2024"></label></div>
      <div class="tiny muted" style="margin:10px 0">แนวโน้มต่อปี = ความชันของเส้นถดถอย (หน่วยข้อมูล/ปี) ใช้ทุกปีที่มีค่า · เปลี่ยนแปลง/% ใช้ปีแรกกับปีท้าย · พิกเซลที่มีค่าน้อยกว่าที่กำหนด → ไม่มีข้อมูล</div>
      <button id="trRun" class="primary">${IC.play}คำนวณ</button></div>`;
    const draw = () => {
      $('#trItems').innerHTML = st.items.length ? `<table><thead><tr><th>ปี</th><th>ชุดข้อมูล</th><th></th></tr></thead><tbody>${st.items.map((x, i) => {
        const d = okR.find(r => r.id === x.id);
        return `<tr><td style="width:110px"><input type="number" data-y="${i}" value="${esc(x.year)}" style="width:90px"></td><td>#${x.id} ${esc(d?.name || '?')}</td><td style="text-align:right"><button class="sm ghost danger" data-x="${i}">${IC.minus}</button></td></tr>`;
      }).join('')}</tbody></table>` : '<div class="small muted">ยังไม่ได้เพิ่มชุดข้อมูล (อย่างน้อย 2 ปี)</div>';
      $$('[data-y]').forEach(e => e.oninput = () => st.items[+e.dataset.y].year = e.value);
      $$('#trItems [data-x]').forEach(e => e.onclick = () => { st.items.splice(+e.dataset.x, 1); draw(); resFill($('#trRes'), st.items.map(x => x.id)); });
    };
    dsPicker($('#trPick'), okR, FOL, opt, '— เลือกชุดข้อมูลเพื่อเพิ่ม —');
    $('#trAdd').onclick = () => {
      const id = +$('#trPick').value; if (!id) return;
      if (st.items.some(x => x.id === id)) return toast('เพิ่มชุดนี้แล้ว', true);
      st.items.push({ id, year: yearOf(okR.find(r => r.id === id)) });
      st.items.sort((a, b) => (+a.year || 0) - (+b.year || 0)); draw(); resFill($('#trRes'), st.items.map(x => x.id));
    };
    const thr = () => $('#trThrF').classList.toggle('hide', !$('#trStat').value.startsWith('count_'));
    $('#trStat').onchange = thr; thr();
    draw(); resFill($('#trRes'), st.items.map(x => x.id));
    $('#trRun').onclick = () => {
      if (st.items.some(x => x.year === '' || x.year == null)) return toast('ใส่ปีให้ครบทุกชุด', true);
      runJob('trend', { items: st.items.map(x => ({ dataset_id: x.id, year: +x.year })), stat: $('#trStat').value,
        threshold: $('#trThr').value === '' ? null : +$('#trThr').value, min_years: +$('#trMin').value || null,
        target_res: $('#trRes').value, aoi_id: +$('#trAoi').value || null, name: $('#trName').value.trim() || null }, done);
    };
  } else if (TOOLS.tab === 'mosaic') {
    body.innerHTML = `<div class="card" style="max-width:920px">
      <div class="small muted" style="margin-bottom:10px">ต่อไฟล์ราสเตอร์หลายแผ่น (เช่น ภาพดาวเทียมหลายแผ่นที่ติดกัน · ข้อมูลรายจังหวัด) เป็นไฟล์เดียว — ทุกไฟล์ต้องระบบพิกัดและจำนวนแบนด์เดียวกัน ใช้ความละเอียดของไฟล์แรก</div>
      ${checklist(rs, 'msL')}
      <div class="grid-form" style="margin-top:12px"><label class="field"><span>ส่วนที่ซ้อนกันใช้ค่าจาก</span><select id="msM"><option value="first">ไฟล์แรกที่มีค่า</option><option value="last">ไฟล์หลังสุด</option><option value="min">ค่าต่ำสุด</option><option value="max">ค่าสูงสุด</option></select></label>
        <label class="field"><span>ชื่อผลลัพธ์</span><input type="text" id="msName" placeholder="เช่น ภาพรวมภาคเหนือ"></label></div>
      <button id="msRun" class="primary" style="margin-top:12px">${IC.play}รวมราสเตอร์</button></div>`;
    wireCheck('msL');
    $('#msRun').onclick = () => runJob('mosaic', { dataset_ids: checked('msL'), method: $('#msM').value, name: $('#msName').value.trim() || null }, done);
  } else {
    body.innerHTML = `<div class="card" style="max-width:920px">
      <div class="small muted" style="margin-bottom:10px">รวม shapefile / GeoPackage / GeoJSON หลายชั้นเป็นชั้นเดียว (GeoPackage) — แปลงพิกัดตามชั้นแรก · เพิ่มคอลัมน์ <span class="mono">source</span> บอกว่ามาจากชั้นไหน · ฟิลด์ที่ไม่ตรงกันเว้นว่าง</div>
      ${checklist(vs, 'vmL')}
      <div class="grid-form" style="margin-top:12px"><label class="field"><span>รวมรูป (dissolve)</span><select id="vmD"><option value="">ไม่รวม — เก็บทุกรูปตามเดิม</option><option value="all">รวมเป็นรูปเดียว</option><option value="field">รวมตามฟิลด์…</option></select></label>
        <div class="tiny muted full">ถ้ารวมไว้เพื่อแปลงเป็นราสเตอร์แบบมี/ไม่มี (presence) ไม่ต้องรวมรูป — ผลพิกเซลเท่ากัน และเร็วกว่ามาก (รวมรูปชุดใหญ่ เช่น น้ำท่วมทั้งปี 28 ล้านจุดยอด ใช้ ~2 นาที)</div>
        <label class="field hide" id="vmFF"><span>ฟิลด์</span><input type="text" id="vmF" placeholder="เช่น prov_code หรือ source"></label>
        <label class="field"><span>ชื่อผลลัพธ์</span><input type="text" id="vmName" placeholder="เช่น ขอบเขตรวม"></label></div>
      <button id="vmRun" class="primary" style="margin-top:12px">${IC.play}รวมเวกเตอร์</button></div>`;
    wireCheck('vmL');
    $('#vmD').onchange = () => $('#vmFF').classList.toggle('hide', $('#vmD').value !== 'field');
    $('#vmRun').onclick = () => runJob('vmerge', { dataset_ids: checked('vmL'), dissolve: !!$('#vmD').value,
      dissolve_field: $('#vmD').value === 'field' ? $('#vmF').value.trim() : null, name: $('#vmName').value.trim() || null }, done);
  }
}

// ================= V3: ระบบ (3.8) =================
async function pageSystem() {
  const s = await api(ENGINE + '/api/system');
  const v = $('#view');
  const DN = { database: 'ไฟล์ที่ก๊อปเข้า / ดาวน์โหลด', derived: 'ผลแปลง', maps: 'แผนที่ไบแวเรียต', aoi: 'พื้นที่ศึกษา', cache: 'แคช (สร้างใหม่ได้เอง)', logs: 'log งาน' };
  v.innerHTML = head('System', 'ระบบ', `Ainulindalë v${STATE.version} · workspace ${esc(STATE.workspace)}`)
    + `<div class="cols2"><div>
      <div class="card"><div class="card-head"><h2><span class="dot"></span>พื้นที่ใน workspace</h2></div>
        <table><tbody>${Object.entries(s.dirs).map(([k, x]) => `<tr><td><b>${k}/</b><div class="tiny muted">${DN[k] || ''}</div></td><td>${fmt(x.files, 0)} ไฟล์</td><td style="text-align:right"><b>${bytes(x.bytes)}</b></td><td><button class="sm ghost" onclick='openFolder(${attr(x.path)})'>${IC.folder}</button></td></tr>`).join('')}</tbody></table></div>
      <div class="card"><div class="card-head"><h2><span class="dot" style="background:var(--peach);color:var(--peach)"></span>แคช</h2></div>
        <table class="kv"><tr><td>สำเนาพรีวิว (overview)</td><td>${bytes(s.cache.preview.bytes)} · ${s.cache.preview.files} ไฟล์</td></tr>
          <tr><td>ค่าสุ่ม (ฮิสโทแกรม/ควอนไทล์)</td><td>${bytes(s.cache.samples.bytes)}</td></tr><tr><td>ไทล์ในหน่วยความจำ</td><td>${fmt(s.tile_cache, 0)} + ลิงก์ ${fmt(s.link_cache, 0)}</td></tr></table>
        <div class="row" style="margin-top:12px"><button id="clrTiles" class="sm">ล้างไทล์ในหน่วยความจำ</button><button id="clrPrev" class="sm danger">ลบสำเนาพรีวิว</button></div>
        <div class="tiny muted" style="margin-top:6px">ลบสำเนาพรีวิวแล้ว แอปสร้างใหม่ให้เองเมื่อเปิดหน้าชุดข้อมูล (ไฟล์ใหญ่อาจใช้เวลาหลายนาที)</div></div>
      <div class="card"><div class="card-head"><h2><span class="dot" style="background:var(--coral);color:var(--coral)"></span>ผลของงานที่ล้มเหลว/ยกเลิก</h2><span class="chip">${s.dead_jobs.length}</span></div>
        ${s.dead_jobs.length ? `<div class="small">${s.dead_jobs.map(j => `<div class="mono tiny">#${j.id} ${esc(j.title)} · ${esc(j.out_dir)}</div>`).join('')}</div><button id="clrDead" class="sm danger" style="margin-top:10px">${IC.trash}ลบโฟลเดอร์ผลที่ไม่สมบูรณ์</button>` : '<div class="small muted">ไม่มี</div>'}</div>
    </div><div>
      <div class="card"><div class="card-head"><h2><span class="dot" style="background:var(--lav);color:var(--lav)"></span>โทเคน (เข้ารหัส)</h2><button class="sm" id="secAdd">${IC.plus}เพิ่ม</button></div>
        ${s.secrets.length ? `<table><tbody>${s.secrets.map(x => `<tr><td>${IC.lock}${esc(x.name)}</td><td class="mono tiny muted">${x.id}</td><td style="text-align:right"><button class="sm ghost danger" data-sec="${x.id}">${IC.trash}</button></td></tr>`).join('')}</tbody></table>` : '<div class="small muted">ยังไม่มี</div>'}
        <div class="tiny muted" style="margin-top:8px">เข้ารหัสด้วย Windows DPAPI · ใช้กับลิงก์ ArcGIS / WMS ที่ต้องยืนยันตัวตน · ไม่ถูกบันทึกใน lineage หรือ log</div></div>
      <div class="card" id="aiCard"></div>
    </div></div>`;
  if (window.AIDock) AIDock.settingsCard($('#aiCard'));
  const clr = async (what, ask) => {
    if (ask && !await ui.confirm('ยืนยัน', `<p>${ask}</p>`, 'ดำเนินการ')) return;
    const r = await api(ENGINE + '/api/system/clear', { json: { what } }); toast(`เรียบร้อย${r.freed ? ' · คืนพื้นที่ ' + bytes(r.freed) : ''}`); route();
  };
  $('#clrTiles').onclick = () => clr('tiles');
  $('#clrPrev').onclick = () => clr('preview', 'ลบสำเนาพรีวิวทั้งหมด? แอปจะสร้างใหม่ทีละชุดเมื่อเปิดดู');
  if ($('#clrDead')) $('#clrDead').onclick = () => clr('dead_jobs', 'ลบโฟลเดอร์ผลของงานที่ล้มเหลว/ยกเลิก (ไฟล์ที่ไม่สมบูรณ์) — ย้อนกลับไม่ได้');
  $('#secAdd').onclick = async () => { if (await addSecret()) route(); };
  $$('[data-sec]').forEach(b => b.onclick = async () => { if (await ui.confirm('ลบโทเคน?', '<p>ลิงก์ที่ใช้โทเคนนี้จะเข้าไม่ได้</p>', 'ลบ')) { await api(ENGINE + '/api/secrets/' + b.dataset.sec, { method: 'DELETE' }); route(); } });
}

// ================= แผนที่ซ้อนชั้น (Map viewer) =================
// ชั้นข้อมูลหลายชุดบนแผนที่เดียว: เปิด/ปิด · ลำดับ (ลาก/↑↓) · ความโปร่งใส · สไตล์ต่อชั้น · คลิกดูค่าทุกชั้น · คำอธิบาย
const VKEY = 'viewerLayers.v1';
const vLoad = () => { try { return JSON.parse(localStorage.getItem(VKEY)) || []; } catch { return []; } };
const vSave = L_ => { try { localStorage.setItem(VKEY, JSON.stringify(L_)); } catch { } };
const V_PAL = ['#f7a8cc', '#9ee8d4', '#a6cdff', '#ffc2a8', '#c3b6ff', '#f6e3a1', '#ff9aa8'];
function viewerAdd(items) {                       // ใช้จากหน้าอื่น: เพิ่มชั้นแล้วไปหน้าแผนที่ซ้อนชั้น
  const L_ = vLoad();
  for (const it of items) if (!L_.some(l => l.key === it.key)) L_.unshift(it);
  vSave(L_);
}
function vLayerFromDs(d, i = 0) {
  const kind = d.kind === 'link' ? (d.meta.view ? 'linktile' : 'linkdata') : d.kind;
  return { key: (d.kind === 'link' ? 'lk:' : 'ds:') + d.id, kind, id: d.id, name: d.name, visible: true, opacity: 1,
    style: { stroke: V_PAL[i % V_PAL.length], width: 1.2, fill: V_PAL[i % V_PAL.length], fillOpacity: .15, useColor: (d.meta.fields || []).some(f => (f.name || f) === 'color') } };
}

async function pageViewer() {
  const [all, aois] = await Promise.all([api(ENGINE + '/api/datasets'), api(ENGINE + '/api/aoi')]);
  const byKey = {};
  all.forEach(d => byKey[(d.kind === 'link' ? 'lk:' : 'ds:') + d.id] = d);
  aois.forEach(a => byKey['aoi:' + a.id] = a);
  let layers = vLoad().filter(l => byKey[l.key]);          // ชั้นที่ชุดข้อมูลถูกลบไปแล้วตัดทิ้ง
  const v = $('#view');
  v.innerHTML = `<div class="viewer">
    <div class="vpanel">
      <div class="row" style="justify-content:space-between"><div><div class="eyebrow">Map</div><h2 style="font-size:20px">แผนที่ซ้อนชั้น</h2></div>
        <div class="row"><a class="btn sm" href="#/report?viewer=1" title="ส่งออกชั้นที่เปิดอยู่เป็นแผนที่สำหรับพิมพ์">${IC.pdf}รายงาน</a><button class="primary sm" id="vAdd">${IC.plus}เพิ่มชั้น</button></div></div>
      <div class="tiny muted" style="margin:6px 0 10px">ชั้นบนสุดในรายการ = อยู่บนสุดของแผนที่ · ลากเพื่อสลับลำดับ</div>
      <div id="vList" class="vlist"></div>
      <div id="vSym" class="vsym hide"></div>
      <h3>คำอธิบาย</h3><div id="vLegend" class="vlegend"></div>
      <h3>ค่าที่จุด</h3><div id="vPt" class="small muted">คลิกบนแผนที่เพื่อดูค่าของทุกชั้นที่เปิดอยู่</div>
    </div>
    <div class="vmap"><div class="mapbar vbar"><div class="seg" id="bm"><button data-k="gh">ดาวเทียม</button><button data-k="osm">แผนที่</button><button data-k="none">ไม่มี</button></div>
      <span class="tiny muted" id="mapNote"></span></div><div id="map"></div></div></div>`;
  const mp = baseMap('map');
  window._mapObj = mp;
  bmSeg(mp, $('#bm'));
  mp.setView([13.2, 100.9], 6);
  const objs = new Map();                                    // key → { obj, pane }
  let styles = {};                                           // ds id → style (คำอธิบาย)
  const save = () => vSave(layers);

  // ---------- วาดชั้นบนแผนที่ ----------
  const paneOf = l => {
    const n = 'p_' + l.key.replace(/\W/g, '_');
    if (!mp.getPane(n)) mp.createPane(n);
    return n;
  };
  const vecStyle = l => f => ({
    pane: paneOf(l), color: l.style.useColor && f?.properties?.color ? '#ffffff' : l.style.stroke, weight: +l.style.width,
    opacity: l.opacity, fillColor: l.style.useColor && f?.properties?.color ? f.properties.color : l.style.fill,
    fillOpacity: (l.style.useColor && f?.properties?.color ? .85 : +l.style.fillOpacity) * l.opacity,
  });
  const loadVec = async (l, o) => {
    if (!l.visible) return;
    const bb = mp.getBounds();
    const q = [bb.getWest(), bb.getSouth(), bb.getEast(), bb.getNorth()].map(x => x.toFixed(5)).join(',');
    const base = l.kind === 'linkdata' ? `${ENGINE}/api/links/${l.id}` : `${ENGINE}/api/datasets/${l.id}`;
    const my = (o.req = (o.req || 0) + 1);
    try {
      const r = await fetch(`${base}/features?bbox=${q}&z=${mp.getZoom()}&limit=3000${l.style.useColor ? '&fields=color,code' : ''}`);
      if (!r.ok) return;
      const gj = await r.json();
      if (my !== o.req) return;
      o.obj.clearLayers(); o.obj.addData(gj);
      o.trunc = r.headers.get('X-Truncated') === '1';
      renderList();
    } catch { }
  };
  const make = l => {
    const pane = paneOf(l);
    let obj;
    if (l.kind === 'raster') { obj = L.tileLayer(rBase(l), { pane, maxZoom: 22, opacity: l.opacity }); if (l.rstyle) applyRStyle(l, obj); }
    else if (l.kind === 'linktile') obj = L.tileLayer(`${ENGINE}/api/links/${l.id}/tile/{z}/{x}/{y}.png`, { pane, maxZoom: 22, opacity: l.opacity });
    else if (l.kind === 'aoi') {
      obj = L.geoJSON(null, { style: () => ({ pane, color: l.style.stroke, weight: +l.style.width + 1, fill: true, fillColor: l.style.fill, fillOpacity: +l.style.fillOpacity * l.opacity, opacity: l.opacity }) });
      api(`${ENGINE}/api/aoi/${l.id}.geojson`).then(g => { obj.addData(g); obj.setStyle(() => ({ pane, color: l.style.stroke, weight: +l.style.width + 1, fillColor: l.style.fill, fillOpacity: +l.style.fillOpacity * l.opacity, opacity: l.opacity })); });
    } else {
      obj = L.geoJSON(null, { pane, style: vecStyle(l), pointToLayer: (f, ll) => L.circleMarker(ll, { pane, radius: 4 }) });
    }
    const o = { obj, pane };
    objs.set(l.key, o);
    if (['vector', 'linkdata'].includes(l.kind)) loadVec(l, o);
    return o;
  };
  // สไตล์ raster เฉพาะหน้านี้ (l.rstyle) → ส่งเป็นสไตล์ชั่วคราวให้เซิร์ฟเวอร์ (token) ไม่แตะสไตล์ของชุดข้อมูล
  const rBase = l => `${ENGINE}/api/datasets/${l.id}/tile/{z}/{x}/{y}.png?v=${encodeURIComponent(byKey[l.key].fingerprint || '')}${l.clip && byKey['aoi:' + l.clip] ? '&clip=' + l.clip : ''}`;
  const applyRStyle = async (l, obj) => {
    obj = obj || objs.get(l.key)?.obj;
    if (!obj) return;
    const my = (obj._stReq = (obj._stReq || 0) + 1);
    let url = rBase(l);
    if (l.rstyle) { try { url += '&st=' + (await api(ENGINE + '/api/style-preview', { json: { dataset_id: l.id, style: l.rstyle } })).token; } catch { } }
    if (my === obj._stReq) obj.setUrl(url);
  };
  const openSym = l => {
    const box = $('#vSym');
    box.classList.remove('hide'); box.dataset.k = l.key;
    symPanel(byKey[l.key], {
      el: box, viewer: true, style: l.rstyle || null,
      onStyle: s => { l.rstyle = JSON.parse(JSON.stringify(s)); save(); applyRStyle(l); renderLegend(); renderList(); },
      onReset: () => { delete l.rstyle; save(); applyRStyle(l); renderLegend(); renderList(); },
      onClose: () => { box.classList.add('hide'); box.innerHTML = ''; delete box.dataset.k; },
    });
    box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  };
  const sync = () => {
    for (const [k, o] of objs) if (!layers.some(l => l.key === k)) { mp.removeLayer(o.obj); objs.delete(k); }
    if ($('#vSym').dataset.k && !layers.some(l => l.key === $('#vSym').dataset.k)) { $('#vSym').classList.add('hide'); $('#vSym').innerHTML = ''; delete $('#vSym').dataset.k; }
    const n = layers.length;
    layers.forEach((l, i) => {
      const o = objs.get(l.key) || make(l);
      mp.getPane(o.pane).style.zIndex = String(400 + (n - i) * 2);    // บนสุดของรายการ = บนสุดของแผนที่
      if (l.visible && !mp.hasLayer(o.obj)) { o.obj.addTo(mp); if (['vector', 'linkdata'].includes(l.kind)) loadVec(l, o); }
      if (!l.visible && mp.hasLayer(o.obj)) mp.removeLayer(o.obj);
      if (o.obj.setOpacity) o.obj.setOpacity(l.opacity);
      else if (l.kind === 'aoi') o.obj.setStyle({ color: l.style.stroke, weight: +l.style.width + 1, fillColor: l.style.fill, fillOpacity: +l.style.fillOpacity * l.opacity, opacity: l.opacity });
      else o.obj.setStyle(vecStyle(l));
    });
    save(); renderLegend();
  };
  let mt; mp.on('moveend', () => { clearTimeout(mt); mt = setTimeout(() => layers.forEach(l => { const o = objs.get(l.key); if (o && ['vector', 'linkdata'].includes(l.kind)) loadVec(l, o); }), 250); });

  // ---------- รายการชั้น ----------
  const KCH = { raster: ['raster', 'raster'], vector: ['vector', 'vector'], linktile: ['ลิงก์ภาพ', 'map'], linkdata: ['ลิงก์ข้อมูล', 'vector'], aoi: ['พื้นที่ศึกษา', 'derived'] };
  const open = new Set();
  let dragKey = null;
  const renderList = () => {
    const el = $('#vList');
    if (!layers.length) { el.innerHTML = '<div class="empty">ยังไม่มีชั้น — กด "เพิ่มชั้น"</div>'; return; }
    el.innerHTML = layers.map((l, i) => {
      const d = byKey[l.key], o = objs.get(l.key);
      const [kl, kc] = KCH[l.kind] || [l.kind, ''];
      const vec = ['vector', 'linkdata', 'aoi'].includes(l.kind);
      return `<div class="vrow ${l.visible ? '' : 'off'}" draggable="true" data-k="${esc(l.key)}">
        <div class="vhead"><span class="grip" title="ลากเพื่อสลับลำดับ">⋮⋮</span>
          <label class="eye" title="แสดง/ซ่อน"><input type="checkbox" data-a="vis" ${l.visible ? 'checked' : ''}><i></i></label>
          <span class="vswatch" style="${l.kind === 'raster' || l.kind === 'linktile' ? 'background:linear-gradient(135deg,#c3b6ff,#9ee8d4)' : `background:${l.style.fill};border-color:${l.style.stroke}`}"></span>
          <span class="vname" title="${esc(l.name)}">${esc(l.name)}</span>
          <span class="chip ${kc}" style="font-size:10.5px">${kl}</span>
          <button class="sm ghost" data-a="more" title="ตั้งค่า">${open.has(l.key) ? '▴' : '▾'}</button></div>
        ${open.has(l.key) ? `<div class="vbody">
          <label class="row small">ความทึบ <input type="range" data-a="op" min="0" max="1" step="0.05" value="${l.opacity}"><b>${Math.round(l.opacity * 100)}%</b></label>
          ${vec ? `<div class="vgrid">
            ${l.kind !== 'aoi' && d?.meta?.fields?.some(f => (f.name || f) === 'color') ? `<label class="row small full"><input type="checkbox" data-a="uc" ${l.style.useColor ? 'checked' : ''}> ใช้สีจากข้อมูล (ฟิลด์ color)</label>` : ''}
            <label class="small">เส้น <input type="color" data-a="stroke" value="${l.style.stroke}"></label>
            <label class="small">หนา <input type="range" data-a="width" min="0" max="5" step="0.2" value="${l.style.width}"></label>
            <label class="small">พื้น <input type="color" data-a="fill" value="${l.style.fill}"></label>
            <label class="small">ความทึบพื้น <input type="range" data-a="fo" min="0" max="1" step="0.05" value="${l.style.fillOpacity}"></label></div>` : ''}
          ${l.kind === 'raster' ? `<div class="row small" style="margin-top:6px"><button class="sm" data-a="sym">${IC.palette}ปรับสัญลักษณ์</button>
            <span class="tiny ${l.rstyle ? '' : 'muted'}" ${l.rstyle ? 'style="color:var(--mint)"' : ''}>${l.rstyle ? 'ปรับเฉพาะแผนที่นี้' : 'ตามสไตล์ของชุดข้อมูล'}</span></div>
            <label class="row small" style="margin-top:6px" title="ตัดการแสดงผลตามรูปพื้นที่ศึกษา — แสดงผลเท่านั้น ไฟล์ไม่เปลี่ยน">แสดง <select data-a="clip" class="sm"><option value="">ทั้งกรอบข้อมูล</option>${aoiOptions(aois, { text: a => esc(a.name), sel: l.clip || '' })}</select></label>` : ''}
          ${o?.trunc ? '<div class="tiny" style="color:var(--butter)">แสดงไม่ครบในกรอบนี้ — ซูมเข้า</div>' : ''}
          <div class="row" style="margin-top:8px">
            <button class="sm" data-a="zoom">${IC.target}ซูมไปชั้นนี้</button>
            <button class="sm ghost" data-a="up" ${i === 0 ? 'disabled' : ''}>↑</button><button class="sm ghost" data-a="down" ${i === layers.length - 1 ? 'disabled' : ''}>↓</button>
            ${l.kind !== 'aoi' ? `<a class="btn sm ghost" href="#/ds/${l.id}">เปิดหน้าข้อมูล</a>` : ''}
            <span class="spacer"></span><button class="sm ghost danger" data-a="rm">${IC.trash}</button></div></div>` : ''}
      </div>`;
    }).join('');
    $$('.vrow', el).forEach(row => {
      const l = layers.find(x => x.key === row.dataset.k);
      $$('[data-a]', row).forEach(c => {
        const a = c.dataset.a;
        const ev = c.type === 'range' || c.type === 'color' ? 'oninput' : c.tagName === 'INPUT' || c.tagName === 'SELECT' ? 'onchange' : 'onclick';
        c[ev] = () => {
          if (a === 'vis') { l.visible = c.checked; row.classList.toggle('off', !l.visible); sync(); return; }
          if (a === 'clip') { l.clip = c.value || null; applyRStyle(l); sync(); return; }
          if (a === 'more') { open.has(l.key) ? open.delete(l.key) : open.add(l.key); renderList(); return; }
          if (a === 'op') { l.opacity = +c.value; c.nextElementSibling.textContent = Math.round(l.opacity * 100) + '%'; sync(); return; }
          if (a === 'uc') l.style.useColor = c.checked;
          if (a === 'stroke') l.style.stroke = c.value;
          if (a === 'fill') l.style.fill = c.value;
          if (a === 'width') l.style.width = +c.value;
          if (a === 'fo') l.style.fillOpacity = +c.value;
          if (['uc', 'stroke', 'fill', 'width', 'fo'].includes(a)) { sync(); if (a === 'uc') { const o = objs.get(l.key); loadVec(l, o); } $('.vswatch', row).style.cssText = `background:${l.style.fill};border-color:${l.style.stroke}`; return; }
          if (a === 'zoom') { zoomLayer(l); return; }
          if (a === 'sym') { openSym(l); return; }
          const i = layers.indexOf(l);
          if (a === 'up' && i > 0) [layers[i - 1], layers[i]] = [layers[i], layers[i - 1]];
          if (a === 'down' && i < layers.length - 1) [layers[i + 1], layers[i]] = [layers[i], layers[i + 1]];
          if (a === 'rm') layers.splice(i, 1);
          sync(); renderList();
        };
      });
      // ลากสลับลำดับ
      row.ondragstart = e => { dragKey = l.key; row.classList.add('drag'); e.dataTransfer.effectAllowed = 'move'; };
      row.ondragend = () => { dragKey = null; row.classList.remove('drag'); $$('.vrow', el).forEach(r => r.classList.remove('over')); };
      row.ondragover = e => { e.preventDefault(); if (dragKey && dragKey !== l.key) row.classList.add('over'); };
      row.ondragleave = () => row.classList.remove('over');
      row.ondrop = e => {
        e.preventDefault(); row.classList.remove('over');
        if (!dragKey || dragKey === l.key) return;
        const from = layers.findIndex(x => x.key === dragKey);
        const [m] = layers.splice(from, 1);
        layers.splice(layers.indexOf(l), 0, m);
        sync(); renderList();
      };
    });
  };
  const zoomLayer = l => {
    const d = byKey[l.key];
    const b = l.kind === 'aoi' ? d.bbox : d?.meta?.bounds_wgs84;
    if (b) mp.flyToBounds([[b[1], b[0]], [b[3], b[2]]], { padding: [20, 20], duration: .7 });
  };

  // ---------- คำอธิบาย ----------
  const renderLegend = async () => {
    const el = $('#vLegend');
    const vis = layers.filter(l => l.visible);
    if (!vis.length) { el.innerHTML = '<div class="tiny muted">—</div>'; return; }
    for (const l of vis) if (l.kind === 'raster' && !styles[l.id]) { try { styles[l.id] = (await api(`${ENGINE}/api/datasets/${l.id}/style`)).style; } catch { styles[l.id] = {}; } }
    el.innerHTML = vis.map(l => {
      let body = '';
      if (l.kind === 'raster') {
        const s = l.rstyle || styles[l.id] || {}, it = ((s.type === 'paletted' ? s.entries : s.stops) || []).filter(e => e.visible !== false);
        body = s.type === 'pseudocolor' && s.interp === 'linear'
          ? `<div class="ml-bar" style="background:linear-gradient(90deg,${it.map(x => x.color).join(',')})"></div><div class="ml-mm"><span>${esc(it[0]?.label ?? '')}</span><span>${esc(it.at(-1)?.label ?? '')}</span></div>`
          : it.slice(0, 10).map(e => `<div class="ml-row"><i style="background:${e.color}"></i>${esc(e.label ?? e.value)}</div>`).join('') + (it.length > 10 ? `<div class="tiny muted">… อีก ${it.length - 10}</div>` : '');
      } else if (l.kind === 'linktile') body = '<div class="tiny muted">ภาพจากบริการ</div>';
      else body = `<div class="ml-row"><i style="background:${l.style.useColor ? 'linear-gradient(135deg,#e8e8e8,#574249)' : l.style.fill};border:2px solid ${l.style.stroke}"></i>${l.style.useColor ? 'สีตามข้อมูล' : esc(l.name)}</div>`;
      return `<div class="vleg"><b>${esc(l.name)}</b>${body}</div>`;
    }).join('');
  };

  // ---------- คลิกดูค่าทุกชั้น ----------
  let mark = null;
  mp.on('click', async e => {
    const { lat } = e.latlng, lng = e.latlng.wrap().lng;
    if (mark) mp.removeLayer(mark);
    // หมุดอยู่ pane ของตัวเองเหนือทุกชั้น (ชั้นข้อมูลแต่ละชั้นมี pane z-index 402+ ส่วน overlayPane ปกติ = 400 → หมุดเคยจมใต้ชั้น)
    if (!mp.getPane('vMark')) { const pn = mp.createPane('vMark'); pn.style.zIndex = '690'; pn.style.pointerEvents = 'none'; }
    mark = L.circleMarker(e.latlng, { pane: 'vMark', interactive: false, radius: 7, color: '#f6e3a1', weight: 2.5, fillOpacity: 0 }).addTo(mp);
    const vis = layers.filter(l => l.visible && ['raster', 'vector'].includes(l.kind));
    if (!vis.length) { $('#vPt').innerHTML = '<span class="muted">ไม่มีชั้นข้อมูล (raster/vector) ที่เปิดอยู่</span>'; return; }
    $('#vPt').innerHTML = `<div class="mono muted">${lat.toFixed(6)}, ${lng.toFixed(6)}</div><div class="tiny muted">กำลังอ่านค่า…</div>`;
    const res = await Promise.all(vis.map(l => api(`${ENGINE}/api/datasets/${l.id}/point?lon=${lng}&lat=${lat}&z=${mp.getZoom()}`).catch(er => ({ error: er.message }))));
    $('#vPt').innerHTML = `<div class="mono muted" style="margin-bottom:6px">${lat.toFixed(6)}, ${lng.toFixed(6)}</div>` + vis.map((l, i) => {
      const r = res[i];
      let val;
      if (r.error) val = `<span style="color:var(--coral)">${esc(r.error)}</span>`;
      else if (r.kind === 'raster') {
        if (r.outside) val = '<span class="muted">นอกขอบเขต</span>';
        else { const b = r.bands[(byKey[l.key].band || 1) - 1] || r.bands[0]; val = b.nodata ? `<span class="muted">nodata${r.nodata_as != null ? ' → ' + r.nodata_as : ''}</span>` : `<b>${fmt(b.value, 4)}</b>${r.density != null ? ` <span class="tiny muted">(${fmt(r.density, 1)} /ตร.กม.)</span>` : ''}${r.color ? ` <i class="dotc" style="background:${r.color}"></i>` : ''}`; }
      } else val = r.features?.length ? Object.entries(r.features[0].attrs).slice(0, 6).map(([k, x]) => `<div class="tiny"><span class="muted">${esc(k)}</span> ${esc(x)}</div>`).join('') : '<span class="muted">ไม่มี feature</span>';
      return `<div class="vpt"><div class="vpt-n">${esc(l.name)}</div><div>${val}</div></div>`;
    }).join('');
  });

  // ---------- เพิ่มชั้น ----------
  $('#vAdd').onclick = async () => {
    const have = new Set(layers.map(l => l.key));
    const groups = [['ข้อมูลนำเข้า', all.filter(d => d.role === 'input' && d.kind !== 'link')], ['ข้อมูลที่แปลงแล้ว', all.filter(d => d.role === 'derived')],
      ['แผนที่ไบแวเรียต', all.filter(d => d.role === 'map')], ['ลิงก์', all.filter(d => d.kind === 'link')]];
    const row = (key, name, sub) => `<label><input type="checkbox" value="${esc(key)}" ${have.has(key) ? 'checked disabled' : ''}><span>${esc(name)} <span class="tiny muted">${esc(sub)}</span></span></label>`;
    const html = groups.filter(g => g[1].length).map(([t, ds]) => `<div class="tiny muted" style="margin:8px 0 2px">${t}</div>` +
      ds.map(d => row((d.kind === 'link' ? 'lk:' : 'ds:') + d.id, d.name, d.kind === 'link' ? d.meta.type_label : d.kind === 'raster' ? (d.meta.res_label || '').split(' (')[0] : `${fmt(d.meta.features, 0)} feature`)).join('')).join('')
      + [['พื้นที่ศึกษาพื้นฐาน', aois.filter(a => a.builtin)], ['พื้นที่ศึกษาที่สร้างเอง', aois.filter(a => !a.builtin)]].map(([t, xs]) => xs.length
        ? `<div class="tiny muted" style="margin:8px 0 2px">${t}</div>` + xs.map(a => row('aoi:' + a.id, a.name, `${fmt(a.area_km2, 0)} ตร.กม.`)).join('') : '').join('');
    const pick = await ui.open('เพิ่มชั้นข้อมูล', `${CL_Q}<div class="checklist" style="max-height:52vh">${html}</div>`,
      [{ label: 'ยกเลิก', cls: 'ghost', value: () => null }, { label: 'เพิ่ม', cls: 'primary', value: () => $$('#mBody input:checked:not(:disabled)').map(i => i.value) }]);
    if (!pick || !pick.length) return;
    pick.forEach((k, i) => {
      const d = byKey[k];
      const l = k.startsWith('aoi:') ? { key: k, kind: 'aoi', id: d.id, name: d.name, visible: true, opacity: 1, style: { stroke: '#f6e3a1', width: 1.5, fill: '#c3b6ff', fillOpacity: .08 } }
        : vLayerFromDs(d, layers.length + i);
      layers.unshift(l);
    });
    sync(); renderList();
    zoomLayer(layers[0]);
  };

  sync(); renderList();
  const first = layers.find(l => l.visible);
  if (first) zoomLayer(first);
}

// ================= ออกแบบรายงาน — ตัวแก้แบบแคนวาส (v0.5) =================
// เริ่มจากเทมเพลต → ลาก/ย่อขยาย/แก้ข้อความ/เพิ่มองค์ประกอบได้ · หน้าจอ = PDF (พิมพ์ด้วย Edge headless จาก report.js ตัวเดียวกัน)
const RDOC = 'reportDoc.v2';
const BM_LABEL = { none: 'ไม่มี', esri_light: 'เทาอ่อน Esri (เหมาะพิมพ์)', esri_dark: 'เทาเข้ม Esri', esri_topo: 'ภูมิประเทศ Esri', esri_imagery: 'ภาพดาวเทียม Esri', osm: 'OpenStreetMap', google_hybrid: 'Google Hybrid ⚠ ตรวจข้อกำหนดก่อนเผยแพร่' };
const RP_SIZE = { map: [120, 90], inset: [40, 30], legend: [50, 60], scalebar: [50, 12], north: [10, 14], text: [70, 12], rect: [40, 25], line: [60, 1], image: [30, 20], kpi: [90, 24], chart: [80, 50], prov: [60, 40], credits: [110, 12] };
const RP_ICON = { map: '🗺', inset: '📍', legend: '☰', scalebar: '📏', north: '🧭', text: 'T', rect: '▭', line: '―', image: '🖼', kpi: '#', chart: '📊', prov: 'ℹ', credits: '©' };
const RP_F = {
  text: [['text', 'ข้อความ', 'area'], ['fs', 'ขนาด (pt)', 'num', [4, 120, .5]], ['fw', 'น้ำหนัก', 'sel', { 300: 'บาง', 400: 'ปกติ', 500: 'กลาง', 600: 'หนา', 700: 'หนามาก' }], ['color', 'สีตัวอักษร', 'color'],
    ['align', 'จัดแนว', 'seg', { left: 'ซ้าย', center: 'กลาง', right: 'ขวา' }], ['valign', 'แนวตั้ง', 'seg', { top: 'บน', middle: 'กลาง', bottom: 'ล่าง' }], ['lh', 'ระยะบรรทัด', 'num', [.8, 3, .05]],
    ['ls', 'ระยะตัวอักษร (em)', 'num', [-.1, .5, .01]], ['italic', 'ตัวเอียง', 'chk'], ['upper', 'ตัวพิมพ์ใหญ่ (อังกฤษ)', 'chk'], ['bg', 'พื้นหลัง', 'colorx'], ['bc', 'สีกรอบ', 'colorx'],
    ['bw', 'ความหนากรอบ (มม.)', 'num', [0, 5, .05]], ['pad', 'ระยะขอบใน (มม.)', 'num', [0, 30, .5]], ['r', 'มุมโค้ง (มม.)', 'num', [0, 30, .5]]],
  map: [['grid', 'กริดพิกัด', 'sel', { none: 'ไม่แสดง', ticks: 'ขีดที่ขอบกรอบ', lines: 'เส้นตาราง' }], ['gridLabels', 'ป้ายพิกัด', 'sel', { '': 'ไม่แสดง', lb: 'ซ้าย + ล่าง (นอกกรอบ)', lbtr: 'ทุกด้าน (นอกกรอบ)', i: 'ในกรอบ' }],
    ['gfs', 'ขนาดป้ายพิกัด (pt)', 'num', [4, 16, .5]], ['gridColor', 'สีเส้นตาราง', 'color'], ['gridOp', 'ความทึบเส้นตาราง', 'range', [0, 1, .05]], ['fw', 'เส้นกรอบ (มม.)', 'num', [0, 3, .05]], ['fc', 'สีกรอบ/ป้ายพิกัด', 'color'],
    ['bg', 'พื้นหลังกรอบ', 'colorx'], ['labels', 'ป้ายชื่อขอบเขต', 'chk'], ['lfs', 'ขนาดป้ายชื่อ (pt)', 'num', [3, 24, .5]], ['lcolor', 'สีป้ายชื่อ', 'color'], ['halo', 'ขอบรอบป้ายชื่อ', 'colorx']],
  inset: [['title', 'หัวข้อ', 'txt'], ['fs', 'ขนาดหัวข้อ (pt)', 'num', [4, 16, .5]], ['basemap', 'พื้นหลัง', 'sel', BM_LABEL], ['zoom', 'ซูม', 'range', [.3, 5, .1]], ['rc', 'สีกรอบพื้นที่', 'color'],
    ['fw', 'เส้นกรอบ (มม.)', 'num', [0, 3, .05]], ['fc', 'สีกรอบ', 'color']],
  legend: [['title', 'หัวข้อ', 'txt'], ['tfs', 'ขนาดหัวข้อ (pt)', 'num', [5, 36, .5]], ['fs', 'ขนาดตัวอักษร (pt)', 'num', [4, 28, .5]], ['color', 'สีตัวอักษร', 'color'], ['cols', 'จำนวนคอลัมน์', 'num', [1, 4, 1]],
    ['bg', 'พื้นหลัง', 'colorx'], ['bc', 'สีกรอบ', 'colorx'], ['bw', 'ความหนากรอบ', 'num', [0, 3, .05]], ['pad', 'ระยะขอบใน', 'num', [0, 15, .5]], ['r', 'มุมโค้ง', 'num', [0, 10, .5]]],
  scalebar: [['style', 'รูปแบบ', 'sel', { alt: 'แท่งสลับสี', double: 'แท่งคู่', line: 'เส้นมีขีด' }], ['seg', 'จำนวนช่อง', 'num', [1, 10, 1]], ['ratio', 'แสดงมาตราส่วน 1:xxx', 'chk'],
    ['align', 'จัดแนว', 'seg', { left: 'ซ้าย', center: 'กลาง', right: 'ขวา' }], ['fs', 'ขนาดตัวอักษร', 'num', [4, 18, .5]], ['color', 'สี', 'color'], ['bg', 'พื้นหลัง', 'colorx']],
  north: [['style', 'รูปแบบ', 'sel', { classic: 'ลูกศรสองสี', simple: 'ลูกศรเส้น', compass: 'เข็มทิศ', star: 'ดาวสี่แฉก' }], ['color', 'สี', 'color']],
  rect: [['fill', 'สีพื้น', 'colorx'], ['stroke', 'สีเส้น', 'colorx'], ['sw', 'ความหนาเส้น (มม.)', 'num', [0, 5, .05]], ['r', 'มุมโค้ง (มม.)', 'num', [0, 40, .5]], ['op', 'ความทึบ', 'range', [0, 1, .05]]],
  line: [['color', 'สี', 'color'], ['width', 'ความหนา (มม.)', 'num', [.05, 5, .05]], ['dash', 'เส้นประ', 'chk']],
  image: [['fit', 'การจัดภาพ', 'sel', { contain: 'พอดีกรอบ', cover: 'เต็มกรอบ (ตัดขอบ)' }]],
  kpi: [['fs', 'ขนาดตัวเลข (pt)', 'num', [6, 48, .5]], ['lfs', 'ขนาดคำอธิบาย', 'num', [4, 16, .5]], ['color', 'สีตัวเลข', 'color'], ['bg', 'พื้นการ์ด', 'colorx'], ['bc', 'กรอบการ์ด', 'colorx'],
    ['r', 'มุมโค้ง', 'num', [0, 10, .5]], ['gap', 'ระยะห่าง', 'num', [0, 10, .5]]],
  chart: [['title', 'หัวข้อ (auto = อัตโนมัติ)', 'txt'], ['tfs', 'ขนาดหัวข้อ', 'num', [4, 24, .5]], ['fs', 'ขนาดตัวอักษร', 'num', [4, 16, .5]], ['color', 'สีตัวอักษร', 'color'], ['bg', 'พื้นหลัง', 'colorx']],
  prov: [['title', 'หัวข้อ', 'txt'], ['tfs', 'ขนาดหัวข้อ', 'num', [4, 24, .5]], ['fs', 'ขนาดตัวอักษร', 'num', [4, 16, .5]], ['color', 'สี', 'color'], ['note', 'รวมหมายเหตุ', 'chk']],
  credits: [['extra', 'ข้อความบรรทัดแรก (เช่น ข้อความปฏิเสธความรับผิดชอบ)', 'area'], ['fs', 'ขนาดตัวอักษร', 'num', [4, 14, .25]], ['color', 'สี', 'color'],
    ['align', 'จัดแนว', 'seg', { left: 'ซ้าย', center: 'กลาง', right: 'ขวา' }], ['note', 'แสดงหมายเหตุ', 'chk'], ['author', 'แสดงผู้จัดทำ', 'chk'], ['crs', 'แสดงระบบพิกัด', 'chk']],
};

async function pageReport(qs) {
  const gen = window._routeGen, alive = () => gen === window._routeGen && location.hash.startsWith('#/report');
  const [all, aois] = await Promise.all([api(ENGINE + '/api/datasets'), api(ENGINE + '/api/aoi')]);
  if (!alive()) return;
  const byKey = {};
  all.forEach(d => byKey[(d.kind === 'link' ? 'lk:' : 'ds:') + d.id] = d);
  aois.forEach(a => byKey['aoi:' + a.id] = a);
  const blankMap = () => ({ layers: [], basemap: 'esri_light', basemap_opacity: 1, boundary: { key: '', color: '#3a3f4f', width: .6, label_field: '' }, extent: { type: 'data' } });
  let doc; try { doc = JSON.parse(localStorage.getItem(RDOC)); } catch { }
  if (!doc || doc.v !== 2) doc = Object.assign(RPT.fromTemplate('gov_l', {}), { map: blankMap(), font: 'Sarabun', meta: { title: '', subtitle: '', org: 'GISTDA', author: '', map_no: '', date: '', note: '', caption: '' } });
  const resetViews = () => doc.els.forEach(e => { if (e.type === 'map') { e.p.view = null; e.p.auto = true; } });
  if (qs.get('ds')) {
    const d = all.find(x => x.id == qs.get('ds'));
    if (d) { doc.map.layers = [vLayerFromDs(d)]; doc.meta.title = d.name; resetViews(); }
  } else if (qs.get('viewer')) {
    doc.map.layers = vLoad().filter(l => l.visible && byKey[l.key]).map(l => ({ key: l.key, opacity: l.opacity, style: l.style, rstyle: l.rstyle, name: l.name, kind: l.kind }));
    resetViews();
  } else if (qs.get('ai')) {                                 // ผู้ช่วย AI เสนอรายงาน (ผู้ใช้กดยืนยันแล้ว) → เริ่มหน้าใหม่จากเทมเพลต + ชั้นข้อมูล + ข้อความ
    let sp = null; try { sp = JSON.parse(sessionStorage.getItem('ainu-ai-report')); sessionStorage.removeItem('ainu-ai-report'); } catch { }
    if (sp && RPT.TEMPLATES[sp.template]) {
      const meta = Object.assign({ title: '', subtitle: '', org: 'GISTDA', author: '', map_no: '', date: new Date().toLocaleDateString(I18N.locale()), note: '', caption: '' }, sp.meta || {});
      doc = Object.assign(RPT.fromTemplate(sp.template, {}), { map: blankMap(), font: doc.font || 'Sarabun', meta });
      doc.map.layers = (sp.dataset_ids || []).map((id, i) => all.find(x => x.id === id)).filter(Boolean).map((d, i) => vLayerFromDs(d, i));
      if (sp.extent_aoi_id && byKey['aoi:' + sp.extent_aoi_id]) doc.map.extent = { type: 'aoi', aoi_id: sp.extent_aoi_id };
      resetViews();
    }
  }
  if (qs.get('ds') || qs.get('viewer') || qs.get('ai')) history.replaceState(null, '', '#/report');
  doc.map.layers = doc.map.layers.filter(l => byKey[l.key]);
  if (/^carto_/.test(doc.map.basemap)) doc.map.basemap = 'esri_light';

  let data = { maps: {}, insets: {}, info: null }, sel = null, z = 1, fitMode = true, panMode = null, editing = null, tab = 'tpl';
  const ctx = () => ({ hasStats: !!data.info?.stats?.kpi?.length, hasBars: !!data.info?.stats?.bars?.length });
  const byId = id => doc.els.find(e => e.id === id);
  const r1 = v => Math.round(v * 10) / 10;
  const fontLink = f => {
    let l = document.getElementById('rptFont');
    if (!l) { l = document.createElement('link'); l.id = 'rptFont'; l.rel = 'stylesheet'; document.head.appendChild(l); }
    l.href = RPT.fontHref([f || 'Sarabun', 'Sarabun']);
  };
  fontLink(doc.font);

  const v = $('#view');
  v.innerHTML = `<div class="rp">
    <aside class="rp-side"><div class="seg rp-tabs">${[['tpl', 'เทมเพลต'], ['data', 'ข้อมูล'], ['text', 'ข้อความ'], ['els', 'องค์ประกอบ']].map(([k, t]) => `<button data-t="${k}" class="${k === tab ? 'on' : ''}">${t}</button>`).join('')}</div>
      <div id="rpSide" class="rp-scroll"></div></aside>
    <section class="rp-main">
      <div class="rp-bar">
        <button class="sm ghost" id="rpUndo" title="เลิกทำ (Ctrl+Z)">↶</button><button class="sm ghost" id="rpRedo" title="ทำซ้ำ (Ctrl+Y)">↷</button><span class="rp-sep"></span>
        <button class="sm ghost" id="rpZo" title="ย่อ">−</button><button class="sm ghost" id="rpFit" title="พอดีจอ"><span id="rpZv">100%</span></button><button class="sm ghost" id="rpZi" title="ขยาย">+</button><span class="rp-sep"></span>
        <select id="rpPaper" title="ขนาดกระดาษ">${[['A4|landscape', 'A4 แนวนอน'], ['A4|portrait', 'A4 แนวตั้ง'], ['A3|landscape', 'A3 แนวนอน'], ['A3|portrait', 'A3 แนวตั้ง'], ['A5|landscape', 'A5 แนวนอน'], ['A5|portrait', 'A5 แนวตั้ง'], ['custom', 'กำหนดเอง…']].map(([k, t]) => `<option value="${k}">${t}</option>`).join('')}</select>
        <select id="rpFont" title="ฟอนต์ทั้งหน้า">${Object.entries(RPT.FONTS).map(([k, t]) => `<option value="${esc(k)}">${esc(t.split(' — ')[0])}</option>`).join('')}</select>
        <span class="spacer"></span><span id="rpStat" class="tiny muted"></span>
        <select id="rpFmt"><option value="pdf">PDF</option><option value="png">PNG</option></select>
        <select id="rpDpi"><option value="150">150 dpi</option><option value="200" selected>200 dpi</option><option value="300">300 dpi</option></select>
        <button class="primary sm" id="rpExport">${IC.download}ส่งออก</button></div>
      <div class="rp-stage" id="rpStage"><div id="rpWrap"><div id="rpScale"><div id="rpPage"></div><div id="rpOv"></div></div></div></div>
    </section>
    <aside class="rp-props rp-scroll" id="rpProps"></aside></div>`;
  const stage = $('#rpStage');
  const stat = (t, err) => { $('#rpStat').innerHTML = err ? `<span style="color:var(--coral)">${esc(t)}</span>` : esc(t); };

  // ---------- บันทึก / ประวัติ (เลิกทำ) ----------
  let saveWarned = false;
  const save = () => { if (!alive()) return; try { localStorage.setItem(RDOC, JSON.stringify(doc)); } catch { if (!saveWarned) { saveWarned = true; toast('บันทึกการจัดหน้าในเบราว์เซอร์ไม่ได้ (รูปภาพใหญ่เกินไป?)', true); } } };
  const snap = () => JSON.stringify(doc);
  let last = snap(), hist = [], fut = [], ct = null;
  const commit = () => { clearTimeout(ct); const s = snap(); if (s === last) return; hist.push(last); if (hist.length > 100) hist.shift(); fut = []; last = s; save(); undoBtns(); };
  const commitSoon = () => { clearTimeout(ct); ct = setTimeout(commit, 450); };
  const undoBtns = () => { $('#rpUndo').disabled = !hist.length; $('#rpRedo').disabled = !fut.length; };
  const restore = s => {
    const old = doc; doc = JSON.parse(s); last = s; save();
    const sz = e => { const o = old.els.find(x => x.id === e.id); return !o || o.w !== e.w || o.h !== e.h || JSON.stringify(o.p.view) !== JSON.stringify(e.p.view) || o.p.auto !== e.p.auto; };
    const mapChanged = JSON.stringify(old.map) !== JSON.stringify(doc.map);
    if (old.font !== doc.font) fontLink(doc.font);
    if (!byId(sel)) sel = null;
    layoutStage(); full(); side(); props();
    if (mapChanged) refreshAll(); else doc.els.forEach(e => { if (e.type === 'map' && sz(e)) refreshMap(e.id, 0); if (e.type === 'inset' && sz(e)) refreshInset(e.id); });
    undoBtns();
  };
  const undo = () => { if (!hist.length) return; fut.push(last); restore(hist.pop()); };
  const redo = () => { if (!fut.length) return; hist.push(last); restore(fut.pop()); };

  // ---------- วาดหน้า ----------
  const loading = new Set();
  const node = id => document.querySelector(`#rpPage > [data-id="${id}"]`);
  const deco = (n, e) => {
    if (!n) return;
    n.classList.toggle('rp-loading', loading.has(e.id));
    n.classList.toggle('rp-lock', !!e.lock);
    n.classList.toggle('rpt-nofill', e.type === 'rect' && !e.p.fill);
    n.classList.toggle('rp-panning', panMode === e.id);
    if (['text', 'credits', 'legend', 'prov'].includes(e.type)) {        // ข้อความล้นกรอบ → ขอบแดง + คำแนะนำ
      const inn = n.firstElementChild, over = inn && inn.scrollHeight > inn.clientHeight + 2;
      n.classList.toggle('rp-over', !!over);
      n.title = over ? 'ข้อความล้นกรอบ — ขยายกล่องหรือลดขนาดตัวอักษร (ส่วนที่ล้นจะไม่ถูกพิมพ์)' : '';
    }
  };
  const full = () => { RPT.render($('#rpPage'), doc, data, { editor: true }); doc.els.forEach(e => deco(node(e.id), e)); drawSel(); };
  const redraw = e => { const n = node(e.id); if (!n) return full(); RPT.draw(n, e, doc, data, { editor: true }); deco(n, e); };
  const redrawTypes = (...ts) => doc.els.filter(e => ts.includes(e.type)).forEach(redraw);
  const place = e => { const n = node(e.id); if (n) Object.assign(n.style, { left: e.x + 'mm', top: e.y + 'mm', width: e.w + 'mm', height: e.h + 'mm', zIndex: 10 + (e.z || 0) }); };
  const layoutStage = () => {
    const [W, H] = RPT.size(doc), pw = W * 3.7795, ph_ = H * 3.7795;
    if (fitMode) z = Math.max(.15, Math.min((stage.clientWidth - 56) / pw, (stage.clientHeight - 56) / ph_, 3));
    Object.assign($('#rpScale').style, { width: W + 'mm', height: H + 'mm', transform: `scale(${z})` });
    Object.assign($('#rpWrap').style, { width: pw * z + 'px', height: ph_ * z + 'px' });
    $('#rpOv').style.setProperty('--hs', (9 / z) + 'px');
    $('#rpOv').style.setProperty('--bw', (1.5 / z) + 'px');
    $('#rpZv').textContent = Math.round(z * 100) + '%';
    const pk = doc.paper.size === 'custom' ? 'custom' : `${doc.paper.size}|${doc.paper.orient}`;
    $('#rpPaper').value = pk; $('#rpFont').value = doc.font || 'Sarabun';
  };
  const dpiNow = () => Math.max(72, Math.min(240, Math.round(3.7795 * z * (devicePixelRatio || 1) * 25.4 / 24) * 24));

  // ---------- ข้อมูลจากเซิร์ฟเวอร์ ----------
  const reqs = {}, mt = {};
  const mapFor = e => data.maps[e?.p?.link] || data.maps[doc.els.find(x => x.type === 'map' && !x.hidden)?.id];
  const refreshMap = (id, delay = 300) => {
    clearTimeout(mt[id]);
    mt[id] = setTimeout(async () => {
      const e = byId(id); if (!e) return;
      if (!doc.map.layers.length) { delete data.maps[id]; redraw(e); stat('ยังไม่มีชั้นข้อมูล — เพิ่มที่แท็บ "ข้อมูล"'); return; }
      const my = reqs[id] = (reqs[id] || 0) + 1;
      loading.add(id); deco(node(id), e); stat('กำลังวาดแผนที่…');
      const t0 = Date.now();
      try {
        const r = await api(ENGINE + '/api/report/map', { json: { map: doc.map, w: e.w, h: e.h, dpi: dpiNow(), view: e.p.auto === false ? e.p.view : null } });
        if (reqs[id] !== my || !alive()) return;
        data.maps[id] = r;
        const ee = byId(id); if (ee && ee.p.auto !== false) { ee.p.view = r.view; last = snap(); save(); }
        stat(`วาดแผนที่ ${((Date.now() - t0) / 1000).toFixed(1)} วินาที`);
      } catch (er) { if (reqs[id] === my) stat(er.message, true); }
      if (reqs[id] !== my) return;
      loading.delete(id);
      const ee = byId(id); if (ee) redraw(ee);
      redrawTypes('scalebar');
      doc.els.filter(x => x.type === 'inset').forEach(x => refreshInset(x.id));
    }, delay);
  };
  const refreshInset = async id => {
    const e = byId(id), m = mapFor(e); if (!e || !m) return;
    const my = reqs[id] = (reqs[id] || 0) + 1;
    try {
      const r = await api(ENGINE + '/api/report/inset', { json: { ext: m.ext, w: e.w, h: e.h, dpi: dpiNow(), basemap: e.p.basemap, zoom: e.p.zoom } });
      if (reqs[id] === my && alive()) { data.insets[id] = r; redraw(byId(id)); }
    } catch { }
  };
  const refreshInfo = async () => {
    try { data.info = await api(ENGINE + '/api/report/info', { json: { map: doc.map } }); } catch (er) { stat(er.message, true); }
    if (!alive()) return;
    redrawTypes('legend', 'kpi', 'chart', 'prov', 'credits');
    if (tab === 'tpl') side();
    if (sel && byId(sel)?.type === 'legend') props();
  };
  const refreshAll = () => { refreshInfo(); doc.els.filter(e => e.type === 'map').forEach(e => refreshMap(e.id, 0)); };

  // ---------- เลือก / กรอบเลือก / เส้นนำ ----------
  const drawSel = () => {
    const ov = $('#rpOv'), e = byId(sel);
    ov.innerHTML = e ? `<div class="rp-sel ${e.lock ? 'lock' : ''}" style="left:${e.x}mm;top:${e.y}mm;width:${e.w}mm;height:${e.h}mm">
      ${e.lock ? `<span class="rp-lockic">${IC.lock}</span>` : ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'].map(h => `<i data-h="${h}" class="h-${h}"></i>`).join('')}</div>` : '';
    ov.insertAdjacentHTML('beforeend', '<div id="rpGuides"></div>');
  };
  const guides = g => { const el = $('#rpGuides'); if (el) el.innerHTML = g.map(x => x.v != null ? `<b class="gv" style="left:${x.v}mm"></b>` : `<b class="gh" style="top:${x.h}mm"></b>`).join(''); };
  const select = id => {
    if (panMode && panMode !== id) endPan();
    sel = id; drawSel(); props();
    if (tab === 'els') side();
  };
  const snapTo = (e, x, y, w, h, hd) => {
    const [W, H] = RPT.size(doc), th = 6 / (3.7795 * z);
    const xs = [0, W / 2, W], ys = [0, H / 2, H];
    doc.els.forEach(o => { if (o.id === e.id || o.hidden) return; xs.push(o.x, o.x + o.w / 2, o.x + o.w); ys.push(o.y, o.y + o.h / 2, o.y + o.h); });
    const best = (vals, cs) => { let b = null; vals.forEach(v_ => cs.forEach(c => { const d = c - v_; if (Math.abs(d) <= th && (!b || Math.abs(d) < Math.abs(b.d))) b = { d, c }; })); return b; };
    const g = [];
    if (!hd) {
      const bx = best([x, x + w / 2, x + w], xs); if (bx) { x += bx.d; g.push({ v: bx.c }); }
      const by = best([y, y + h / 2, y + h], ys); if (by) { y += by.d; g.push({ h: by.c }); }
    } else {
      if (hd.includes('w')) { const b = best([x], xs); if (b) { x += b.d; w -= b.d; g.push({ v: b.c }); } }
      if (hd.includes('e')) { const b = best([x + w], xs); if (b) { w += b.d; g.push({ v: b.c }); } }
      if (hd.includes('n')) { const b = best([y], ys); if (b) { y += b.d; h -= b.d; g.push({ h: b.c }); } }
      if (hd.includes('s')) { const b = best([y + h], ys); if (b) { h += b.d; g.push({ h: b.c }); } }
    }
    return { x, y, w, h, g };
  };
  const drag = (ev, onMove, onUp) => {
    const sx = ev.clientX, sy = ev.clientY, k = 3.7795 * z;
    stage.setPointerCapture(ev.pointerId);
    const mv = m => onMove((m.clientX - sx) / k, (m.clientY - sy) / k, m);
    const up = m => { stage.removeEventListener('pointermove', mv); stage.removeEventListener('pointerup', up); stage.removeEventListener('pointercancel', up); guides([]); onUp?.((m.clientX - sx) / k, (m.clientY - sy) / k, m); };
    stage.addEventListener('pointermove', mv); stage.addEventListener('pointerup', up); stage.addEventListener('pointercancel', up);
  };
  const startMove = (ev, e) => {
    const ox = e.x, oy = e.y; let moved = false;
    drag(ev, (dx, dy, m) => {
      if (!moved && Math.hypot(dx, dy) * 3.7795 * z < 3) return;
      moved = true;
      let x = ox + dx, y = oy + dy;
      if (!m.altKey) { const s = snapTo(e, x, y, e.w, e.h); x = s.x; y = s.y; guides(s.g); }
      e.x = r1(x); e.y = r1(y); place(e); drawSel(); posFields();
    }, () => { if (moved) commit(); });
  };
  const startResize = (ev, hd) => {
    const e = byId(sel); if (!e || e.lock) return;
    const o = { x: e.x, y: e.y, w: e.w, h: e.h }, ar = o.w / o.h;
    const heavy = ['map', 'inset'].includes(e.type);
    drag(ev, (dx, dy, m) => {
      let { x, y, w, h } = o;
      if (hd.includes('e')) w = o.w + dx;
      if (hd.includes('w')) { w = o.w - dx; x = o.x + dx; }
      if (hd.includes('s')) h = o.h + dy;
      if (hd.includes('n')) { h = o.h - dy; y = o.y + dy; }
      if (m.shiftKey && hd.length === 2) { if (w / h > ar) h = w / ar; else w = h * ar; if (hd.includes('n')) y = o.y + o.h - h; if (hd.includes('w')) x = o.x + o.w - w; }
      else if (!m.altKey) { const s = snapTo(e, x, y, w, h, hd); ({ x, y, w, h } = s); guides(s.g); }
      const mn = e.type === 'line' ? .2 : 2;
      if (w < mn) { if (hd.includes('w')) x -= mn - w; w = mn; }
      if (h < mn) { if (hd.includes('n')) y -= mn - h; h = mn; }
      Object.assign(e, { x: r1(x), y: r1(y), w: r1(w), h: r1(h) });
      if (heavy) place(e); else redraw(e);
      drawSel(); posFields();
    }, () => {
      commit();
      if (e.type === 'map') refreshMap(e.id, 0);
      if (e.type === 'inset') refreshInset(e.id);
    });
  };

  // ---------- เลื่อน/ซูมแผนที่ภายในกรอบ (ดับเบิลคลิกแผนที่) ----------
  const startPanMode = id => { panMode = id; const e = byId(id); deco(node(id), e); stat('โหมดเลื่อนแผนที่: ลากเพื่อเลื่อน · หมุนล้อเมาส์เพื่อซูม · Esc หรือดับเบิลคลิกเพื่อจบ'); };
  const endPan = () => { const id = panMode; panMode = null; const e = byId(id); if (e) deco(node(id), e); stat(''); };
  const startPan = ev => {
    const e = byId(panMode), m = data.maps[panMode]; if (!e || !m) return;
    const img = node(e.id)?.querySelector('.rpt-mapimg'); if (!img) return;
    drag(ev, (dx, dy) => { img.style.transform = `translate(${dx}mm,${dy}mm)`; },
      (dx, dy) => {
        if (Math.abs(dx) + Math.abs(dy) < .3) { img.style.transform = ''; return; }
        const ext = m.ext, vw = Object.assign({}, e.p.view || m.view);
        vw.cx -= dx * (ext[2] - ext[0]) / e.w; vw.cy += dy * (ext[3] - ext[1]) / e.h;
        e.p.view = vw; e.p.auto = false; commit(); refreshMap(e.id, 0);
      });
  };
  let wz = 1;
  stage.addEventListener('wheel', ev => {
    if (!panMode) { if (ev.ctrlKey) { ev.preventDefault(); fitMode = false; z = Math.max(.15, Math.min(4, z * (ev.deltaY > 0 ? 1 / 1.1 : 1.1))); layoutStage(); drawSel(); } return; }
    const n = ev.target.closest('#rpPage > .rpt-el'); if (!n || n.dataset.id !== panMode) return;
    ev.preventDefault();
    const e = byId(panMode), img = n.querySelector('.rpt-mapimg'); if (!e || !img) return;
    const f = ev.deltaY > 0 ? 1.15 : 1 / 1.15;
    wz /= f; img.style.transform = `scale(${wz})`;
    e.p.view = Object.assign({}, e.p.view || data.maps[e.id]?.view); e.p.view.span *= f; e.p.auto = false;
    clearTimeout(mt['w' + e.id]);
    mt['w' + e.id] = setTimeout(() => { wz = 1; commit(); refreshMap(e.id, 0); }, 450);
  }, { passive: false });

  // ---------- เมาส์บนหน้า ----------
  stage.addEventListener('pointerdown', ev => {
    if (ev.button !== 0) return;
    if (ev.target.closest('[contenteditable="true"]')) return;
    const h = ev.target.closest('[data-h]');
    if (h) { ev.preventDefault(); startResize(ev, h.dataset.h); return; }
    const n = ev.target.closest('#rpPage > .rpt-el');
    if (panMode && n?.dataset.id === panMode) { ev.preventDefault(); startPan(ev); return; }
    if (!n) { select(null); return; }
    ev.preventDefault();
    if (sel !== n.dataset.id) select(n.dataset.id);
    const e = byId(sel); if (e && !e.lock) startMove(ev, e);
  });
  stage.addEventListener('dblclick', ev => {
    // pointer capture ตอนกดลาก ทำให้ target ของ dblclick เป็น stage → หาองค์ประกอบจากตำแหน่งเมาส์แทน
    const hit = document.elementsFromPoint(ev.clientX, ev.clientY).find(x => x.matches?.('#rpPage > .rpt-el:not(.rpt-nofill)'));
    const n = ev.target.closest('#rpPage > .rpt-el') || hit; if (!n) return;
    const e = byId(n.dataset.id); if (!e) return;
    if (e.type === 'map') { panMode === e.id ? endPan() : startPanMode(e.id); return; }
    if (e.type === 'text') editText(e, n);
  });
  const editText = (e, n) => {
    const tx = n.querySelector('.rpt-tx'); if (!tx) return;
    const one = /^\{(\w+)\}$/.exec((e.p.text || '').trim());
    editing = { id: e.id, key: one ? one[1] : null };
    tx.innerText = one ? (doc.meta[one[1]] || '') : (e.p.text || '');
    tx.contentEditable = 'true'; tx.focus();
    const r = document.createRange(); r.selectNodeContents(tx); const s = getSelection(); s.removeAllRanges(); s.addRange(r);
    tx.onkeydown = k => { if (k.key === 'Escape') { k.preventDefault(); tx.blur(); } };
    tx.onblur = () => {
      const val = tx.innerText.replace(/\n+$/, '');
      if (editing?.key) doc.meta[editing.key] = val; else e.p.text = val;
      tx.contentEditable = 'false'; editing = null;
      redrawTypes('text', 'credits'); commit(); props(); if (tab === 'text') side();
    };
  };

  // ---------- คีย์ลัด ----------
  const onKey = ev => {
    if (!document.getElementById('rpPage')) { document.removeEventListener('keydown', onKey); return; }
    if (ev.target.closest?.('input,textarea,select,[contenteditable="true"]')) return;
    const c = ev.ctrlKey || ev.metaKey, k = ev.key.toLowerCase();
    if (c && k === 'z') { ev.preventDefault(); ev.shiftKey ? redo() : undo(); return; }
    if (c && k === 'y') { ev.preventDefault(); redo(); return; }
    if (ev.key === 'Escape') { if (panMode) endPan(); else select(null); return; }
    const e = byId(sel); if (!e) return;
    if (c && k === 'd') { ev.preventDefault(); dup(e); return; }
    if (ev.key === 'Delete' || ev.key === 'Backspace') { ev.preventDefault(); removeEl(e); return; }
    const st = ev.shiftKey ? 5 : .5;
    const mv = { ArrowLeft: [-st, 0], ArrowRight: [st, 0], ArrowUp: [0, -st], ArrowDown: [0, st] }[ev.key];
    if (mv && !e.lock) { ev.preventDefault(); e.x = r1(e.x + mv[0]); e.y = r1(e.y + mv[1]); place(e); drawSel(); posFields(); commitSoon(); }
  };
  if (window._rpKey) document.removeEventListener('keydown', window._rpKey);
  window._rpKey = onKey; document.addEventListener('keydown', onKey);
  if (window._rpResize) window.removeEventListener('resize', window._rpResize);
  window._rpResize = () => { if (document.getElementById('rpPage') && fitMode) { layoutStage(); drawSel(); } };
  window.addEventListener('resize', window._rpResize);

  // ---------- จัดการองค์ประกอบ ----------
  const maxZ = () => Math.max(0, ...doc.els.map(e => e.z || 0));
  const addEl = type => {
    const [W, H] = RPT.size(doc), [w, h] = RP_SIZE[type];
    const e = { id: RPT.uid(), type, x: r1((W - w) / 2), y: r1((H - h) / 2), w, h, z: maxZ() + 1, p: JSON.parse(JSON.stringify(RPT.TYPES[type].p)) };
    if (type === 'map') e.p.auto = true;
    doc.els.push(e); full(); select(e.id); commit();
    if (type === 'map') refreshMap(e.id, 0);
    if (type === 'inset') refreshInset(e.id);
  };
  const dup = e => {
    const c = JSON.parse(JSON.stringify(e)); c.id = RPT.uid(); c.x = r1(c.x + 4); c.y = r1(c.y + 4); c.z = maxZ() + 1; c.lock = false;
    doc.els.push(c);
    if (data.maps[e.id]) data.maps[c.id] = data.maps[e.id];
    if (data.insets[e.id]) data.insets[c.id] = data.insets[e.id];
    full(); select(c.id); commit();
  };
  const removeEl = e => { doc.els = doc.els.filter(x => x.id !== e.id); delete data.maps[e.id]; sel = null; full(); props(); side(); commit(); };
  const order = (e, dir) => {
    const s = [...doc.els].sort((a, b) => (a.z || 0) - (b.z || 0));
    const i = s.indexOf(e);
    if (dir === 'top') { s.splice(i, 1); s.push(e); } else if (dir === 'bottom') { s.splice(i, 1); s.unshift(e); }
    else { const j = i + (dir === 'up' ? 1 : -1); if (j < 0 || j >= s.length) return; [s[i], s[j]] = [s[j], s[i]]; }
    s.forEach((x, k) => x.z = k);
    doc.els.forEach(place); drawSel(); commit(); if (tab === 'els') side();
  };

  // ---------- แผงคุณสมบัติ (ขวา) ----------
  const posFields = () => { const e = byId(sel); if (!e) return; ['x', 'y', 'w', 'h'].forEach(k => { const i = $(`#rpPos_${k}`); if (i && document.activeElement !== i) i.value = e[k]; }); };
  const fieldHtml = (p, [k, label, kind, o]) => {
    const val = p[k];
    if (kind === 'area') return `<label class="field full"><span>${label}</span><textarea rows="3" data-f="${k}">${esc(val ?? '')}</textarea></label>`;
    if (kind === 'txt') return `<label class="field full"><span>${label}</span><input type="text" data-f="${k}" value="${esc(val ?? '')}"></label>`;
    if (kind === 'num') return `<label class="field"><span>${label}</span><input type="number" data-f="${k}" min="${o[0]}" max="${o[1]}" step="${o[2]}" value="${val ?? ''}"></label>`;
    if (kind === 'range') return `<label class="field"><span>${label} <b>${Math.round((val ?? 0) * 100) / 100}</b></span><input type="range" data-f="${k}" min="${o[0]}" max="${o[1]}" step="${o[2]}" value="${val ?? 0}"></label>`;
    if (kind === 'chk') return `<label class="row small rp-chk"><input type="checkbox" data-f="${k}" ${val ? 'checked' : ''}> ${label}</label>`;
    if (kind === 'sel') return `<label class="field"><span>${label}</span><select data-f="${k}">${Object.entries(o).map(([a, b]) => `<option value="${esc(a)}" ${String(val) === a ? 'selected' : ''}>${esc(b)}</option>`).join('')}</select></label>`;
    if (kind === 'seg') return `<div class="field"><span>${label}</span><div class="seg rp-seg" data-f="${k}">${Object.entries(o).map(([a, b]) => `<button type="button" data-v="${a}" class="${val === a ? 'on' : ''}">${b}</button>`).join('')}</div></div>`;
    if (kind === 'color' || kind === 'colorx') {
      const hex = /^#[0-9a-f]{6}/i.test(val || '') ? val.slice(0, 7) : '#ffffff';
      return `<div class="field"><span>${label}</span><div class="row rp-col"><input type="color" data-f="${k}" value="${hex}" class="${!val ? 'none' : ''}">${kind === 'colorx' ? `<button type="button" class="sm ghost" data-clear="${k}" title="ไม่มีสี">${val ? '✕' : 'ไม่มี'}</button>` : ''}</div></div>`;
    }
    return '';
  };
  const props = () => {
    const el = $('#rpProps'), e = byId(sel);
    if (!e) {
      const [W, H] = RPT.size(doc);
      el.innerHTML = `<h3 class="rp-h">หน้ากระดาษ</h3><div class="grid-form">
        <div class="field full"><span>ขนาด</span><div class="small">${esc($('#rpPaper').selectedOptions[0]?.textContent || '')} · ${r1(W)} × ${r1(H)} มม.</div></div>
        <div class="field"><span>สีพื้นหน้า</span><input type="color" id="rpBg" value="${(doc.bg || '#ffffff').slice(0, 7)}"></div>
        <label class="field full"><span>ฟอนต์ทั้งหน้า</span><select id="rpFont2">${Object.entries(RPT.FONTS).map(([k, t]) => `<option value="${esc(k)}" ${k === doc.font ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select></label></div>
        <div class="note" style="margin-top:12px">Sarabun คือฟอนต์สารบรรณที่ออกแบบจาก TH Sarabun New (ฟอนต์มาตรฐานหนังสือราชการตามมติ ครม.) แต่ขยายสัดส่วนให้ใช้ขนาด pt เดียวกับฟอนต์ทั่วไป</div>
        <h3 class="rp-h">วิธีใช้</h3><div class="tiny muted rp-help">
          • คลิกเลือก · ลากย้าย · ลากจุดมุมเพื่อย่อ/ขยาย (Shift = คงสัดส่วน, Alt = ไม่ดูดเส้นนำ)<br>
          • ดับเบิลคลิกข้อความเพื่อพิมพ์แก้ · ดับเบิลคลิกแผนที่เพื่อเลื่อน/ซูมแผนที่ในกรอบ<br>
          • ลูกศร = ขยับ 0.5 มม. (Shift = 5 มม.) · Delete = ลบ · Ctrl+D = ทำสำเนา · Ctrl+Z / Ctrl+Y = เลิกทำ/ทำซ้ำ · Ctrl+ล้อเมาส์ = ซูมหน้า<br>
          • ข้อความใส่ตัวแทนได้ เช่น <code>{title}</code> <code>{org}</code> <code>{date}</code> <code>{map_no}</code> — แก้ที่แท็บ "ข้อความ" ครั้งเดียวเปลี่ยนทุกที่</div>`;
      $('#rpBg').oninput = () => { doc.bg = $('#rpBg').value; $('#rpPage').style.background = doc.bg; commitSoon(); };
      $('#rpFont2').onchange = () => setFont($('#rpFont2').value);
      return;
    }
    const T_ = RPT.TYPES[e.type];
    let h = `<div class="rp-ph"><b>${RP_ICON[e.type]} ${T_.name}</b><div class="row">
        <button class="sm ghost" data-act="dup" title="ทำสำเนา (Ctrl+D)">${IC.copy}</button><button class="sm ghost" data-act="lock" title="${e.lock ? 'ปลดล็อก' : 'ล็อกตำแหน่ง'}">${e.lock ? IC.lock : IC.unlock}</button>
        <button class="sm ghost" data-act="hide" title="ซ่อนตอนพิมพ์">${e.hidden ? IC.eyeOff : IC.eye}</button><button class="sm ghost danger" data-act="del" title="ลบ (Delete)">${IC.trash}</button></div></div>
      <div class="rp-pos">${['x', 'y', 'w', 'h'].map(k => `<label><span>${{ x: 'X', y: 'Y', w: 'กว้าง', h: 'สูง' }[k]}</span><input type="number" step="0.5" id="rpPos_${k}" value="${e[k]}"></label>`).join('')}<span class="tiny muted">มม.</span></div>
      <div class="row rp-ord"><span class="tiny muted">ลำดับชั้น</span><button class="sm ghost" data-act="top" title="บนสุด">⤒</button><button class="sm ghost" data-act="up" title="ขึ้น">↑</button><button class="sm ghost" data-act="down" title="ลง">↓</button><button class="sm ghost" data-act="bottom" title="ล่างสุด">⤓</button></div>`;
    if (e.type === 'map') h += `<div class="rp-box"><div class="row" style="flex-wrap:wrap;gap:6px"><button class="sm" data-act="fit">พอดีข้อมูล</button><button class="sm ghost" data-act="zin">ซูมเข้า</button><button class="sm ghost" data-act="zout">ซูมออก</button><button class="sm ghost" data-act="pan">${panMode === e.id ? 'จบการเลื่อน' : 'เลื่อนแผนที่'}</button></div>
      <div class="tiny muted" style="margin-top:6px">${e.p.auto === false ? 'กำหนดกรอบเอง' : 'กรอบอัตโนมัติตามข้อมูล/พื้นที่ศึกษา'} · ชั้นข้อมูลและแผนที่พื้นหลังตั้งที่แท็บ "ข้อมูล"</div></div>`;
    if (e.type === 'text') h += `<div class="rp-box"><span class="tiny muted">แทรกข้อมูล: </span>${Object.entries(RPT.META).map(([k, t]) => `<button class="chip rp-ins" data-ins="${k}" title="{${k}}">${t}</button>`).join('')}</div>`;
    if (e.type === 'image') h += `<div class="rp-box"><input type="file" accept="image/*" id="rpImg"><div class="tiny muted" style="margin-top:4px">PNG/JPG/SVG — ย่อเหลือไม่เกิน 1200 px เก็บในการจัดหน้า</div></div>`;
    h += `<div class="grid-form rp-fields">${(RP_F[e.type] || []).map(f => fieldHtml(e.p, f)).join('')}</div>`;
    if (e.type === 'legend' && data.info?.legend?.length) h += `<h3 class="rp-h">รายการและชื่อที่แสดง</h3><div class="tiny muted" style="margin-bottom:6px">เปลี่ยนชื่อได้เฉพาะในรายงาน (ใส่ - เพื่อซ่อนหัวข้อ)</div>` +
      data.info.legend.map(it => `<div class="row rp-legrow"><input type="checkbox" data-skip="${esc(it.name)}" ${(e.p.skip || []).includes(it.name) ? '' : 'checked'} title="แสดง/ซ่อน">
        <input type="text" data-rn="${esc(it.name)}" value="${esc((e.p.names || {})[it.name] || '')}" placeholder="${esc(it.name)}"></div>`).join('');
    el.innerHTML = h;
    const after = k => {
      if (e.type === 'inset' && ['basemap', 'zoom'].includes(k)) refreshInset(e.id); else redraw(e);
      commitSoon();
    };
    $$('[data-f]', el).forEach(i => {
      const k = i.dataset.f;
      if (i.classList.contains('rp-seg')) { $$('button', i).forEach(b => b.onclick = () => { e.p[k] = b.dataset.v; $$('button', i).forEach(x => x.classList.toggle('on', x === b)); after(k); }); return; }
      const ev = i.type === 'checkbox' || i.tagName === 'SELECT' ? 'onchange' : 'oninput';
      i[ev] = () => {
        let val = i.type === 'checkbox' ? i.checked : i.type === 'number' || i.type === 'range' ? +i.value : i.value;
        if (i.tagName === 'SELECT' && /^\d+$/.test(val) && k === 'fw') val = +val;
        e.p[k] = val;
        if (i.type === 'range') i.previousElementSibling.querySelector('b').textContent = Math.round(val * 100) / 100;
        if (i.type === 'color') { i.classList.remove('none'); const c = el.querySelector(`[data-clear="${k}"]`); if (c) c.textContent = '✕'; }
        after(k);
      };
    });
    $$('[data-clear]', el).forEach(b => b.onclick = () => { e.p[b.dataset.clear] = ''; b.textContent = 'ไม่มี'; b.previousElementSibling.classList.add('none'); after(b.dataset.clear); });
    $$('[data-rn]', el).forEach(i => i.oninput = () => { e.p.names = Object.assign({}, e.p.names); if (i.value.trim()) e.p.names[i.dataset.rn] = i.value; else delete e.p.names[i.dataset.rn]; redraw(e); commitSoon(); });
    $$('[data-skip]', el).forEach(c => c.onchange = () => { const s = new Set(e.p.skip || []); c.checked ? s.delete(c.dataset.skip) : s.add(c.dataset.skip); e.p.skip = [...s]; redraw(e); commit(); });
    ['x', 'y', 'w', 'h'].forEach(k => $(`#rpPos_${k}`).onchange = () => {
      e[k] = Math.max(k === 'w' || k === 'h' ? .2 : -500, r1(+$(`#rpPos_${k}`).value)); place(e); if (!['map', 'inset'].includes(e.type)) redraw(e); drawSel(); commit();
      if ((k === 'w' || k === 'h') && e.type === 'map') refreshMap(e.id, 0);
      if ((k === 'w' || k === 'h') && e.type === 'inset') refreshInset(e.id);
    });
    $$('[data-ins]', el).forEach(b => b.onclick = () => {
      const ta = el.querySelector('[data-f="text"]'), t = `{${b.dataset.ins}}`, s = ta.selectionStart ?? ta.value.length;
      ta.value = ta.value.slice(0, s) + t + ta.value.slice(ta.selectionEnd ?? s); e.p.text = ta.value; redraw(e); commit();
    });
    $('#rpImg') && ($('#rpImg').onchange = () => {
      const f = $('#rpImg').files[0]; if (!f) return;
      const rd = new FileReader();
      rd.onload = () => {
        if (f.type === 'image/svg+xml') { e.p.src = rd.result; redraw(e); commit(); return; }
        const im = new Image();
        im.onload = () => {
          const k = Math.min(1, 1200 / Math.max(im.width, im.height)), cv = document.createElement('canvas');
          cv.width = Math.round(im.width * k); cv.height = Math.round(im.height * k);
          cv.getContext('2d').drawImage(im, 0, 0, cv.width, cv.height);
          e.p.src = cv.toDataURL(f.type === 'image/jpeg' ? 'image/jpeg' : 'image/png', .9);
          if (Math.abs(e.w / e.h - im.width / im.height) > .05) { e.h = r1(e.w * im.height / im.width); place(e); drawSel(); }
          redraw(e); commit();
        };
        im.src = rd.result;
      };
      rd.readAsDataURL(f);
    });
    $$('[data-act]', el).forEach(b => b.onclick = () => {
      const a = b.dataset.act;
      if (a === 'dup') return dup(e);
      if (a === 'del') return removeEl(e);
      if (a === 'lock') { e.lock = !e.lock; deco(node(e.id), e); drawSel(); props(); commit(); return; }
      if (a === 'hide') { e.hidden = !e.hidden; redraw(e); props(); commit(); if (tab === 'els') side(); return; }
      if (['top', 'up', 'down', 'bottom'].includes(a)) return order(e, a);
      if (a === 'fit') { e.p.auto = true; e.p.view = null; commit(); refreshMap(e.id, 0); props(); return; }
      if (a === 'zin' || a === 'zout') { const vw = Object.assign({}, e.p.view || data.maps[e.id]?.view); if (!vw.span) return; vw.span *= a === 'zin' ? .8 : 1.25; e.p.view = vw; e.p.auto = false; commit(); refreshMap(e.id, 0); props(); return; }
      if (a === 'pan') { panMode === e.id ? endPan() : startPanMode(e.id); props(); }
    });
  };
  const setFont = f => { doc.font = f; fontLink(f); $('#rpPage').style.fontFamily = `'${f}', 'Sarabun', sans-serif`; $('#rpFont').value = f; commit(); setTimeout(() => { redrawTypes('scalebar', 'chart'); }, 600); };

  // ---------- แผงซ้าย ----------
  const polySrc = [...all.filter(isPolySrc), ...aois.map(a => ({ id: a.id, name: a.name, aoi: true }))];
  const side = () => {
    $$('.rp-tabs button').forEach(b => b.classList.toggle('on', b.dataset.t === tab));
    const el = $('#rpSide');
    if (tab === 'tpl') {
      el.innerHTML = `<div class="tiny muted" style="margin-bottom:10px">เลือกแบบเริ่มต้น แล้วปรับต่อได้ทุกส่วน · เปลี่ยนเทมเพลตจะคงชั้นข้อมูลและข้อความไว้</div><div class="rp-tpls">` +
        Object.entries(RPT.TEMPLATES).map(([k, t]) => `<div class="rp-tpl ${doc.template === k ? 'on' : ''}" data-k="${k}"><div class="rp-thumb"><div class="rp-tscale"><div class="rp-tpage"></div></div></div>
          <b>${esc(t.name)}</b><span>${esc(t.desc)}</span></div>`).join('') + '</div>';
      $$('.rp-tpl', el).forEach(c => {
        const k = c.dataset.k, tmp = Object.assign(RPT.fromTemplate(k, ctx()), { meta: doc.meta, font: doc.font });
        const [W, H] = RPT.size(tmp), box = $('.rp-thumb', c);
        const fit = () => { const s = (box.clientWidth || c.clientWidth - 20 || 200) / (W * 3.7795); $('.rp-tscale', c).style.transform = `scale(${s})`; box.style.height = H * 3.7795 * s + 'px'; };
        RPT.render($('.rp-tpage', c), tmp, { info: data.info, maps: {}, insets: {} }, { editor: true });
        fit(); requestAnimationFrame(fit);                       // วัดใหม่หลังจัดหน้าเสร็จ (กันภาพย่อล้นขวา)
        c.onclick = async () => {
          if (doc.els.length && !await ui.confirm('ใช้เทมเพลตนี้?', `<p>การจัดหน้าปัจจุบันจะถูกแทนที่ด้วย "<b>${esc(RPT.TEMPLATES[k].name)}</b>" (ชั้นข้อมูลและข้อความยังอยู่ · กด Ctrl+Z ย้อนกลับได้)</p>`, 'ใช้เทมเพลต')) return;
          const nd = RPT.fromTemplate(k, ctx(), {});
          Object.assign(doc, { template: k, paper: nd.paper, bg: nd.bg, els: nd.els });
          data.maps = {}; data.insets = {}; sel = null;
          fitMode = true; layoutStage(); full(); props(); side(); commit();
          doc.els.filter(e => e.type === 'map').forEach(e => refreshMap(e.id, 0));
        };
      });
    } else if (tab === 'data') {
      const m = doc.map;
      el.innerHTML = `<h3 class="rp-h">ชั้นข้อมูล <button class="sm" id="rpAdd" style="float:right">${IC.plus}เพิ่ม</button></h3><div id="rpLayers" class="vlist"></div>
        <div class="tiny muted" style="margin:6px 0 4px">บนสุด = อยู่บนสุด · raster ใช้สไตล์ Symbology (หรือที่ปรับในแผนที่ซ้อนชั้น) · <a href="#/report?viewer=1">ดึงจากแผนที่ซ้อนชั้น</a></div>
        <h3 class="rp-h">แผนที่พื้นหลัง</h3><div class="grid-form">
          <label class="field full"><select id="rpBm">${Object.entries(BM_LABEL).map(([k, t]) => `<option value="${k}" ${k === m.basemap ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
          <label class="field full"><span>ความทึบ <b id="rpBop">${Math.round(m.basemap_opacity * 100)}%</b></span><input type="range" id="rpBo" min="0" max="1" step="0.05" value="${m.basemap_opacity}"></label></div>
        <h3 class="rp-h">เส้นขอบเขต</h3><div class="grid-form">
          <label class="field full"><select id="rpBd"><option value="">ไม่แสดง</option>${polySrc.map(s => { const k = s.aoi ? 'aoi:' + s.id : (s.kind === 'link' ? 'lk:' : 'ds:') + s.id; return `<option value="${k}" ${k === m.boundary.key ? 'selected' : ''}>${s.aoi ? '◎ ' + esc(s.name) : srcLabel(s)}</option>`; }).join('')}</select></label>
          <label class="field"><span>ป้ายชื่อจากฟิลด์</span><select id="rpLf"></select></label>
          <div class="field"><span>สี / หนา</span><div class="row" style="flex-wrap:nowrap"><input type="color" id="rpBc" value="${m.boundary.color}"><input type="range" id="rpBw" min="0.1" max="3" step="0.1" value="${m.boundary.width}" style="flex:1"></div></div></div>
        <h3 class="rp-h">กรอบแผนที่เริ่มต้น</h3><label class="field full"><select id="rpExt"><option value="data">ครอบชั้นข้อมูลทั้งหมด</option>${aoiOptions(aois, { val: a => 'aoi:' + a.id, text: a => esc(a.name), sel: m.extent.type === 'aoi' ? 'aoi:' + m.extent.aoi_id : null })}</select></label>
        <div class="tiny muted" style="margin-top:6px">เลื่อน/ซูมละเอียด: ดับเบิลคลิกแผนที่บนหน้า</div>`;
      const mapChanged = (resetView) => { if (resetView) resetViews(); commit(); refreshAll(); };
      const fillLf = () => {
        const k = m.boundary.key, d = byKey[k];
        const fs = d && !k.startsWith('aoi:') ? fieldNames(d) : (k.startsWith('aoi:') ? ['name'] : []);
        $('#rpLf').innerHTML = '<option value="">ไม่แสดงป้าย</option>' + fs.map(f => `<option ${f === m.boundary.label_field ? 'selected' : ''}>${esc(f)}</option>`).join('');
      };
      fillLf();
      const renderLayers = () => {
        $('#rpLayers').innerHTML = m.layers.map((l, i) => `<div class="vrow"><div class="vhead">
          <span class="vswatch" style="${['raster', 'linktile'].includes(l.kind) ? 'background:linear-gradient(135deg,#c3b6ff,#9ee8d4)' : `background:${l.style?.fill};border-color:${l.style?.stroke}`}"></span>
          <span class="vname" title="${esc(byKey[l.key]?.name || l.name)}">${esc(byKey[l.key]?.name || l.name)}</span>
          <input type="range" min="0" max="1" step="0.05" value="${l.opacity}" data-i="${i}" data-a="op" style="width:56px" title="ความทึบ">
          <button class="sm ghost" data-i="${i}" data-a="up" ${i === 0 ? 'disabled' : ''}>↑</button><button class="sm ghost" data-i="${i}" data-a="down" ${i === m.layers.length - 1 ? 'disabled' : ''}>↓</button>
          <button class="sm ghost danger" data-i="${i}" data-a="rm">✕</button></div></div>`).join('') || '<div class="empty">ยังไม่มีชั้น</div>';
        $$('[data-a]', $('#rpLayers')).forEach(b => b[b.dataset.a === 'op' ? 'onchange' : 'onclick'] = () => {
          const i = +b.dataset.i, L_ = m.layers;
          if (b.dataset.a === 'op') L_[i].opacity = +b.value;
          if (b.dataset.a === 'up') [L_[i - 1], L_[i]] = [L_[i], L_[i - 1]];
          if (b.dataset.a === 'down') [L_[i + 1], L_[i]] = [L_[i], L_[i + 1]];
          if (b.dataset.a === 'rm') L_.splice(i, 1);
          renderLayers(); mapChanged(b.dataset.a === 'rm');
        });
      };
      renderLayers();
      $('#rpAdd').onclick = async () => {
        const have = new Set(m.layers.map(l => l.key));
        const items = [...all.map(d => [(d.kind === 'link' ? 'lk:' : 'ds:') + d.id, d.name, d.kind === 'link' ? d.meta.type_label : (d.role === 'map' ? 'แผนที่' : d.kind)]), ...aois.map(a => ['aoi:' + a.id, a.name, 'พื้นที่ศึกษา'])];
        const pick = await ui.open('เพิ่มชั้นข้อมูล', `${CL_Q}<div class="checklist" style="max-height:52vh">${items.map(([k, n, t]) => `<label><input type="checkbox" value="${esc(k)}" ${have.has(k) ? 'checked disabled' : ''}><span>${esc(n)} <span class="tiny muted">${esc(t)}</span></span></label>`).join('')}</div>`,
          [{ label: 'ยกเลิก', cls: 'ghost', value: () => null }, { label: 'เพิ่ม', cls: 'primary', value: () => $$('#mBody input:checked:not(:disabled)').map(i => i.value) }]);
        if (!pick?.length) return;
        pick.forEach((k, i) => {
          const d = byKey[k];
          m.layers.unshift(k.startsWith('aoi:') ? { key: k, kind: 'aoi', name: d.name, opacity: 1, style: { stroke: '#e5484d', width: 1.5, fill: '#e5484d', fillOpacity: 0 } } : vLayerFromDs(d, m.layers.length + i));
        });
        if (!doc.meta.title) doc.meta.title = byKey[pick[0]]?.name || '';
        renderLayers(); mapChanged(true);
      };
      $('#rpBm').onchange = () => { m.basemap = $('#rpBm').value; mapChanged(); };
      $('#rpBo').oninput = () => { $('#rpBop').textContent = Math.round($('#rpBo').value * 100) + '%'; };
      $('#rpBo').onchange = () => { m.basemap_opacity = +$('#rpBo').value; mapChanged(); };
      $('#rpBd').onchange = async () => {
        m.boundary.key = $('#rpBd').value; m.boundary.label_field = '';
        const d = byKey[m.boundary.key]; if (d?.kind === 'link') { try { await ensureLinkFields(d); } catch { } }
        fillLf(); mapChanged();
      };
      $('#rpLf').onchange = () => { m.boundary.label_field = $('#rpLf').value; mapChanged(); };
      $('#rpBc').onchange = () => { m.boundary.color = $('#rpBc').value; mapChanged(); };
      $('#rpBw').onchange = () => { m.boundary.width = +$('#rpBw').value; mapChanged(); };
      $('#rpExt').value = m.extent.type === 'aoi' ? 'aoi:' + m.extent.aoi_id : 'data';
      $('#rpExt').onchange = () => { const x = $('#rpExt').value; m.extent = x === 'data' ? { type: 'data' } : { type: 'aoi', aoi_id: +x.split(':')[1] }; mapChanged(true); };
    } else if (tab === 'text') {
      el.innerHTML = `<div class="tiny muted" style="margin-bottom:8px">ข้อความเหล่านี้ไปแสดงในทุกกล่องที่ใช้ตัวแทน เช่น <code>{title}</code> · ช่องที่ว่างจะถูกซ่อนบรรทัดนั้นอัตโนมัติ</div><div class="grid-form">` +
        Object.entries(RPT.META).map(([k, t]) => k === 'note' || k === 'caption' ? `<label class="field full"><span>${t}</span><textarea rows="3" data-m="${k}">${esc(doc.meta[k] || '')}</textarea></label>`
          : `<label class="field ${['title', 'subtitle', 'org'].includes(k) ? 'full' : ''}"><span>${t}</span><input type="text" data-m="${k}" value="${esc(doc.meta[k] || '')}" ${k === 'date' ? 'placeholder="ว่าง = วันนี้ (พ.ศ.)"' : ''}></label>`).join('') + '</div>';
      $$('[data-m]', el).forEach(i => i.oninput = () => { doc.meta[i.dataset.m] = i.value; redrawTypes('text', 'credits', 'prov'); commitSoon(); });
    } else {
      const s = [...doc.els].sort((a, b) => (b.z || 0) - (a.z || 0));
      el.innerHTML = `<h3 class="rp-h">เพิ่มองค์ประกอบ</h3><div class="rp-add">${Object.entries(RPT.TYPES).map(([k, t]) => `<button class="sm ghost" data-add="${k}"><i>${RP_ICON[k]}</i>${t.name}</button>`).join('')}</div>
        <h3 class="rp-h">ทุกองค์ประกอบในหน้า <span class="tiny muted">(บนสุดก่อน)</span></h3><div class="rp-list">` +
        s.map(e => `<div class="rp-li ${e.id === sel ? 'on' : ''} ${e.hidden ? 'off' : ''}" data-id="${e.id}"><i>${RP_ICON[e.type]}</i><span>${esc(e.type === 'text' ? RPT.fill(e.p.text, doc).slice(0, 34) || '(ข้อความว่าง)' : RPT.TYPES[e.type].name)}</span>
          <button class="sm ghost" data-v="${e.id}" title="ซ่อน/แสดง">${e.hidden ? IC.eyeOff : IC.eye}</button><button class="sm ghost" data-l="${e.id}" title="ล็อก">${e.lock ? IC.lock : IC.unlock}</button></div>`).join('') + '</div>';
      $$('[data-add]', el).forEach(b => b.onclick = () => addEl(b.dataset.add));
      $$('.rp-li', el).forEach(r => r.onclick = ev => {
        const e = byId(r.dataset.id);
        if (ev.target.dataset.v) { e.hidden = !e.hidden; redraw(e); commit(); side(); return; }
        if (ev.target.dataset.l) { e.lock = !e.lock; deco(node(e.id), e); drawSel(); commit(); side(); return; }
        select(r.dataset.id);
      });
    }
  };
  $$('.rp-tabs button').forEach(b => b.onclick = () => { tab = b.dataset.t; side(); });

  // ---------- แถบเครื่องมือ ----------
  $('#rpUndo').onclick = undo; $('#rpRedo').onclick = redo;
  $('#rpZi').onclick = () => { fitMode = false; z = Math.min(4, z * 1.2); layoutStage(); drawSel(); };
  $('#rpZo').onclick = () => { fitMode = false; z = Math.max(.15, z / 1.2); layoutStage(); drawSel(); };
  $('#rpFit').onclick = () => { fitMode = true; layoutStage(); drawSel(); };
  $('#rpFont').onchange = () => setFont($('#rpFont').value);
  $('#rpPaper').onchange = async () => {
    const [W0, H0] = RPT.size(doc), val = $('#rpPaper').value;
    let np;
    if (val === 'custom') {
      const r = await ui.prompt('ขนาดกระดาษ (มม.)', `${r1(W0)} x ${r1(H0)}`, 'กว้าง x สูง เช่น 174 x 140');
      const mm = /([\d.]+)\s*[x×*]\s*([\d.]+)/.exec(r || '');
      if (!mm) { layoutStage(); return; }
      np = { size: 'custom', w: +mm[1], h: +mm[2] };
    } else { const [s, o] = val.split('|'); np = { size: s, orient: o }; }
    const old = doc.paper; doc.paper = np;
    const [W1, H1] = RPT.size(doc), kx = W1 / W0, ky = H1 / H0;
    if (Math.abs(kx - 1) > .001 || Math.abs(ky - 1) > .001) {
      doc.els.forEach(e => { e.x = r1(e.x * kx); e.w = r1(e.w * kx); e.y = r1(e.y * ky); e.h = r1(e.h * ky); });
    }
    if (old !== np) { fitMode = true; layoutStage(); full(); commit(); doc.els.forEach(e => { if (e.type === 'map') refreshMap(e.id, 0); if (e.type === 'inset') refreshInset(e.id); }); props(); }
  };
  $('#rpExport').onclick = async () => {
    const b = $('#rpExport'), fmt = $('#rpFmt').value, dpi = +$('#rpDpi').value;
    if (editing) document.activeElement?.blur();
    b.disabled = true; const t0 = Date.now();
    const tick = setInterval(() => stat(`กำลังส่งออก ${fmt.toUpperCase()} ${dpi} dpi… ${Math.round((Date.now() - t0) / 1000)} วินาที`), 500);
    try {
      const r = await fetch(ENGINE + '/api/report/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ doc, format: fmt, dpi }) });
      if (!r.ok) throw new Error((await r.json()).error);
      const blob = await r.blob();
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
      a.download = (RPT.fill('{title}', doc) || 'map').replace(/[\\/:*?"<>|]+/g, '_') + '.' + fmt; a.click();
      clearInterval(tick); stat(`ส่งออกแล้ว · ${((Date.now() - t0) / 1000).toFixed(1)} วินาที · ${(blob.size / 1048576).toFixed(1)} MB`);
    } catch (e) { clearInterval(tick); stat(e.message, true); }
    finally { b.disabled = false; }
  };

  // ---------- เริ่ม ----------
  layoutStage(); full(); side(); props(); undoBtns();
  refreshAll();
  if (document.fonts) document.fonts.ready.then(() => { if (document.getElementById('rpPage')) { redrawTypes('scalebar', 'chart', 'north'); doc.els.forEach(e => deco(node(e.id), e)); } });
}

// ---------------- พื้นที่ศึกษาแบบด่วน (ทุกหน้าที่มีช่องพื้นที่ศึกษา) ----------------
const AOI_SELECTS = ['aoi', 'rsAoi', 'vgAoi', 'rzAoi', 'dlAoi', 'zAoi', 'cAoi'];
function enhanceAoiSelects() {
  for (const id of AOI_SELECTS) {
    const s = document.getElementById(id);
    if (!s || s._aoiPick) continue;
    s._aoiPick = true;
    const o = document.createElement('option'); o.value = '__pick'; o.textContent = '＋ เลือกจากชั้นขอบเขต (จังหวัด/อำเภอ/ตำบล)…'; s.appendChild(o);
    let last = s.value === '__pick' ? '' : s.value;
    // ดักก่อน handler ของหน้า (capture ที่ตัวแม่) — ไม่ให้ค่า "__pick" หลุดไปถึงหน้า
    s.parentElement.addEventListener('change', async e => {
      if (e.target !== s) return;
      if (s.value !== '__pick') { last = s.value; return; }
      e.stopPropagation();
      s.value = last;
      const a = await aoiPicker();
      if (!a) return;
      for (const id2 of AOI_SELECTS) {                    // ใส่ตัวเลือกใหม่ให้ทุกช่องในหน้า
        const s2 = document.getElementById(id2);
        if (s2) {                                         // ลงหมวด "ที่สร้างเอง" (ไม่มี → สร้างหมวด)
          let g = [...s2.querySelectorAll('optgroup')].find(x => x.dataset.user);
          if (!g) { g = document.createElement('optgroup'); g.label = 'พื้นที่ศึกษาที่สร้างเอง'; g.dataset.user = 1; s2.insertBefore(g, s2.querySelector('option[value="__pick"]')); }
          const n = document.createElement('option'); n.value = a.id; n.textContent = `${a.name} · ${fmt(a.area_km2, 0)} ตร.กม.`; g.prepend(n);
        }
      }
      s.value = String(a.id); last = s.value;
      s.dispatchEvent(new Event('change', { bubbles: true }));
    }, true);
  }
}
async function aoiPicker() {
  const all = await api(ENGINE + '/api/datasets');
  const srcs = all.filter(isPolySrc);
  if (!srcs.length) { toast('ยังไม่มีชั้นขอบเขต — เพิ่มไฟล์ขอบเขต หรือลิงก์ (เช่น GISTDA L05_Province) ที่คลังข้อมูลก่อน', true); return null; }
  const sel = new Set();
  let src = srcs[0], field = null, shown = [];
  const pr = ui.open('เลือกพื้นที่ศึกษาจากชั้นขอบเขต', `
    <div class="grid-form"><label class="field full"><span>ชั้นขอบเขต</span><select id="apSrc">${srcs.map(d => `<option value="${d.id}">${srcLabel(d)}</option>`).join('')}</select></label>
      <label class="field"><span>ฟิลด์ชื่อ</span><select id="apField"></select></label><label class="field"><span>ค้นหา</span><input type="search" id="apQ" placeholder="พิมพ์ชื่อ…"></label></div>
    <div class="small muted" id="apN" style="margin:8px 0 4px"></div><div class="checklist" id="apList" style="max-height:260px"></div>
    <label class="field" style="margin-top:10px"><span>ชื่อพื้นที่ศึกษา</span><input type="text" id="apName"></label>`,
    [{ label: 'ยกเลิก', cls: 'ghost', value: () => null }, { label: 'ใช้พื้นที่นี้', cls: 'primary', value: () => ({ name: $('#apName').value.trim() }) }]);
  const base = () => src.kind === 'link' ? `${ENGINE}/api/links/${src.id}` : `${ENGINE}/api/datasets/${src.id}`;
  const render = () => {
    $('#apList').innerHTML = shown.map(x => `<label><input type="checkbox" value="${esc(x)}" ${sel.has(x) ? 'checked' : ''}><span>${esc(x)}</span></label>`).join('') || '<div class="tiny muted" style="padding:8px">ไม่พบ</div>';
    $$('#apList input').forEach(i => i.onchange = () => { i.checked ? sel.add(i.value) : sel.delete(i.value); upd(); });
  };
  const upd = () => { if (!$('#apName').dataset.touched) $('#apName').value = [...sel].slice(0, 3).join(' + ') + (sel.size > 3 ? ` และอีก ${sel.size - 3}` : ''); };
  const load = async () => {
    $('#apN').textContent = 'กำลังอ่านรายชื่อ…';
    try {
      const r = await api(`${base()}/field-values?field=${encodeURIComponent(field)}&q=${encodeURIComponent($('#apQ').value)}`);
      shown = r.values; render();
      $('#apN').innerHTML = `${fmt(r.total, 0)} รายการ${r.total > r.values.length ? ` · แสดง ${r.values.length} — พิมพ์ค้นหาเพื่อกรอง` : ''}${r.text_lost ? `<div class="note warn small" style="margin:6px 0 0">${TEXT_LOST}</div>` : ''}`;
    } catch (e) { $('#apN').innerHTML = `<span style="color:var(--coral)">${esc(e.message)}</span>`; }
  };
  const setSrc = async () => {
    src = srcs.find(d => d.id == $('#apSrc').value); sel.clear();
    try { await ensureLinkFields(src); } catch (e) { $('#apN').innerHTML = `<span style="color:var(--coral)">${esc(e.message)}</span>`; return; }
    const fs = fieldNames(src); field = guessNameField(fs);
    $('#apField').innerHTML = fs.map(f => `<option ${f === field ? 'selected' : ''}>${esc(f)}</option>`).join('');
    load();
  };
  $('#apSrc').onchange = setSrc;
  $('#apField').onchange = () => { field = $('#apField').value; sel.clear(); load(); };
  let qt; $('#apQ').oninput = () => { clearTimeout(qt); qt = setTimeout(load, 250); };
  $('#apName').oninput = () => $('#apName').dataset.touched = 1;
  setSrc();
  const res = await pr;
  if (!res) return null;
  if (!sel.size) { toast('ยังไม่ได้เลือกพื้นที่', true); return null; }
  try {
    toast('กำลังสร้างพื้นที่ศึกษา…', false, 2500);
    const r = await api(ENGINE + '/api/aoi', { json: { name: res.name || [...sel].join(' + '), field, values: [...sel], [src.kind === 'link' ? 'link_id' : 'dataset_id']: src.id } });
    toast(`สร้างพื้นที่ศึกษา "${r.aoi.name}" แล้ว · ${fmt(r.aoi.area_km2, 1)} ตร.กม.`);
    return r.aoi;
  } catch (e) { toast(e.message, true); return null; }
}

// เซิร์ฟเวอร์ (run.bat) ยังรันโค้ดเก่า → แถบเตือน + ปุ่มรีสตาร์ต
function versionBanner() {
  const b = document.createElement('div');
  b.className = 'ver-banner';
  if (!ainuEngine.same) {                          // v1: หน้าเว็บอัปเดตเองแล้ว แต่ตัวประมวลผลในเครื่องต้องดาวน์โหลดรุ่นใหม่
    b.innerHTML = `<b>ตัวประมวลผลในเครื่องเป็นรุ่นเก่า</b> (v${esc(STATE.version)}) แต่หน้าเว็บเป็น v${UI_VERSION} — การแก้ไขใหม่ยังไม่มีผล
      <a class="btn sm primary" href="${esc(window.AINU_DOWNLOAD_URL)}">ดาวน์โหลดรุ่นใหม่</a>
      <span class="tiny muted">ปิดหน้าต่าง Ainulindale → แตก zip ทับโฟลเดอร์เดิม (ข้อมูลใน workspace ไม่หาย) → เปิด Ainulindale.bat</span>`;
    document.body.appendChild(b);
    return;
  }
  b.innerHTML = `<b>เซิร์ฟเวอร์ยังเป็นรุ่นเก่า</b> (v${esc(STATE.version)}) แต่หน้าเว็บเป็น v${UI_VERSION} — ฟีเจอร์ใหม่บางอย่างจะใช้ไม่ได้ <button class="sm primary" id="vbGo">รีสตาร์ตเซิร์ฟเวอร์</button><span class="tiny muted">หรือปิดหน้าต่าง run.bat แล้วเปิดใหม่</span>`;
  document.body.appendChild(b);
  $('#vbGo').onclick = async () => {
    $('#vbGo').disabled = true; $('#vbGo').textContent = 'กำลังรีสตาร์ต…';
    try { await api(ENGINE + '/api/system/restart', { json: {} }); } catch { b.querySelector('.tiny').textContent = 'เซิร์ฟเวอร์รุ่นนี้ยังไม่มีปุ่มรีสตาร์ต — ปิดหน้าต่าง run.bat แล้วเปิดใหม่'; return; }
    for (let i = 0; i < 60; i++) {
      await new Promise(r => setTimeout(r, 1000));
      try { const s = await api(ENGINE + '/api/state'); if (s.version === UI_VERSION) { location.reload(); return; } } catch { }
    }
    b.querySelector('.tiny').textContent = 'รอนานเกิน — ปิดหน้าต่าง run.bat แล้วเปิดใหม่';
  };
}

// ---------------- เริ่ม ----------------
(async () => {
  $$('[data-ic]').forEach(e => e.innerHTML = IC[e.dataset.ic]);
  await ainuEngine.gate();                                   // v1: รอจนเชื่อมต่อ + จับคู่ตัวประมวลผลในเครื่องได้
  STATE = await api(ENGINE + '/api/state');
  $('#ver').textContent = 'v' + STATE.version;
  if (STATE.version !== UI_VERSION) versionBanner();
  $('#ws').textContent = STATE.workspace;
  ainuEngine.badge(STATE);
  jobBadge(); setInterval(jobBadge, 3000);
  route();
  if (window.AIDock) AIDock.init();                         // ผู้ช่วย AI (โชว์เฉพาะเมื่อเปิดใช้ในหน้า "ระบบ")
})();
