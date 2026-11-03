import { api } from './api.js';
import { append, h, icon, toast, fmtDate, s10 } from './dom.js';
const add = (el, ...kids) => append(el, kids);   // native Element.append would print arrays/false as text
import { band, bandLabel } from './charts.js';

export const portal = () => document.documentElement.dataset.portal;

export function statusChip(status) {
  const m = { PENDING: ['warn', 'clock', 'Pending'], RESUBMITTED: ['warn', 'refresh', 'Rescoring'], QUEUED: ['grey', 'clock', 'Queued'], SCORED: ['', 'check', 'Scored'] }[status] || ['grey', 'file', status];
  return h('span', { class: 'chip ' + m[0] }, icon(m[1], 12), m[2]);
}
export const chips = (tags, cls = 'skill') => h('div', { class: 'chips' }, (tags || []).map((t) => h('span', { class: 'chip ' + cls }, t)));
export function typeIcon(t) { return icon(t === 'GITHUB' ? 'github' : t === 'PORTFOLIO' ? 'globe' : 'award', 14); }
export const typeLabel = (t) => ({ GITHUB: 'GitHub repository', PORTFOLIO: 'Portfolio link', CERTIFICATE: 'Certificate' }[t] || t);

export function scorePill(n10, small = false) {
  return h('span', { class: 'score-pill ' + band(n10), title: bandLabel(n10, portal()) }, s10(n10), h('span', { class: 'sr-only' }, ' out of 10, ' + bandLabel(n10, portal())));
}
export function subScoreBars(subs) {
  return h('div', null, subs.map((s) => h('div', { style: 'margin-bottom:12px' },
    h('div', { class: 'row between small', style: 'margin-bottom:4px' }, h('span', null, s.label), h('span', { class: 'mono mute' }, `${s.score.toFixed(1)} / ${s.max}`)),
    h('div', { class: 'bar', role: 'img', 'aria-label': `${s.label}: ${s.score.toFixed(1)} of ${s.max}` }, h('i', { style: `width:${Math.min(100, (s.score / s.max) * 100)}%` })))));
}
export function assessmentChip(a) {
  const m = { valid: ['', 'check', 'Assessment valid'], due_soon: ['warn', 'clock', `Assessment expires in ${a.days_left} days`], expired: ['bad', 'alert', 'Assessment expired - provisional'],
    failed: ['bad', 'alert', 'Assessment not passed - provisional'], not_started: ['warn', 'alert', 'Assessment not taken - provisional'] }[a.status] || ['grey', 'file', a.status];
  return h('span', { class: 'chip ' + m[0] }, icon(m[1], 12), m[2]);
}
export const empty = (msg, ...extra) => h('div', { class: 'empty' }, h('p', null, msg), extra);
export function spinner(label) {
  return h('div', { class: 'row', role: 'status' }, h('span', { class: 'spin', style: 'display:inline-flex;color:var(--accent)' }, icon('refresh', 18)), h('span', { class: 'mute' }, label),
    h('span', { class: 'typing', 'aria-hidden': 'true' }, h('i'), h('i'), h('i')));
}
export function skeleton() {
  return h('div', { role: 'status', 'aria-busy': 'true' }, h('span', { class: 'sr-only' }, 'Loading'), h('div', { class: 'skeleton title' }), h('div', { class: 'skeleton line', style: 'width:70%' }),
    h('div', { class: 'grid3', style: 'margin-top:18px' }, [1, 2, 3].map(() => h('div', { class: 'skeleton block' }))));
}
export function card(children, { chrome = null, cls = '' } = {}) {
  const dots = ['#f85149', '#d29922', '#3fb950'].map((c) => h('span', { class: 'dot', style: `background:${c}` }));
  return h('section', { class: 'card ' + cls }, chrome && h('div', { class: 'card-chrome', 'aria-hidden': 'true' }, dots, h('span', { style: 'margin-left:8px' }, chrome)), h('div', { class: 'card-body' }, children));
}
export function pageHead(title, sub, actions) {
  return h('div', { class: 'row between', style: 'margin-bottom:20px' }, h('div', null, h('h1', { class: 'cm cm-caret' }, title), sub && h('p', { class: 'mute', style: 'margin-top:4px' }, sub)), actions);
}

// Certificates are opened through short-lived signed URLs; evidence links open safely in a new tab.
export function evidenceList(evidence) {
  return h('div', null, evidence.map((e) => h('div', { class: 'row', style: 'align-items:flex-start;margin-bottom:10px;gap:10px;flex-wrap:nowrap' },
    h('span', { class: 'mute', style: 'margin-top:3px' }, typeIcon(e.type)),
    h('div', { class: 'grow' },
      h('div', { class: 'small mute' }, typeLabel(e.type)),
      e.url && h('a', { href: e.url, target: '_blank', rel: 'noopener noreferrer', style: 'word-break:break-all' }, e.url),
      e.has_file && h('div', null, h('button', { class: 'btn ghost small', type: 'button', onclick: async () => {
        try { const r = await api('GET', `/evidence/${e.id}/file-url`); window.open(r.url, '_blank', 'noopener'); } catch (err) { toast(err.message, { error: true }); }
      } }, icon('download', 12), e.file_name || 'Open file')),
      e.description && h('div', { class: 'small', style: 'margin-top:2px' }, e.description)))));
}

// Full score presentation used by candidates (with advice) and recruiters (without).
export function scoreView(sc, { advice = true, animate = true } = {}) {
  const left = h('div', { class: 'stack' },
    h('div', { class: 'row', style: 'gap:20px' }, scoreRingEl(sc.out_of_10, 120, animate),
      h('div', null, h('div', { class: 'small mute' }, 'ProofScore'), h('div', { style: 'font-size:16px;font-weight:600' }, bandLabel(sc.out_of_10, portal())),
        h('div', { class: 'small mute', style: 'max-width:220px;margin-top:4px' }, 'Quality and relevance of the evidence - not a hiring decision.'))),
    radarEl(sc.sub_scores), subScoreBars(sc.sub_scores));
  const right = h('div', null);
  if (sc.strengths.length) add(right, h('h3', { class: 'cm', style: 'margin-bottom:8px' }, 'Strengths'),
    sc.strengths.map((s) => h('div', { class: 'good-item' }, icon('check', 14), h('span', null, s))), h('div', { class: 'spacer' }));
  if (advice) add(right, h('h3', { class: 'cm', style: 'margin-bottom:8px' }, 'Recommended actions'),
    sc.recommendations.length ? sc.recommendations.map((r) => h('div', { class: 'rec' }, h('div', { class: 'lbl' }, `${r.label}${r.potential_gain ? ' - up to +' + r.potential_gain.toFixed(1) + ' pts' : ''}`), h('div', null, r.text)))
      : h('p', { class: 'mute' }, 'No major gaps found. Nice work.'));
  else if (sc.gaps && sc.gaps.length) add(right, h('h3', { class: 'cm', style: 'margin-bottom:8px' }, 'Areas still developing'), chips(sc.gaps, 'warn'));
  add(right, h('details', { style: 'margin-top:18px' }, h('summary', { class: 'mute small', style: 'cursor:pointer' }, 'What was measured'),
    h('ul', { class: 'small', style: 'padding-left:18px' }, sc.facts.map((f) => h('li', null, f))),
    h('p', { class: 'footer-note' }, `Scored by ${sc.model_version}${sc.model_version === 'demo-seed' ? ' (demo data)' : ''} - data quality: ${sc.data_quality}. Prototype model trained on synthetic data; treat scores as indicative.`)));
  return h('div', { class: 'grid2' + (animate ? ' anim' : '') }, left, right);
}
import { scoreRing as scoreRingEl, radar as radarEl } from './charts.js';
export { fmtDate };
