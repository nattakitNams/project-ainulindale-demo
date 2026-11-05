// ================= ตัวช่วยติดตั้ง (แสดงเมื่อตัวประมวลผลอยู่ในโหมด setup) =================
// หน้าเว็บสั่งงาน app/setup_server.py ที่รันในเครื่องผู้ใช้ — เว็บเองติดตั้งอะไรลงเครื่องไม่ได้ (เบราว์เซอร์ไม่อนุญาต)
window.AinuSetup = (function () {
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const call = async (path, body) => {
    const r = await fetch(ENGINE + path, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || r.statusText);
    return d;
  };
  const css = `#ainuSetup{position:fixed;inset:0;z-index:9999;overflow:auto;background:#15172a;font-family:Anuphan,sans-serif;color:#e8e9f5}
    #ainuSetup .wrap{max-width:860px;margin:0 auto;padding:40px 22px 60px} #ainuSetup h1{font-size:28px;margin:4px 0 6px} #ainuSetup .eb{font:600 12px 'JetBrains Mono',monospace;letter-spacing:.12em;color:#c3b6ff}
    #ainuSetup .lead{color:#b5b8d0;margin:0 0 22px} #ainuSetup .steps{display:flex;gap:6px;margin:0 0 20px} #ainuSetup .steps span{flex:1;height:5px;border-radius:5px;background:#ffffff14}
    #ainuSetup .steps span.on{background:#c3b6ff} #ainuSetup .card{background:#23263a;border:1px solid #ffffff1a;border-radius:18px;padding:22px 24px;margin-bottom:16px}
    #ainuSetup h2{font-size:18px;margin:0 0 12px} #ainuSetup p,#ainuSetup li{color:#c9cbe0;font-size:14px;line-height:1.7} #ainuSetup ul{padding-left:20px;margin:6px 0}
    #ainuSetup code{background:#ffffff12;padding:1px 6px;border-radius:5px;font:12.5px 'JetBrains Mono',monospace} #ainuSetup b{color:#fff}
    #ainuSetup .ok{color:#9ee8d4} #ainuSetup .bad{color:#ff9aa8} #ainuSetup .warn{color:#f6e3a1}
    #ainuSetup .grid{display:grid;grid-template-columns:1fr 1fr;gap:14px} @media(max-width:700px){#ainuSetup .grid{grid-template-columns:1fr}}
    #ainuSetup .opt{display:flex;gap:10px;align-items:flex-start;padding:12px 14px;border:1px solid #ffffff1a;border-radius:12px;margin:8px 0;cursor:pointer}
    #ainuSetup .opt.on{border-color:#c3b6ff;background:#c3b6ff12} #ainuSetup input[type=text]{width:100%;background:#15172a;border:1px solid #ffffff26;border-radius:10px;color:#fff;padding:9px 11px;font:13px 'JetBrains Mono',monospace;margin-top:6px}
    #ainuSetup .btn{background:#c3b6ff;color:#1b1d30;border:0;border-radius:12px;padding:11px 20px;font:600 15px Anuphan,sans-serif;cursor:pointer} #ainuSetup .btn:disabled{opacity:.45;cursor:default}
    #ainuSetup .btn.ghost{background:transparent;color:#c3b6ff;border:1px solid #c3b6ff66} #ainuSetup .row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
    #ainuSetup .bar{height:12px;border-radius:8px;background:#ffffff14;overflow:hidden;margin:12px 0 8px} #ainuSetup .bar i{display:block;height:100%;background:linear-gradient(90deg,#9ee8d4,#c3b6ff);transition:width .4s}
    #ainuSetup pre{background:#0f1020;border-radius:10px;padding:10px 12px;max-height:220px;overflow:auto;font:11.5px/1.5 'JetBrains Mono',monospace;color:#aeb2cc;white-space:pre-wrap}
    #ainuSetup .pk{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px} #ainuSetup .pk span{font:11.5px 'JetBrains Mono',monospace;background:#ffffff0f;border-radius:6px;padding:2px 7px;color:#c9cbe0}
    #ainuSetup .drv{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px} #ainuSetup .drv button{background:#ffffff0f;border:1px solid #ffffff1f;color:#e8e9f5;border-radius:9px;padding:6px 10px;font:12px 'JetBrains Mono',monospace;cursor:pointer}
    #ainuSetup .tree{font:12.5px/1.7 'JetBrains Mono',monospace;color:#c9cbe0;background:#0f1020;border-radius:10px;padding:10px 14px}`;

  async function run() {
    const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
    const el = document.createElement('div'); el.id = 'ainuSetup'; document.body.appendChild(el);
    let S = await call('/api/setup/status'), step = 0, agreed = false, wsMode = 'inside', wsPath = S.default_workspace, chk = null;
    const sep = S.root.includes('\\') ? '\\' : '/';

    const treeWs = () => wsMode === 'inside' ? '└─ workspace' + sep + ' &nbsp;&nbsp;&nbsp;&nbsp;← ผลลัพธ์ แคช บันทึก'
      : chk?.inside_app ? '└─ ' + esc(wsPath.slice(S.root.length).replace(/^[\\/]+/, '')) + sep + ' &nbsp;← ผลลัพธ์ แคช บันทึก'
        : '<span class="warn">└─ (ผลลัพธ์อยู่นอกโฟลเดอร์แอป: ' + esc(wsPath) + ' — ลบแอปแล้วไม่ถูกลบตาม)</span>';
    const draw = () => {
      const steps = `<div class="steps">${[0, 1, 2, 3].map(i => `<span class="${i <= step ? 'on' : ''}"></span>`).join('')}</div>`;
      let body = '';
      if (step === 0) body = `<div class="card"><h2>ก่อนเริ่ม — สิ่งที่ตัวติดตั้งจะทำ และไม่ทำ</h2>
          <div class="grid"><div><p><b class="ok">✔ ทำ</b></p><ul>
            <li>ดาวน์โหลดแพ็กเกจ Python ${S.packages.length || ''} รายการ (~${S.download_mb_est} MB) จาก <b>PyPI</b> (pypi.org) แหล่งทางการเท่านั้น</li>
            <li>${S.hashed ? 'ตรวจ <b>SHA-256</b> ทุกไฟล์กับค่าที่ล็อกไว้ — ไฟล์ถูกดัดแปลงจะติดตั้งไม่ผ่าน' : '<span class="warn">รุ่นทดสอบ: ยังไม่ได้ล็อกค่า SHA-256</span>'}</li>
            <li>ติดตั้งลงโฟลเดอร์แอปเท่านั้น: <code>${esc(S.root)}</code></li></ul></div>
          <div><p><b class="bad">✘ ไม่ทำ</b></p><ul>
            <li>ไม่ขอสิทธิ์ผู้ดูแลระบบ (admin) · ไม่แก้ registry</li><li>ไม่แตะ Python หรือโปรแกรมอื่นในเครื่อง</li>
            <li>ไม่อัปโหลดไฟล์ข้อมูลของคุณไปที่ใด</li><li>ไม่เก็บแคชไว้นอกโฟลเดอร์แอป</li></ul></div></div></div>
        <div class="card"><h2>ข้อมูลของคุณ</h2><ul>
          <li>การคำนวณทั้งหมดเกิดใน <b>เครื่องนี้</b> — หน้าเว็บเป็นแค่หน้าจอสั่งงาน</li>
          <li>ตัวประมวลผลรับคำสั่งเฉพาะจากเครื่องนี้ (127.0.0.1) และหน้าเว็บที่จับคู่แล้ว</li>
          <li><b>สิ่งที่ออกอินเทอร์เน็ต:</b> ภาพแผนที่พื้นหลัง (Esri / OpenStreetMap / Google — ผู้ให้บริการเห็นบริเวณที่คุณดู), ฟอนต์ (Google Fonts), บริการแผนที่ที่คุณเพิ่มเป็นลิงก์เอง</li>
          <li><b>ถอนการติดตั้ง:</b> ลบโฟลเดอร์แอปทิ้ง (หรือรัน <code>uninstall.bat</code>)</li></ul>
          <label class="row" style="margin-top:12px;cursor:pointer"><input type="checkbox" id="suAgree" ${agreed ? 'checked' : ''}> ฉันเข้าใจและต้องการติดตั้ง</label></div>
        <div class="row"><button class="btn" id="suNext" ${agreed ? '' : 'disabled'}>ถัดไป: เลือกที่เก็บผลลัพธ์ →</button></div>`;
      if (step === 1) body = `<div class="card"><h2>ที่เก็บผลลัพธ์</h2>
          <p>แผนที่ไบแวเรียต ไฟล์แปลงความละเอียด แคช และบันทึกงาน จะเก็บที่นี่ · ไฟล์ข้อมูลต้นทางของคุณ <b>ไม่ถูกคัดลอก</b> (แอปจำแค่ตำแหน่งไฟล์)</p>
          <div class="opt ${wsMode === 'inside' ? 'on' : ''}" data-m="inside"><input type="radio" ${wsMode === 'inside' ? 'checked' : ''}><div><b>ในโฟลเดอร์แอป (แนะนำ)</b><br><code>${esc(S.default_workspace)}</code><br><span class="ok" style="font-size:13px">ลบโฟลเดอร์แอปทีเดียว = ลบหมด</span></div></div>
          <div class="opt ${wsMode === 'custom' ? 'on' : ''}" data-m="custom"><input type="radio" ${wsMode === 'custom' ? 'checked' : ''}><div style="flex:1"><b>เลือกเอง</b> — เช่น ไดรฟ์ที่พื้นที่เหลือเยอะ (ผลลัพธ์ 10 ม. ทั้งประเทศใช้หลาย GB)
            ${wsMode === 'custom' ? `<input type="text" id="suPath" value="${esc(wsPath)}"><div class="drv">${S.drives.map(d => `<button data-d="${esc(d.path)}">${esc(d.path)} ว่าง ${d.free_gb} GB</button>`).join('')}</div>` : ''}</div></div>
          <div id="suChk" style="font-size:13.5px;margin-top:10px"></div></div>
        <div class="card"><h2>หลังติดตั้ง ทุกอย่างจะอยู่ที่</h2><div class="tree">${esc(S.root)}${sep}<br>
          ├─ Ainulindale.bat &nbsp;&nbsp;← เปิดแอป<br>├─ python${sep} &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;← Python ส่วนตัวของแอป + แพ็กเกจ<br>├─ app${sep} · web${sep} &nbsp;&nbsp;← โค้ด<br>
          <span id="suTreeWs">${treeWs()}</span></div></div>
        <div class="row"><button class="btn ghost" id="suBack">← กลับ</button><button class="btn" id="suNext">ถัดไป: ติดตั้ง →</button></div>`;
      if (step === 2) {
        const P = S._p || {};
        const run_ = ['running', 'done', 'failed'].includes(P.state);
        body = `<div class="card"><h2>ตรวจเครื่อง</h2><ul>
            <li>Python ส่วนตัวของแอป: <b>${esc(S.python)}</b> <span class="ok">✔</span></li>
            <li>อินเทอร์เน็ต (pypi.org): ${S.internet ? '<span class="ok">✔ เชื่อมต่อได้</span>' : '<span class="bad">✘ เชื่อมต่อไม่ได้ — ต้องใช้ตอนติดตั้งครั้งแรก</span>'}</li>
            <li>Microsoft Edge / Chrome (ใช้พิมพ์ PDF): ${S.edge ? '<span class="ok">✔ พบ</span>' : '<span class="warn">ไม่พบ — ใช้งานอื่นได้ แต่ส่งออก PDF ไม่ได้</span>'}</li>
            <li>ที่เก็บผลลัพธ์: <code>${esc(wsPath)}</code></li></ul>
            <p style="margin-top:10px">แพ็กเกจที่จะติดตั้ง (~${S.download_mb_est} MB ดาวน์โหลด · ~${S.installed_mb_est} MB หลังติดตั้ง):</p>
            <div class="pk">${S.packages.map(p => `<span>${esc(p.name)} ${esc(p.version)}</span>`).join('')}</div></div>
          <div class="card"><h2>ติดตั้ง</h2>
            <div class="bar"><i style="width:${Math.round((P.pct || 0) * 100)}%"></i></div>
            <div class="row" style="justify-content:space-between"><span>${esc(P.step || 'พร้อม')}</span><span>${Math.round((P.pct || 0) * 100)}%</span></div>
            ${P.error ? `<p class="bad">${esc(P.error)}</p>` : ''}
            ${run_ ? `<details ${P.state === 'failed' ? 'open' : ''} style="margin-top:10px"><summary style="cursor:pointer;color:#b5b8d0;font-size:13px">บันทึกการติดตั้ง</summary><pre id="suLog">${esc((P.log || []).join('\n'))}</pre></details>` : ''}</div>
          <div class="row">${P.state === 'running' ? '' : `<button class="btn ghost" id="suBack">← กลับ</button>`}
            ${P.state === 'done' ? '' : `<button class="btn" id="suInstall" ${P.state === 'running' || !S.internet ? 'disabled' : ''}>${P.state === 'failed' ? 'ลองอีกครั้ง' : P.state === 'running' ? 'กำลังติดตั้ง…' : 'ติดตั้ง'}</button>`}
            ${P.state === 'done' ? '<button class="btn" id="suGo">ติดตั้งเสร็จ — เริ่มใช้งาน →</button>' : ''}</div>`;
      }
      if (step === 3) body = `<div class="card"><h2>กำลังเปิดตัวประมวลผล…</h2><p id="suWait">รอสักครู่ หน้านี้จะเปิดแอปให้เอง</p></div>`;
      el.innerHTML = `<div class="wrap"><div class="eb">AINULINDALË · ตัวช่วยติดตั้ง</div><h1>ติดตั้งตัวประมวลผลในเครื่องนี้</h1>
        <p class="lead">เครื่อง <b>${esc(S.machine || '')}</b> · โฟลเดอร์แอป <code>${esc(S.root)}</code></p>${steps}${body}</div>`;
      bind();
    };
    const checkWs = async () => {
      const box = el.querySelector('#suChk'); if (!box) return;
      try {
        chk = await call('/api/setup/check_path', { path: wsPath });
        box.innerHTML = chk.ok ? `<span class="ok">✔ ใช้ได้</span>${chk.free_gb != null ? ` · ว่าง ${chk.free_gb} GB` : ''}${chk.exists ? '' : ' · จะสร้างโฟลเดอร์ใหม่'}`
          + (chk.warn || []).map(w => `<div class="warn">⚠ ${esc(w)}</div>`).join('') : `<span class="bad">✘ ${esc(chk.error)}</span>`;
      } catch (e) { box.innerHTML = `<span class="bad">${esc(e.message)}</span>`; chk = null; }
      const n = el.querySelector('#suNext'); if (n) n.disabled = !chk?.ok;
      const tl = el.querySelector('#suTreeWs'); if (tl) tl.innerHTML = treeWs();
    };
    let pollT = null;
    const poll = async () => {
      clearTimeout(pollT);
      try { S._p = await call('/api/setup/progress'); } catch { }
      if (step === 2) {
        const keepOpen = el.querySelector('details')?.open;
        draw();
        if (keepOpen) { const d = el.querySelector('details'); if (d) d.open = true; }
        const lg = el.querySelector('#suLog'); if (lg) lg.scrollTop = lg.scrollHeight;
      }
      if (S._p?.state === 'running') pollT = setTimeout(poll, 1200);
    };
    const bind = () => {
      const q = s => el.querySelector(s);
      if (q('#suAgree')) q('#suAgree').onchange = e => { agreed = e.target.checked; q('#suNext').disabled = !agreed; };
      el.querySelectorAll('.opt').forEach(o => o.onclick = e => {
        if (e.target.tagName === 'INPUT' && e.target.type === 'text' || e.target.tagName === 'BUTTON') return;
        wsMode = o.dataset.m; if (wsMode === 'inside') wsPath = S.default_workspace; draw(); checkWs();
      });
      if (q('#suPath')) q('#suPath').oninput = e => { wsPath = e.target.value.trim(); clearTimeout(q('#suPath')._t); q('#suPath')._t = setTimeout(checkWs, 400); };
      el.querySelectorAll('[data-d]').forEach(b => b.onclick = () => { wsPath = b.dataset.d + 'Ainulindale_workspace'; draw(); checkWs(); });
      if (q('#suBack')) q('#suBack').onclick = () => { step--; draw(); if (step === 1) checkWs(); };
      if (q('#suNext')) q('#suNext').onclick = () => { step++; draw(); if (step === 1) checkWs(); if (step === 2) poll(); };
      if (q('#suInstall')) q('#suInstall').onclick = async () => {
        try { await call('/api/setup/install', { workspace: wsPath }); poll(); } catch (e) { alert(e.message); }
      };
      if (q('#suGo')) q('#suGo').onclick = async () => {
        step = 3; draw();
        try { await call('/api/setup/start_engine', {}); } catch (e) { q('#suWait').textContent = e.message; return; }
        for (let i = 0; i < 90; i++) {                         // รอตัวประมวลผลจริงขึ้นแทนที่ (พอร์ตเดิม)
          await new Promise(r => setTimeout(r, 1000));
          try { const h = await (await fetch(ENGINE + '/api/engine/hello')).json(); if (h.mode === 'engine') { location.reload(); return; } } catch { }
        }
        el.querySelector('#suWait').textContent = 'ตัวประมวลผลยังไม่ขึ้น — ปิดหน้าต่าง Ainulindale แล้วเปิด Ainulindale.bat ใหม่';
      };
    };
    S.machine = (await call('/api/engine/hello')).machine;
    S._p = await call('/api/setup/progress');
    if (S._p.state === 'running' || S._p.state === 'done') step = 2;  // เปิดหน้าใหม่ระหว่างติดตั้ง → ไปหน้าความคืบหน้าเลย
    draw();
    if (step === 2) poll();
    return new Promise(() => { });                                 // ไม่คืนค่า: แอปหลักไม่เริ่มจนกว่าจะติดตั้งเสร็จ
  }
  return { run };
})();
