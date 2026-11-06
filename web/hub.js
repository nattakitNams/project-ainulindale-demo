// Ainulindalë — Data hub: รายชื่อว่าใครมีข้อมูลอะไร อยู่ที่ไหน (ไม่เก็บไฟล์ · กดไปโหลดที่ต้นทาง)
// ข้อมูลจาก hub/index.json + hub/desc_XX.json (สร้างด้วย tools/build_hub.py) · คำอธิบายดึงจากต้นทาง ไม่ได้เขียนเอง
'use strict';
const HUB = { idx: null, desc: {}, q: '', th: '', src: '', ty: '', lc: '', cover: '', old: false, sort: 'name', shown: 40, links: {} };
const HUB_SRC = { other: 'ผู้ผลิตโดยตรง', platform: 'แพลตฟอร์ม', pc: 'Planetary Computer', gee: 'Earth Engine' };
const HUB_LC = { open: ['เปิด', 'var(--mint)', 'ใช้/แจกต่อได้ (ระบุที่มา)'], nc: ['ไม่ใช่เชิงพาณิชย์', 'var(--butter)', 'ห้ามใช้เชิงพาณิชย์'], check: ['ตรวจเงื่อนไข', 'var(--muted)', 'อ่านเงื่อนไขของผู้ผลิตก่อนใช้'] };
const HUB_COVER = { global: 'ทั้งโลก', thailand: 'ไทย', other: 'นอกไทย', partial: 'บางส่วน', unknown: 'ไม่ระบุ' };
try { HUB.links = JSON.parse(localStorage.getItem('ainu-hub-links') || '{}'); } catch { HUB.links = {}; }
const hubSaveLinks = () => { try { localStorage.setItem('ainu-hub-links', JSON.stringify(HUB.links)); } catch { } };

async function hubLoad() {
  if (!HUB.idx) {
    const r = await fetch('hub/index.json?v=' + UI_VERSION);
    if (!r.ok) throw new Error('โหลดรายชื่อ Data hub ไม่ได้');
    HUB.idx = await r.json();
    HUB.idx.items.forEach(it => { it._s = [it.t, it.id, it.pr, it.p, ...(it.kw || []), it.sd].filter(Boolean).join(' ').toLowerCase(); });
  }
  return HUB.idx;
}
async function hubDesc(it) {
  if (!(it.sh in HUB.desc)) {
    const r = await fetch(`hub/desc_${String(it.sh).padStart(2, '0')}.json?v=${UI_VERSION}`);
    HUB.desc[it.sh] = r.ok ? await r.json() : {};
  }
  return HUB.desc[it.sh][it.k] || {};
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
    return `<p>${lines.join(' ')}</p>`;
  }).join('');
}
const hubYears = it => it.a || it.b ? `${(it.a || '?').slice(0, 4)}–${it.b ? it.b.slice(0, 4) : 'ปัจจุบัน'}` : '';
const hubGsd = g => !g || !g.length ? '' : (g.length === 1 ? fmt(g[0], 2) : `${fmt(g[0], 2)}–${fmt(g[g.length - 1], 2)}`) + ' ม.';
const hubTheme = k => HUB.idx.meta.themes.find(t => t.k === k);
const hubDot = u => { const r = HUB.links[u]; return r ? `<i class="hub-dot ${r.state}" title="${esc(hubLinkNote(r))}"></i>` : ''; };
const hubLinkNote = r => `${r.status ? 'HTTP ' + r.status : 'ไม่ตอบ'}${r.note ? ' · ' + r.note : ''}${r.final ? ' → ' + r.final : ''} · ตรวจเมื่อ ${new Date(r.at).toLocaleString('th-TH')}`;

async function hubCheck(urls, btn) {
  urls = [...new Set(urls.filter(Boolean))];
  if (!urls.length) return;
  const label = btn?.innerHTML;
  const out = [];
  try {
    for (let i = 0; i < urls.length; i += 40) {
      if (btn) btn.innerHTML = `${IC.refresh}กำลังตรวจ ${Math.min(i + 40, urls.length)}/${urls.length}…`;
      if (btn) btn.disabled = true;
      const r = await api(ENGINE + '/api/hub/check', { json: { urls: urls.slice(i, i + 40) } });
      r.results.forEach(x => { HUB.links[x.url] = { ...x, at: Date.now() }; out.push(x); });
    }
    hubSaveLinks();
    const bad = out.filter(x => x.state === 'bad').length, warn = out.filter(x => x.state === 'warn').length;
    toast(`ตรวจ ${out.length} ลิงก์ · ใช้ได้ ${out.length - bad - warn}${warn ? ` · เข้าได้แต่มีเงื่อนไข ${warn}` : ''}${bad ? ` · เสีย ${bad}` : ''}`, bad > 0);
  } catch (e) { toast('ตรวจลิงก์ไม่ได้: ' + e.message, true); }
  if (btn) { btn.innerHTML = label; btn.disabled = false; }
  return out;
}

function hubFilter() {
  const words = HUB.q.toLowerCase().split(/\s+/).filter(Boolean);
  let list = HUB.idx.items.filter(it =>
    (!HUB.th || it.th.includes(HUB.th)) && (!HUB.src || it.s === HUB.src) && (!HUB.ty || it.ty === HUB.ty) && (!HUB.lc || it.lc === HUB.lc)
    && (!HUB.cover || (HUB.cover === 'th' ? ['global', 'thailand', 'partial'].includes(it.cv) : it.cv === HUB.cover))
    && (HUB.old || !it.dp) && words.every(w => it._s.includes(w)));
  if (HUB.sort === 'new') list = [...list].sort((a, b) => (b.b || '9999') .localeCompare(a.b || '9999') || (b.a || '').localeCompare(a.a || ''));
  else if (HUB.sort === 'name') list = [...list].sort((a, b) => (a.s === 'other' ? 0 : 1) - (b.s === 'other' ? 0 : 1) || a.t.localeCompare(b.t));
  return list;
}

function hubCard(it) {
  const L = HUB_LC[it.lc];
  return `<a class="hub-card" href="#/hub/${encodeURIComponent(it.k)}">
    <div class="hub-top"><b>${esc(it.t)}</b>${it.dp ? '<span class="chip warn">เลิกใช้แล้ว</span>' : ''}</div>
    <div class="small muted">${esc(it.pr || '')}${it.pr ? ' · ' : ''}<span class="hub-src s-${it.s}">${esc(HUB_SRC[it.s])}</span></div>
    <div class="hub-meta tiny">${[it.ty === 'platform' ? 'แพลตฟอร์ม' : HUB.idx.meta.types[it.ty], hubYears(it), hubGsd(it.g), it.cd, HUB_COVER[it.cv]].filter(Boolean).map(esc).join(' · ')}</div>
    <div class="hub-th">${it.th.slice(0, 3).map(k => `<span>${esc(hubTheme(k)?.th || k)}</span>`).join('')}
      <span class="hub-lc" style="--c:${L[1]}" title="${esc(it.l || 'ไม่ระบุ')} — ${L[2]}">${L[0]}</span>${hubDot(it.u)}</div></a>`;
}

async function pageHub(key) {
  const v = $('#view');
  const ix = await hubLoad();
  if (key) return hubDetail(ix.items.find(it => it.k === key));
  const cnt = k => ix.items.filter(it => it.th.includes(k) && (HUB.old || !it.dp)).length;
  v.innerHTML = head('Data hub', 'แหล่งข้อมูลภูมิสารสนเทศ', `รายชื่อว่าใครมีข้อมูลอะไร อยู่ที่ไหน ${fmt(ix.meta.count, 0)} รายการ — แอปไม่ได้เก็บไฟล์ กดเข้าไปดูรายละเอียดแล้วไปโหลดที่ต้นทาง`,
    `<button class="ghost" id="hbChk" title="ตรวจว่าลิงก์ในผลค้นหาที่แสดงอยู่ยังเปิดได้">${IC.link}ตรวจลิงก์ในหน้านี้</button>`)
    + `<div class="card hub-filter">
      <input type="search" id="hbQ" placeholder="ค้นหา: ชื่อ, ผู้ผลิต, คำสำคัญ เช่น population, flood, NDVI, Sentinel, Thailand" value="${esc(HUB.q)}">
      <div class="hub-themes"><button class="chip ${HUB.th ? '' : 'on'}" data-th="">ทุกหมวด</button>${ix.meta.themes.map(t => `<button class="chip ${HUB.th === t.k ? 'on' : ''}" data-th="${t.k}" title="${esc(t.en)}">${esc(t.th)} <em>${cnt(t.k)}</em></button>`).join('')}</div>
      <div class="hub-sel">
        <label><span>แหล่ง</span><select id="hbSrc"><option value="">ทั้งหมด</option>${Object.entries(HUB_SRC).map(([k, t]) => `<option value="${k}" ${HUB.src === k ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
        <label><span>ชนิดข้อมูล</span><select id="hbTy"><option value="">ทั้งหมด</option>${Object.entries(ix.meta.types).map(([k, t]) => `<option value="${k}" ${HUB.ty === k ? 'selected' : ''}>${t}</option>`).join('')}</select></label>
        <label><span>เงื่อนไขการใช้</span><select id="hbLc"><option value="">ทั้งหมด</option>${Object.entries(HUB_LC).map(([k, t]) => `<option value="${k}" ${HUB.lc === k ? 'selected' : ''}>${t[0]} — ${t[2]}</option>`).join('')}</select></label>
        <label><span>ครอบคลุม</span><select id="hbCv"><option value="">ทั้งหมด</option><option value="th" ${HUB.cover === 'th' ? 'selected' : ''}>มีประเทศไทย</option><option value="thailand" ${HUB.cover === 'thailand' ? 'selected' : ''}>เฉพาะไทย/ภูมิภาค</option><option value="global" ${HUB.cover === 'global' ? 'selected' : ''}>ทั้งโลก</option></select></label>
        <label><span>เรียง</span><select id="hbSort"><option value="name" ${HUB.sort === 'name' ? 'selected' : ''}>ชื่อ (ผู้ผลิตโดยตรงก่อน)</option><option value="new" ${HUB.sort === 'new' ? 'selected' : ''}>ข้อมูลล่าสุดก่อน</option></select></label>
        <label class="row small"><input type="checkbox" id="hbOld" ${HUB.old ? 'checked' : ''}> แสดงชุดที่เลิกใช้แล้ว</label>
      </div></div>
    <div id="hbRes"></div>
    <div class="tiny muted hub-credit">${ix.meta.credits.map(esc).join('<br>')} · สร้างรายชื่อเมื่อ ${esc(ix.meta.built)}</div>`;
  const draw = () => {
    const list = hubFilter();
    $('#hbRes').innerHTML = `<div class="small muted" style="margin:4px 2px 10px">${fmt(list.length, 0)} รายการ</div>
      <div class="hub-grid">${list.slice(0, HUB.shown).map(hubCard).join('') || '<p class="muted">ไม่พบ — ลองคำค้นอื่น หรือล้างตัวกรอง</p>'}</div>
      ${list.length > HUB.shown ? `<div style="text-align:center;margin:14px"><button class="ghost" id="hbMore">แสดงเพิ่ม (${fmt(list.length - HUB.shown, 0)} เหลือ)</button></div>` : ''}`;
    $('#hbMore') && ($('#hbMore').onclick = () => { HUB.shown += 60; draw(); });
    return list;
  };
  let tq;
  $('#hbQ').oninput = () => { clearTimeout(tq); tq = setTimeout(() => { HUB.q = $('#hbQ').value.trim(); HUB.shown = 40; draw(); }, 200); };
  $$('[data-th]').forEach(b => b.onclick = () => { HUB.th = b.dataset.th; HUB.shown = 40; $$('[data-th]').forEach(x => x.classList.toggle('on', x === b)); draw(); });
  [['#hbSrc', 'src'], ['#hbTy', 'ty'], ['#hbLc', 'lc'], ['#hbCv', 'cover'], ['#hbSort', 'sort']].forEach(([id, k]) => $(id).onchange = () => { HUB[k] = $(id).value; HUB.shown = 40; draw(); });
  $('#hbOld').onchange = () => { HUB.old = $('#hbOld').checked; draw(); };
  $('#hbChk').onclick = async () => { const list = hubFilter().slice(0, HUB.shown); await hubCheck(list.map(it => it.u), $('#hbChk')); draw(); };
  draw();
}

async function hubDetail(it) {
  const v = $('#view');
  if (!it) { v.innerHTML = `<div class="note err">ไม่พบรายการนี้ใน Data hub</div><p><a href="#/hub">← กลับ Data hub</a></p>`; return; }
  const x = await hubDesc(it), d = x.desc || {}, LC = HUB_LC[it.lc];
  const links = [
    ['หน้าข้อมูล / ดาวน์โหลด', it.u, it.s === 'gee' ? 'หน้าแคตตาล็อกของ Earth Engine' : it.s === 'pc' ? 'หน้าแคตตาล็อกของ Planetary Computer' : 'เว็บไซต์ผู้ผลิต'],
    it.m && it.s !== 'other' && it.s !== 'platform' ? ['ข้อมูลประกอบ (STAC JSON)', it.m, 'ไฟล์ข้อมูลประกอบที่เครื่องอ่านได้'] : null,
    ...(x.providers || []).filter(p => p.url).map(p => [`ผู้ให้: ${p.name}`, p.url, (p.roles || []).join(', ')]),
    d.source_url && d.source_url !== it.u && d.source_url !== it.m ? ['ที่มาของคำอธิบาย', d.source_url, d.source] : null,
  ].filter((l, i, arr) => l && arr.findIndex(o => o && o[1] === l[1]) === i);      // ลิงก์ซ้ำ (เช่น ผู้ให้ = หน้าแคตตาล็อก) แสดงครั้งเดียว
  const facts = [
    ['รหัสชุดข้อมูล', it.id ? `<code>${esc(it.id)}</code>` : ''],
    ['แหล่ง', `${esc(it.p)}`],
    ['ผู้ผลิต / ผู้ให้บริการ', esc(it.pr || '')],
    ['ชนิดข้อมูล', esc(it.tr || HUB.idx.meta.types[it.ty] || '')],
    ['ช่วงเวลา', esc(hubYears(it))],
    ['ความถี่', esc(it.cd || '')],
    ['ความละเอียด', esc(hubGsd(it.g))],
    ['ครอบคลุม', esc(HUB_COVER[it.cv] || '') + (it.bb ? ` <span class="tiny muted mono">[${it.bb.map(n => fmt(n, 2)).join(', ')}]</span>` : '')],
    ['เงื่อนไขการใช้', `<span class="hub-lc" style="--c:${LC[1]}">${LC[0]}</span> ${esc(it.l || 'ไม่ระบุในรายชื่อ — ดูที่ต้นทาง')} <span class="tiny muted">· ${LC[2]}</span>`],
    ['หมวด', it.th.map(k => `<a class="chip" href="#/hub" data-goth="${k}">${esc(hubTheme(k)?.th || k)}</a>`).join(' ')],
    ['คำสำคัญ (จากต้นทาง)', esc((x.keywords || []).join(', '))],
    it.n ? ['หมายเหตุ', esc(it.n)] : null,
  ].filter(f => f && f[1]);
  v.innerHTML = `<p style="margin:0 0 10px"><a href="#/hub">← Data hub</a></p>`
    + head(esc(HUB_SRC[it.s]) + (it.dp ? ' · <span style="color:var(--butter)">เลิกใช้แล้ว</span>' : ''), esc(it.t), esc(it.sd || ''),
      `<button class="ghost" id="hdChk">${IC.link}ตรวจสอบลิงก์</button><a class="btn primary" href="${esc(it.u)}" target="_blank" rel="noopener noreferrer">${IC.download}ไปหน้าดาวน์โหลด</a>`)
    + `<div class="cols2 hub-detail">
      <div>
        <div class="card"><div class="card-head"><h2>คำอธิบาย</h2></div>
          ${d.about ? `<div class="note info small">${esc(d.about)}</div>` : ''}
          <div class="hub-desc">${d.text ? hubMd(d.text, d.fmt) : '<p class="muted">ยังไม่มีคำอธิบายจากต้นทาง — กด "ไปหน้าดาวน์โหลด" เพื่ออ่านที่เว็บผู้ผลิต</p>'}</div>
          ${d.text ? `<div class="tiny muted hub-attr">ที่มา: <a href="${esc(d.source_url)}" target="_blank" rel="noopener noreferrer">${esc(d.source)}</a> · ${esc(d.license_note || '')} · แอปไม่ได้เขียนหรือแก้ข้อความนี้</div>` : ''}
        </div>
        ${x.citation ? `<div class="card"><div class="card-head"><h2>การอ้างอิง (จากต้นทาง)</h2></div><div class="hub-desc small">${hubMd(x.citation, 'md')}</div></div>` : ''}
        ${x.terms ? `<div class="card"><div class="card-head"><h2>เงื่อนไขการใช้ (จากต้นทาง)</h2></div><div class="hub-desc small">${hubMd(x.terms, 'md')}</div></div>` : ''}
      </div>
      <div>
        <div class="card"><div class="card-head"><h2>ข้อมูลโดยย่อ</h2></div><table class="kv">${facts.map(([k, val]) => `<tr><td>${k}</td><td>${val}</td></tr>`).join('')}</table>
          ${it.bb && it.cv !== 'global' ? '<div id="hdMap" class="hub-map"></div>' : ''}</div>
        <div class="card"><div class="card-head"><h2>ลิงก์</h2></div>
          <div class="hub-links">${links.map(([t, u, sub]) => `<div class="hub-link" data-u="${esc(u)}"><div><a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(t)}</a>
            <div class="tiny muted">${esc(sub || '')}</div><div class="tiny mono muted hub-url">${esc(u)}</div></div><div class="hub-st">${hubStatus(u)}</div></div>`).join('')}</div>
          <div class="tiny muted" style="margin-top:8px">ตรวจผ่านตัวประมวลผลในเครื่องคุณ (อ่านแค่ส่วนหัว ไม่โหลดไฟล์) · บางเว็บปฏิเสธโปรแกรมตรวจแต่เปิดด้วยเบราว์เซอร์ได้</div></div>
      </div></div>`;
  $$('[data-goth]').forEach(a => a.onclick = () => { HUB.th = a.dataset.goth; HUB.shown = 40; });
  $('#hdChk').onclick = async () => { await hubCheck(links.map(l => l[1]), $('#hdChk')); $$('.hub-link').forEach(el => $('.hub-st', el).innerHTML = hubStatus(el.dataset.u)); };
  if ($('#hdMap')) {
    const mp = baseMap('hdMap'); maps.push(mp);
    const b = it.bb, r = L.rectangle([[b[1], b[0]], [b[3], b[2]]], { color: '#f7a8cc', weight: 2, fillOpacity: .12 }).addTo(mp);
    mp.fitBounds(r.getBounds(), { padding: [10, 10], maxZoom: 7 });
  }
}
function hubStatus(u) {
  const r = HUB.links[u];
  if (!r) return '<span class="tiny muted">ยังไม่ได้ตรวจ</span>';
  const t = { ok: 'ใช้ได้', warn: 'มีเงื่อนไข', bad: 'เสีย' }[r.state];
  return `<span class="hub-badge ${r.state}" title="${esc(hubLinkNote(r))}">${t}${r.status ? ' · ' + r.status : ''}</span>${r.note ? `<div class="tiny muted">${esc(r.note)}</div>` : ''}`;
}
