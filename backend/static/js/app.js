import { api, session, setAuthLostHandler } from './api.js';
import { ago, clear, h, icon, put, toast } from './dom.js';
import { skeleton } from './components.js';
import { techBackdrop, welcomeSplash } from './fx.js';
import * as pub from './views/public.js';
import * as cand from './views/candidate.js';
import * as rec from './views/recruiter.js';
import * as adm from './views/admin.js';

const HOME = { CANDIDATE: '#/candidate/overview', RECRUITER: '#/recruiter/search', ADMIN: '#/admin/dashboard' };
const PORTAL = { CANDIDATE: 'candidate', RECRUITER: 'recruiter', ADMIN: 'admin' };
const NAV = {
  CANDIDATE: [['#/candidate/overview', 'Overview', 'grid'], ['#/candidate/portfolio', 'Evidence locker', 'archive'], ['#/candidate/add', 'Add evidence', 'plus'], ['#/candidate/assessments', 'Assessments', 'check'],
    ['#/candidate/jobs', 'Opportunities', 'briefcase'], ['#/candidate/messages', 'Messages', 'message'], ['#/candidate/profile', 'Profile', 'file']],
  RECRUITER: [['#/recruiter/search', 'Candidate search', 'search'], ['#/recruiter/shortlist', 'Shortlist', 'bookmark'], ['#/recruiter/jobs', 'Jobs', 'building'], ['#/recruiter/messages', 'Messages', 'message']],
  ADMIN: [['#/admin/dashboard', 'Dashboard', 'shield'], ['#/admin/registers', 'Registers', 'file'], ['#/admin/audit', 'Audit log', 'clock'], ['#/admin/settings', 'Settings', 'refresh']],
};
// [pattern, view, role (null = public), page title]
const ROUTES = [
  ['#/', pub.landing, null, 'ProofHire'],
  ['#/login/:role', (p, c) => pub.auth('login')(p, c), null, 'Log in'],
  ['#/register/:role', (p, c) => pub.auth('register')(p, c), null, 'Create account'],
  ['#/candidate/overview', cand.overview, 'CANDIDATE', 'Overview'],
  ['#/candidate/portfolio', cand.portfolio, 'CANDIDATE', 'Portfolio'],
  ['#/candidate/add', cand.evidenceForm, 'CANDIDATE', 'Add evidence'],
  ['#/candidate/exhibit/:id', cand.exhibit, 'CANDIDATE', 'Score and feedback'],
  ['#/candidate/exhibit/:id/resubmit', cand.evidenceForm, 'CANDIDATE', 'Resubmit evidence'],
  ['#/candidate/assessments', cand.assessments, 'CANDIDATE', 'Assessments'],
  ['#/candidate/assessments/take/:field', cand.takeAssessment, 'CANDIDATE', 'Assessment'],
  ['#/candidate/jobs', cand.jobs, 'CANDIDATE', 'Job listings'],
  ['#/candidate/messages', cand.messages, 'CANDIDATE', 'Messages'],
  ['#/candidate/profile', cand.profile, 'CANDIDATE', 'Profile'],
  ['#/recruiter/search', rec.search, 'RECRUITER', 'Candidate search'],
  ['#/recruiter/candidate/:id', rec.candidate, 'RECRUITER', 'Candidate profile'],
  ['#/recruiter/shortlist', rec.shortlist, 'RECRUITER', 'Shortlist'],
  ['#/recruiter/messages', rec.messages, 'RECRUITER', 'Messages'],
  ['#/recruiter/jobs', rec.jobs, 'RECRUITER', 'Jobs'],
  ['#/admin/dashboard', adm.dashboard, 'ADMIN', 'Dashboard'],
  ['#/admin/registers', adm.registers, 'ADMIN', 'Registers'],
  ['#/admin/audit', adm.audit, 'ADMIN', 'Audit log'],
  ['#/admin/settings', adm.settings, 'ADMIN', 'Settings'],
].map(([pat, view, role, title]) => ({ re: new RegExp('^' + pat.replace(/:(\w+)/g, '(?<$1>[^/]+)') + '$'), view, role, title }));

const state = { meta: { fields: [], demo: false }, cleanups: [], navId: 0, shell: null, notifTimer: null };

export const ctx = {
  get user() { return (session.get() || {}).user || null; },
  get meta() { return state.meta; },
  home: (role) => HOME[role],
  navigate(hash) { if (location.hash === hash) route(); else location.hash = hash; },
  onCleanup(fn) { state.cleanups.push(fn); },
  setPortal, toggleMode, refreshNotifications: () => pollNotifications(),
  async afterAuth() { await welcomeSplash(ctx.user); ctx.navigate(HOME[ctx.user.role]); },
};

function mode() { return localStorage.getItem('ph_mode') || null; }
function setPortal(p) {
  const root = document.documentElement;
  root.dataset.portal = p;
  root.dataset.mode = mode() || 'dark';
}
function toggleMode() {
  const next = document.documentElement.dataset.mode === 'dark' ? 'light' : 'dark';
  localStorage.setItem('ph_mode', next);
  document.documentElement.dataset.mode = next;
  const b = document.getElementById('mode-btn');
  if (b) { clear(b).append(icon(next === 'dark' ? 'sun' : 'moon')); b.setAttribute('aria-label', next === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'); }
}
export const modeButton = () => {
  const dark = document.documentElement.dataset.mode === 'dark';
  return h('button', { class: 'icon-btn', id: 'mode-btn', type: 'button', 'aria-label': dark ? 'Switch to light mode' : 'Switch to dark mode', onclick: toggleMode }, icon(dark ? 'sun' : 'moon'));
};

function logout(msg) {
  session.clear(); state.shell = null; clearInterval(state.notifTimer);
  document.getElementById('toasts').replaceChildren();
  if (msg) toast(msg, { error: true });
  if (location.hash === '#/') route(); else location.hash = '#/';
}
setAuthLostHandler((err) => logout(err.code === 'TOKEN_EXPIRED' ? 'Your session expired. Please log in again.' : err.message));

// ---------------------------------------------------------------- notifications
async function pollNotifications() {
  if (!session.get() || !state.shell) return;
  try {
    const r = await api('GET', '/notifications');
    const { bell } = state.shell;
    state.shell.items = r.items;
    const count = bell.querySelector('.badge-count');
    if (r.unread) { if (count) count.textContent = r.unread; else bell.append(h('span', { class: 'badge-count', 'aria-hidden': 'true' }, r.unread)); } else if (count) count.remove();
    bell.setAttribute('aria-label', `Notifications, ${r.unread} unread`);
    if (state.shell.role === 'CANDIDATE') refreshSide();
  } catch { /* shown elsewhere if auth fails */ }
}
function notificationsMenu() {
  const wrap = h('div', { style: 'position:relative' });
  const bell = h('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Notifications', 'aria-haspopup': 'true', 'aria-expanded': 'false' }, icon('bell'));
  let menu = null;
  const close = () => { if (menu) { menu.remove(); menu = null; bell.setAttribute('aria-expanded', 'false'); } };
  bell.addEventListener('click', async (e) => {
    e.stopPropagation();
    if (menu) return close();
    await pollNotifications();
    const items = state.shell.items || [];
    menu = h('div', { class: 'menu wide', role: 'menu' },
      items.length ? [h('button', { class: 'menu-item small mute', type: 'button', onclick: async () => { await api('POST', '/notifications/read', {}); close(); pollNotifications(); } }, 'Mark all as read'),
        items.map((n) => h('button', { class: 'menu-item' + (n.is_read ? '' : ' unread'), type: 'button', role: 'menuitem', onclick: async () => {
          if (!n.is_read) await api('POST', '/notifications/read', { ids: [n.id] });
          close(); pollNotifications(); if (n.link) ctx.navigate(n.link);
        } }, h('div', null, n.message), h('div', { class: 'small mute' }, ago(n.created_at))))]
        : h('div', { class: 'menu-item mute' }, 'No notifications yet.'));
    wrap.append(menu); bell.setAttribute('aria-expanded', 'true');
  });
  document.addEventListener('click', (e) => { if (menu && !wrap.contains(e.target)) close(); });
  wrap.append(bell);
  return { wrap, bell };
}

// candidate sidebar: messages badge + profile-strength card
async function refreshSide() {
  const sh = state.shell; if (!sh || !sh.strengthBox) return;
  try {
    const [p, subs, st] = await Promise.all([api('GET', '/candidate/profile'), api('GET', '/candidate/submissions'), api('GET', '/candidate/stats')]);
    const x = cand.profileStrength(p, subs);
    put(sh.strengthBox, h('div', { class: 'row between' }, h('strong', null, 'Profile strength'), h('span', { class: 'mono accent' }, x.pct + '%')),
      h('div', { class: 'bar', style: 'margin:8px 0' }, h('i', { style: `width:${x.pct}%` })), h('p', { class: 'small' }, x.next ? x.next[2] : 'Profile complete.'));
    const link = sh.nav.querySelector('a[data-href="#/candidate/messages"]'); const old = link && link.querySelector('.nav-badge'); if (old) old.remove();
    if (link && st.messages) link.append(h('span', { class: 'nav-badge' }, st.messages));
  } catch { /* retry on next poll */ }
}

// ---------------------------------------------------------------- shell + routing
function buildShell(user) {
  const nav = h('nav', { class: 'nav', 'aria-label': 'Main' }, NAV[user.role].map(([href, label, ic]) => h('a', { href, 'data-href': href }, icon(ic, 15), label)));
  const { wrap, bell } = notificationsMenu();
  const main = h('main', { id: 'main', tabindex: '-1' });
  const initials = user.name.split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase();
  const userMenuWrap = h('div', { style: 'position:relative' });
  const avatar = h('button', { class: 'avatar', type: 'button', 'aria-label': 'Account menu', 'aria-haspopup': 'true' }, initials);
  let um = null;
  avatar.addEventListener('click', (e) => {
    e.stopPropagation();
    if (um) { um.remove(); um = null; return; }
    um = h('div', { class: 'menu', role: 'menu' }, h('div', { class: 'menu-item mute small' }, h('div', null, user.name), h('div', null, user.email)),
      h('button', { class: 'menu-item', type: 'button', role: 'menuitem', onclick: () => logout() }, icon('logout', 14), ' Log out'));
    userMenuWrap.append(um);
  });
  document.addEventListener('click', (e) => { if (um && !userMenuWrap.contains(e.target)) { um.remove(); um = null; } });
  userMenuWrap.append(avatar);
  const strengthBox = h('div', { class: 'strength-card' });
  const root = h('div', { class: 'app' }, techBackdrop(PORTAL[user.role], { ambient: true }),
    h('aside', { class: 'sidebar' }, h('div', null, h('a', { class: 'brand', href: HOME[user.role] }, icon(user.role === 'CANDIDATE' ? 'terminal' : user.role === 'RECRUITER' ? 'building' : 'shield', 18), 'ProofHire'), nav),
      user.role === 'CANDIDATE' && strengthBox,
      h('div', { class: 'side-foot user-foot' }, h('span', { class: 'avatar sm', 'aria-hidden': 'true' }, initials), h('div', { class: 'grow' }, h('div', { class: 'who' }, user.name), h('div', { class: 'small' }, { CANDIDATE: 'Candidate', RECRUITER: 'Recruiter', ADMIN: 'Administrator' }[user.role])),
        h('button', { class: 'icon-btn plain', type: 'button', 'aria-label': 'Log out', onclick: () => logout() }, icon('logout', 16)))),
    h('div', { class: 'main-col' }, h('div', { class: 'topbar' }, modeButton(), wrap, user.role === 'CANDIDATE' && h('a', { class: 'btn add-ev', href: '#/candidate/add' }, icon('plus', 15), 'Add evidence'), userMenuWrap), main));
  state.shell = { root, main, nav, bell, items: [], role: user.role, strengthBox };
  clearInterval(state.notifTimer);
  state.notifTimer = setInterval(pollNotifications, 10000);
  pollNotifications();
  return state.shell;
}

async function route() {
  const id = ++state.navId;
  state.cleanups.splice(0).forEach((fn) => { try { fn(); } catch { /* ignore */ } });
  const hash = location.hash || '#/';
  const s = session.get();
  const found = ROUTES.map((r) => [r, r.re.exec(hash)]).find(([, m]) => m);
  const app = document.getElementById('app');
  if (!found) { return ctx.navigate(s ? HOME[s.user.role] : '#/'); }
  const [r, m] = found;
  const params = m.groups || {};
  if (r.role === null) {
    if (s && hash === '#/') return ctx.navigate(HOME[s.user.role]);
    state.shell = null; clearInterval(state.notifTimer);
    document.title = r.title === 'ProofHire' ? 'ProofHire - skills-based recruitment' : `${r.title} - ProofHire`;
    clear(app);
    try { app.append(await r.view(params, ctx)); } catch (e) { app.append(errorBox(e)); }
    return;
  }
  if (!s) return ctx.navigate('#/');
  if (s.user.role !== r.role) return ctx.navigate(HOME[s.user.role]);
  setPortal(PORTAL[s.user.role]);
  if (!state.shell || state.shell.role !== s.user.role || !app.contains(state.shell.root)) { clear(app); app.append(buildShell(s.user).root); }
  const { main, nav } = state.shell;
  nav.querySelectorAll('a').forEach((a) => (hash.startsWith(a.dataset.href) ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current')));
  document.title = `${r.title} - ProofHire`;
  main.classList.remove('settled');
  clear(main).append(skeleton());
  try {
    const node = await r.view(params, ctx);
    if (id !== state.navId) return;      // user navigated away while loading
    clear(main).append(node);
    setTimeout(() => { if (id === state.navId) main.classList.add('settled'); }, 1000);   // entrance animations play once per navigation, never on polling redraws
    main.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  } catch (e) {
    if (id === state.navId) clear(main).append(errorBox(e));
  }
}
function errorBox(e) {
  return h('div', { class: 'auth-wrap' }, h('div', { class: 'card card-body', role: 'alert' }, h('h2', null, 'Something went wrong'), h('p', { class: 'mute', style: 'margin:8px 0 14px' }, e.message || 'Unexpected error.'),
    h('button', { class: 'btn', type: 'button', onclick: route }, 'Try again')));
}

async function boot() {
  try { state.meta = await api('GET', '/meta'); } catch { /* offline: pages show their own errors */ }
  const s = session.get();
  if (s) { try { const r = await api('GET', '/auth/me'); session.set({ token: s.token, user: r.user }); } catch { session.clear(); } }
  setPortal(session.get() ? PORTAL[session.get().user.role] : 'public');
  window.addEventListener('hashchange', route);
  route();
}
boot();
