import { api, session } from './api.js';
import { h, svg, toast } from './dom.js';

// ---------------------------------------------------------------- per-portal animated backdrops
// candidate = IT (code rain + network), recruiter = corporate (skyline + growth chart + org tree), admin = ops/fix (gears + radar + status LEDs).
const GL = '01{}<>/=;$#λ∑≈'.split('');
function gear(g, cx, cy, r, teeth, rot) {
  g.beginPath();
  for (let i = 0; i < teeth * 2; i++) { const a = rot + (i * Math.PI) / teeth, q = i % 2 ? r : r * 1.2; g.lineTo(cx + Math.cos(a) * q, cy + Math.sin(a) * q); }
  g.closePath(); g.stroke(); g.beginPath(); g.arc(cx, cy, r * .45, 0, 7); g.stroke();
}
const SCENES = {
  candidate: {
    trail: true,
    init: (w, h) => ({ cols: Array.from({ length: Math.ceil(w / 18) }, () => Math.random() * -h / 14),
      nodes: Array.from({ length: Math.min(55, Math.round(w / 28)) }, () => ({ x: Math.random() * w, y: Math.random() * h, vx: (Math.random() - .5) * .35, vy: (Math.random() - .5) * .35 })) }),
    draw(g, w, h, t, acc, S) {
      g.font = '14px "JetBrains Mono", monospace'; g.fillStyle = acc; g.globalAlpha = .22;
      S.cols.forEach((y, i) => { g.fillText(GL[(Math.random() * GL.length) | 0], i * 18, y * 14); S.cols[i] = y * 14 > h && Math.random() > .975 ? 0 : y + .45; });
      g.strokeStyle = acc; g.lineWidth = 1;
      S.nodes.forEach((n, i) => {
        n.x = (n.x + n.vx + w) % w; n.y = (n.y + n.vy + h) % h;
        for (let j = i + 1; j < S.nodes.length; j++) {
          const m = S.nodes[j], d = Math.hypot(n.x - m.x, n.y - m.y);
          if (d < 150) { g.globalAlpha = (1 - d / 150) * .35; g.beginPath(); g.moveTo(n.x, n.y); g.lineTo(m.x, m.y); g.stroke();
            const p = (t / 90 + i * .37) % 1; g.globalAlpha = (1 - d / 150) * .9; g.fillRect(n.x + (m.x - n.x) * p - 1.5, n.y + (m.y - n.y) * p - 1.5, 3, 3); }
        }
        g.globalAlpha = .7; g.fillRect(n.x - 2, n.y - 2, 4, 4);
      });
    },
  },
  recruiter: {
    init: (w, h) => { const b = []; for (let x = 0; x < w; x += 0) { const bw = 36 + Math.random() * 54; b.push({ x, w: bw, h: 90 + Math.random() * Math.min(300, h * .4), lit: Math.random() }); x += bw + 6; } return { b }; },
    draw(g, w, h, t, acc, S) {
      g.strokeStyle = acc; g.fillStyle = acc; g.lineWidth = 1;
      S.b.forEach((b) => {                                   // skyline with blinking office windows
        g.globalAlpha = .22; g.strokeRect(b.x, h - b.h, b.w, b.h);
        for (let wy = h - b.h + 10; wy < h - 12; wy += 16) for (let wx = b.x + 8; wx < b.x + b.w - 8; wx += 14) {
          const on = Math.sin(wx * 12.9 + wy * 78.2 + Math.floor(t / 70) * (b.lit + .3)) > .55; g.globalAlpha = on ? .55 : .1; g.fillRect(wx, wy, 6, 8); }
      });
      g.lineWidth = 2; g.globalAlpha = .6; g.beginPath();      // growth chart that keeps drawing itself
      const pts = 48, prog = ((t / 3) % (pts + 30));
      for (let i = 0; i <= Math.min(prog, pts); i++) { const x = w * .08 + (i / pts) * w * .84, y = h * .46 - i * (h * .006) - Math.sin(i * .5 + t / 80) * 14; i ? g.lineTo(x, y) : g.moveTo(x, y); }
      g.stroke(); g.lineWidth = 1;
      for (let k = 0; k < 3; k++) { const cx = w * (.2 + k * .3), cy = h * .14, p = (t / 120 + k * .3) % 1;   // org-chart links
        g.globalAlpha = .3; [-70, 0, 70].forEach((dx) => { g.beginPath(); g.moveTo(cx, cy); g.lineTo(cx + dx, cy + 46); g.stroke(); g.strokeRect(cx + dx - 9, cy + 46, 18, 12); });
        g.strokeRect(cx - 12, cy - 12, 24, 24); g.globalAlpha = .9; g.fillRect(cx - 2 + (p * 140 - 70) * (p > .5 ? 1 : 0), cy + 46 * p, 4, 4); }
    },
  },
  admin: {
    init: () => ({ blips: Array.from({ length: 7 }, () => ({ a: Math.random() * 6.28, r: .15 + Math.random() * .8, seen: -999 })) }),
    draw(g, w, h, t, acc, S) {
      const cx = w * .5, cy = h * .5, R = Math.min(w, h) * .42, sw = t / 55;
      g.strokeStyle = acc; g.fillStyle = acc; g.lineWidth = 1; g.globalAlpha = .2;
      [1, .66, .33].forEach((k) => { g.beginPath(); g.arc(cx, cy, R * k, 0, 7); g.stroke(); });
      g.beginPath(); g.moveTo(cx - R, cy); g.lineTo(cx + R, cy); g.moveTo(cx, cy - R); g.lineTo(cx, cy + R); g.stroke();
      for (let i = 0; i < 28; i++) { const a = sw - i * .02; g.globalAlpha = (1 - i / 28) * .22; g.beginPath(); g.moveTo(cx, cy); g.arc(cx, cy, R, a - .02, a); g.fill(); }
      S.blips.forEach((b) => { const d = (((sw - b.a) % 6.283) + 6.283) % 6.283; if (d < .06) b.seen = t; const age = t - b.seen;
        if (age < 140) { g.globalAlpha = 1 - age / 140; g.beginPath(); g.arc(cx + Math.cos(b.a) * R * b.r, cy + Math.sin(b.a) * R * b.r, 4, 0, 7); g.fill(); } });
      g.globalAlpha = .28; g.lineWidth = 2;                  // meshing gears: the "fix" motif
      gear(g, w * .14, h * .8, 46, 12, t / 120); gear(g, w * .14 + 88, h * .8 - 52, 30, 8, -t / 80 + .2); gear(g, w * .88, h * .2, 56, 14, -t / 150);
      g.lineWidth = 1; for (let i = 0; i < 20; i++) { const on = Math.sin(i * 3.1 + Math.floor(t / 40) * 1.7) > .2; g.globalAlpha = on ? .8 : .15; g.fillRect(w * .5 - 150 + i * 15, h - 28, 8, 8); }
    },
  },
};

export function techBackdrop(kind = 'candidate', { ambient = false } = {}) {
  const sc = SCENES[kind] || SCENES.candidate;
  const cv = h('canvas', { class: 'tech-bg' + (ambient ? ' ambient' : ''), 'aria-hidden': 'true' });
  const g = cv.getContext('2d');
  const still = matchMedia('(prefers-reduced-motion: reduce)').matches;
  let w = 0, h0 = 0, t = 0, S = null;
  const css = (v, d) => getComputedStyle(document.documentElement).getPropertyValue(v).trim() || d;
  const size = () => { w = cv.width = innerWidth; h0 = cv.height = innerHeight; S = sc.init(w, h0); };
  function frame() {
    if (!cv.isConnected) { removeEventListener('resize', size); return; }
    g.globalAlpha = sc.trail ? .16 : 1; g.fillStyle = css('--bg', '#0b1210'); g.fillRect(0, 0, w, h0);
    sc.draw(g, w, h0, t, css('--accent', '#3fb950'), S); g.globalAlpha = 1; t++;
    if (!still) requestAnimationFrame(frame);
  }
  size(); addEventListener('resize', size);
  requestAnimationFrame(() => { g.globalAlpha = 1; g.fillStyle = css('--bg', '#0b1210'); g.fillRect(0, 0, w, h0); frame(); });
  return cv;
}

// ---------------------------------------------------------------- post-login transition
const SPLASH = {
  CANDIDATE: ['$ git push proofhire --verified', 'compiling your evidence locker...', 'workspace ready'],
  RECRUITER: ['Opening your talent pipeline', 'Syncing shortlist and messages', 'Dashboard ready'],
  ADMIN: ['Running system diagnostics', 'Checking queues, registers, audit log', 'All systems operational'],
};
export function welcomeSplash(user) {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return Promise.resolve();
  const lines = SPLASH[user.role] || [];
  const log = h('div', { class: 'splash-log mono' });
  const el = h('div', { class: 'splash', role: 'status', 'aria-live': 'polite' }, techBackdrop(user.role.toLowerCase(), { ambient: true }),
    h('div', { class: 'splash-box' }, h('div', { class: 'splash-ring' }), h('h2', null, `Welcome, ${user.name.split(' ')[0]}`), log, h('div', { class: 'bar splash-bar' }, h('i'))));
  document.body.append(el);
  lines.forEach((l, i) => setTimeout(() => log.append(h('div', null, h('span', { class: 'accent' }, i === lines.length - 1 ? '✓ ' : '› '), l)), 150 + i * 380));
  return new Promise((res) => setTimeout(() => { el.classList.add('out'); setTimeout(() => { el.remove(); res(); }, 280); }, 1450));
}

// ---------------------------------------------------------------- Apple / Google / LinkedIn sign-in
const LOGO = {
  google: () => svg('svg', { viewBox: '0 0 24 24', width: 18, height: 18 }, svg('path', { fill: '#EA4335', d: 'M12 10.2v3.9h5.5c-.2 1.3-1.6 3.8-5.5 3.8a6 6 0 0 1 0-12c1.9 0 3.1.8 3.8 1.5l2.6-2.5A9.6 9.6 0 0 0 12 2.4a9.6 9.6 0 1 0 0 19.2c5.5 0 9.2-3.9 9.2-9.3 0-.6-.1-1.1-.2-1.6z' })),
  apple: () => svg('svg', { viewBox: '0 0 24 24', width: 18, height: 18, fill: 'currentColor' }, svg('path', { d: 'M16.4 12.6c0-2.3 1.9-3.4 2-3.5a4.3 4.3 0 0 0-3.4-1.8c-1.4-.2-2.8.8-3.5.8s-1.8-.8-3-.8a4.5 4.5 0 0 0-3.8 2.3c-1.6 2.8-.4 7 1.2 9.3.8 1.100 1.700 2.400 2.900 2.300 1.200 0 1.600-.7 3-.7s1.800.7 3 .7 2-1.100 2.800-2.300a9.700 9.700 0 0 0 1.300-2.600 4 4 0 0 1-2.500-3.700zM14.100 5.800A4 4 0 0 0 15 3a4 4 0 0 0-2.600 1.400 3.800 3.800 0 0 0-1 2.700 3.300 3.300 0 0 0 2.700-1.300z' })),
  linkedin: () => svg('svg', { viewBox: '0 0 24 24', width: 18, height: 18 }, svg('path', { fill: '#0A66C2', d: 'M20.4 2H3.6A1.600 1.600 0 0 0 2 3.600v16.800A1.600 1.600 0 0 0 3.600 22h16.800a1.600 1.600 0 0 0 1.600-1.600V3.600A1.600 1.600 0 0 0 20.400 2zM8 19H5V9.500h3zM6.500 8.200a1.700 1.700 0 1 1 0-3.400 1.700 1.700 0 0 1 0 3.400zM19 19h-3v-4.600c0-1.100 0-2.500-1.500-2.500S13 13.100 13 14.300V19h-3V9.500h2.800v1.300a3.100 3.100 0 0 1 2.800-1.500c3 0 3.600 2 3.600 4.600z' })),
};
const NAME = { google: 'Google', apple: 'Apple', linkedin: 'LinkedIn' };

// Stand-in for the OAuth consent step: asks which account to use, then calls POST /auth/social.
// Replace chooser() with a real redirect to each provider once OAuth client IDs are configured.
export function socialSignIn({ role, mode, extras, onDone }) {
  function chooser(provider) {
    const email = h('input', { type: 'email', id: 'so-email', placeholder: 'you@example.com', autocomplete: 'email' });
    const err = h('div', { class: 'err small', role: 'alert', style: 'color:var(--bad);min-height:18px' });
    const dlg = h('div', { class: 'so-overlay', role: 'dialog', 'aria-modal': 'true', 'aria-label': `Continue with ${NAME[provider]}` },
      h('div', { class: 'card so-dialog' }, h('div', { class: 'row', style: 'gap:10px;margin-bottom:12px' }, LOGO[provider](), h('strong', null, `Continue with ${NAME[provider]}`)),
        h('p', { class: 'small mute', style: 'margin-bottom:12px' }, `Use the ${NAME[provider]} account e-mail you want to sign ${mode === 'login' ? 'in' : 'up'} with.`),
        h('label', { for: 'so-email', class: 'small' }, 'Account e-mail'), email, err,
        h('div', { class: 'row', style: 'margin-top:12px' },
          h('button', { class: 'btn', type: 'button', onclick: async (e) => {
            e.target.disabled = true; err.textContent = '';
            try {
              const res = await api('POST', '/auth/social', { provider, email: email.value, role, ...extras() });
              if (res.user.role !== role) throw new Error('That account belongs to a different portal.');
              session.set(res); dlg.remove(); onDone(res);
            } catch (x) { err.textContent = x.message; e.target.disabled = false; }
          } }, 'Continue'),
          h('button', { class: 'btn ghost', type: 'button', onclick: () => dlg.remove() }, 'Cancel'))));
    dlg.addEventListener('keydown', (e) => { if (e.key === 'Escape') dlg.remove(); });
    document.body.append(dlg); email.focus();
  }
  return h('div', { class: 'social' }, h('div', { class: 'or-line' }, h('span', null, `or ${mode === 'login' ? 'log in' : 'sign up'} with`)),
    h('div', { class: 'social-row' }, Object.keys(NAME).map((p) => h('button', { class: 'btn ghost social-btn', type: 'button', onclick: () => chooser(p) }, LOGO[p](), NAME[p]))));
}
