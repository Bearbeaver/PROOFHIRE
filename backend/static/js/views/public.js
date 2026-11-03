import { api, session } from '../api.js';
import { field, h, icon, option, put } from '../dom.js';
import { modeButton } from '../app.js';
import { socialSignIn, techBackdrop } from '../fx.js';

const ROLES = { candidate: 'CANDIDATE', recruiter: 'RECRUITER', admin: 'ADMIN' };
const TITLES = { candidate: 'Candidate portal', recruiter: 'Recruiter portal', admin: 'Administrator sign-in' };

export function landing(_p, ctx) {
  ctx.setPortal('public');
  const portal = (cls, tag, text, role, color) => h('div', { class: 'card portal-card', style: `border-top-color:${color}` },
    h('div', { class: 'mono small', style: `color:${color}` }, tag), h('p', null, text),
    h('a', { class: 'btn', href: `#/login/${role}`, style: `background:${color};border-color:${color};color:#0a0e14` }, `Continue as ${role}`, icon('arrow', 14)));
  return h('div', { class: 'landing' },
    h('div', { class: 'mono small mute', style: 'letter-spacing:1px' }, 'PROOFHIRE'),
    h('h1', null, 'Recruit on evidence, not resumes.'),
    h('p', { class: 'mute', style: 'max-width:480px' }, 'Candidates prove their skills with real projects. Recruiters review the evidence and a transparent ProofScore, not just the claims.'),
    h('div', { class: 'portals' },
      portal('', 'FOR CANDIDATES', 'Submit a GitHub project, portfolio or certificate, get a ProofScore with feedback, and keep it verified with standardised assessments.', 'candidate', '#3fb950'),
      portal('', 'FOR RECRUITERS', 'Search candidates by skill and ProofScore, review the evidence behind every score, then shortlist and contact.', 'recruiter', '#5b8def')),
    h('div', { class: 'steps' },
      h('div', null, h('strong', null, '1. Submit evidence'), h('p', { class: 'small mute' }, 'Link a repository, portfolio or certificate.')),
      h('div', null, h('strong', null, '2. Get scored'), h('p', { class: 'small mute' }, 'The ProofScore Engine rates seven dimensions out of 10.')),
      h('div', null, h('strong', null, '3. Improve and resubmit'), h('p', { class: 'small mute' }, 'Annotated feedback shows exactly what to fix.'))),
    h('p', { class: 'footer-note' }, h('a', { href: '#/login/admin' }, 'Administrator sign-in')));
}

export function auth(mode) {
  return async (params, ctx) => {
    const key = params.role;
    if (!ROLES[key] || (mode === 'register' && key === 'admin')) { ctx.navigate('#/'); return h('div'); }
    ctx.setPortal(key);
    const role = ROLES[key];
    let errors = {}, formError = '', busy = false, focusBad = false;
    const data = { name: '', email: '', password: '', company: '', field: (ctx.meta.fields || [])[0] };
    const wrap = h('div', { class: 'auth-wrap' });

    async function submit(e, demo = false) {
      e && e.preventDefault();
      if (busy) return;
      if (!demo) {
        const local = {};
        if (mode === 'register' && data.name.trim().length < 2) local.name = 'Enter your full name.';
        if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(data.email.trim())) local.email = 'Enter a valid email address.';
        if (!data.password) local.password = 'Enter your password.';
        else if (mode === 'register' && data.password.length < 8) local.password = 'Password must be at least 8 characters.';
        if (mode === 'register' && role === 'RECRUITER' && data.company.trim().length < 2) local.company = 'Enter your company name.';
        if (Object.keys(local).length) { errors = local; formError = ''; focusBad = true; return draw(); }
      }
      busy = true; errors = {}; formError = ''; draw();
      try {
        const res = demo ? await api('POST', '/auth/demo', { role })
          : mode === 'login' ? await api('POST', '/auth/login', { email: data.email, password: data.password })
          : await api('POST', '/auth/register', { ...data, role });
        if (res.user.role !== role) { formError = `That account is not a ${key} account.`; busy = false; return draw(); }
        session.set(res);
        ctx.afterAuth();
      } catch (err) {
        busy = false;
        const f = err.details && err.details.field;
        if (f) errors[f] = err.message; else formError = err.message;
        draw();
      }
    }
    const input = (id, label, type, extra = {}) => field(label, h('input', { id, type, value: data[id], required: true, autocomplete: extra.ac, maxlength: extra.max,
      oninput: (e) => { data[id] = e.target.value; } }), { id, error: errors[id], help: extra.help });

    function draw() {
      const form = h('form', { onsubmit: submit, novalidate: true },
        mode === 'register' && input('name', 'Full name', 'text', { ac: 'name', max: 80 }),
        input('email', 'Email', 'email', { ac: 'email', max: 254 }),
        input('password', 'Password', 'password', { ac: mode === 'login' ? 'current-password' : 'new-password', help: mode === 'register' ? 'At least 8 characters.' : null }),
        mode === 'register' && role === 'RECRUITER' && input('company', 'Company', 'text', { ac: 'organization', max: 80 }),
        mode === 'register' && role === 'CANDIDATE' && field('Your tech role', h('select', { id: 'field', onchange: (e) => { data.field = e.target.value; } },
          Object.entries(ctx.meta.role_groups || { Roles: ctx.meta.fields || [] }).map(([grp, list]) => h('optgroup', { label: grp }, list.map((f) => option(f, f, f === data.field))))), { id: 'field', help: 'Pick the role you are applying for. Your standardised assessment follows the nearest skills track.' }),
        formError && h('div', { class: 'field invalid' }, h('div', { class: 'err', role: 'alert' }, formError)),
        h('button', { class: 'btn', type: 'submit', style: 'width:100%;justify-content:center', disabled: busy }, busy ? 'Please wait...' : mode === 'login' ? 'Log in' : 'Create account'));
      const demo = ctx.meta.demo && mode === 'login' && h('button', { class: 'btn ghost', type: 'button', style: 'width:100%;justify-content:center;margin-top:10px;border-style:dashed', disabled: busy, onclick: () => submit(null, true) }, 'Continue with demo account');
      const social = key !== 'admin' && socialSignIn({ role, mode, extras: () => ({ name: data.name, company: data.company, field: data.field }), onDone: () => ctx.afterAuth() });
      const alt = key !== 'admin' && h('p', { class: 'small mute', style: 'text-align:center;margin-top:16px' }, mode === 'login' ? 'New here? ' : 'Already have an account? ',
        h('a', { href: `#/${mode === 'login' ? 'register' : 'login'}/${key}` }, mode === 'login' ? 'Create an account' : 'Log in'));
      put(wrap, techBackdrop(key), h('div', { class: 'card auth-card glass' },
        h('div', { class: 'row between', style: 'margin-bottom:14px' }, h('a', { href: '#/', class: 'small mute' }, '← Back'), modeButton()),
        h('div', { class: 'mono small', style: 'color:var(--accent);text-transform:uppercase' }, TITLES[key]),
        h('h1', { style: 'margin:4px 0 18px' }, mode === 'login' ? 'Log in' : 'Create account'), form, social, demo, alt));
      const bad = wrap.querySelector('[aria-invalid="true"]');
      if (bad && focusBad) { bad.focus(); focusBad = false; }
      else { const first = wrap.querySelector('input'); if (first && !busy && !wrap.dataset.focused) { first.focus(); wrap.dataset.focused = '1'; } }
    }
    draw();
    return wrap;
  };
}
