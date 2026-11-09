// ผู้ช่วย AI — ขั้นที่ 1: เปิด/ปิดในหน้า "ระบบ" · ช่องแชตลอยมุมขวาล่าง (ย่อเป็นปุ่มได้) · ล็อกอินด้วย API key ในช่องแชต
// key ส่งไปเก็บเข้ารหัสในตัวประมวลผลครั้งเดียวตอนเชื่อมต่อ — หน้าเว็บไม่เก็บ/ไม่ได้รับค่ากลับ · ประวัติแชตเก็บในเบราว์เซอร์นี้
const AIDock = (() => {
  const HKEY = 'ainu-ai-chat', OKEY = 'ainu-ai-open';
  let st = null, busy = false, hist = [];
  const ls = { get: (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } }, set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { } } };
  const md = s => esc(s).replace(/```([\s\S]*?)```/g, '<pre>$1</pre>').replace(/`([^`\n]+)`/g, '<code>$1</code>').replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>');

  async function refresh() { st = await api(ENGINE + '/api/ai'); return st; }

  async function init() {
    try { await refresh(); } catch { return; }
    hist = ls.get(HKEY, []);
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
      d.querySelector('[data-a=clear]').onclick = () => { hist = []; ls.set(HKEY, hist); chatView(); };
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
        const r = await api(ENGINE + '/api/ai/chat', { json: { messages: hist.map(x => ({ role: x.role, content: x.content })), page: location.hash || '#/' } });
        hist.push({ role: 'assistant', content: r.reply, used: r.used || [], note: r.note,
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
  const KIND_TH = { set_value_type: 'ตั้งประเภทค่า', create_aoi: 'สร้างพื้นที่ศึกษา', run_job: 'รันงาน' };
  function propCard(p, mi, pi) {
    const e = p.estimate || {};
    const est = p.action === 'run_job'
      ? (e.ok ? `<div class="tiny">${esc(e.resolution || '')}${e.size?.[0] ? ` · ${fmt(e.size[0], 0)} × ${fmt(e.size[1], 0)} พิกเซล` : ''}${e.aoi ? ' · ' + esc(e.aoi) : ''}</div>`
        + (e.warnings || []).map(w => `<div class="tiny warn-t">${esc(w)}</div>`).join('')
        : `<div class="tiny warn-t">ตรวจไม่ผ่านตอนเสนอ: ${esc(e.error || '?')} — จะตรวจอีกครั้งตอนรัน</div>`) : '';
    const detail = p.action === 'run_job' ? `<details class="tiny"><summary>ค่าที่ตั้ง</summary><pre translate="no">${esc(JSON.stringify(p.args.params, null, 1))}</pre></details>` : '';
    const stx = { pending: '', running: '<span class="tiny muted">กำลังส่ง…</span>', done: `<span class="tiny ok-t">${IC.check}${esc(p.result || 'เรียบร้อย')}</span>`,
      rejected: '<span class="tiny muted">ไม่ทำ</span>', failed: `<span class="tiny warn-t">${esc(p.result || 'ไม่สำเร็จ')}</span>` }[p.state];
    return `<div class="ai-prop ${p.state}" data-m="${mi}" data-p="${pi}"><div class="small"><b>${KIND_TH[p.action] || p.action}</b> · <span translate="no">${esc(p.title)}</span></div>${est}${detail}
      <div class="row" style="margin-top:6px;gap:6px">${p.state === 'pending' ? `<button class="sm primary" data-ok>${IC.check}ยืนยัน</button><button class="sm ghost" data-no>ไม่ทำ</button>` : stx}</div></div>`;
  }

  async function decide(mi, pi, ok) {
    const p = hist[mi].proposals[pi];
    if (p.state !== 'pending') return;
    if (!ok) { p.state = 'rejected'; api(ENGINE + '/api/ai/reject', { json: { id: p.id } }).catch(() => { }); save(); drawMsgs(); return; }
    p.state = 'running'; drawMsgs();
    try {
      const r = await api(ENGINE + '/api/ai/confirm', { json: { id: p.id } });
      p.state = 'done'; p.result = r.message;
      hist.push({ role: 'event', content: r.message + (r.job_id ? ' — กำลังประมวลผล' : '') });
      if (r.job_id) watchJob(r.job_id);
      if (typeof jobBadge === 'function') jobBadge();
    } catch (e) { p.state = 'failed'; p.result = e.message; hist.push({ role: 'event', content: `ไม่สำเร็จ: ${p.title} — ${e.message}` }); }
    save(); drawMsgs();
  }

  // ติดตามงานที่รันจากข้อเสนอ → แจ้งผลในแชต (ผลนี้ส่งให้ AI ในรอบถัดไปด้วย)
  function watchJob(id) {
    const tick = async () => {
      let j;
      try { j = (await api(ENGINE + '/api/jobs')).find(x => x.id === id); } catch { return setTimeout(tick, 5000); }
      if (!j) return;
      if (['queued', 'running', 'cancelling'].includes(j.status)) return setTimeout(tick, 3000);
      const did = j.result?.dataset_id;
      hist.push({ role: 'event', content: j.status === 'done' ? `งาน #${id} เสร็จแล้ว${did ? ` → ผลลัพธ์ชุดข้อมูล #${did}` : ''}` : `งาน #${id} ${j.status === 'failed' ? 'ล้มเหลว: ' + (j.error || '') : j.status}`, link: did ? `#/ds/${did}` : null });
      save(); drawMsgs();
    };
    setTimeout(tick, 2000);
  }

  function drawMsgs() {
    const m = dock().querySelector('.ai-msgs');
    if (!m) return;
    m.innerHTML = (hist.length ? '' : `<div class="tiny muted" style="padding:6px 2px">${st.mode === 'propose' ? 'เช่น "สร้างไบแวเรียตประชากร 2024 × จำนวนปีน้ำท่วม ทั้งประเทศ ความละเอียด 1 กม." — ผู้ช่วยจะตรวจข้อมูลแล้วเสนองานให้กดยืนยัน' : 'เช่น "ข้อมูลน้ำท่วมกับประชากรควรตั้งประเภทค่าอะไร" · "หาข้อมูลความหนาแน่นประชากรใน Data hub ให้หน่อย"'}</div>`)
      + hist.map((x, mi) => x.role === 'event'
        ? `<div class="ai-msg event">${esc(x.content)}${x.link ? ` <a href="${x.link}">เปิดผลลัพธ์</a>` : ''}</div>`
        : `<div class="ai-msg ${x.role}" ${x.role !== 'error' ? 'translate="no"' : ''}>${x.role === 'assistant' ? md(x.content) : esc(x.content)}</div>`
          + (x.used?.length ? `<div class="ai-used tiny muted">ตรวจข้อมูล: ${[...new Set(x.used.map(u => u.tool))].join(', ')}${x.used.some(u => u.error) ? ' · บางคำขอผิดพลาด' : ''}</div>` : '')
          + (x.note ? `<div class="ai-used tiny muted">${esc(x.note)}</div>` : '')
          + (x.proposals || []).map((p, pi) => propCard(p, mi, pi)).join('')).join('')
      + (busy ? '<div class="ai-msg assistant typing"><i></i><i></i><i></i></div>' : '');
    m.querySelectorAll('.ai-prop').forEach(c => {
      const mi = +c.dataset.m, pi = +c.dataset.p;
      c.querySelector('[data-ok]')?.addEventListener('click', () => decide(mi, pi, true));
      c.querySelector('[data-no]')?.addEventListener('click', () => decide(mi, pi, false));
    });
    m.scrollTop = m.scrollHeight;
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
          <div class="tiny muted" style="margin-top:4px">ผู้ช่วยอ่านคลัง/ประเมินงาน/ค้น Data hub ได้เอง · งานที่เปลี่ยนข้อมูล (ตั้งประเภทค่า, รันงาน, สร้างพื้นที่ศึกษา) รันเมื่อคุณกดยืนยันเท่านั้น · ลบ/ถังขยะ/โทเคนไม่มีให้ผู้ช่วยใช้</div></td></tr></table>
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
