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
// ภาษาอังกฤษ: ชื่อหมวดมีในรายชื่อแล้ว (en) · ชนิดข้อมูล/เครดิตอยู่ในไฟล์รายชื่อเป็นไทย → ใช้ชุดนี้แทน
const HUB_EN = I18N.lang === 'en';
const hubThName = t => t ? (HUB_EN ? t.en : t.th) : '';
const HUB_TYPES_EN = { raster: 'Raster', timeseries: 'Raster time series', vector: 'Vector', table: 'Table/API', multidim: 'Multidimensional (NetCDF/Zarr)',
  pointcloud: 'Point cloud', service: 'Map service', scan: 'Scanned image/map' };
const hubType = k => k === 'platform' ? 'แพลตฟอร์ม' : (HUB_EN ? HUB_TYPES_EN[k] : HUB.idx.meta.types[k]) || k;
const HUB_CREDITS_EN = ['Collection lists: Planetary-Computer-Catalog and Earth-Engine-Catalog (giswqs on GitHub)',
  'Descriptions — Planetary Computer: Microsoft STAC API · Earth Engine: Google STAC catalog (earthengine-catalog)',
  'Open data portals (GISTDA, LDD, data.go.th, HDX): names, descriptions and files from each portal\'s CKAN API',
  'Wikipedia descriptions are used under CC BY-SA 4.0 — each entry links to the original article',
  'Check the license / terms of use of each dataset at the source before using or redistributing it'];
const hubLinkNote = r => `${r.status ? 'HTTP ' + r.status : 'ไม่ตอบ'}${r.note ? ' · ' + r.note : ''}${r.final ? ' → ' + r.final : ''} · ตรวจเมื่อ ${new Date(r.at).toLocaleString(I18N.locale())}`;
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
  const row = it => [it.t, it.id, it.p, (it.og || [it.pr]).filter(Boolean).join('; '), I18N.tr(hubType(it.ty)), it.tr, it.th.map(k => hubThName(hubTheme(k)) || k).join('; '),
    it.a, it.b, it.up, (it.g || []).join('–'), it.cd, tt(HUB_COVER[it.cv]), it.l, tt(HUB_LC[it.lc][0]), it.u, it.m, it.nr,
    tt(HUB_ST[st(it.u).state] || 'ยังไม่ได้ตรวจ'), st(it.u).status, st(it.u).at ? new Date(st(it.u).at).toISOString().slice(0, 16).replace('T', ' ') : '', it.ds];
  const tt = s => I18N.tr(String(s ?? ''));                  // ภาษาอังกฤษ → หัวคอลัมน์/สถานะเป็นอังกฤษด้วย
  cols.forEach((c, i) => { cols[i] = tt(c); });
  let lines = [cols.map(q).join(',')];
  if (withRes) {
    const get = await hubAllDesc();
    lines = [[...cols, ...['ไฟล์/บริการในชุด', 'รูปแบบ', 'ลิงก์ไฟล์', 'สถานะลิงก์ไฟล์'].map(tt)].map(q).join(',')];
    list.forEach(it => {
      const rs = get(it).resources || [];
      if (!rs.length) lines.push([...row(it), '', '', '', ''].map(q).join(','));
      rs.forEach(r => lines.push([...row(it), r.name, r.format, r.url, tt(HUB_ST[st(r.url).state] || 'ยังไม่ได้ตรวจ')].map(q).join(',')));
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

// ต้องมีบัญชี/โทเคนไหม — กติกาเดียวกับ app/hub_access.py (แก้ที่หนึ่งต้องแก้อีกที่)
const HUB_SAT = ['sentinel-2-l2a', 'landsat-c2-l2', 'sentinel-1-rtc', 'alos-palsar-mosaic', 'modis-13Q1-061', 'cop-dem-glo-30', 'esa-worldcover', 'io-lulc-annual-v02', 'jrc-gsw'];
const HUB_ACC_HOST = {
  'eogdata.mines.edu': ['account', 'บัญชี EOG (Colorado School of Mines)'], 'earthexplorer.usgs.gov': ['account', 'บัญชี USGS EROS'],
  'search.earthdata.nasa.gov': ['account', 'บัญชี NASA Earthdata'], 'oceancolor.gsfc.nasa.gov': ['account', 'บัญชี NASA Earthdata'],
  'search.asf.alaska.edu': ['account', 'บัญชี NASA Earthdata (ASF)'], 'dataspace.copernicus.eu': ['account', 'บัญชี Copernicus Data Space'],
  'marine.copernicus.eu': ['account', 'บัญชี Copernicus Marine'], 'www.emdat.be': ['account', 'บัญชี EM-DAT'],
  'globalfishingwatch.org': ['account', 'บัญชี Global Fishing Watch'], 'glad.earthengine.app': ['account', 'บัญชี Google Earth Engine (ไฟล์ดิบ) / ดูบนเว็บได้'],
  'firms.modaps.eosdis.nasa.gov': ['key', 'MAP_KEY ของ FIRMS (ขอฟรีด้วยอีเมล)'], 'opentopography.org': ['key', 'API key ของ OpenTopography (สมัครฟรี)'],
};
const HUB_ACC = { app: ['ดึงเข้าแอปได้', 'ok'], open: ['ไม่ต้องมีบัญชี', ''], account: ['ต้องมีบัญชี', 'warn'], key: ['ต้องใช้ API key', 'warn'] };
function hubAccess(it) {
  if (it.s === 'gee') return ['account', 'บัญชี Google Earth Engine (ลงทะเบียนฟรี) — ไม่มีไฟล์ตรง ต้องส่งออกจาก GEE เอง'];
  if (it.s === 'pc') return HUB_SAT.includes(it.k.split(':')[1]) ? ['app', 'ดึงเข้าแอปได้เลย (เครื่องมือ → ภาพดาวเทียม) ไม่ต้องมีบัญชี'] : ['open', 'ไม่ต้องมีบัญชี — Planetary Computer ออกโทเคนชั่วคราวให้อัตโนมัติ'];
  if (it.ni) return ['app', 'มีไฟล์ที่แอปนำเข้าคลังได้เอง'];
  let h = ''; try { h = new URL(it.u).host.toLowerCase(); } catch { }
  return HUB_ACC_HOST[h] || ['open', 'เปิด — ดาวน์โหลดจากหน้าเว็บได้โดยไม่ต้องล็อกอิน (ตรวจเงื่อนไขการใช้ก่อน)'];
}
const hubAccChip = it => { const [k, why] = hubAccess(it), [t, c] = HUB_ACC[k]; return `<span class="chip ${c}" title="${esc(why)}">${k === 'account' || k === 'key' ? IC.lock : ''}${t}</span>`; };

function hubCard(it) {
  const L = HUB_LC[it.lc];
  return `<a class="hub-card" href="#/hub/${encodeURIComponent(it.k)}">
    <div class="hub-top"><b translate="no">${esc(it.t)}</b>${it.dp ? '<span class="chip warn">เลิกใช้แล้ว</span>' : ''}${it.ni ? `<span class="chip ok" title="มีไฟล์ที่แอปนำเข้าคลังได้เอง">นำเข้าได้ ${it.ni}</span>` : hubAccChip(it)}</div>
    <div class="small muted"><span translate="no">${esc((it.og || [it.pr]).filter(Boolean).slice(0, 2).join(', '))}</span>${it.og || it.pr ? ' · ' : ''}<span class="hub-src s-${it.s}" translate="no">${esc(it.p)}</span></div>
    <div class="hub-meta tiny">${[hubType(it.ty), hubYears(it) || (it.y ? (it.y[0] === it.y[1] ? `ปี ${it.y[0]}` : `${it.y[0]}–${it.y[1]}`) : '') || (it.up ? 'อัปเดต ' + it.up : ''), hubGsd(it.g), it.cd, it.nr ? it.nr + ' ไฟล์/บริการ' : '', HUB_COVER[it.cv]].filter(Boolean).map(esc).join(' · ')}</div>
    <div class="hub-th">${it.th.slice(0, 3).map(k => `<span>${esc(hubThName(hubTheme(k)) || k)}</span>`).join('')}
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
      <div class="hub-themes"><button class="chip ${HUB.th ? '' : 'on'}" data-th="">ทุกหมวด</button>${ix.meta.themes.map(t => `<button class="chip ${HUB.th === t.k ? 'on' : ''}" data-th="${t.k}" ${HUB_EN ? '' : `title="${esc(t.en)}"`}>${esc(hubThName(t))} <em>${cnt(t.k)}</em></button>`).join('')}</div>
      <div class="hub-sel">
        <label class="hub-org"><span>หน่วยงาน</span><div class="row" style="flex-wrap:nowrap;gap:4px"><input type="text" id="hbOrg" list="hbOrgs" placeholder="พิมพ์ชื่อหน่วยงาน เช่น GISTDA, กรมพัฒนาที่ดิน, NASA" value="${esc(HUB.org)}"><button class="sm ghost" id="hbOrgX" title="ล้าง">${IC.x}</button></div>
          <datalist id="hbOrgs">${ix.meta.orgs.map(([o, n]) => `<option value="${esc(o)}">${n} ชุด</option>`).join('')}</datalist></label>
        <label><span>แหล่ง</span><select id="hbPlat"><option value="">ทั้งหมด</option>${ix.meta.platforms.map(([p, n]) => `<option value="${esc(p)}" ${HUB.plat === p ? 'selected' : ''} translate="no">${esc(p)} (${n})</option>`).join('')}</select></label>
        <label><span>ชนิดข้อมูล</span><select id="hbTy"><option value="">ทั้งหมด</option>${Object.keys(ix.meta.types).map(k => `<option value="${k}" ${HUB.ty === k ? 'selected' : ''}>${esc(hubType(k))}</option>`).join('')}</select></label>
        <label><span>เงื่อนไขการใช้</span><select id="hbLc"><option value="">ทั้งหมด</option>${Object.entries(HUB_LC).map(([k, t]) => `<option value="${k}" ${HUB.lc === k ? 'selected' : ''}>${t[0]} — ${t[2]}</option>`).join('')}</select></label>
        <label><span>ครอบคลุม</span><select id="hbCv"><option value="">ทั้งหมด</option><option value="th" ${HUB.cover === 'th' ? 'selected' : ''}>มีประเทศไทย</option><option value="thailand" ${HUB.cover === 'thailand' ? 'selected' : ''}>เฉพาะไทย/ภูมิภาค</option><option value="global" ${HUB.cover === 'global' ? 'selected' : ''}>ทั้งโลก</option></select></label>
        <label><span>สถานะลิงก์</span><select id="hbLink"><option value="">ทั้งหมด</option>${Object.entries(HUB_ST).map(([k, t]) => `<option value="${k}" ${HUB.link === k ? 'selected' : ''}>${t}</option>`).join('')}<option value="none" ${HUB.link === 'none' ? 'selected' : ''}>ยังไม่ได้ตรวจ</option></select></label>
        <label><span>เรียง</span><select id="hbSort"><option value="name" ${HUB.sort === 'name' ? 'selected' : ''}>ชื่อ (แหล่งไทย/ผู้ผลิตโดยตรงก่อน)</option><option value="new" ${HUB.sort === 'new' ? 'selected' : ''}>ข้อมูลล่าสุดก่อน</option></select></label>
        <label class="row small"><input type="checkbox" id="hbOld" ${HUB.old ? 'checked' : ''}> แสดงชุดที่เลิกใช้แล้ว</label>
      </div></div>
    <div id="hbRes"></div>
    <div class="tiny muted hub-credit">${(HUB_EN ? HUB_CREDITS_EN : ix.meta.credits).map(esc).join('<br>')} · สร้างรายชื่อเมื่อ ${esc(ix.meta.built)}</div>`;
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

// นำเข้าไฟล์จาก Data hub เข้าคลัง: ชื่อ · พื้นที่ศึกษา (ค่าเริ่มต้น = พื้นที่พื้นฐาน เช่น ประเทศไทย) · ประเภทค่า → งานดาวน์โหลดในตัวประมวลผล
async function hubImport(it, r) {
  let aois = [];
  try { aois = await api(ENGINE + '/api/aoi'); } catch (e) { return toast(e.message, true); }
  const base = aois.find(a => a.builtin);
  const nm = (r.name || r.url.split('/').pop()).replace(/\/content$/, '').replace(/\.(tiff?|geojson|json)$/i, '');
  const guess = /(^|[_\W])(ppp|pop|population|count)([_\W]|$)/i.test(nm) ? 'count' : /night|viirs|ndvi|density|_pd_|temperature|rain/i.test(nm) ? 'density' : '';
  const isTif = /\.tiff?(\/content)?(\?|$)/i.test(r.url);
  const o = await ui.open('นำเข้าคลังจาก Data hub', `<p class="small" translate="no"><b>${esc(it.t)}</b><br><span class="mono tiny">${esc(r.name || r.url)}</span></p>
    <label class="field"><span>ชื่อในคลัง</span><input type="text" id="hiName" value="${esc(nm)}"></label>
    <label class="field" style="margin-top:8px"><span>พื้นที่</span><select id="hiAoi"><option value="">ทั้งไฟล์ (ไม่ตัด)</option>${aoiOptions(aois, { sel: base ? base.id : '' })}</select></label>
    ${isTif ? `<label class="field" style="margin-top:8px"><span>ประเภทค่า</span><select id="hiVt"><option value="">ยังไม่ระบุ (ยืนยันทีหลังในหน้าชุดข้อมูล)</option>${['count', 'density', 'class'].map(k => `<option value="${k}" ${k === guess ? 'selected' : ''}>${esc(VT_SHORT[k] || k)}</option>`).join('')}</select>
      <span class="tiny muted">${guess ? 'แอปเดาจากชื่อไฟล์ — ตรวจให้ตรงความหมายของข้อมูล' : 'เช่น จำนวนคน/พิกเซล = จำนวนนับ · ดัชนี/ความหนาแน่น = ค่าต่อเนื่อง · รหัสชั้น = ชั้น'}</span></label>` : ''}
    <p class="tiny muted" style="margin-top:10px">ตัดตามกรอบพื้นที่ศึกษา · เซิร์ฟเวอร์ที่ไม่รองรับการอ่านบางส่วนจะดาวน์โหลดทั้งไฟล์ก่อน · ดูความคืบหน้าในแท็บงาน</p>`,
    [{ label: 'ยกเลิก', cls: 'ghost', value: () => null }, { label: 'นำเข้า', cls: 'primary', value: () => ({ name: $('#hiName').value.trim(), aoi_id: +$('#hiAoi').value || null, value_type: $('#hiVt')?.value || null }) }]);
  if (!o) return;
  try {
    const x = await api(ENGINE + '/api/hub/import', { json: { hub_key: it.k, url: r.url, ...o } });
    toast(x.message); if (typeof jobBadge === 'function') jobBadge();
  } catch (e) { toast(e.message, true); }
}

async function hubDetail(it) {
  const v = $('#view');
  if (!it) { v.innerHTML = `<div class="note err">ไม่พบรายการนี้ใน Data hub</div><p><a href="#/hub">← กลับ Data hub</a></p>`; return; }
  const x = await hubDesc(it), d = x.desc || {}, LC = HUB_LC[it.lc];
  const links = [
    ['หน้าข้อมูล / ดาวน์โหลด', it.u, it.s === 'gee' ? 'หน้าแคตตาล็อกของ Earth Engine' : it.s === 'pc' ? 'หน้าแคตตาล็อกของ Planetary Computer' : it.s === 'ckan' ? `หน้าชุดข้อมูลใน ${it.p}` : 'เว็บไซต์ผู้ผลิต'],
    x.source_page ? ['เว็บไซต์ของชุดข้อมูล', x.source_page, 'ลิงก์ที่ผู้ให้ข้อมูลระบุ'] : null,
    it.m && it.s !== 'other' && it.s !== 'platform' ? [it.s === 'ckan' ? 'ข้อมูลประกอบ (CKAN API JSON)' : 'ข้อมูลประกอบ (STAC JSON)', it.m, 'ไฟล์ข้อมูลประกอบที่เครื่องอ่านได้'] : null,
    ...(x.mirrors || []).map(m => [`มีในพอร์ทัลอื่นด้วย: ${m.platform}`, m.url, 'ชุดเดียวกันที่พอร์ทัลอื่นดึงไปแสดง']),
    ...(x.providers || []).filter(p => p.url).map(p => [`ผู้ให้: ${p.name}`, p.url, (p.roles || []).join(', ')]),
    d.source_url && d.source_url !== it.u && d.source_url !== it.m ? ['ที่มาของคำอธิบาย', d.source_url, d.source] : null,
  ].filter((l, i, arr) => l && arr.findIndex(o => o && o[1] === l[1]) === i);      // ลิงก์ซ้ำแสดงครั้งเดียว
  const res = x.resources || [];
  const orgs = (it.og || []).length ? it.og : (it.pr ? [it.pr] : []);
  const facts = [
    ['รหัสชุดข้อมูล', it.id ? `<code>${esc(it.id)}</code>` : ''],
    ['แหล่ง', `<span translate="no">${esc(it.p)}</span>`],
    ['หน่วยงาน', orgs.map(o => `<a class="chip" href="#/hub" data-goorg="${esc(o)}" translate="no">${esc(o)}</a>`).join(' ')],
    ['ชนิดข้อมูล', esc([hubType(it.ty), it.tr].filter(Boolean).join(' · '))],
    ['ช่วงเวลา', esc(hubYears(it))],
    ['อัปเดตล่าสุด', esc(it.up || '')],
    ['ความถี่', esc(it.cd || '')],
    ['ความละเอียด', esc(hubGsd(it.g))],
    ['ครอบคลุม', esc(HUB_COVER[it.cv] || '') + (it.bb ? ` <span class="tiny muted mono">[${it.bb.map(n => fmt(n, 2)).join(', ')}]</span>` : '')],
    ['เงื่อนไขการใช้', `<span class="hub-lc" style="--c:${LC[1]}">${LC[0]}</span> ${esc(it.l || 'ไม่ระบุในรายชื่อ — ดูที่ต้นทาง')} <span class="tiny muted">· ${LC[2]}</span>`],
    ['หมวด', it.th.map(k => `<a class="chip" href="#/hub" data-goth="${k}">${esc(hubThName(hubTheme(k)) || k)}</a>`).join(' ')],
    ['คำสำคัญ (จากต้นทาง)', `<span translate="no">${esc((x.keywords || []).join(', '))}</span>`],
    it.n ? ['หมายเหตุ', esc(it.n)] : null,
  ].filter(f => f && f[1]);
  const linkRow = (t, u, sub, raw, act) => `<div class="hub-link"><div><a href="${esc(u)}" target="_blank" rel="noopener noreferrer"${raw ? ' translate="no"' : ''}>${esc(t)}</a>
    ${sub ? `<div class="tiny muted">${esc(sub)}</div>` : ''}<div class="tiny mono muted hub-url">${esc(u)}</div></div><div class="hub-st">${act || ''}${hubStatus(u)}</div></div>`;
  // ไฟล์ที่แอปนำเข้าเองได้ (GeoTIFF / GeoJSON ลิงก์ตรง) → ปุ่ม "นำเข้าคลัง" (ตัดตามพื้นที่ศึกษา) · ไฟล์อื่น = ลิงก์ดาวน์โหลดตรง
  const canImport = r => !r.key && /\.(tiff?)(\/content)?(\?|$)|\.(geo)?json(\?|$)/i.test(r.url || '');
  const nImp = res.filter(canImport).length;
  v.innerHTML = `<p style="margin:0 0 10px"><a href="#/hub">← Data hub</a></p>`
    + head(`<span translate="no">${esc(it.p)}</span>` + (it.dp ? ' · <span style="color:var(--butter)">เลิกใช้แล้ว</span>' : ''), `<span translate="no">${esc(it.t)}</span>`, `<span translate="no">${esc(it.sd || '')}</span>`,
      `<a class="btn primary" href="${esc(it.u)}" target="_blank" rel="noopener noreferrer">${IC.download}ไปหน้าดาวน์โหลด</a>`)
    + (() => { const [k, why] = hubAccess(it), sat = it.s === 'pc' && HUB_SAT.includes(it.k.split(':')[1]);
      return `<div class="note ${k === 'account' || k === 'key' ? 'warn' : 'info'} small" style="margin-bottom:12px">${hubAccChip(it)} ${esc(why)}${sat ? ` · <a href="#/tools?t=sat" onclick="TOOLS.sat={collection:'${it.k.split(':')[1]}',zoom:9,cloud_max:20}">เปิดเครื่องมือดึงภาพ →</a>` : ''}</div>`; })()
    + `<div class="cols2 hub-detail">
      <div>
        <div class="card"><div class="card-head"><h2>คำอธิบาย</h2></div>
          ${d.about ? `<div class="note info small">${esc(d.about)}</div>` : ''}
          <div class="hub-desc">${d.text ? hubMd(d.text, d.fmt) : '<p class="muted">ยังไม่มีคำอธิบายจากต้นทาง — กด "ไปหน้าดาวน์โหลด" เพื่ออ่านที่เว็บผู้ผลิต</p>'}</div>
          ${d.text ? `<div class="tiny muted hub-attr">ที่มา: <a href="${esc(d.source_url)}" target="_blank" rel="noopener noreferrer">${esc(d.source)}</a> · ${esc(d.license_note || '')} · แอปไม่ได้เขียนหรือแก้ข้อความนี้</div>` : ''}
        </div>
        ${(x.variables || []).length ? `<div class="card"><div class="card-head"><h2>ตัวแปร / แบนด์</h2><span class="chip">${x.variables.length}</span></div>
          <div class="tiny muted" style="margin-bottom:6px">จาก metadata ต้นทาง · ค่าจริง = ค่าในไฟล์ × scale + offset</div>
          <table class="small hub-vars"><thead><tr><th>ชื่อ</th><th>ความหมาย</th><th>หน่วย</th><th>scale / offset</th></tr></thead><tbody>${x.variables.slice(0, 40).map(v => `<tr><td class="mono" translate="no">${esc(v.name)}${v.field ? ' <span class="tiny muted">(ฟิลด์)</span>' : ''}</td>
            <td translate="no">${esc(v.desc || '')}${v.classes ? `<div class="tiny muted">${esc(v.classes)}</div>` : ''}</td><td translate="no">${esc(v.unit || '')}</td>
            <td class="mono">${v.scale != null ? '× ' + esc(v.scale) : ''}${v.offset ? ' + ' + esc(v.offset) : ''}</td></tr>`).join('')}</tbody></table></div>` : ''}
        ${it.yl ? `<div class="card"><div class="card-head"><h2>ปีที่มีไฟล์</h2><span class="chip">${it.yl.length} ปี</span></div><div class="small mono">${it.yl.join(' · ')}</div></div>` : ''}
        ${res.length ? `<div class="card"><div class="card-head"><h2>ไฟล์ / บริการในชุดนี้ <span class="muted small">${fmt(it.nr || res.length, 0)} รายการ${it.nr > res.length ? ` (แสดง ${res.length})` : ''}</span></h2></div>
          ${nImp ? `<div class="note info small" style="margin-top:0">นำเข้าคลังได้ ${fmt(nImp, 0)} ไฟล์ — กด "นำเข้าคลัง" แล้วเลือกพื้นที่ศึกษา แอปจะดาวน์โหลดเฉพาะส่วนที่ต้องการ (ถ้าเซิร์ฟเวอร์รองรับ) ตัดตามพื้นที่ แล้วเพิ่มเข้าคลังให้</div>` : ''}
          <div class="hub-links">${res.map((r, i) => linkRow(r.name || r.url.split('/').pop() || r.url, r.url, [r.format ? 'รูปแบบ: ' + r.format : '', r.size ? fmt(r.size / 1e6, 1) + ' MB' : '', r.key ? 'ต้องใช้ API key ของคุณเอง — แอปซ่อนคีย์ที่ติดมากับลิงก์ต้นทางไว้ ({YOUR_API_KEY})' : ''].filter(Boolean).join(' · '), true,
            canImport(r) ? `<button class="sm primary" data-imp="${i}">${IC.download}นำเข้าคลัง</button>` : '')).join('')}</div></div>` : ''}
        ${res.some(r => /\.zip(\?|$)/i.test(r.url || '')) && nImp < 5 ? `<div class="card" id="hbCard"><div class="card-head"><h2>ไฟล์ย่อยจากโฟลเดอร์ต้นทาง</h2><span class="tiny muted">ต้นทางลงไว้เป็น ZIP ก้อนใหญ่ — ถ้าเซิร์ฟเวอร์เปิดรายชื่อโฟลเดอร์ เลือกนำเข้าทีละไฟล์ได้</span></div>
          <div class="row"><input type="text" id="hbYears" placeholder="ปี เช่น 2015,2020" style="width:150px"><input type="text" id="hbMatch" placeholder="คำในชื่อไฟล์ เช่น _t_60_,_t_65_" style="flex:1"><input type="text" id="hbMust" placeholder="ต้องมี เช่น 1km" style="width:120px"><button class="sm" id="hbGo">ดูไฟล์</button></div>
          <div id="hbOut" class="small muted" style="margin-top:8px">กด "ดูไฟล์" (ไม่ใส่ปี = ดู ZIP ล่าสุดเป็นตัวอย่าง)</div></div>` : ''}
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
  $$('[data-imp]').forEach(b => b.onclick = () => hubImport(it, res[+b.dataset.imp]));
  if ($('#hbGo')) $('#hbGo').onclick = async () => {               // ไฟล์ย่อยในโฟลเดอร์ต้นทาง (แอปเปิดรายชื่อโฟลเดอร์ให้)
    const out = $('#hbOut'); out.textContent = 'กำลังเปิดโฟลเดอร์ต้นทาง…';
    try {
      const q = new URLSearchParams({ key: it.k, years: $('#hbYears').value.trim(), match: $('#hbMatch').value.trim(), must: $('#hbMust').value.trim() });
      const r = await api(`${ENGINE}/api/hub/browse?${q}`);
      if (!r.total) { out.innerHTML = `ไม่พบไฟล์${r.browsed ? ` (ดู ${r.browsed.zips_checked} โฟลเดอร์)` : ''} — ลองคำอื่น หรือเว้นช่องคำว่างเพื่อดูชนิดไฟล์ทั้งหมด`; return; }
      out.innerHTML = `<div class="tiny muted">${fmt(r.total, 0)} ไฟล์${r.total > r.files.length ? ` (แสดง ${r.files.length})` : ''} · ${fmt(r.files.reduce((a, f) => a + (f.size_mb || 0), 0), 0)} MB${r.browsed?.note ? ' · ' + esc(r.browsed.note) : ''}
          ${!$('#hbMatch').value.trim() && r.patterns.length ? '<br>ชนิดไฟล์: ' + r.patterns.slice(0, 40).map(p => `<code>${esc(p.pattern)}</code>`).join(' ') : ''}</div>
        <div class="hub-links">${r.files.slice(0, 200).map((f, i) => linkRow(f.name, f.url, [f.year, f.size_mb ? fmt(f.size_mb, 1) + ' MB' : ''].filter(Boolean).join(' · '), true,
          `<button class="sm primary" data-hb="${i}">${IC.download}นำเข้าคลัง</button>`)).join('')}</div>`;
      $$('[data-hb]').forEach(b => b.onclick = () => hubImport(it, r.files[+b.dataset.hb]));
    } catch (e) { out.innerHTML = `<span class="note err">${esc(e.message)}</span>`; }
  };
  $$('[data-goth]').forEach(a => a.onclick = () => { HUB.th = a.dataset.goth; HUB.shown = 40; });
  $$('[data-goorg]').forEach(a => a.onclick = () => { HUB.org = a.dataset.goorg; HUB.shown = 40; });
  if ($('#hdMap')) {
    const mp = baseMap('hdMap'); maps.push(mp);
    const b = it.bb, r = L.rectangle([[b[1], b[0]], [b[3], b[2]]], { color: '#f7a8cc', weight: 2, fillOpacity: .12 }).addTo(mp);
    mp.fitBounds(r.getBounds(), { padding: [10, 10], maxZoom: 7 });
  }
}
