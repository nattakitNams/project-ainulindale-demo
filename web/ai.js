// ผู้ช่วย AI — ขั้นที่ 1: เปิด/ปิดในหน้า "ระบบ" · ช่องแชตลอยมุมขวาล่าง (ย่อเป็นปุ่มได้) · ล็อกอินด้วย API key ในช่องแชต
// key ส่งไปเก็บเข้ารหัสในตัวประมวลผลครั้งเดียวตอนเชื่อมต่อ — หน้าเว็บไม่เก็บ/ไม่ได้รับค่ากลับ · ประวัติแชตเก็บในเบราว์เซอร์นี้
const AIDock = (() => {
  const HKEY = 'ainu-ai-chat', OKEY = 'ainu-ai-open', CKEY = 'ainu-ai-chat-id';
  let st = null, busy = false, hist = [], plan = null, cid = null;
  const newCid = () => 'c' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  const ls = { get: (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } }, set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { } } };
  // markdown อย่างง่าย + ลิงก์คลิกได้ ([ชื่อ](url) และ URL เปล่า) — เปิดแท็บใหม่ · รับเฉพาะ http(s)
  const md = s => esc(s).replace(/```([\s\S]*?)```/g, '<pre>$1</pre>')
    .replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
    .replace(/(^|[\s(>])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" target="_blank" rel="noopener noreferrer">$2</a>')
    .replace(/`([^`\n]+)`/g, '<code>$1</code>').replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>');

  async function refresh() { st = await api(ENGINE + '/api/ai'); return st; }

  async function init() {
    try { await refresh(); } catch { return; }
    hist = ls.get(HKEY, []);
    cid = ls.get(CKEY, null) || newCid(); ls.set(CKEY, cid);
    try { plan = (await api(`${ENGINE}/api/ai/plan?chat=${cid}`)).plan; } catch { }
    render();
  }

  function dock() {
    let d = document.getElementById('aiDock');
    if (!d) { d = document.createElement('div'); d.id = 'aiDock'; document.body.appendChild(d); }
    return d;
  }

  function render() {
    const d = dock();
    if (!st || !st.enabled) { d.innerHTML = ''; d.className = ''; return; }
    const open = ls.get(OKEY, true);
    d.className = open ? 'open' : '';
    if (!open) {
      d.innerHTML = `<button class="ai-fab" title="เปิดผู้ช่วย AI">${IC.chat}</button>`;
      d.querySelector('.ai-fab').onclick = () => { ls.set(OKEY, true); render(); };
      return;
    }
    d.innerHTML = `<div class="ai-panel">
      <div class="ai-head"><b>ผู้ช่วย AI</b>${st.connected ? `<span class="chip" translate="no" title="${esc(st.provider_label)}">${esc(st.model || '')}</span>` : ''}
        <span class="spacer"></span>
        ${st.connected ? `<button class="ghost sm" data-a="clear" title="ล้างบทสนทนา">${IC.trash}</button><button class="ghost sm" data-a="set" title="ตั้งค่า (รุ่น / ออกจากระบบ)">${IC.gear}</button>` : ''}
        <button class="ghost sm" data-a="min" title="ซ่อน">${IC.minus}</button></div>
      <div class="ai-body"></div></div>`;
    d.querySelector('[data-a=min]').onclick = () => { ls.set(OKEY, false); render(); };
    if (st.connected) {
      d.querySelector('[data-a=clear]').onclick = () => { hist = []; ls.set(HKEY, hist); cid = newCid(); ls.set(CKEY, cid); plan = null; chatView(); };
      d.querySelector('[data-a=set]').onclick = () => { location.hash = '#/system'; };
      chatView();
    } else loginView();
  }

  // ---------- ล็อกอิน (อยู่ในช่องแชต) ----------
  function loginView() {
    const b = dock().querySelector('.ai-body');
    b.innerHTML = `<div class="ai-login">
      <p class="small" style="margin-top:0">เชื่อมต่อผู้ให้บริการ AI ด้วย API key ของคุณ</p>
      <label class="field"><span>ผู้ให้บริการ</span><select id="aiProv">${st.providers.map(p => `<option value="${p.id}">${esc(p.label)}</option>`).join('')}</select></label>
      <label class="field aiBase hide"><span>ที่อยู่เซิร์ฟเวอร์</span><input type="text" id="aiBase" placeholder="http://localhost:11434/v1" autocomplete="off" spellcheck="false"></label>
      <label class="field"><span>API key <span class="aiOpt tiny muted hide">(ไม่ต้องใส่ถ้าเซิร์ฟเวอร์ไม่ใช้)</span></span><input type="password" id="aiKey" autocomplete="off" spellcheck="false" placeholder="วาง key ที่นี่"></label>
      <div class="tiny" id="aiKeyUrl"></div>
      <button class="primary" id="aiGo" style="margin-top:10px;width:100%">เชื่อมต่อ</button>
      <div class="tiny muted ai-note" style="margin-top:10px;line-height:1.6">${IC.lock}key ถูกเข้ารหัสเก็บในตัวประมวลผลบนเครื่องนี้ (Windows DPAPI) — ไม่เก็บในเบราว์เซอร์ ไม่ขึ้นเว็บ<br>
        ส่งให้ AI: ข้อความแชต + ชื่อ/ประเภทของชุดข้อมูลในคลัง (ไม่ส่งไฟล์ข้อมูล)<br>
        ใช้บัญชีแบบรายเดือน (ChatGPT Plus / Claude Pro) แทน API key ไม่ได้</div></div>`;
    const sync = () => {
      const p = st.providers.find(x => x.id === $('#aiProv').value);
      b.querySelector('.aiBase').classList.toggle('hide', p.id !== 'compat');
      b.querySelector('.aiOpt').classList.toggle('hide', !p.key_optional);
      $('#aiKeyUrl').innerHTML = p.key_url ? `<a href="${p.key_url}" target="_blank" rel="noopener" class="ai-link">ขอ API key ที่นี่ ${IC.ext}</a>` : 'Ollama: <span class="mono">http://localhost:11434/v1</span> · OpenRouter: <span class="mono">https://openrouter.ai/api/v1</span>';
    };
    $('#aiProv').onchange = sync; sync();
    $('#aiGo').onclick = async () => {
      const btn = $('#aiGo'); btn.disabled = true; btn.textContent = 'กำลังตรวจ key…';
      try {
        st = await api(ENGINE + '/api/ai/login', { json: { provider: $('#aiProv').value, api_key: $('#aiKey').value, base_url: $('#aiBase').value } });
        $('#aiKey').value = '';
        toast(`เชื่อมต่อแล้ว · ${st.model}`);
        render();
      } catch (e) { toast(e.message, true); btn.disabled = false; btn.textContent = 'เชื่อมต่อ'; }
    };
  }

  // ---------- แชต ----------
  function chatView() {
    const b = dock().querySelector('.ai-body');
    b.innerHTML = `<div class="ai-msgs"></div>
      <div class="ai-input"><textarea id="aiTxt" rows="2" placeholder="ถามอะไรก็ได้เกี่ยวกับข้อมูลหรือการใช้แอป… (Enter ส่ง · Shift+Enter ขึ้นบรรทัด)"></textarea><button class="primary" id="aiSend" title="ส่ง">${IC.send}</button></div>`;
    drawMsgs();
    const send = async () => {
      const t = $('#aiTxt').value.trim();
      if (!t || busy) return;
      hist.push({ role: 'user', content: t }); $('#aiTxt').value = ''; busy = true; drawMsgs();
      try {
        const r = await api(ENGINE + '/api/ai/chat', { json: { messages: hist.map(x => ({ role: x.role, content: x.content })), page: location.hash || '#/', chat_id: cid } });
        if (r.plan !== undefined) plan = r.plan;
        hist.push({ role: 'assistant', content: r.reply, used: r.used || [], note: r.note, docs: r.docs || [], usage: r.usage,
          proposals: (r.proposals || []).map(p => ({ ...p, state: 'pending' })) });
      } catch (e) { hist.push({ role: 'error', content: e.message }); }
      busy = false; save(); drawMsgs();
    };
    $('#aiSend').onclick = send;
    $('#aiTxt').onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); } };
    $('#aiTxt').focus();
  }

  const save = () => ls.set(HKEY, hist.slice(-60));

  // การ์ดข้อเสนอ: AI เสนอ → ผู้ใช้ตรวจ (ขนาด/คำเตือน) → กดยืนยันจึงรัน · ข้อเสนอใช้ได้ครั้งเดียว (หมดอายุ 30 นาที)
  const KIND_TH = { set_value_type: 'ตั้งประเภทค่า', create_aoi: 'สร้างพื้นที่ศึกษา', run_job: 'รันงาน', create_report: 'ทำรายงาน', download: 'ดาวน์โหลดเข้าคลัง',
    create_folders: 'สร้างโฟลเดอร์', move_folder: 'ย้ายเข้าโฟลเดอร์', recipe: 'สูตรงาน (รันเองทุกขั้น)' };
  const STEP_TH = { satellite: 'ดึงภาพดาวเทียม', download: 'นำเข้าจาก Data hub', calc: 'สูตรคำนวณ', trend: 'อนุกรมเวลา', change: 'เปรียบเทียบ', bivariate: 'ไบแวเรียต',
    resample: 'ปรับความละเอียด', rasterize: 'แปลงเป็นราสเตอร์', hex: 'หกเหลี่ยม', hexbiv: 'ไบแวเรียตหกเหลี่ยม', vgrid: 'กริดเวกเตอร์', mosaic: 'รวมราสเตอร์', vmerge: 'รวมเวกเตอร์', stats: 'สถิติความสัมพันธ์' };
  const ST_IC = { todo: '○', running: '◐', done: '●', failed: '✕', skipped: '–' };

  // การ์ดดาวน์โหลดจาก Data hub: ไฟล์ · ปี · ขนาด · พื้นที่ · ประเภทค่า (เลือกได้) · สัญญาอนุญาต · แหล่ง
  function dlCard(p) {
    const a = p.args, f = a.file || {}, e = p.estimate || {};
    const vt = p.state === 'pending'
      ? `<select data-k="value_type"><option value="">ยังไม่ระบุ (ยืนยันทีหลัง)</option>${['count', 'density', 'class'].map(k => `<option value="${k}" ${a.value_type === k ? 'selected' : ''}>${VT_TH[k]}</option>`).join('')}</select>`
      : (VT_TH[a.value_type] || 'ยังไม่ระบุ');
    const rows = [['ชุดข้อมูล', `<span translate="no">${esc(a.title || '')}</span>`], ['ไฟล์', `<span translate="no">${esc(f.name || '')}</span>${f.year ? ` · ปี ${f.year}` : ''}${f.size_mb ? ` · ${fmt(f.size_mb, 1)} MB` : ''}`],
      ['พื้นที่', a.aoi_name ? `ตัดตามกรอบ <span translate="no">${esc(a.aoi_name)}</span>` : 'ทั้งไฟล์'],
      ['ประเภทค่า', `<span class="ai-res">${vt}</span>`], ['ชื่อในคลัง', `<span translate="no">${esc(a.name || '')}</span>`]];
    if (e.ok) rows.push(['ข้อมูลไฟล์', `${esc(e.crs || '')}${e.size?.[0] ? ` · ${fmt(e.size[0], 0)} × ${fmt(e.size[1], 0)} พิกเซลทั้งไฟล์` : ''}${e.note ? `<br><span class="warn-t">${esc(e.note)}</span>` : ''}`]);
    else if (e.error) rows.push(['ข้อมูลไฟล์', `<span class="warn-t">เปิดหัวไฟล์ไม่ได้: ${esc(e.error)}</span>`]);
    if (a.license) rows.push(['สัญญาอนุญาต', esc(a.license)]);
    if (a.source) rows.push(['แหล่ง', `<a href="${esc(a.source)}" target="_blank" rel="noopener">เปิดหน้าต้นทาง</a>`]);
    return `<table class="kv ai-kv">${rows.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('')}</table>`;
  }
  const isBiv = p => p.action === 'run_job' && ['bivariate', 'hexbiv'].includes(p.args?.kind);
  const METHODS = [['quantile', 'ควอนไทล์'], ['equal', 'ช่วงเท่ากัน'], ['breaks', 'กำหนดเกณฑ์เอง'], ['degurba', 'DEGURBA']];

  const VT_TH = { count: 'จำนวนนับ', density: 'ค่าต่อเนื่อง', class: 'ชั้น' };
  const METRIC_TH = { density: 'ความหนาแน่น (ต่อ ตร.กม.)', per_pixel: 'ค่าต่อพิกเซล', value: 'ค่าตามไฟล์' };
  const dsOf = (p, id) => (p.info?.datasets || {})[String(id)] || {};
  const dsLabel = (p, id) => { const d = dsOf(p, id); return `#${id} ${d.name || ''}`; };

  // แก้ค่าไบแวเรียตในการ์ดก่อนยืนยัน (ชื่อแกน / ค่าที่ใช้ / จำนวนคลาส / วิธีแบ่ง / เกณฑ์ / ลำดับ) — ค่าที่ผู้ใช้แก้ส่งไปตรวจซ้ำตอนรัน
  function axisEditor(p) {
    const P = p.args.params;
    return `<div class="ai-edit">${['x', 'y'].map(ax => { const c = P[ax] || {}, d = dsOf(p, c.dataset_id), cnt = d.value_type === 'count'; return `<div class="ai-ax"><b>แกน ${ax.toUpperCase()}</b>
      <div class="tiny muted ai-ds"><span translate="no">${esc(dsLabel(p, c.dataset_id))}</span>${d.value_type ? ' · ' + VT_TH[d.value_type] : ''}</div>
      <input data-ax="${ax}" data-k="label" value="${esc(c.label || '')}" placeholder="ชื่อแกน">
      <label class="tiny">ค่าที่ใช้ ${cnt ? `<select data-ax="${ax}" data-k="metric">${['density', 'per_pixel'].map(k => `<option value="${k}" ${k === (c.metric || 'density') ? 'selected' : ''}>${METRIC_TH[k]}</option>`).join('')}</select>` : `<b>${METRIC_TH.value}</b>`}</label>
      <div class="row" style="gap:4px"><select data-ax="${ax}" data-k="n">${[1, 2, 3, 4, 5].map(n => `<option ${n == (c.n || 3) ? 'selected' : ''}>${n}</option>`).join('')}</select>
        <select data-ax="${ax}" data-k="method">${METHODS.map(([k, t]) => `<option value="${k}" ${k === (c.method || 'quantile') ? 'selected' : ''}>${t}</option>`).join('')}</select></div>
      ${c.method === 'breaks' ? `<input data-ax="${ax}" data-k="breaks" value="${esc((c.breaks || []).join(', '))}" placeholder="เกณฑ์ เช่น 300, 1500">` : ''}
      <label class="tiny"><input type="checkbox" data-ax="${ax}" data-k="order" ${c.order === 'classify_first' ? 'checked' : ''}> จัดชั้นก่อนแล้ว majority</label></div>`; }).join('')}</div>`;
  }

  // ค่าที่ตั้งเป็นตารางอ่านง่าย (แทน JSON) — ชื่อชุดข้อมูล/พื้นที่ศึกษาจาก info ที่เซิร์ฟเวอร์แนบมา
  const JOB_TH = { bivariate: 'ไบแวเรียต (กริด)', hexbiv: 'ไบแวเรียตหกเหลี่ยม', resample: 'ปรับความละเอียด / ตัดพื้นที่', rasterize: 'แปลงเวกเตอร์เป็นราสเตอร์',
    hex: 'แปลงเป็นหกเหลี่ยม', vgrid: 'กริดเวกเตอร์', change: 'เปรียบเทียบ 2 ช่วงเวลา', download: 'ดาวน์โหลดจากลิงก์' };
  const MODE_TH = { presence: 'มี / ไม่มี (1 / 0)', attribute: 'ค่าจากฟิลด์', majority: 'ค่าจากฟิลด์ที่กินพื้นที่มากสุด', fraction: 'สัดส่วนพื้นที่ (0–1)', diff: 'ผลต่าง', pct: 'ร้อยละที่เปลี่ยน', transition: 'การเปลี่ยนชั้น' };
  function summary(p) {
    const P = p.args.params, rows = [['งาน', JOB_TH[p.args.kind] || p.args.kind]];
    if (P.purpose) rows.push(['วัตถุประสงค์', `<span translate="no">${esc(P.purpose)}</span>`]);
    const aoiName = id => (p.info?.aois || {})[String(id)] || `#${id}`;
    const resName = v => (p.res_options || []).find(o => String(o.value) === String(v))?.label || `${v}`;
    const axis = ax => {
      const c = P[ax]; if (!c) return;
      const d = dsOf(p, c.dataset_id), m = METHODS.find(x => x[0] === (c.method || 'quantile'))?.[1] || c.method;
      rows.push([`แกน ${ax.toUpperCase()}`, `<span translate="no">${esc(dsLabel(p, c.dataset_id))}</span>${d.value_type ? ` <span class="muted">(${VT_TH[d.value_type]})</span>` : ''}${c.label ? `<br>ชื่อแกน: <span translate="no">${esc(c.label)}</span>` : ''}
        <br>ค่าที่ใช้: ${METRIC_TH[d.value_type === 'count' ? (c.metric || 'density') : 'value']} · ${c.n || 3} คลาส · ${esc(m)}${c.method === 'breaks' && c.breaks?.length ? ` (${c.breaks.join(', ')})` : ''}${c.order === 'classify_first' ? ' · จัดชั้นก่อนแล้ว majority' : ''}${c.field ? ` · คอลัมน์ ${esc(c.field)}` : ''}`]);
    };
    axis('x'); axis('y');
    if (P.dataset_id) rows.push(['ชุดข้อมูล', `<span translate="no">${esc(dsLabel(p, P.dataset_id))}</span>`]);
    if (P.dataset_ids) rows.push(['ชุดข้อมูล', `<span translate="no">${P.dataset_ids.map(i => esc(dsLabel(p, i))).join('<br>')}</span>`]);
    if (P.a_id) rows.push(['ก่อน → หลัง', `<span translate="no">${esc(dsLabel(p, P.a_id))} → ${esc(dsLabel(p, P.b_id))}</span>`]);
    if (P.mode) rows.push(['วิธี', MODE_TH[P.mode] || P.mode]);
    if (P.field) rows.push(['ฟิลด์', `<span translate="no">${esc(P.field)}</span>`]);
    if (P.grid) rows.push(['กริด', P.grid === 'ref' ? `ตรงกับ <span translate="no">${esc(dsLabel(p, P.ref_dataset_id))}</span>` : `กำหนดเอง${P.crs ? ' · ' + esc(P.crs) : ''}`]);
    if (P.target_res) rows.push(['ความละเอียด', esc(resName(P.target_res))]);
    if (P.size_km) rows.push(['ขนาดหกเหลี่ยม', `${fmt(P.size_km, 3)} กม.`]);
    rows.push(['พื้นที่', P.aoi_id ? `<span translate="no">${esc(aoiName(P.aoi_id))}</span>` : 'ทั้งขอบเขตข้อมูล']);
    if (P.extent_aoi_id || P.extent_dataset_id) rows.push(['ขอบเขตผลลัพธ์', `<span translate="no">${esc(P.extent_aoi_id ? aoiName(P.extent_aoi_id) : dsLabel(p, P.extent_dataset_id))}</span>`]);
    if (P.palette) rows.push(['พาเลท', esc(String(P.palette).replace(/^b:/, ''))]);
    if (P.highlight?.length) rows.push(['เขตเน้น', `รหัส ${P.highlight.join(', ')}`]);
    if (P.name) rows.push(['ชื่อผลลัพธ์', `<span translate="no">${esc(P.name)}</span>`]);
    return `<table class="kv ai-kv">${rows.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('')}</table>`;
  }

  function propCard(p, mi, pi) {
    const e = p.estimate || {};
    const est = p.action === 'run_job'
      ? (p.edited ? '<div class="tiny warn-t">แก้ค่าแล้ว — ตรวจอีกครั้งตอนรัน</div>' : e.ok ? `<div class="tiny">${esc(e.resolution || '')}${e.size?.[0] ? ` · ${fmt(e.size[0], 0)} × ${fmt(e.size[1], 0)} พิกเซล` : ''}${e.aoi ? ' · ' + esc(e.aoi) : ''}</div>`
        + (e.warnings || []).map(w => `<div class="tiny warn-t">${esc(w)}</div>`).join('')
        : `<div class="tiny warn-t">ตรวจไม่ผ่านตอนเสนอ: ${esc(e.error || '?')} — จะตรวจอีกครั้งตอนรัน</div>`)
      : p.action === 'create_report' && e.layers ? `<div class="tiny">${esc(e.template)} · <span translate="no">${esc(e.layers.join(', '))}</span></div>`
      : p.action === 'download' ? dlCard(p)
      : p.action === 'create_folders' ? `<div class="tiny">${(p.args.paths || []).map(x => `${IC.folder}<span translate="no">${esc(x)}</span>${(p.args.new || []).includes(x) ? '' : ' <span class="muted">(มีแล้ว)</span>'}`).join('<br>')}</div>`
      : p.action === 'recipe' ? `<ol class="ai-steps tiny">${(p.args.steps || []).map(st => `<li><b translate="no">${esc(st.title)}</b> <span class="muted">${STEP_TH[st.kind] || st.kind}</span>${JSON.stringify(st.params).includes('"$s') ? ' <span class="muted">· ใช้ผลขั้นก่อน</span>' : ''}</li>`).join('')}</ol>
          <div class="tiny muted">ยืนยันครั้งเดียว — แอปรันทุกขั้นเองโดยไม่ใช้ผู้ช่วยระหว่างทาง (ประหยัดโทเคน) · ขั้นไหนพลาดจะหยุดแล้วแจ้ง</div>`
      : p.action === 'move_folder' ? `<div class="tiny"><span translate="no">${(p.args.names || []).map(esc).join(', ')}</span> → ${IC.folder}<span translate="no">${esc(p.args.folder)}</span></div>` : '';
    const P = p.args?.params || {};
    const resEd = p.state !== 'pending' || p.action !== 'run_job' ? ''
      : p.res_options?.length ? `<label class="ai-res tiny">ความละเอียด <select data-k="target_res">${p.res_options.map(o => `<option value="${esc(o.value)}" ${String(o.value) === String(P.target_res) ? 'selected' : ''}>${esc(o.label)} · ${fmt(o.pixels / 1e6, 1)} ล้านพิกเซล${o.same_as_source ? ' · = ข้อมูล' : ''}</option>`).join('')}</select></label>`
      : ['hex', 'hexbiv'].includes(p.args.kind) ? `<label class="ai-res tiny">ขนาดหกเหลี่ยม (กม.) <input type="number" min="0.01" step="any" data-k="size_km" value="${esc(P.size_km ?? 1)}"></label>` : '';
    const edit = resEd + (isBiv(p) && p.state === 'pending' ? axisEditor(p) : '');
    const detail = p.action === 'run_job' ? `<details class="tiny"><summary>ค่าที่ตั้ง</summary>${summary(p)}</details>` : '';
    const stx = { pending: '', running: '<span class="tiny muted">กำลังส่ง…</span>', done: `<span class="tiny ok-t">${IC.check}${esc(p.result || 'เรียบร้อย')}</span>`,
      rejected: '<span class="tiny muted">ไม่ทำ</span>', moved: '<span class="tiny muted">เปิดไปปรับในหน้าสร้างไบแวเรียตแล้ว</span>',
      failed: `<span class="tiny warn-t">${esc(p.result || 'ไม่สำเร็จ')}</span>` }[p.state];
    const purpose = p.args?.params?.purpose || p.args?.purpose;
    return `<div class="ai-prop ${p.state}" data-m="${mi}" data-p="${pi}"><div class="small"><b>${KIND_TH[p.action] || p.action}</b> · <span translate="no">${esc(p.title)}</span></div>
      ${purpose ? `<div class="ai-purpose tiny">${IC.target}<span>วัตถุประสงค์: <span translate="no">${esc(purpose)}</span></span></div>` : ''}${est}${edit}${detail}
      <div class="row" style="margin-top:6px;gap:6px">${p.state === 'pending' ? `<button class="sm primary" data-ok>${IC.check}${p.action === 'create_report' ? 'เปิดตัวออกแบบรายงาน' : 'ยืนยัน'}</button>`
        + (isBiv(p) ? `<button class="sm ghost" data-form title="ใส่ค่าทั้งหมดลงฟอร์มหน้าสร้างไบแวเรียต แล้วปรับ/รันเอง">ปรับในหน้าสร้างไบแวเรียต</button>` : '')
        + '<button class="sm ghost" data-no>ไม่ทำ</button>' : stx}</div></div>`;
  }

  function onEdit(p, el) {
    const k = el.dataset.k;
    if (p.action === 'download') { p.args[k] = el.value || null; p.edited = true; save(); drawMsgs(); return; }   // ประเภทค่าของไฟล์ที่จะโหลด
    if (!el.dataset.ax) {                                   // ค่าระดับงาน: ความละเอียด / ขนาดหกเหลี่ยม
      p.args.params[k] = k === 'size_km' ? +el.value : el.value;
      p.edited = true; save(); drawMsgs(); return;
    }
    const P = p.args.params, c = P[el.dataset.ax] = P[el.dataset.ax] || {};
    if (k === 'n') c.n = +el.value;
    else if (k === 'order') c.order = el.checked ? 'classify_first' : 'auto';
    else if (k === 'breaks') c.breaks = el.value.split(/[,\s]+/).map(Number).filter(v => !isNaN(v) && el.value.trim());
    else c[k] = el.value;
    if (k === 'method' && el.value === 'breaks' && !(c.breaks || []).length) c.breaks = [];
    p.edited = true; save(); drawMsgs();                      // วาดใหม่ทุกครั้ง: ช่องเกณฑ์ / สรุปค่าที่ตั้งตรงกับที่แก้
  }

  // ใส่ค่าที่ AI เสนอลงฟอร์มหน้าสร้างไบแวเรียต (BIV ใน app.js) แล้วเปิดหน้านั้น — ข้อเสนอนี้ไม่ใช้แล้ว
  function toForm(p) {
    const P = p.args.params;
    ['x', 'y'].forEach(ax => Object.assign(BIV[ax], { breaks: [], label: '' }, P[ax] || {}));
    Object.assign(BIV, { target_res: P.target_res || null, aoi_id: P.aoi_id || null, name: P.name || '', colors: null, highlight: P.highlight || [],
      out: p.args.kind === 'hexbiv' ? 'hex' : 'raster', size_km: P.size_km || BIV.size_km });
    if (P.palette) BIV.pal = P.palette.startsWith('b:') ? P.palette : 'b:' + P.palette;
    location.hash = '#/biv';
    if (location.hash === '#/biv') route();
  }

  async function decide(mi, pi, ok, form) {
    const p = hist[mi].proposals[pi];
    if (p.state !== 'pending') return;
    if (!ok) {
      p.state = form ? 'moved' : 'rejected';
      api(ENGINE + '/api/ai/reject', { json: { id: p.id } }).catch(() => { });
      if (form) { hist.push({ role: 'event', content: 'ผู้ใช้เปิดค่าที่เสนอไปปรับในหน้าสร้างไบแวเรียตเอง' }); toForm(p); }
      save(); drawMsgs(); return;
    }
    p.state = 'running'; drawMsgs();
    try {
      const edited = !p.edited ? undefined : p.action === 'download' ? { value_type: p.args.value_type || null } : p.args.params;
      const r = await api(ENGINE + '/api/ai/confirm', { json: { id: p.id, params: edited } });
      p.state = 'done'; p.result = r.message;
      hist.push({ role: 'event', content: r.message + (r.job_id ? ' — กำลังประมวลผล' : '') });
      if (r.recipe_id) watchRecipe(r.recipe_id);
      else if (r.job_id) watchJob(r.job_id);
      else if (!r.report && !hist[mi].proposals.some(q => q.state === 'pending' || q.state === 'running') && !watching.size) setTimeout(autoContinue, 300);
      if (r.report) { try { sessionStorage.setItem('ainu-ai-report', JSON.stringify(r.report)); } catch { } location.hash = '#/report?ai=1'; }
      if (typeof jobBadge === 'function') jobBadge();
    } catch (e) { p.state = 'failed'; p.result = e.message; hist.push({ role: 'event', content: `ไม่สำเร็จ: ${p.title} — ${e.message}` }); }
    save(); drawMsgs();
  }

  // ติดตามงานที่รันจากข้อเสนอ → แจ้งผลในแชต (ผลนี้ส่งให้ AI ในรอบถัดไปด้วย)
  // งานที่ผู้ช่วยเสนอเสร็จครบทุกงาน → แชตเดินต่อเอง 1 รอบ: ผู้ช่วยเขียนโน้ตประวัติชุดใหม่ แล้วสรุป/ถามขั้นต่อไป (เช่น ตั้งค่าไบแวเรียต)
  const watching = new Set();
  async function autoContinue() {
    if (busy || !st?.connected || !st?.enabled) return;
    busy = true; drawMsgs();
    try {
      const r = await api(ENGINE + '/api/ai/chat', { json: { messages: hist.map(x => ({ role: x.role, content: x.content })), page: location.hash || '#/', chat_id: cid } });
      if (r.plan !== undefined) plan = r.plan;
      hist.push({ role: 'assistant', content: r.reply, used: r.used || [], note: r.note, docs: r.docs || [], usage: r.usage, proposals: (r.proposals || []).map(p => ({ ...p, state: 'pending' })) });
    } catch (e) { hist.push({ role: 'error', content: e.message }); }
    busy = false; save(); drawMsgs();
  }

  // สูตรงาน: อัปเดตข้อความเดียวในแชตตามความคืบหน้า → เสร็จแล้วส่งสรุปให้ผู้ช่วยอ่านครั้งเดียว
  function watchRecipe(id) {
    const ev = { role: 'event', content: 'สูตรงานเริ่มแล้ว', recipe: id };
    hist.push(ev); save(); drawMsgs();
    watching.add('r' + id);
    const tick = async () => {
      let r;
      try { r = await api(`${ENGINE}/api/recipes/${id}`); } catch { return setTimeout(tick, 5000); }
      ev.steps = r.steps.map(st => ({ t: st.title, s: st.status, o: st.output, e: st.error }));
      const live = ['queued', 'running'].includes(r.status);
      ev.content = live ? `สูตรงาน "${r.title}" — ขั้น ${r.steps.filter(x => x.status === 'done').length}/${r.steps.length}` : r.summary;
      save(); drawMsgs();
      if (live) return setTimeout(tick, 4000);
      watching.delete('r' + id);
      if (!watching.size) autoContinue();
    };
    setTimeout(tick, 1500);
  }

  function watchJob(id) {
    watching.add(id);
    const tick = async () => {
      let j;
      try { j = (await api(ENGINE + '/api/jobs')).find(x => x.id === id); } catch { return setTimeout(tick, 5000); }
      if (!j) { watching.delete(id); return; }
      if (['queued', 'running', 'cancelling'].includes(j.status)) return setTimeout(tick, 3000);
      const did = j.result?.dataset_id;
      hist.push({ role: 'event', content: j.status === 'done' ? `งาน #${id} เสร็จแล้ว${did ? ` → ผลลัพธ์ชุดข้อมูล #${did}` : ''}` : `งาน #${id} ${j.status === 'failed' ? 'ล้มเหลว: ' + (j.error || '') : j.status}`, link: did ? `#/ds/${did}` : null });
      watching.delete(id);
      save(); drawMsgs();
      if (!watching.size) autoContinue();
    };
    setTimeout(tick, 2000);
  }

  let shownN = 0, shownH = null, shownM = null;                                                       // จำนวนข้อความที่แสดงไปแล้ว (แยกคำตอบใหม่ออกจากการวาดซ้ำ)
  function drawMsgs() {
    const m = dock().querySelector('.ai-msgs');
    if (!m) return;
    const SI = { todo: '○', doing: '◐', done: '●', blocked: '✕', skipped: '–' };
    const planHtml = plan && (plan.goal || plan.steps?.length) ? `<details class="ai-plan" ${ls.get('ainu-ai-plan-open', true) ? 'open' : ''}><summary><b>แผนงาน</b>
        <span class="tiny muted">${(plan.steps || []).filter(s => s.status === 'done').length}/${(plan.steps || []).length} ขั้น${plan.blockers?.length ? ` · ติด ${plan.blockers.length}` : ''}</span></summary>
      ${plan.goal ? `<div class="small" translate="no">${esc(plan.goal)}</div>` : ''}${plan.purpose ? `<div class="tiny muted" translate="no">วัตถุประสงค์: ${esc(plan.purpose)}</div>` : ''}
      <ol>${(plan.steps || []).map(s => `<li class="st-${s.status}"><span class="ai-si">${SI[s.status] || '○'}</span><span translate="no">${esc(s.title)}${s.note ? ` <span class="tiny muted">— ${esc(s.note)}</span>` : ''}${(s.outputs || []).map(o => ` <a href="#/ds/${o}" class="tiny">#${o}</a>`).join('')}</span></li>`).join('')}</ol>
      ${(plan.decisions || []).length ? `<div class="tiny muted" translate="no">ตกลงแล้ว: ${plan.decisions.map(esc).join(' · ')}</div>` : ''}
      ${(plan.blockers || []).map(b => `<div class="tiny warn-t" translate="no">ติด: ${esc(b)}</div>`).join('')}</details>` : '';
    const keep = m.scrollTop, grew = hist.length > shownN;
    m.innerHTML = planHtml + (hist.length ? '' : `<div class="tiny muted" style="padding:6px 2px">เริ่มจากบอกว่าจะทำแผนที่ไปเพื่ออะไร ใครดู — เช่น "อยากรู้ว่าพื้นที่ไหนคนอยู่หนาแน่นและน้ำท่วมซ้ำบ่อย เพื่อเสนอผู้บริหารจัดลำดับพื้นที่ช่วยเหลือทั้งประเทศ"<br>${st.mode === 'propose' ? 'ผู้ช่วยจะถามสิ่งที่ยังไม่ชัด ออกแบบการวิเคราะห์ตามวัตถุประสงค์ แล้วเสนองานให้กดยืนยัน' : 'ผู้ช่วยจะแนะนำการวิเคราะห์และการตั้งค่าตามวัตถุประสงค์'}</div>`)
      + hist.map((x, mi) => x.role === 'event'
        ? `<div class="ai-msg event">${x.recipe && x.steps ? `<div>${esc(x.content.split('\n')[0])}</div><ol class="ai-steps tiny">${x.steps.map(st => `<li class="st-${st.s}"><span class="ai-si">${ST_IC[st.s] || '○'}</span> <span translate="no">${esc(st.t)}</span>${st.o ? ` <a href="#/ds/${st.o}">#${st.o}</a>` : ''}${st.e ? ` <span class="warn-t">${esc(st.e)}</span>` : ''}</li>`).join('')}</ol>` : esc(x.content)}${x.link ? ` <a href="${x.link}">เปิดผลลัพธ์</a>` : ''}</div>`
        : `<div class="ai-msg ${x.role}" data-mi="${mi}" ${x.role !== 'error' ? 'translate="no"' : ''}>${x.role === 'assistant' ? md(x.content) : esc(x.content)}</div>`
          + (x.used?.length ? `<div class="ai-used tiny muted">ตรวจข้อมูล: ${[...new Set(x.used.map(u => u.tool))].join(', ')}${x.used.some(u => u.error) ? ' · บางคำขอผิดพลาด' : ''}</div>` : '')
          + (x.note ? `<div class="ai-used tiny muted">${esc(x.note)}</div>` : '')
          + (x.usage?.calls ? `<div class="ai-used tiny muted" title="โทเคนที่ส่ง/รับในคำตอบนี้ — ส่วนที่แคชคิดราคาถูกกว่ามาก">โทเคน: ส่ง ${fmt(x.usage.input, 0)}${x.usage.cached ? ` (แคช ${fmt(x.usage.cached, 0)})` : ''} · ตอบ ${fmt(x.usage.output, 0)} · ${x.usage.calls} รอบ</div>` : '')
          + (x.docs || []).map(d => `<div class="ai-doc">${IC.pdf}<div><b translate="no">${esc(d.title)}</b><div class="tiny muted">เอกสาร v${d.version} · ${d.lines} บรรทัด${d.tables ? ` · ${d.tables} ตาราง` : ''}</div></div>
              <a class="btn sm" href="${ENGINE}${d.url}" target="_blank" rel="noopener">เปิด</a><a class="btn sm ghost" href="${ENGINE}${d.url}?raw=1">${IC.download}.md</a></div>`).join('')
          + (x.proposals || []).map((p, pi) => propCard(p, mi, pi)).join('')
          + ((x.proposals || []).filter(p => p.state === 'pending').length > 1 ? `<button class="sm primary ai-all" data-all="${mi}">${IC.check}ยืนยันทั้งหมด (${x.proposals.filter(p => p.state === 'pending').length})</button>` : '')).join('')
      + (busy ? '<div class="ai-msg assistant typing"><i></i><i></i><i></i></div>' : '');
    m.querySelectorAll('[data-all]').forEach(b => b.onclick = async () => {
      const mi = +b.dataset.all;
      for (let pi = 0; pi < hist[mi].proposals.length; pi++) if (hist[mi].proposals[pi].state === 'pending') await decide(mi, pi, true);
    });
    m.querySelectorAll('.ai-prop').forEach(c => {
      const mi = +c.dataset.m, pi = +c.dataset.p;
      c.querySelector('[data-ok]')?.addEventListener('click', () => decide(mi, pi, true));
      c.querySelector('[data-no]')?.addEventListener('click', () => decide(mi, pi, false));
      c.querySelector('[data-form]')?.addEventListener('click', () => decide(mi, pi, false, true));
      c.querySelectorAll('.ai-edit [data-k], .ai-res [data-k]').forEach(el => el.addEventListener('change', () => onEdit(hist[mi].proposals[pi], el)));
    });
    const pd = m.querySelector('.ai-plan');
    if (pd) pd.ontoggle = () => ls.set('ainu-ai-plan-open', pd.open);
    // คำตอบใหม่ → เลื่อนให้หัวคำตอบอยู่บนสุด (อ่านจากต้นข้อความ ไม่ต้องเลื่อนขึ้นเอง) · ผู้ใช้เพิ่งส่ง/รอคำตอบ → ล่างสุด
    // อัปเดตอื่น (ยืนยันข้อเสนอ แผนงาน งานเสร็จ) → คงตำแหน่งเดิม
    const firstNew = grew && shownH === hist && shownM === m ? hist.findIndex((x, i) => i >= shownN && x.role === 'assistant') : -1;
    if (shownH !== hist || shownM !== m) m.scrollTop = m.scrollHeight;                 // เปิด/สลับแชต → ไปข้อความล่าสุด
    else if (busy || (grew && hist[hist.length - 1]?.role === 'user')) m.scrollTop = m.scrollHeight;
    else if (firstNew >= 0) {
      const el = m.querySelector(`[data-mi="${firstNew}"]`);
      m.scrollTop = el ? el.getBoundingClientRect().top - m.getBoundingClientRect().top + m.scrollTop - 8 : m.scrollHeight;
    } else m.scrollTop = keep;
    shownN = hist.length; shownH = hist; shownM = m;
  }

  // ---------- การ์ดในหน้า "ระบบ" ----------
  async function settingsCard(el) {
    try { await refresh(); } catch (e) { el.innerHTML = `<div class="note err">${esc(e.message)}</div>`; return; }
    el.innerHTML = `<div class="card-head"><h2><span class="dot" style="background:var(--mint);color:var(--mint)"></span>ผู้ช่วย AI</h2>
        <label class="switch"><input type="checkbox" id="aiOn" ${st.enabled ? 'checked' : ''}><i></i><span class="small">${st.enabled ? 'เปิดใช้งาน' : 'ปิดใช้งาน'}</span></label></div>
      <p class="small muted" style="margin-top:0">เปิดแล้วจะมีช่องแชตมุมขวาล่างทุกหน้า (ซ่อนได้) · ล็อกอินด้วย API key ในช่องแชต</p>
      ${st.connected ? `<table class="kv"><tr><td>ผู้ให้บริการ</td><td>${esc(st.provider_label)}${st.base_url ? ` <span class="mono tiny">${esc(st.base_url)}</span>` : ''}</td></tr>
        <tr><td>รุ่น</td><td><div class="row"><select id="aiModel" translate="no"><option>${esc(st.model)}</option></select><button class="sm ghost" id="aiLoadM">โหลดรายการรุ่น</button></div></td></tr>
        <tr><td>สิทธิ์</td><td><select id="aiMode"><option value="propose" ${st.mode === 'propose' ? 'selected' : ''}>เสนองาน — ต้องกดยืนยันทุกครั้ง</option><option value="read" ${st.mode === 'read' ? 'selected' : ''}>อ่านอย่างเดียว</option></select>
          <div class="tiny muted" style="margin-top:4px">ผู้ช่วยอ่านคลัง/ประเมินงาน/ค้น Data hub ได้เอง · งานที่เปลี่ยนข้อมูล (ตั้งประเภทค่า, รันงาน, สร้างพื้นที่ศึกษา, ทำรายงาน) รันเมื่อคุณกดยืนยันเท่านั้น · ลบ/ถังขยะ/โทเคนไม่มีให้ผู้ช่วยใช้</div></td></tr></table>
        <button class="sm danger" id="aiOut" style="margin-top:10px">ออกจากระบบ (ลบ key)</button>`
      : `<div class="small muted">${st.enabled ? 'ยังไม่ได้เชื่อมต่อ — ใส่ key ในช่องแชตมุมขวาล่าง' : 'ยังไม่ได้เชื่อมต่อ'}</div>`}`;
    $('#aiOn').onchange = async () => {
      st = await api(ENGINE + '/api/ai', { method: 'PATCH', json: { enabled: $('#aiOn').checked } });
      if (st.enabled) ls.set(OKEY, true);
      render(); settingsCard(el);
    };
    if (!st.connected) return;
    $('#aiLoadM').onclick = async () => {
      try {
        const r = await api(ENGINE + '/api/ai/models', { json: {} });
        $('#aiModel').innerHTML = r.models.map(x => `<option ${x === r.model ? 'selected' : ''}>${esc(x)}</option>`).join('');
      } catch (e) { toast(e.message, true); }
    };
    $('#aiMode').onchange = async () => { st = await api(ENGINE + '/api/ai', { method: 'PATCH', json: { mode: $('#aiMode').value } }); toast('เปลี่ยนสิทธิ์แล้ว'); render(); };
    $('#aiModel').onchange = async () => { st = await api(ENGINE + '/api/ai', { method: 'PATCH', json: { model: $('#aiModel').value } }); toast('เปลี่ยนรุ่นแล้ว'); render(); };
    $('#aiOut').onclick = async () => {
      if (!await ui.confirm('ออกจากระบบ?', '<p>ลบ API key ที่เข้ารหัสเก็บไว้ในเครื่องนี้ (ต้องใส่ใหม่ถ้าจะใช้อีก)</p>', 'ลบ key')) return;
      st = await api(ENGINE + '/api/ai/logout', { json: {} }); render(); settingsCard(el);
    };
  }

  return { init, settingsCard, refresh };
})();
window.AIDock = AIDock;
