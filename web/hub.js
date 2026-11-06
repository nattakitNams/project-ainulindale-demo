// Ainulindalë — Data hub: รายชื่อว่าใครมีข้อมูลอะไร อยู่ที่ไหน (ไม่เก็บไฟล์ · กดไปโหลดที่ต้นทาง)
// ข้อมูลจาก hub/index.json + hub/desc_XX.json (สร้างด้วย tools/build_hub.py) · คำอธิบายดึงจากต้นทาง ไม่ได้เขียนเอง
'use strict';
const HUB = { idx: null, desc: {}, q: '', th: '', plat: '', org: '', ty: '', lc: '', cover: '', link: '', old: false, sort: 'name', shown: 40, links: {}, run: null, withRes: false };
const HUB_LC = { open: ['เปิด', 'var(--mint)', 'ใช้/แจกต่อได้ (ระบุที่มา)'], nc: ['ไม่ใช่เชิงพาณิชย์', 'var(--butter)', 'ห้ามใช้เชิงพาณิชย์'], check: ['ตรวจเงื่อนไข', 'var(--muted)', 'อ่านเงื่อนไขของผู้ผลิตก่อนใช้'] };
const HUB_COVER = { global: 'ทั้งโลก', thailand: 'ไทย', other: 'นอกไทย', partial: 'บางส่วน', unknown: 'ไม่ระบุ' };
const HUB_ST = { ok: 'ใช้ได้', warn: 'มีเงื่อนไข', bad: 'เสีย' };
try { HUB.links = JSON.parse(localStorage.getItem('ainu-hub-links') || '{}'); } catch { HUB.links = {}; }
const hubSaveLinks = () => { try { localStorage.setItem('ainu-hub-links', JSON.stringify(HUB.links)); } catch { } };

async function hubLoad() {
  if (!HUB.idx) {
    const r = await fetch('hub/index.json?v=' + UI_VERSION);
    if (!r.ok) throw new Error('โหลดรายชื่อ Data hub ไม่ได้');
    HUB.idx = await r.json();
    HUB.idx.items.forEach(it => { it._s = [it.t, it.id, it.pr, it.p, ...(it.og || []), ...(it.kw || []), it.sd].filter(Boolean).join(' ').toLowerCase(); });
  }
  return HUB.idx;
}
async function hubShard(sh) {
  if (!(sh in HUB.desc)) {
    const r = await fetch(`hub/desc_${String(sh).padStart(2, '0')}.json?v=${UI_VERSION}`);
    HUB.desc[sh] = r.ok ? await r.json() : {};
  }
  return HUB.desc[sh];
}
const hubDesc = async it => (await hubShard(it.sh))[it.k] || {};
async function hubAllDesc() {
  await Promise.all([...new Set(HUB.idx.items.map(it => it.sh))].map(hubShard));
  return it => HUB.desc[it.sh]?.[it.k] || {};
}

// markdown แบบจำกัด (escape ทั้งหมดก่อน → ลิงก์ http(s) · ตัวหนา/เอียง · รายการ · ย่อหน้า) — ไม่รัน HTML จากต้นทาง
function hubMd(src, fmt) {
  let s = esc(String(src || '').replace(/\r/g, '').trim());
  if (fmt !== 'md') return s.split(/\n{2,}/).map(p => `<p>${p.replace(/\n/g, '<br>')}</p>`).join('');
  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (m, t, u) => `<a href="${u}" target="_blank" rel="noopener noreferrer">${t}</a>`)
    .replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, (m, a, u) => `${a}<a href="${u}" target="_blank" rel="noopener noreferrer">${u}</a>`)
    .replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>').replace(/(^|[\s(])[_*]([^_*\n]+)[_*](?=[\s).,;:]|$)/g, '$1<i>$2</i>')
    .replace(/&lt;br\s*\/?&gt;/g, '<br>');
  return s.split(/\n{2,}/).map(p => {
    const lines = p.split('\n');
    if (lines.every(l => /^\s*([*-]|\d+\.)\s+/.test(l))) return `<ul>${lines.map(l => `<li>${l.replace(/^\s*([*-]|\d+\.)\s+/, '')}</li>`).join('')}</ul>`;
    if (/^#{1,6}\s/.test(p)) return `<h4>${p.replace(/^#{1,6}\s/, '')}</h4>`;
    return `<p>${lines.join('<br>')}</p>`;
  }).join('');
}
const hubYears = it => it.a || it.b ? `${(it.a || '?').slice(0, 4)}–${it.b ? it.b.slice(0, 4) : 'ปัจจุบัน'}` : '';
const hubGsd = g => !g || !g.length ? '' : (g.length === 1 ? fmt(g[0], 2) : `${fmt(g[0], 2)}–${fmt(g[g.length - 1], 2)}`) + ' ม.';
const hubTheme = k => HUB.idx.meta.themes.find(t => t.k === k);
const hubLinkNote = r => `${r.status ? 'HTTP ' + r.status : 'ไม่ตอบ'}${r.note ? ' · ' + r.note : ''}${r.final ? ' → ' + r.final : ''} · ตรวจเมื่อ ${new Date(r.at).toLocaleString('th-TH')}`;
const hubDot = u => { const r = HUB.links[u]; return r ? `<i class="hub-dot ${r.state}" title="${esc(HUB_ST[r.state] + ' · ' + hubLinkNote(r))}"></i>` : ''; };
function hubStatus(u) {
  const r = HUB.links[u];
  if (!r) return '<span class="tiny muted">ยังไม่ได้ตรวจ</span>';
  return `<span class="hub-badge ${r.state}" title="${esc(hubLinkNote(r))}">${HUB_ST[r.state]}${r.status ? ' · ' + r.status : ''}</span>${r.note ? `<div class="tiny muted">${esc(r.note)}</div>` : ''}`;
}
// สถานะลิงก์ของชุด: หน้าหลัก (+ ไฟล์ในชุดที่ตรวจแล้ว ถ้ามีเสีย)
const hubItemState = it => HUB.links[it.u]?.state || 'none';

// ---------- ตรวจทุกลิงก์ (ปุ่มเดียว) ----------
async function hubCheckAll(onProgress) {
  const urls = new Map();
  HUB.idx.items.forEach(it => urls.set(it.u, 1));
  if (HUB.withRes) {
    const get = await hubAllDesc();
    HUB.idx.items.forEach(it => (get(it).resources || []).forEach(r => r.url && urls.set(r.url, 1)));
  }
  const all = [...urls.keys()];
  const run = HUB.run = { total: all.length, done: 0, cancel: false, n: { ok: 0, warn: 0, bad: 0 } };
  let i = 0;
  const worker = async () => {
    while (!run.cancel && i < all.length) {
      const chunk = all.slice(i, i += 40);
      try {
        const r = await api(ENGINE + '/api/hub/check', { json: { urls: chunk } });
        r.results.forEach(x => { HUB.links[x.url] = { ...x, at: Date.now() }; run.n[x.state]++; });
      } catch (e) { run.error = e.message; run.cancel = true; }
      run.done = Math.min(i, all.length);
      onProgress(run);
      if (run.done % 200 < 40) hubSaveLinks();
    }
  };
  await Promise.all([worker(), worker()]);           // 2 ชุดพร้อมกัน (ตัวประมวลผลตรวจชุดละ 8 ลิงก์พร้อมกัน) — ไม่ถล่มเว็บต้นทาง
  hubSaveLinks();
  HUB.run = null;
  return run;
}

// ---------- ส่งออก CSV ----------
async function hubExport(list, withRes) {
  const q = v => { const s = v == null ? '' : String(v); return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const st = u => HUB.links[u] || {};
  const T = HUB.idx.meta.types;
  const cols = ['ชื่อชุดข้อมูล', 'รหัส', 'แหล่ง', 'หน่วยงาน', 'ชนิดข้อมูล', 'รูปแบบไฟล์/บริการ', 'หมวด', 'เริ่ม', 'สิ้นสุด', 'อัปเดตล่าสุด', 'ความละเอียด (ม.)', 'ความถี่',
    'ครอบคลุม', 'License', 'เงื่อนไขการใช้', 'ลิงก์', 'ข้อมูลประกอบ', 'จำนวนไฟล์ในชุด', 'สถานะลิงก์', 'HTTP', 'ตรวจเมื่อ', 'ที่มาของคำอธิบาย'];
  const row = it => [it.t, it.id, it.p, (it.og || [it.pr]).filter(Boolean).join('; '), it.ty === 'platform' ? 'แพลตฟอร์ม' : T[it.ty], it.tr, it.th.map(k => hubTheme(k)?.th || k).join('; '),
    it.a, it.b, it.up, (it.g || []).join('–'), it.cd, HUB_COVER[it.cv], it.l, HUB_LC[it.lc][0], it.u, it.m, it.nr,
    HUB_ST[st(it.u).state] || 'ยังไม่ได้ตรวจ', st(it.u).status, st(it.u).at ? new Date(st(it.u).at).toISOString().slice(0, 16).replace('T', ' ') : '', it.ds];
  let lines = [cols.map(q).join(',')];
  if (withRes) {
    const get = await hubAllDesc();
    lines = [[...cols, 'ไฟล์/บริการในชุด', 'รูปแบบ', 'ลิงก์ไฟล์', 'สถานะลิงก์ไฟล์'].map(q).join(',')];
    list.forEach(it => {
      const rs = get(it).resources || [];
      if (!rs.length) lines.push([...row(it), '', '', '', ''].map(q).join(','));
      rs.forEach(r => lines.push([...row(it), r.name, r.format, r.url, HUB_ST[st(r.url).state] || 'ยังไม่ได้ตรวจ'].map(q).join(',')));
    });
  } else list.forEach(it => lines.push(row(it).map(q).join(',')));
  const blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });       // BOM → Excel อ่านภาษาไทยถูก
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `data_hub_${new Date().toISOString().slice(0, 10)}_${list.length}${withRes ? '_files' : ''}.csv`;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  toast(`ส่งออก ${fmt(list.length, 0)} ชุด${withRes ? ' (รวมไฟล์ในชุด ' + fmt(lines.length - 1, 0) + ' แถว)' : ''}`);
}

function hubFilter() {
  const words = HUB.q.toLowerCase().split(/\s+/).filter(Boolean);
  let list = HUB.idx.items.filter(it =>
    (!HUB.th || it.th.includes(HUB.th)) && (!HUB.plat || it.p === HUB.plat) && (!HUB.org || (it.og || []).includes(HUB.org))
    && (!HUB.ty || it.ty === HUB.ty) && (!HUB.lc || it.lc === HUB.lc)
    && (!HUB.cover || (HUB.cover === 'th' ? ['global', 'thailand', 'partial'].includes(it.cv) : it.cv === HUB.cover))
    && (!HUB.link || hubItemState(it) === HUB.link)
    && (HUB.old || !it.dp) && words.every(w => it._s.includes(w)));
  if (HUB.sort === 'new') list = [...list].sort((a, b) => (b.up || b.b || '9999').localeCompare(a.up || a.b || '9999') || (b.a || '').localeCompare(a.a || ''));
  else if (HUB.sort === 'name') { const o = { other: 0, ckan: 1, platform: 2, pc: 3, gee: 4 }; list = [...list].sort((a, b) => (o[a.s] ?? 5) - (o[b.s] ?? 5) || a.t.localeCompare(b.t, 'th')); }
  return list;
}

function hubCard(it) {
  const L = HUB_LC[it.lc];
  return `<a class="hub-card" href="#/hub/${encodeURIComponent(it.k)}">
    <div class="hub-top"><b>${esc(it.t)}</b>${it.dp ? '<span class="chip warn">เลิกใช้แล้ว</span>' : ''}</div>
    <div class="small muted">${esc((it.og || [it.pr]).filter(Boolean).slice(0, 2).join(', '))}${it.og || it.pr ? ' · ' : ''}<span class="hub-src s-${it.s}">${esc(it.p)}</span></div>
    <div class="hub-meta tiny">${[it.ty === 'platform' ? 'แพลตฟอร์ม' : HUB.idx.meta.types[it.ty], hubYears(it) || (it.up ? 'อัปเดต ' + it.up : ''), hubGsd(it.g), it.cd, it.nr ? it.nr + ' ไฟล์/บริการ' : '', HUB_COVER[it.cv]].filter(Boolean).map(esc).join(' · ')}</div>
    <div class="hub-th">${it.th.slice(0, 3).map(k => `<span>${esc(hubTheme(k)?.th || k)}</span>`).join('')}
      <span class="hub-lc" style="--c:${L[1]}" title="${esc(it.l || 'ไม่ระบุ')} — ${L[2]}">${L[0]}</span>${hubDot(it.u)}</div></a>`;
}

async function pageHub(key) {
  const v = $('#view');
  const ix = await hubLoad();
  if (key) return hubDetail(ix.items.find(it => it.k === key));
  const cnt = k => ix.items.filter(it => it.th.includes(k) && (HUB.old || !it.dp)).length;
  const checked = () => ix.items.filter(it => HUB.links[it.u]).length;
  v.innerHTML = head('Data hub', 'แหล่งข้อมูลภูมิสารสนเทศ', `รายชื่อว่าใครมีข้อมูลอะไร อยู่ที่ไหน ${fmt(ix.meta.count, 0)} รายการ — แอปไม่ได้เก็บไฟล์ กดเข้าไปดูรายละเอียดแล้วไปโหลดที่ต้นทาง`,
    `<button class="ghost" id="hbCsv" title="รายการตามตัวกรองที่เลือกอยู่: ชื่อ หน่วยงาน ลิงก์ สถานะลิงก์ ฯลฯ">${IC.download}ส่งออก CSV</button>
     <button class="primary" id="hbChk" title="ตรวจลิงก์ของทุกชุดในรายการ">${IC.link}ตรวจสอบทุกลิงก์</button>`)
    + `<div id="hbRun" class="card hub-run hide"></div>
    <div class="card hub-filter">
      <input type="search" id="hbQ" placeholder="ค้นหา: ชื่อ, หน่วยงาน, คำสำคัญ เช่น ไฟป่า, ประชากร, flood, NDVI, Sentinel" value="${esc(HUB.q)}">
      <div class="hub-themes"><button class="chip ${HUB.th ? '' : 'on'}" data-th="">ทุกหมวด</button>${ix.meta.themes.map(t => `<button class="chip ${HUB.th === t.k ? 'on' : ''}" data-th="${t.k}" title="${esc(t.en)}">${esc(t.th)} <em>${cnt(t.k)}</em></button>`).join('')}</div>
      <div class="hub-sel">
        <label class="hub-org"><span>หน่วยงาน</span><div class="row" style="flex-wrap:nowrap;gap:4px"><input type="text" id="hbOrg" list="hbOrgs" placeholder="พิมพ์ชื่อหน่วยงาน เช่น GISTDA, กรมพัฒนาที่ดิน, NASA" value="${esc(HUB.org)}"><button class="sm ghost" id="hbOrgX" title="ล้าง">${IC.x}</button></div>
          <datalist id="hbOrgs">${ix.meta.orgs.map(([o, n]) => `<option value="${esc(o)}">${n} ชุด</option>`).join('')}</datalist></label>
        <label><span>แหล่ง</span><select id="hbPlat"><option value="">ทั้งหมด</option>${ix.meta.platforms.map(([p, n]) => `<option value="${esc(p)}" ${HUB.plat === p ? 'selected' : ''}>${esc(p)} (${n})</option>`).join('')}</select></label>
        <label><span>ชนิดข้อมูล</span><select id="hbTy"><option value="">ทั้งหมด</option>${Object.entries(ix.meta.types).map(([k, t]) => `<option value="${k}" ${HUB.ty === k ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
        <label><span>เงื่อนไขการใช้</span><select id="hbLc"><option value="">ทั้งหมด</option>${Object.entries(HUB_LC).map(([k, t]) => `<option value="${k}" ${HUB.lc === k ? 'selected' : ''}>${t[0]} — ${t[2]}</option>`).join('')}</select></label>
        <label><span>ครอบคลุม</span><select id="hbCv"><option value="">ทั้งหมด</option><option value="th" ${HUB.cover === 'th' ? 'selected' : ''}>มีประเทศไทย</option><option value="thailand" ${HUB.cover === 'thailand' ? 'selected' : ''}>เฉพาะไทย/ภูมิภาค</option><option value="global" ${HUB.cover === 'global' ? 'selected' : ''}>ทั้งโลก</option></select></label>
        <label><span>สถานะลิงก์</span><select id="hbLink"><option value="">ทั้งหมด</option>${Object.entries(HUB_ST).map(([k, t]) => `<option value="${k}" ${HUB.link === k ? 'selected' : ''}>${t}</option>`).join('')}<option value="none" ${HUB.link === 'none' ? 'selected' : ''}>ยังไม่ได้ตรวจ</option></select></label>
        <label><span>เรียง</span><select id="hbSort"><option value="name" ${HUB.sort === 'name' ? 'selected' : ''}>ชื่อ (แหล่งไทย/ผู้ผลิตโดยตรงก่อน)</option><option value="new" ${HUB.sort === 'new' ? 'selected' : ''}>ข้อมูลล่าสุดก่อน</option></select></label>
        <label class="row small"><input type="checkbox" id="hbOld" ${HUB.old ? 'checked' : ''}> แสดงชุดที่เลิกใช้แล้ว</label>
      </div></div>
    <div id="hbRes"></div>
    <div class="tiny muted hub-credit">${ix.meta.credits.map(esc).join('<br>')} · สร้างรายชื่อเมื่อ ${esc(ix.meta.built)}</div>`;
  const summary = () => {
    const n = { ok: 0, warn: 0, bad: 0 };
    ix.items.forEach(it => { const s = HUB.links[it.u]?.state; if (s) n[s]++; });
    return n;
  };
  const draw = () => {
    const list = hubFilter(), n = summary(), c = checked();
    $('#hbRes').innerHTML = `<div class="row small muted" style="margin:4px 2px 10px;gap:12px">${fmt(list.length, 0)} รายการ
      ${c ? `<span class="spacer"></span><span>ลิงก์ที่ตรวจแล้ว ${fmt(c, 0)}/${fmt(ix.items.length, 0)}: <span class="hub-badge ok">ใช้ได้ ${fmt(n.ok, 0)}</span> <span class="hub-badge warn">มีเงื่อนไข ${fmt(n.warn, 0)}</span> <span class="hub-badge bad">เสีย ${fmt(n.bad, 0)}</span></span>` : ''}</div>
      <div class="hub-grid">${list.slice(0, HUB.shown).map(hubCard).join('') || '<p class="muted">ไม่พบ — ลองคำค้นอื่น หรือล้างตัวกรอง</p>'}</div>
      ${list.length > HUB.shown ? `<div style="text-align:center;margin:14px"><button class="ghost" id="hbMore">แสดงเพิ่ม (${fmt(list.length - HUB.shown, 0)} เหลือ)</button></div>` : ''}`;
    $('#hbMore') && ($('#hbMore').onclick = () => { HUB.shown += 60; draw(); });
    return list;
  };
  const redraw = () => { HUB.shown = 40; draw(); };
  let tq;
  $('#hbQ').oninput = () => { clearTimeout(tq); tq = setTimeout(() => { HUB.q = $('#hbQ').value.trim(); redraw(); }, 200); };
  $$('[data-th]').forEach(b => b.onclick = () => { HUB.th = b.dataset.th; $$('[data-th]').forEach(x => x.classList.toggle('on', x === b)); redraw(); });
  [['#hbPlat', 'plat'], ['#hbTy', 'ty'], ['#hbLc', 'lc'], ['#hbCv', 'cover'], ['#hbLink', 'link'], ['#hbSort', 'sort']].forEach(([id, k]) => $(id).onchange = () => { HUB[k] = $(id).value; redraw(); });
  const orgs = new Set(ix.meta.orgs.map(o => o[0]));
  $('#hbOrg').oninput = () => { const s = $('#hbOrg').value.trim(); const next = orgs.has(s) ? s : ''; if (next !== HUB.org) { HUB.org = next; redraw(); } };
  $('#hbOrgX').onclick = () => { $('#hbOrg').value = ''; HUB.org = ''; redraw(); };
  $('#hbOld').onchange = () => { HUB.old = $('#hbOld').checked; draw(); };
  $('#hbCsv').onclick = async () => {
    const list = hubFilter();
    const pick = await ui.open('ส่งออก CSV', `<p>${fmt(list.length, 0)} ชุดตามตัวกรองที่เลือกอยู่ (ไม่กรอง = ทั้งหมด) — ชื่อ หน่วยงาน แหล่ง ลิงก์ License สถานะลิงก์ ฯลฯ</p>
      <p class="small muted">"รวมไฟล์ในชุด" = 1 แถวต่อไฟล์/บริการ (เช่น ชุดของ GISTDA ที่มีหลายบริการ)</p>`,
      [{ label: 'ยกเลิก', cls: 'ghost', value: () => null }, { label: 'รวมไฟล์ในชุด', value: () => 'res' }, { label: 'รายการชุดข้อมูล', cls: 'primary', value: () => 'ds' }]);
    if (pick) await hubExport(list, pick === 'res');
  };
  const showRun = run => {
    const el = $('#hbRun');
    el.classList.remove('hide');
    const pct = run.total ? run.done / run.total * 100 : 0;
    el.innerHTML = `<div class="row" style="gap:10px"><b>${run.cancel && run.done < run.total ? 'หยุดแล้ว' : run.done >= run.total ? 'ตรวจเสร็จ' : 'กำลังตรวจลิงก์…'}</b>
      <span class="small muted">${fmt(run.done, 0)}/${fmt(run.total, 0)}</span>
      <span class="hub-badge ok">ใช้ได้ ${fmt(run.n.ok, 0)}</span><span class="hub-badge warn">มีเงื่อนไข ${fmt(run.n.warn, 0)}</span><span class="hub-badge bad">เสีย ${fmt(run.n.bad, 0)}</span>
      <span class="spacer"></span>${run.done < run.total && !run.cancel ? '<button class="sm ghost" id="hbStop">หยุด</button>' : `${run.n.bad ? '<button class="sm" id="hbShowBad">ดูเฉพาะที่เสีย</button>' : ''}<button class="sm ghost" id="hbHide">${IC.x}</button>`}</div>
      <div class="hub-prog"><i style="width:${pct}%"></i></div>${run.error ? `<div class="note err small">${esc(run.error)}</div>` : ''}`;
    $('#hbStop') && ($('#hbStop').onclick = () => { run.cancel = true; });
    $('#hbHide') && ($('#hbHide').onclick = () => el.classList.add('hide'));
    $('#hbShowBad') && ($('#hbShowBad').onclick = () => { HUB.link = 'bad'; $('#hbLink').value = 'bad'; redraw(); });
  };
  $('#hbChk').onclick = async () => {
    if (HUB.run) return;
    const go = await ui.open('ตรวจสอบทุกลิงก์', `<p>ตรวจลิงก์หน้าข้อมูลของทุกชุด ${fmt(ix.items.length, 0)} ลิงก์ ผ่านตัวประมวลผลในเครื่องคุณ (อ่านแค่ส่วนหัว ไม่โหลดไฟล์) — ใช้เวลาหลายนาที หยุดกลางทางได้</p>
      <label class="row small"><input type="checkbox" id="hbWithRes" ${HUB.withRes ? 'checked' : ''}> รวมลิงก์ไฟล์/บริการในแต่ละชุดด้วย (พอร์ทัลข้อมูลเปิด — นานขึ้นมาก)</label>
      <p class="tiny muted">บางเว็บปฏิเสธโปรแกรมตรวจ (403) หรือต้องล็อกอิน (401) → "มีเงื่อนไข" — เปิดด้วยเบราว์เซอร์อาจได้</p>`,
      [{ label: 'ยกเลิก', cls: 'ghost', value: () => false }, { label: 'เริ่มตรวจ', cls: 'primary', value: () => { HUB.withRes = $('#hbWithRes').checked; return true; } }]);
    if (!go) return;
    $('#hbChk').disabled = true;
    let t0 = 0;
    const run = await hubCheckAll(r => { showRun(r); if (Date.now() - t0 > 1500) { t0 = Date.now(); draw(); } });
    showRun(run); draw();
    $('#hbChk') && ($('#hbChk').disabled = false);
  };
  if (HUB.run) showRun(HUB.run);
  draw();
}

async function hubDetail(it) {
  const v = $('#view');
  if (!it) { v.innerHTML = `<div class="note err">ไม่พบรายการนี้ใน Data hub</div><p><a href="#/hub">← กลับ Data hub</a></p>`; return; }
  const x = await hubDesc(it), d = x.desc || {}, LC = HUB_LC[it.lc];
  const links = [
    ['หน้าข้อมูล / ดาวน์โหลด', it.u, it.s === 'gee' ? 'หน้าแคตตาล็อกของ Earth Engine' : it.s === 'pc' ? 'หน้าแคตตาล็อกของ Planetary Computer' : it.s === 'ckan' ? `หน้าชุดข้อมูลใน ${it.p}` : 'เว็บไซต์ผู้ผลิต'],
    x.source_page ? ['เว็บไซต์ของชุดข้อมูล', x.source_page, 'ลิงก์ที่ผู้ให้ข้อมูลระบุ'] : null,
    it.m && it.s !== 'other' && it.s !== 'platform' ? [it.s === 'ckan' ? 'ข้อมูลประกอบ (CKAN API JSON)' : 'ข้อมูลประกอบ (STAC JSON)', it.m, 'ไฟล์ข้อมูลประกอบที่เครื่องอ่านได้'] : null,
    ...(x.mirrors || []).map(m => [`มีใน ${m.platform} ด้วย`, m.url, 'ชุดเดียวกันที่พอร์ทัลอื่นดึงไปแสดง']),
    ...(x.providers || []).filter(p => p.url).map(p => [`ผู้ให้: ${p.name}`, p.url, (p.roles || []).join(', ')]),
    d.source_url && d.source_url !== it.u && d.source_url !== it.m ? ['ที่มาของคำอธิบาย', d.source_url, d.source] : null,
  ].filter((l, i, arr) => l && arr.findIndex(o => o && o[1] === l[1]) === i);      // ลิงก์ซ้ำแสดงครั้งเดียว
  const res = x.resources || [];
  const orgs = (it.og || []).length ? it.og : (it.pr ? [it.pr] : []);
  const facts = [
    ['รหัสชุดข้อมูล', it.id ? `<code>${esc(it.id)}</code>` : ''],
    ['แหล่ง', esc(it.p)],
    ['หน่วยงาน', orgs.map(o => `<a class="chip" href="#/hub" data-goorg="${esc(o)}">${esc(o)}</a>`).join(' ')],
    ['ชนิดข้อมูล', esc([it.ty === 'platform' ? 'แพลตฟอร์ม' : HUB.idx.meta.types[it.ty], it.tr].filter(Boolean).join(' · '))],
    ['ช่วงเวลา', esc(hubYears(it))],
    ['อัปเดตล่าสุด', esc(it.up || '')],
    ['ความถี่', esc(it.cd || '')],
    ['ความละเอียด', esc(hubGsd(it.g))],
    ['ครอบคลุม', esc(HUB_COVER[it.cv] || '') + (it.bb ? ` <span class="tiny muted mono">[${it.bb.map(n => fmt(n, 2)).join(', ')}]</span>` : '')],
    ['เงื่อนไขการใช้', `<span class="hub-lc" style="--c:${LC[1]}">${LC[0]}</span> ${esc(it.l || 'ไม่ระบุในรายชื่อ — ดูที่ต้นทาง')} <span class="tiny muted">· ${LC[2]}</span>`],
    ['หมวด', it.th.map(k => `<a class="chip" href="#/hub" data-goth="${k}">${esc(hubTheme(k)?.th || k)}</a>`).join(' ')],
    ['คำสำคัญ (จากต้นทาง)', esc((x.keywords || []).join(', '))],
    it.n ? ['หมายเหตุ', esc(it.n)] : null,
  ].filter(f => f && f[1]);
  const linkRow = (t, u, sub) => `<div class="hub-link"><div><a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(t)}</a>
    ${sub ? `<div class="tiny muted">${esc(sub)}</div>` : ''}<div class="tiny mono muted hub-url">${esc(u)}</div></div><div class="hub-st">${hubStatus(u)}</div></div>`;
  v.innerHTML = `<p style="margin:0 0 10px"><a href="#/hub">← Data hub</a></p>`
    + head(esc(it.p) + (it.dp ? ' · <span style="color:var(--butter)">เลิกใช้แล้ว</span>' : ''), esc(it.t), esc(it.sd || ''),
      `<a class="btn primary" href="${esc(it.u)}" target="_blank" rel="noopener noreferrer">${IC.download}ไปหน้าดาวน์โหลด</a>`)
    + `<div class="cols2 hub-detail">
      <div>
        <div class="card"><div class="card-head"><h2>คำอธิบาย</h2></div>
          ${d.about ? `<div class="note info small">${esc(d.about)}</div>` : ''}
          <div class="hub-desc">${d.text ? hubMd(d.text, d.fmt) : '<p class="muted">ยังไม่มีคำอธิบายจากต้นทาง — กด "ไปหน้าดาวน์โหลด" เพื่ออ่านที่เว็บผู้ผลิต</p>'}</div>
          ${d.text ? `<div class="tiny muted hub-attr">ที่มา: <a href="${esc(d.source_url)}" target="_blank" rel="noopener noreferrer">${esc(d.source)}</a> · ${esc(d.license_note || '')} · แอปไม่ได้เขียนหรือแก้ข้อความนี้</div>` : ''}
        </div>
        ${res.length ? `<div class="card"><div class="card-head"><h2>ไฟล์ / บริการในชุดนี้ <span class="muted small">${fmt(it.nr || res.length, 0)} รายการ${it.nr > res.length ? ` (แสดง ${res.length})` : ''}</span></h2></div>
          <div class="hub-links">${res.map(r => linkRow(r.name || r.url.split('/').pop() || r.url, r.url, [r.format ? 'รูปแบบ: ' + r.format : '', r.key ? 'ต้องใช้ API key ของคุณเอง — แอปซ่อนคีย์ที่ติดมากับลิงก์ต้นทางไว้ ({YOUR_API_KEY})' : ''].filter(Boolean).join(' · '))).join('')}</div></div>` : ''}
        ${x.citation ? `<div class="card"><div class="card-head"><h2>การอ้างอิง (จากต้นทาง)</h2></div><div class="hub-desc small">${hubMd(x.citation, 'md')}</div></div>` : ''}
        ${x.terms ? `<div class="card"><div class="card-head"><h2>เงื่อนไขการใช้ (จากต้นทาง)</h2></div><div class="hub-desc small">${hubMd(x.terms, 'md')}</div></div>` : ''}
      </div>
      <div>
        <div class="card"><div class="card-head"><h2>ข้อมูลโดยย่อ</h2></div><table class="kv">${facts.map(([k, val]) => `<tr><td>${k}</td><td>${val}</td></tr>`).join('')}</table>
          ${it.bb && it.cv !== 'global' ? '<div id="hdMap" class="hub-map"></div>' : ''}</div>
        <div class="card"><div class="card-head"><h2>ลิงก์</h2></div>
          <div class="hub-links">${links.map(([t, u, sub]) => linkRow(t, u, sub)).join('')}</div>
          <div class="tiny muted" style="margin-top:8px">สถานะจากการกด "ตรวจสอบทุกลิงก์" ในหน้า Data hub</div></div>
      </div></div>`;
  $$('[data-goth]').forEach(a => a.onclick = () => { HUB.th = a.dataset.goth; HUB.shown = 40; });
  $$('[data-goorg]').forEach(a => a.onclick = () => { HUB.org = a.dataset.goorg; HUB.shown = 40; });
  if ($('#hdMap')) {
    const mp = baseMap('hdMap'); maps.push(mp);
    const b = it.bb, r = L.rectangle([[b[1], b[0]], [b[3], b[2]]], { color: '#f7a8cc', weight: 2, fillOpacity: .12 }).addTo(mp);
    mp.fitBounds(r.getBounds(), { padding: [10, 10], maxZoom: 7 });
  }
}
