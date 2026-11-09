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
      d.innerHTML = `<button class="ai-fab" title="เปิดผู้ช่วย AI">${IC.chat || '💬'}</button>`;
      d.querySelector('.ai-fab').onclick = () => { ls.set(OKEY, true); render(); };
      return;
    }
    d.innerHTML = `<div class="ai-panel">
      <div class="ai-head"><b>ผู้ช่วย AI</b>${st.connected ? `<span class="chip" translate="no" title="${esc(st.provider_label)}">${esc(st.model || '')}</span>` : ''}
        <span class="spacer"></span>
        ${st.connected ? `<button class="ghost sm" data-a="clear" title="ล้างบทสนทนา">${IC.trash}</button><button class="ghost sm" data-a="set" title="ตั้งค่า (รุ่น / ออกจากระบบ)">⚙</button>` : ''}
        <button class="ghost sm" data-a="min" title="ซ่อน">─</button></div>
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
      <div class="tiny muted" style="margin-top:10px;line-height:1.6">🔒 key ถูกเข้ารหัสเก็บในตัวประมวลผลบนเครื่องนี้ (Windows DPAPI) — ไม่เก็บในเบราว์เซอร์ ไม่ขึ้นเว็บ<br>
        ส่งให้ AI: ข้อความแชต + ชื่อ/ประเภทของชุดข้อมูลในคลัง (ไม่ส่งไฟล์ข้อมูล)<br>
        ใช้บัญชีแบบรายเดือน (ChatGPT Plus / Claude Pro) แทน API key ไม่ได้</div></div>`;
    const sync = () => {
      const p = st.providers.find(x => x.id === $('#aiProv').value);
      b.querySelector('.aiBase').classList.toggle('hide', p.id !== 'compat');
      b.querySelector('.aiOpt').classList.toggle('hide', !p.key_optional);
      $('#aiKeyUrl').innerHTML = p.key_url ? `<a href="${p.key_url}" target="_blank" rel="noopener">ขอ API key ที่นี่ ↗</a>` : 'Ollama: <span class="mono">http://localhost:11434/v1</span> · OpenRouter: <span class="mono">https://openrouter.ai/api/v1</span>';
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
      <div class="ai-input"><textarea id="aiTxt" rows="2" placeholder="ถามอะไรก็ได้เกี่ยวกับข้อมูลหรือการใช้แอป… (Enter ส่ง · Shift+Enter ขึ้นบรรทัด)"></textarea><button class="primary" id="aiSend" title="ส่ง">➤</button></div>`;
    drawMsgs();
    const send = async () => {
      const t = $('#aiTxt').value.trim();
      if (!t || busy) return;
      hist.push({ role: 'user', content: t }); $('#aiTxt').value = ''; busy = true; drawMsgs();
      try {
        const r = await api(ENGINE + '/api/ai/chat', { json: { messages: hist, page: location.hash || '#/' } });
        hist.push({ role: 'assistant', content: r.reply });
      } catch (e) { hist.push({ role: 'error', content: e.message }); }
      busy = false; ls.set(HKEY, hist.slice(-60)); drawMsgs();
    };
    $('#aiSend').onclick = send;
    $('#aiTxt').onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); } };
    $('#aiTxt').focus();
  }

  function drawMsgs() {
    const m = dock().querySelector('.ai-msgs');
    if (!m) return;
    m.innerHTML = (hist.length ? '' : `<div class="tiny muted" style="padding:6px 2px">เช่น "ข้อมูลน้ำท่วมกับประชากรควรตั้งประเภทค่าอะไร" · "หาข้อมูลความหนาแน่นประชากรใน Data hub ให้หน่อย"</div>`)
      + hist.map(x => `<div class="ai-msg ${x.role}" ${x.role !== 'error' ? 'translate="no"' : ''}>${x.role === 'assistant' ? md(x.content) : esc(x.content)}</div>`).join('')
      + (busy ? '<div class="ai-msg assistant typing"><i></i><i></i><i></i></div>' : '');
    m.scrollTop = m.scrollHeight;
  }

  // ---------- การ์ดในหน้า "ระบบ" ----------
  async function settingsCard(el) {
    try { await refresh(); } catch (e) { el.innerHTML = `<div class="note err">${esc(e.message)}</div>`; return; }
    el.innerHTML = `<div class="card-head"><h2><span class="dot" style="background:var(--mint);color:var(--mint)"></span>ผู้ช่วย AI</h2>
        <label class="switch"><input type="checkbox" id="aiOn" ${st.enabled ? 'checked' : ''}><i></i><span class="small">${st.enabled ? 'เปิดใช้งาน' : 'ปิดใช้งาน'}</span></label></div>
      <p class="small muted" style="margin-top:0">เปิดแล้วจะมีช่องแชตมุมขวาล่างทุกหน้า (ซ่อนได้) · ล็อกอินด้วย API key ในช่องแชต</p>
      ${st.connected ? `<table class="kv"><tr><td>ผู้ให้บริการ</td><td>${esc(st.provider_label)}${st.base_url ? ` <span class="mono tiny">${esc(st.base_url)}</span>` : ''}</td></tr>
        <tr><td>รุ่น</td><td><div class="row"><select id="aiModel" translate="no"><option>${esc(st.model)}</option></select><button class="sm ghost" id="aiLoadM">โหลดรายการรุ่น</button></div></td></tr></table>
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
    $('#aiModel').onchange = async () => { st = await api(ENGINE + '/api/ai', { method: 'PATCH', json: { model: $('#aiModel').value } }); toast('เปลี่ยนรุ่นแล้ว'); render(); };
    $('#aiOut').onclick = async () => {
      if (!await ui.confirm('ออกจากระบบ?', '<p>ลบ API key ที่เข้ารหัสเก็บไว้ในเครื่องนี้ (ต้องใส่ใหม่ถ้าจะใช้อีก)</p>', 'ลบ key')) return;
      st = await api(ENGINE + '/api/ai/logout', { json: {} }); render(); settingsCard(el);
    };
  }

  return { init, settingsCard, refresh };
})();
window.AIDock = AIDock;
