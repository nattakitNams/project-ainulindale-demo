// Ainulindalë — สองภาษา (ไทย / English)
// หน้าเว็บเขียนเป็นภาษาไทย → เลือก EN แล้วแปลตอนแสดงผล: แทนข้อความไทยด้วยพจนานุกรม (web/i18n_en.js) แบบชิ้นยาวสุดก่อน
// ครอบทุกอย่างที่ขึ้นจอ (หน้า, หน้าต่างถาม-ตอบ, toast, ข้อความจากตัวประมวลผล) ด้วย MutationObserver
// ไม่แปลเนื้อหาของผู้ใช้/ต้นทาง: ชื่อชุดข้อมูล ชื่อหน่วยงาน คำอธิบายจาก Data hub ฯลฯ — ใส่ translate="no" หรือ class ใน SKIP
'use strict';
const I18N = (() => {
  let lang = 'th';
  try { lang = localStorage.getItem('ainu-lang') || 'th'; } catch { }   // ค่าเริ่มต้นไทย · เลือก EN ไว้ → จำไว้
  const SKIP = '[translate="no"], script, style, code, textarea, .hub-desc, .hub-url, .name, .path, .mono, .vname, .leaflet-tile-pane, .rpt-page';
  const TH = /[฀-๿]/;
  let re = null, reShort = null, dict = null;
  const rx = k => k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  function build() {
    dict = window.I18N_EN || {};
    const keys = Object.keys(dict).filter(k => dict[k]).sort((a, b) => b.length - a.length);
    if (!keys.length) return;
    // คำยาว: แทนได้ทุกที่ (ยาวสุดก่อน) · คำสั้น (≤ 5 ตัว เช่น "สี" "ลบ" "ชั้น"): แทนเฉพาะเมื่อไม่ติดอักษรไทยข้างหน้า/หลัง
    // — ภาษาไทยไม่เว้นวรรคระหว่างคำ ไม่งั้นจะไปแทนกลางคำอื่นหรือกลางชื่อข้อมูลของผู้ใช้
    const long = keys.filter(k => k.length > 5), short = keys.filter(k => k.length <= 5);
    re = long.length ? new RegExp(long.map(rx).join('|'), 'g') : null;
    reShort = short.length ? new RegExp(`(?<![\\u0E00-\\u0E7F])(?:${short.map(rx).join('|')})(?![\\u0E00-\\u0E7F])`, 'g') : null;
  }
  // ตัวเลือกที่ผูกกับข้อมูล (value เป็นเลข id เช่น ชุดข้อมูล/พื้นที่ศึกษา): ส่วนแรกก่อน " · " คือชื่อของผู้ใช้ → ไม่แปล แปลเฉพาะส่วนต่อท้าย
  const trText = (s, el) => {
    if (el && el.tagName === 'OPTION' && /^\d+$/.test(el.value || '') && !/^[\s\d.≈~(]/.test(s)) {   // ป้ายความละเอียด (3″, 1.25′) ขึ้นต้นด้วยตัวเลข = ไม่ใช่ชื่อข้อมูล
      const i = s.indexOf(' · ');
      return i < 0 ? s : s.slice(0, i) + tr(s.slice(i));
    }
    return tr(s);
  };
  const tr = s => {
    if (!dict || !TH.test(s)) return s;
    if (re) s = s.replace(re, m => dict[m]);
    if (reShort && TH.test(s)) s = s.replace(reShort, m => dict[m]);
    return s;
  };
  const ATTRS = ['placeholder', 'title', 'aria-label', 'data-tip'];
  function skip(el) { return el && el.closest && el.closest(SKIP); }
  function attrs(el) {
    for (const a of ATTRS) {
      const v = el.getAttribute(a);
      if (v && TH.test(v)) { const t = tr(v); if (t !== v) el.setAttribute(a, t); }
    }
    if (el.tagName === 'INPUT' && (el.type === 'button' || el.type === 'submit') && TH.test(el.value)) el.value = tr(el.value);
  }
  function node(n) {
    if (n.nodeType === 3) {
      if (TH.test(n.nodeValue) && !skip(n.parentElement)) { const v = trText(n.nodeValue, n.parentElement); if (v !== n.nodeValue) n.nodeValue = v; }
      return;
    }
    if (n.nodeType !== 1 || skip(n)) return;
    attrs(n);
    const w = document.createTreeWalker(n, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
      acceptNode: x => x.nodeType === 1 && x.matches(SKIP) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT });
    let x;
    while ((x = w.nextNode())) {
      if (x.nodeType === 3) { if (TH.test(x.nodeValue)) { const v = trText(x.nodeValue, x.parentElement); if (v !== x.nodeValue) x.nodeValue = v; } }
      else attrs(x);
    }
  }
  function start() {
    document.documentElement.lang = lang;
    if (lang !== 'en') return;
    build();
    if (!re && !reShort) return;
    node(document.body);
    new MutationObserver(ms => {
      for (const m of ms) {
        if (m.type === 'characterData' || m.type === 'attributes') node(m.target);
        else m.addedNodes.forEach(node);
      }
    }).observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS });
    const _alert = window.alert, _confirm = window.confirm;
    window.alert = m => _alert(tr(String(m)));
    window.confirm = m => _confirm(tr(String(m)));
  }
  function set(l) { try { localStorage.setItem('ainu-lang', l); } catch { } location.reload(); }
  // ปุ่มสลับภาษา: <span data-lang-switch></span> ที่ไหนก็ได้
  function switches() {
    if (!document.querySelector('.lang-float')) {             // ลอยมุมขวาบน — แสดงเฉพาะตอนหน้าเชื่อมต่อ/ติดตั้งบังหน้าแอป (CSS :has)
      const f = document.createElement('div');
      f.className = 'lang-float'; f.setAttribute('data-lang-switch', '');
      document.body.appendChild(f);
    }
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
