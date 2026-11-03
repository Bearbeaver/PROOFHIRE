// Tiny DOM toolkit. Text is always inserted as text nodes (never innerHTML), so user content cannot inject markup.
export function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'value' || k === 'checked' || k === 'selected' || k === 'disabled') el[k] = v;
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, v);
  }
  append(el, kids);
  return el;
}
export function append(el, kids) {
  for (const k of kids.flat(Infinity)) {
    if (k == null || k === false) continue;
    el.append(k instanceof Node ? k : document.createTextNode(String(k)));
  }
  return el;
}
export function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }
// Replace an element's children. Unlike native replaceChildren this flattens arrays and skips null/false (so `cond && node` is safe).
export function put(el, ...kids) { clear(el); append(el, kids); return el; }

const SVGNS = 'http://www.w3.org/2000/svg';
export function svg(tag, attrs, ...kids) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v != null) el.setAttribute(k, v);
  for (const k of kids.flat(Infinity)) if (k) el.append(k instanceof Node ? k : document.createTextNode(String(k)));
  return el;
}
const P = {
  github: 'M9 19c-4.3 1.4-4.3-2.5-6-3m12 5v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.2 4.2 0 0 0-.1-3.2s-1.1-.3-3.5 1.3a12.3 12.3 0 0 0-6.2 0C6.5 2.8 5.4 3.1 5.4 3.1a4.2 4.2 0 0 0-.1 3.2A4.6 4.6 0 0 0 4 9.5c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V21',
  globe: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM2 12h20M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20z',
  award: 'M12 15a6 6 0 1 0 0-12 6 6 0 0 0 0 12zM8.2 13.9 7 23l5-3 5 3-1.2-9.1',
  plus: 'M12 5v14M5 12h14',
  sparkles: 'M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9zM19 15l.7 1.8 1.8.7-1.8.7L19 20l-.7-1.8-1.8-.7 1.8-.7z',
  archive: 'M21 8v13H3V8M1 3h22v5H1zM10 12h4', code: 'M16 18l6-6-6-6M8 6l-6 6 6 6', grid: 'M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z',
  briefcase: 'M20 7H4a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2zM16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16',
  message: 'M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z', check: 'M20 6 9 17l-5-5', x: 'M18 6 6 18M6 6l12 12',
  alert: 'M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01',
  sun: 'M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4',
  moon: 'M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z',
  bell: 'M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0',
  logout: 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9',
  search: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.3-4.3',
  chevron: 'M9 18l6-6-6-6', bookmark: 'M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z',
  file: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6',
  clock: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 6v6l4 2', terminal: 'M4 17l6-6-6-6M12 19h8',
  building: 'M3 21h18M5 21V5l7-3 7 3v16M9 9h2M13 9h2M9 13h2M13 13h2M9 17h2M13 17h2',
  shield: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z', arrow: 'M5 12h14M12 5l7 7-7 7', refresh: 'M23 4v6h-6M1 20v-6h6M3.5 9a9 9 0 0 1 15-3.4L23 10M1 14l4.5 4.4A9 9 0 0 0 20.5 15',
  flag: 'M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1zM4 22v-7', up: 'M7 17 17 7M7 7h10v10', download: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3',
};
export function icon(name, size = 16) {
  return svg('svg', { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true', focusable: 'false' },
    svg('path', { d: P[name] || P.file }));
}

// ---------------------------------------------------------------- formatting
const MIN = 60e3, HR = 3600e3, DAY = 864e5;
export function ago(iso) {
  const d = Date.now() - new Date(iso).getTime();
  if (d < MIN) return 'just now';
  if (d < HR) return `${Math.floor(d / MIN)} min ago`;
  if (d < DAY) return `${Math.floor(d / HR)} h ago`;
  if (d < 30 * DAY) return `${Math.floor(d / DAY)} day${Math.floor(d / DAY) === 1 ? '' : 's'} ago`;
  return fmtDate(iso);
}
export function fmtDate(iso) { return iso ? new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) : '-'; }
export function fmtDateTime(iso) { return iso ? new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '-'; }
export const s10 = (n) => (Math.round(n * 10) / 10).toFixed(1);

// ---------------------------------------------------------------- toasts & dialogs
const reduced = () => window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
// Animated number: eases from 0 to `to` (instant when the user prefers reduced motion).
export function countUp(el, to, { decimals = 0, ms = 900, suffix = '' } = {}) {
  const fmt = (v) => v.toFixed(decimals) + suffix;
  if (reduced() || !Number.isFinite(to)) { el.textContent = fmt(Number.isFinite(to) ? to : 0); return; }
  const t0 = performance.now();
  el.textContent = fmt(0);
  const step = (t) => { const p = Math.min(1, (t - t0) / ms); el.textContent = fmt(to * (1 - Math.pow(1 - p, 3))); if (p < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
}
export function toast(msg, { error = false, action = null, ms = 4500 } = {}) {
  const box = document.getElementById('toasts');
  const dismiss = () => { t.classList.add('out'); setTimeout(() => t.remove(), 220); };
  const t = h('div', { class: 'toast' + (error ? ' error' : '') }, h('span', null, msg),
    action && h('button', { type: 'button', onclick: () => { dismiss(); action.onClick(); } }, action.label));
  box.append(t);
  setTimeout(dismiss, action ? ms + 3000 : ms);
}
function modal(build) {
  return new Promise((resolve) => {
    const dlg = h('dialog');
    const done = (v) => { dlg.close(); dlg.remove(); resolve(v); };
    build(dlg, done);
    dlg.addEventListener('cancel', (e) => { e.preventDefault(); done(null); });
    document.body.append(dlg);
    dlg.showModal();
  });
}
export function confirmBox({ title, text, confirm = 'Confirm', danger = false }) {
  return modal((dlg, done) => append(dlg, [h('h2', null, title), h('p', { class: 'mute', style: 'margin:10px 0 18px' }, text),
    h('div', { class: 'row', style: 'justify-content:flex-end' },
      h('button', { class: 'btn ghost', type: 'button', onclick: () => done(false) }, 'Cancel'),
      h('button', { class: 'btn' + (danger ? ' danger' : ''), type: 'button', autofocus: true, onclick: () => done(true) }, confirm))]));
}
export function askReason({ title, text, label = 'Reason', confirm = 'Confirm', danger = false, required = true }) {
  return modal((dlg, done) => {
    const ta = h('textarea', { id: 'reason-box', rows: 3, maxlength: 300 });
    const err = h('div', { class: 'err small', style: 'color:var(--bad)' });
    append(dlg, [h('h2', null, title), text && h('p', { class: 'mute', style: 'margin:8px 0' }, text),
      h('div', { class: 'field', style: 'margin-top:12px' }, h('label', { for: 'reason-box' }, label), ta, err),
      h('div', { class: 'row', style: 'justify-content:flex-end' },
        h('button', { class: 'btn ghost', type: 'button', onclick: () => done(null) }, 'Cancel'),
        h('button', { class: 'btn' + (danger ? ' danger' : ''), type: 'button', onclick: () => {
          if (required && ta.value.trim().length < 3) { err.textContent = 'Please give a short reason (at least 3 characters).'; ta.focus(); return; }
          done(ta.value.trim());
        } }, confirm))]);
    setTimeout(() => ta.focus(), 0);
  });
}

// ---------------------------------------------------------------- form helpers
export function field(label, input, { id, error, help } = {}) {
  const wrap = h('div', { class: 'field' + (error ? ' invalid' : '') }, h('label', { for: id }, label), input,
    help && h('div', { class: 'help', id: id && id + '-help' }, help), error && h('div', { class: 'err', role: 'alert', id: id && id + '-err' }, error));
  if (id && error) input.setAttribute('aria-describedby', id + '-err');
  if (error) input.setAttribute('aria-invalid', 'true');
  return wrap;
}
export function option(value, label, selected) { return h('option', { value, selected: !!selected }, label); }
