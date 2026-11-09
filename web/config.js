// ================= Ainulindalë v1 — หน้าเว็บ ↔ ตัวประมวลผลในเครื่องผู้ใช้ =================
// หน้าเว็บนี้วางบนโฮสต์ไหนก็ได้ (GitHub Pages / Cloudflare Pages) แต่ "คำนวณ" ที่เครื่องของผู้ใช้เอง:
//   เบราว์เซอร์ ──fetch──▶ http://127.0.0.1:41217 (ตัวประมวลผล = Python ในเครื่อง) ──▶ ไฟล์ · CPU · RAM
// ไฟล์ข้อมูลไม่ถูกอัปโหลดขึ้นเว็บ · การเรียกที่เปลี่ยนข้อมูลต้องมีโทเคนจับคู่ (ได้จากลิงก์ที่ตัวประมวลผลเปิดให้)
var ENGINE, ENGINE_TOKEN;
(function () {
  const DEFAULT_ENGINE = 'http://127.0.0.1:41217';
  // ไฟล์ติดตั้งอยู่ที่ GitHub Releases (ชื่อไฟล์คงที่ → ลิงก์ latest ใช้ได้ทุกเวอร์ชัน)
  window.AINU_DOWNLOAD_URL = window.AINU_DOWNLOAD_URL || 'https://github.com/nattakitNams/project-ainulindale-demo/releases/latest/download/Ainulindale-setup.zip';
  const get = k => { try { return localStorage.getItem(k); } catch { return null; } };
  const put = (k, v) => { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { } };

  // ลิงก์จับคู่จากตัวประมวลผล: <หน้าเว็บ>#pair=<โทเคน>&engine=<url> → เก็บแล้วลบออกจากแถบที่อยู่
  const takePair = () => {
    if (!location.hash.startsWith('#pair=')) return false;
    const q = new URLSearchParams(location.hash.slice(1));
    put('ainu.token', q.get('pair'));
    if (q.get('engine')) put('ainu.engine', q.get('engine'));
    history.replaceState(null, '', location.pathname + location.search + '#/');
    return true;
  };
  takePair();
  // หน้าเปิดค้างอยู่แล้วกดลิงก์จับคู่ = เปลี่ยนแค่ # → ไม่โหลดใหม่เอง ต้องจับเองแล้วโหลดใหม่
  window.addEventListener('hashchange', e => { if (takePair()) { e.stopImmediatePropagation(); location.reload(); } }, true);
  // เปิดจากตัวประมวลผลเอง (http://127.0.0.1:41217/ui/) = same-origin ไม่ต้องจับคู่
  const SAME = !!document.querySelector('meta[name="ainu-engine"]');
  ENGINE = SAME ? location.origin : (get('ainu.engine') || DEFAULT_ENGINE).replace(/\/+$/, '');
  ENGINE_TOKEN = SAME ? '' : (get('ainu.token') || '');

  // ทุก fetch ที่ไปหาตัวประมวลผล แนบโทเคนให้อัตโนมัติ
  const _fetch = window.fetch.bind(window);
  window.fetch = (u, o = {}) => {
    if (typeof u === 'string' && u.startsWith('/api/')) u = ENGINE + u;
    if (typeof u === 'string' && u.startsWith(ENGINE) && !SAME) {
      o = Object.assign({ targetAddressSpace: 'loopback' }, o);          // Chrome Local Network Access: บอกว่าตั้งใจคุยกับเครื่องตัวเอง
      if (ENGINE_TOKEN) o.headers = Object.assign({}, o.headers || {}, { 'X-Ainu-Token': ENGINE_TOKEN });
    }
    return _fetch(u, o);
  };

  // ---------- หน้าจอเชื่อมต่อ ----------
  const css = `#ainuGate{position:fixed;inset:0;z-index:9999;display:grid;place-items:center;background:#15172acc;backdrop-filter:blur(10px);font-family:Anuphan,sans-serif;color:#e8e9f5}
    #ainuGate .box{width:min(600px,92vw);max-height:92vh;overflow:auto;background:#23263a;border:1px solid #ffffff1f;border-radius:20px;padding:26px 28px;box-shadow:0 30px 80px #0008}
    #ainuGate h2{margin:0 0 6px;font-size:21px} #ainuGate p{color:#b5b8d0;font-size:14px;line-height:1.6;margin:8px 0}
    #ainuGate ol{padding-left:20px;font-size:14px;line-height:1.8;color:#d5d7ea} #ainuGate code{background:#ffffff12;padding:1px 6px;border-radius:5px;font-size:12.5px}
    #ainuGate .row{display:flex;gap:8px;margin-top:10px} #ainuGate input{flex:1;background:#15172a;border:1px solid #ffffff26;border-radius:10px;color:#fff;padding:8px 10px;font:13px 'JetBrains Mono',monospace}
    #ainuGate button{background:#c3b6ff;color:#1b1d30;border:0;border-radius:10px;padding:8px 14px;font:600 13px Anuphan,sans-serif;cursor:pointer}
    #ainuGate .lna{margin:12px 0;padding:10px 12px;border-radius:10px;background:#f6e3a114;border:1px solid #f6e3a155;font-size:13px;line-height:1.6;color:#f6e3a1}
    #ainuGate .lna.bad{background:#ff9aa814;border-color:#ff9aa866;color:#ffc4cc} #ainuGate .lna a{color:#c3b6ff}
    #ainuGate .st{font-size:12.5px;color:#9ee8d4;margin-top:12px} #ainuGate .priv{font-size:12px;color:#8e92ad;border-top:1px solid #ffffff14;margin-top:16px;padding-top:12px}
    .ainu-eng{display:flex;align-items:center;gap:6px;font-size:11.5px;color:#9ee8d4;margin-top:6px} .ainu-eng i{width:7px;height:7px;border-radius:50%;background:#9ee8d4;box-shadow:0 0 8px #9ee8d4}`;
  let el = null;
  const show = (state, info) => {
    if (!el) {
      const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
      el = document.createElement('div'); el.id = 'ainuGate'; document.body.appendChild(el);
    }
    const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    const lna = info?.lna;                                      // สิทธิ์ Local Network Access ของ Chrome/Edge
    const lnaBox = lna === 'denied' ? `<div class="lna bad"><b>เบราว์เซอร์บล็อกไม่ให้หน้านี้คุยกับเครื่องของคุณ</b><br>
          คลิกไอคอน <b>ⓘ / แม่กุญแจ</b> หน้าที่อยู่เว็บ → <b>การเข้าถึงเครือข่ายภายใน / Local network access</b> → <b>อนุญาต (Allow)</b> แล้วรีเฟรชหน้านี้<br>
          หรือใช้หน้าสำรองในเครื่องแทน: <a href="${esc(ENGINE)}/ui/" target="_blank" rel="noopener">${esc(ENGINE)}/ui/</a> (ต้องเปิด Ainulindale.bat ก่อน)</div>`
      : lna === 'prompt' ? `<div class="lna">ถ้าเบราว์เซอร์ถาม <b>"อนุญาตให้เข้าถึงแอป/อุปกรณ์ในเครื่องนี้"</b> ให้กด <b>อนุญาต (Allow)</b> — หน้านี้ต้องคุยกับตัวประมวลผลในเครื่องคุณ (127.0.0.1) ไม่ได้ออกไปเครือข่ายอื่น</div>` : '';
    el.innerHTML = state === 'down' ? `<div class="box"><h2>ใช้ Ainulindalë บนเครื่องของคุณ</h2>${lnaBox}
        <p>หน้าเว็บนี้เป็นแค่หน้าจอ — การคำนวณใช้ CPU / RAM / ไฟล์ของเครื่องคุณ ผ่านตัวประมวลผลเล็กๆ ที่รันในเครื่อง</p>
        <p><b>ติดตั้งครั้งแรก</b> (Windows 10/11 · ไม่ต้องใช้สิทธิ์ admin)</p>
        <ol><li><a href="${esc(window.AINU_DOWNLOAD_URL || 'download/Ainulindale-setup.zip')}" style="color:#c3b6ff;font-weight:600">ดาวน์โหลด Ainulindale-setup.zip</a> (~15 MB)</li>
          <li>แตกไฟล์ไว้ที่ไหนก็ได้ เช่น <code>D:\\Ainulindale</code> — ทุกอย่างของแอปจะอยู่ในโฟลเดอร์นี้</li>
          <li>ดับเบิลคลิก <code>Ainulindale.bat</code> → หน้าเว็บนี้จะเปิดตัวช่วยติดตั้งให้เอง</li></ol>
        <p style="font-size:12.5px">Windows อาจเตือน "Windows protected your PC" เพราะไฟล์ยังไม่ได้ลงนามดิจิทัล → กด <b>More info → Run anyway</b> · โค้ดทั้งหมดเปิดให้ตรวจได้</p>
        <p><b>ติดตั้งแล้ว?</b> เปิด <code>Ainulindale.bat</code> แล้วหน้านี้จะเชื่อมต่อเอง</p>
        <p style="font-size:13px">เปิดแล้วแต่หน้านี้เชื่อมต่อไม่ได้? ใช้หน้าสำรองในเครื่อง <a href="${esc(ENGINE)}/ui/" target="_blank" rel="noopener" style="color:#c3b6ff">${esc(ENGINE)}/ui/</a> (ไม่ต้องขอสิทธิ์เบราว์เซอร์)</p>
        <p>ตัวประมวลผลอยู่ที่อื่น? แก้ที่อยู่:</p>
        <div class="row"><input id="agUrl" value="${esc(ENGINE)}"><button id="agSave">เชื่อมต่อ</button></div>
        <div class="st">กำลังลองเชื่อมต่อ ${esc(ENGINE)} ทุก 3 วินาที…</div>
        <div class="priv">ถ้าเปิดตัวประมวลผลแล้วยังขึ้นหน้านี้: ที่อยู่หน้าเว็บนี้ (<code>${esc(location.origin)}</code>) อาจยังไม่อยู่ใน <code>engine.json → allowed_origins</code><br>
        🔒 ไฟล์ข้อมูลไม่ถูกอัปโหลดขึ้นอินเทอร์เน็ต — หน้าเว็บคุยกับเครื่องคุณโดยตรง · สิ่งที่ออกอินเทอร์เน็ตมีแค่ภาพแผนที่พื้นหลัง ฟอนต์ และบริการแผนที่ที่คุณเพิ่มเอง</div></div>`
      : `<div class="box"><h2>เจอตัวประมวลผลแล้ว — ยังไม่ได้จับคู่</h2>
        <p>เครื่อง <b>${esc(info?.machine || '?')}</b> · ${esc(info?.app || '')} v${esc(info?.version || '')} · ${esc(ENGINE)}</p>
        <p>เพื่อกันเว็บอื่นมาสั่งงานเครื่องคุณ ต้องจับคู่ก่อน: ปิดแล้วเปิด <code>Ainulindale.bat</code> ใหม่ (จะเปิดลิงก์จับคู่ให้) หรือวางโทเคนจากไฟล์ <code>workspace/engine_token.txt</code></p>
        <div class="row"><input id="agTok" placeholder="โทเคนจับคู่"><button id="agPair">จับคู่</button></div>
        <div class="priv">🔒 โทเคนเก็บในเบราว์เซอร์นี้เท่านั้น · ส่งไปที่ตัวประมวลผลในเครื่องคุณ ไม่ผ่านเซิร์ฟเวอร์ของเว็บ</div></div>`;
    const sv = el.querySelector('#agSave');
    if (sv) sv.onclick = () => { put('ainu.engine', el.querySelector('#agUrl').value.trim()); location.reload(); };
    const pr = el.querySelector('#agPair');
    if (pr) pr.onclick = () => { put('ainu.token', el.querySelector('#agTok').value.trim()); location.reload(); };
  };
  const lnaState = async () => {
    for (const name of ['local-network-access', 'loopback-network']) {
      try { return (await navigator.permissions.query({ name })).state; } catch { }
    }
    return null;                                                // เบราว์เซอร์ไม่มีระบบนี้
  };
  const probe = async () => {
    try {
      const r = await _fetch(ENGINE + '/api/engine/hello', { headers: ENGINE_TOKEN ? { 'X-Ainu-Token': ENGINE_TOKEN } : {}, targetAddressSpace: 'loopback' });
      const info = await r.json();
      const ok = SAME || info.paired;
      return { state: !ok ? 'unpaired' : info.mode === 'setup' ? 'setup' : 'ok', info };
    } catch { return { state: 'down', info: { lna: SAME ? null : await lnaState() } }; }
  };

  window.ainuEngine = {
    same: SAME,
    async gate() {
      for (;;) {
        const { state, info } = await probe();
        if (state === 'setup') {                               // ติดตั้งยังไม่เสร็จ → ตัวช่วยติดตั้ง (แอปหลักไม่เริ่ม)
          if (el) { el.remove(); el = null; }
          await new Promise((res, rej) => { const s = document.createElement('script'); s.src = 'setup.js?v=1.0.18'; s.onload = res; s.onerror = rej; document.head.appendChild(s); });
          return window.AinuSetup.run(info);
        }
        if (SAME && state !== 'down') return info;
        if (state === 'ok') { if (el) { el.remove(); el = null; } return info; }
        const key = state + (info?.lna || '');
        if (!el || el.dataset.state !== key || state === 'unpaired') { show(state, info); el.dataset.state = key; }
        if (state === 'unpaired') return new Promise(() => { });        // รอผู้ใช้วางโทเคน (หน้าโหลดใหม่เอง)
        await new Promise(r => setTimeout(r, 3000));
      }
    },
    badge(STATE) {
      const ws = document.getElementById('ws'); if (!ws) return;
      const d = document.createElement('div'); d.className = 'ainu-eng';
      d.innerHTML = `<i></i>${SAME ? 'ตัวประมวลผลในเครื่อง (หน้าสำรอง)' : 'ประมวลผลที่เครื่องนี้ · ' + ENGINE.replace(/^https?:\/\//, '')}`;
      d.title = 'หน้าเว็บนี้สั่งงานตัวประมวลผลที่รันในเครื่องคุณ — ข้อมูลไม่ออกจากเครื่อง';
      ws.after(d);
    },
    forget() { put('ainu.token', null); put('ainu.engine', null); location.reload(); },
  };
})();
