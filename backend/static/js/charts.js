import { countUp, svg } from './dom.js';

export const band = (n10) => (n10 >= 7 ? 'good' : n10 >= 5 ? 'warn' : 'bad');
export function bandLabel(n10, portal) {
  const b = band(n10);
  return portal === 'candidate' ? { good: 'build passing', warn: 'needs work', bad: 'build failing' }[b]
    : { good: 'Strong evidence', warn: 'Developing evidence', bad: 'Needs more evidence' }[b];
}
const COLOR = { good: 'var(--accent)', warn: 'var(--warn)', bad: 'var(--bad)' };

export function scoreRing(n10, size = 120, animate = true) {
  const r = (size - 14) / 2, c = 2 * Math.PI * r, mid = size / 2;
  const out = svg('svg', { width: size, height: size, viewBox: `0 0 ${size} ${size}`, role: 'img', 'aria-label': `ProofScore ${n10.toFixed(1)} out of 10` },
    svg('circle', { class: 'ring-track', cx: mid, cy: mid, r, 'stroke-width': 8 }),
    svg('circle', { class: 'ring-arc', cx: mid, cy: mid, r, 'stroke-width': 8, stroke: COLOR[band(n10)], 'stroke-dasharray': `${(c * n10) / 10} ${c}`, style: `--c:${c}px;--to:${(c * n10) / 10}px`, transform: `rotate(-90 ${mid} ${mid})` }),
    svg('text', { class: 'ring-text', x: mid, y: mid * 0.98, 'text-anchor': 'middle', 'dominant-baseline': 'middle', 'font-size': size * 0.26 }, n10.toFixed(1)),
    svg('text', { class: 'ring-sub', x: mid, y: mid * 1.38, 'text-anchor': 'middle', 'dominant-baseline': 'middle', 'font-size': size * 0.1 }, '/ 10'));
  if (animate) countUp(out.querySelector('.ring-text'), n10, { decimals: 1, ms: 1100 });
  return out;
}

const SHORT = { relevance: 'Relevance', technical_quality: 'Tech quality', complexity: 'Complexity', code_quality: 'Code quality', documentation: 'Docs', testing: 'Testing', impact: 'Impact' };
export function radar(subs, size = 240) {
  const n = subs.length, mid = size / 2, R = size * 0.34;
  const pt = (i, f) => [mid + Math.sin((2 * Math.PI * i) / n) * R * f, mid - Math.cos((2 * Math.PI * i) / n) * R * f];
  const poly = (f) => subs.map((_, i) => pt(i, f).join(',')).join(' ');
  const desc = subs.map((s) => `${s.label} ${s.score.toFixed(1)} of ${s.max}`).join('; ');
  const el = svg('svg', { width: '100%', viewBox: `-60 0 ${size + 120} ${size}`, style: `max-width:${size + 140}px`, role: 'img', 'aria-label': 'Score breakdown radar chart: ' + desc },
    [0.25, 0.5, 0.75, 1].map((f) => svg('polygon', { class: 'radar-grid', points: poly(f) })),
    subs.map((_, i) => svg('line', { class: 'radar-grid', x1: mid, y1: mid, x2: pt(i, 1)[0], y2: pt(i, 1)[1] })),
    svg('polygon', { class: 'radar-shape', points: subs.map((s, i) => pt(i, s.score / s.max).join(',')).join(' ') }),
    subs.map((s, i) => { const [x, y] = pt(i, 1.2); return svg('text', { class: 'radar-label', x, y, 'text-anchor': x < mid - 4 ? 'end' : x > mid + 4 ? 'start' : 'middle', 'dominant-baseline': 'middle' }, SHORT[s.key] || s.label); }));
  return el;
}

export function barChart(data, height = 150) {
  const w = 420, pad = 22, max = Math.max(1, ...data.map((d) => d.count)), bw = (w - pad * 2) / data.length;
  return svg('svg', { class: 'bars-anim', width: '100%', viewBox: `0 0 ${w} ${height + 26}`, role: 'img', 'aria-label': 'Submissions per day: ' + data.map((d) => `${d.date}: ${d.count}`).join(', ') },
    data.map((d, i) => {
      const bh = (d.count / max) * (height - 22), x = pad + i * bw + bw * 0.18;
      return [svg('rect', { x, y: height - bh, width: bw * 0.64, height: Math.max(bh, 1), fill: 'var(--accent)', rx: 2 }),
        svg('text', { x: x + bw * 0.32, y: height - bh - 5, 'text-anchor': 'middle', class: 'radar-label' }, d.count),
        svg('text', { x: x + bw * 0.32, y: height + 16, 'text-anchor': 'middle', class: 'radar-label' }, d.date.slice(5))];
    }));
}
