// Ainulindalë — สองภาษา (ไทย / English)
// หน้าเว็บเขียนเป็นภาษาไทย → เลือก EN แล้วแปลตอนแสดงผล: แทนข้อความไทยด้วยพจนานุกรม (web/i18n_en.js) แบบชิ้นยาวสุดก่อน
// ครอบทุกอย่างที่ขึ้นจอ (หน้า, หน้าต่างถาม-ตอบ, toast, ข้อความจากตัวประมวลผล) ด้วย MutationObserver
// ไม่แปลเนื้อหาของผู้ใช้/ต้นทาง: ชื่อชุดข้อมูล ชื่อหน่วยงาน คำอธิบายจาก Data hub ฯลฯ — ใส่ translate="no" หรือ class ใน SKIP
'use strict';
const I18N = (() => {
  let lang = 'th';
  try { lang = localStorage.getItem('ainu-lang') || 'th'; } catch { }   // ค่าเริ่มต้นไทย · เลือก EN ไว้ → จำไว้   // เลือกไว้ → ตามนั้น · ไม่เคยเลือก → ตามภาษาเบราว์เซอร์
  const SKIP = '[translate="no"], script, style, code, textarea, .hub-desc, .hub-url, .name, .path, .mono, .vname, .leaflet-tile-pane, .rpt-page';
  let re = null, dict = null;
  const TH = /[฀-๿]/;
  function build() {
    dict = window.I18N_EN || {};
    const keys = Object.keys(dict).filter(k => dict[k]).sort((a, b) => b.length - a.length);
    if (!keys.length) return;
    re = new RegExp(keys.map(k => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'g');
  }
  const tr = s => (re && TH.test(s)) ? s.replace(re, m => dict[m]) : s;
  function skip(el) { return el && el.closest && el.closest(SKIP); }
  function node(n) {
    if (n.nodeType === 3) {
      if (TH.test(n.nodeValue) && !skip(n.parentElement)) { const v = tr(n.nodeValue); if (v !== n.nodeValue) n.nodeValue = v; }
      return;
    }
    if (n.nodeType !== 1 || skip(n)) return;
    for (const a of ['placeholder', 'title', 'aria-label', 'data-tip']) {
      const v = n.getAttribute(a);
      if (v && TH.test(v)) n.setAttribute(a, tr(v));
    }
    if ((n.tagName === 'INPUT' && (n.type === 'button' || n.type === 'submit')) && TH.test(n.value)) n.value = tr(n.value);
    const w = document.createTreeWalker(n, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
      acceptNode: x => x.nodeType === 1 && x.matches(SKIP) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT });
    let x;
    while ((x = w.nextNode())) {
      if (x.nodeType === 3) { if (TH.test(x.nodeValue)) { const v = tr(x.nodeValue); if (v !== x.nodeValue) x.nodeValue = v; } }
      else for (const a of ['placeholder', 'title', 'aria-label', 'data-tip']) {
        const v = x.getAttribute(a);
        if (v && TH.test(v)) x.setAttribute(a, tr(v));
      }
    }
  }
  function start() {
    document.documentElement.lang = lang;
    if (lang !== 'en') return;
    build();
    if (!re) return;
    node(document.body);
    new MutationObserver(ms => {
      for (const m of ms) {
        if (m.type === 'characterData') node(m.target);
        else if (m.type === 'attributes') node(m.target);
        else m.addedNodes.forEach(node);
      }
    }).observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['placeholder', 'title', 'aria-label', 'data-tip'] });
    const _alert = window.alert, _confirm = window.confirm;
    window.alert = m => _alert(tr(String(m)));
    window.confirm = m => _confirm(tr(String(m)));
  }
  function set(l) { try { localStorage.setItem('ainu-lang', l); } catch { } location.reload(); }
  // ปุ่มสลับภาษา: <span data-lang-switch></span> ที่ไหนก็ได้
  function switches() {
    document.querySelectorAll('[data-lang-switch]').forEach(el => {
      el.setAttribute('translate', 'no');
      el.classList.add('lang-sw');
      el.innerHTML = `<button data-l="th" class="${lang === 'th' ? 'on' : ''}" title="ภาษาไทย">TH</button><button data-l="en" class="${lang === 'en' ? 'on' : ''}" title="English">EN</button>`;
      el.querySelectorAll('button').forEach(b => b.onclick = () => b.dataset.l !== lang && set(b.dataset.l));
    });
  }
  return { get lang() { return lang; }, tr, start, set, switches, locale: () => lang === 'en' ? 'en-GB' : 'th-TH' };
})();
document.addEventListener('DOMContentLoaded', () => { I18N.switches(); I18N.start(); });
