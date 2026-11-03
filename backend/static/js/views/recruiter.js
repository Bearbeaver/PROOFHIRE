import { api } from '../api.js';
import { ago, askReason, field, fmtDateTime, h, icon, option, put, s10, toast } from '../dom.js';
import { assessmentChip, card, chips, empty, evidenceList, pageHead, scorePill, scoreView } from '../components.js';
import { jobBrowser, jobCards } from './shared.js';

const FILTER_KEY = 'ph_filters';
const loadFilters = () => { try { return { skill: '', field: '', min: 0, verified: false, page: 0, ...JSON.parse(localStorage.getItem(FILTER_KEY)) }; } catch { return { skill: '', field: '', min: 0, verified: false, page: 0 }; } };

function shortlistButton(c, onChange) {
  const btn = h('button', { class: 'btn small ' + (c.shortlisted ? '' : 'ghost'), type: 'button', 'aria-pressed': String(c.shortlisted) });
  const paint = () => { put(btn, icon('bookmark', 13), c.shortlisted ? 'Shortlisted' : 'Shortlist'); btn.className = 'btn small ' + (c.shortlisted ? '' : 'ghost'); btn.setAttribute('aria-pressed', String(c.shortlisted)); };
  btn.addEventListener('click', async (e) => {
    e.preventDefault(); e.stopPropagation();
    const was = c.shortlisted;
    try {
      await api(was ? 'DELETE' : 'PUT', `/recruiter/candidates/${c.candidate_id}/shortlist`);
      c.shortlisted = !was; paint(); onChange && onChange(c);
      toast(was ? `Removed ${c.name} from your shortlist.` : `Shortlisted ${c.name}.`, { action: { label: 'Undo', onClick: async () => { try { await api(was ? 'PUT' : 'DELETE', `/recruiter/candidates/${c.candidate_id}/shortlist`); c.shortlisted = was; paint(); onChange && onChange(c); } catch (err) { toast(err.message, { error: true }); } } } });
    } catch (err) { toast(err.message, { error: true }); }
  });
  paint();
  return btn;
}

function resultRow(c, onChange) {
  return h('article', { class: 'card result' },
    h('div', null,
      h('div', { class: 'row' }, h('a', { href: `#/recruiter/candidate/${c.candidate_id}`, style: 'font-weight:600;font-size:15px' }, c.name), h('span', { class: 'small mute' }, c.field),
        c.provisional && h('span', { class: 'chip warn', title: 'The candidate has not passed a current standardised assessment for their field.' }, icon('alert', 12), 'Provisional')),
      h('div', { class: 'small mute', style: 'margin:2px 0 8px' }, `Top exhibit: ${c.top_exhibit.title} - ${c.exhibit_count} scored exhibit${c.exhibit_count === 1 ? '' : 's'}`),
      chips(c.skills.slice(0, 6))),
    h('div', { class: 'stack', style: 'align-items:flex-end;gap:8px' }, scorePill(c.top_exhibit.out_of_10), shortlistButton(c, onChange), h('a', { class: 'small', href: `#/recruiter/candidate/${c.candidate_id}` }, 'View profile')));
}

// ------------------------------------------------------------------ S6 search
export async function search(_p, ctx) {
  const f = loadFilters();
  const history = await api('GET', '/recruiter/search-history');
  const results = h('div', { 'aria-live': 'polite' });
  let t, seq = 0;
  async function run() {
    const my = ++seq;
    localStorage.setItem(FILTER_KEY, JSON.stringify(f));
    const qs = new URLSearchParams({ min_score: f.min, page: f.page });
    if (f.skill.trim()) qs.set('skill', f.skill.trim()); if (f.field) qs.set('field', f.field); if (f.verified) qs.set('verified', '1');
    try {
      const r = await api('GET', '/recruiter/candidates?' + qs);
      if (my !== seq) return;
      const pages = Math.max(1, Math.ceil(r.total / r.page_size));
      put(results, h('p', { class: 'small mute', style: 'margin-bottom:10px' }, `${r.total} candidate${r.total === 1 ? '' : 's'} - sorted by ProofScore, highest first`),
        r.items.length ? r.items.map((c) => resultRow(c)) : empty('No candidates match these filters.', h('div', { style: 'margin-top:12px' }, h('button', { class: 'btn ghost', type: 'button', onclick: reset }, 'Clear filters'))),
        r.total > r.page_size && h('div', { class: 'row between' }, h('button', { class: 'btn ghost small', type: 'button', disabled: f.page === 0, onclick: () => { f.page--; run(); } }, '← Previous'),
          h('span', { class: 'small mute' }, `Page ${f.page + 1} of ${pages}`), h('button', { class: 'btn ghost small', type: 'button', disabled: f.page + 1 >= pages, onclick: () => { f.page++; run(); } }, 'Next →')));
    } catch (e) { if (my === seq) put(results, h('div', { class: 'banner bad', role: 'alert' }, e.message)); }
  }
  function reset() { Object.assign(f, { skill: '', field: '', min: 0, verified: false, page: 0 }); panel(); run(); }
  const side = h('div');
  function panel() {
    put(side, card([h('h2', { style: 'margin-bottom:14px' }, 'Filters'),
      field('Skills (comma separated)', h('input', { id: 'skill', type: 'search', value: f.skill, placeholder: 'e.g. go, grpc', oninput: (e) => { f.skill = e.target.value; f.page = 0; clearTimeout(t); t = setTimeout(run, 300); } }), { id: 'skill' }),
      field('Field', h('select', { id: 'ffield', onchange: (e) => { f.field = e.target.value; f.page = 0; run(); } }, option('', 'Any field', !f.field), ctx.meta.fields.map((x) => option(x, x, x === f.field))), { id: 'ffield' }),
      h('div', { class: 'field' }, h('label', { for: 'min' }, 'Minimum ProofScore: ', h('output', { id: 'min-out', class: 'mono', style: 'color:var(--text)' }, Number(f.min).toFixed(1))),
        h('input', { id: 'min', type: 'range', min: 0, max: 10, step: 0.5, value: f.min, oninput: (e) => { f.min = Number(e.target.value); f.page = 0; side.querySelector('#min-out').textContent = f.min.toFixed(1); clearTimeout(t); t = setTimeout(run, 200); } })),
      h('label', { class: 'row', style: 'gap:8px;color:var(--text);font-size:14px' }, h('input', { type: 'checkbox', checked: f.verified, onchange: (e) => { f.verified = e.target.checked; f.page = 0; run(); } }), 'Verified only', h('span', { class: 'small mute' }, '(valid assessment)')),
      h('div', { class: 'spacer' }), h('button', { class: 'btn ghost small', type: 'button', onclick: reset }, 'Clear filters'),
      history.length > 0 && h('div', { style: 'margin-top:18px' }, h('div', { class: 'label' }, 'Recent searches'),
        h('div', { class: 'chips' }, history.slice(0, 5).map((x) => h('button', { class: 'chip skill', type: 'button', style: 'cursor:pointer', onclick: () => { Object.assign(f, { skill: x.skill, field: x.field, min: x.min_score, verified: x.verified_only, page: 0 }); panel(); run(); } },
          [x.skill, x.field, x.min_score ? `${x.min_score}+` : '', x.verified_only ? 'verified' : ''].filter(Boolean).join(' - ') || 'all'))))])); 
  }
  panel(); run();
  return h('div', null, pageHead('Candidate search', 'Filter by skill and ProofScore, then open a profile to review the evidence behind each score.'), h('div', { class: 'filter-layout' }, side, results));
}

// ------------------------------------------------------------------ S7 candidate profile
export async function candidate(params, ctx) {
  let c;
  try { c = await api('GET', `/recruiter/candidates/${params.id}`); } catch (e) {
    if (e.status === 404) return card([h('h2', null, 'Candidate not available'), h('p', { class: 'mute', style: 'margin:8px 0 14px' }, 'This candidate has no scored evidence, or their account is no longer active.'), h('a', { class: 'btn', href: '#/recruiter/search' }, 'Back to search')]);
    throw e;
  }
  const contactBox = h('div');
  function contactForm() {
    const ta = h('textarea', { id: 'msg', rows: 4, maxlength: 1000, placeholder: 'Introduce the role and why this candidate caught your eye.' });
    const err = h('div', { class: 'err small', style: 'color:var(--bad)', role: 'alert' });
    put(contactBox, h('div', { class: 'item-card' }, field('Message to ' + c.name, ta, { id: 'msg' }), err,
      h('div', { class: 'row' }, h('button', { class: 'btn', type: 'button', onclick: async (e) => {
        e.target.disabled = true; err.textContent = '';
        try { await api('POST', `/recruiter/candidates/${c.candidate_id}/contact`, { message: ta.value }); toast('Message sent.'); c.last_contacted = new Date().toISOString(); put(contactBox, ); }
        catch (x) { err.textContent = x.message; e.target.disabled = false; }
      } }, 'Send message'), h('button', { class: 'btn ghost', type: 'button', onclick: () => put(contactBox, ) }, 'Cancel'))));
    ta.focus();
  }
  const exhibits = c.exhibits.map((x) => card([h('div', { class: 'row between', style: 'margin-bottom:14px' }, h('div', null, h('h2', null, x.title), h('div', { class: 'small mute' }, `${x.skill_area} - ${x.attempts} scoring attempt${x.attempts === 1 ? '' : 's'}`)),
    h('div', { class: 'row' }, x.moderation === 'FLAGGED' && h('span', { class: 'chip warn' }, 'Under review'),
      h('button', { class: 'btn ghost small', type: 'button', onclick: async () => {
        const reason = await askReason({ title: 'Flag this exhibit', text: 'Tell a moderator why the evidence looks wrong (copied, fake, misleading).', confirm: 'Send flag' });
        if (!reason) return;
        try { await api('POST', `/recruiter/submissions/${x.id}/flag`, { reason }); toast('Thanks - a moderator will review it.'); } catch (e) { toast(e.message, { error: true }); }
      } }, icon('flag', 12), 'Flag'))),
    scoreView(x.score, { advice: false }), h('div', { class: 'spacer' }), h('h3', { style: 'margin-bottom:10px' }, 'Evidence'), evidenceList(x.evidence)]));
  return h('div', null,
    h('a', { href: '#/recruiter/search', class: 'small mute' }, '← Search results'),
    pageHead(c.name, `${c.field}`, h('div', { class: 'row' }, shortlistButton(c), h('button', { class: 'btn small', type: 'button', onclick: contactForm }, icon('arrow', 13), 'Contact'))),
    c.provisional && h('div', { class: 'banner', role: 'status' }, h('span', null, icon('alert', 14), ' Provisional: this candidate has no current standardised assessment for their field, so the ProofScore is not yet verified.')),
    c.last_contacted && h('p', { class: 'small mute', style: 'margin-bottom:10px' }, `You last contacted this candidate ${ago(c.last_contacted)}.`),
    contactBox,
    card([c.bio && h('p', { style: 'margin-bottom:10px' }, c.bio), h('div', { class: 'row' }, chips(c.skills), assessmentChip(c.assessment)),
      c.portfolio_links.length > 0 && h('div', { style: 'margin-top:10px' }, c.portfolio_links.map((l) => h('div', null, h('a', { href: l, target: '_blank', rel: 'noopener noreferrer' }, l))))]),
    h('div', { class: 'spacer' }), h('div', { class: 'stack' }, exhibits));
}

// ------------------------------------------------------------------ S8 shortlist tray
export async function shortlist() {
  const r = await api('GET', '/recruiter/shortlist');
  const list = h('div');
  function draw() {
    put(list, r.items.length ? r.items.map((c) => resultRow(c, (x) => { if (!x.shortlisted) { c.shortlisted = false; } })) : empty('Your shortlist is empty. Shortlist candidates from the search results.', h('div', { style: 'margin-top:12px' }, h('a', { class: 'btn', href: '#/recruiter/search' }, 'Search candidates'))));
  }
  draw();
  return h('div', null, pageHead('Shortlist', 'Your favourites tray. Removing a candidate can be undone from the confirmation message.'),
    r.unavailable > 0 && h('p', { class: 'small mute', style: 'margin-bottom:10px' }, `${r.unavailable} shortlisted candidate${r.unavailable === 1 ? ' is' : 's are'} no longer available.`), list);
}

// ------------------------------------------------------------------ jobs
export async function jobs(_p, ctx) {
  const mine = h('div');
  const st = { title: '', field: ctx.meta.fields[0], location: '', skills: '', description: '', err: '' };
  async function loadMine() { put(mine, jobCards(await api('GET', '/jobs?mine=1'))); }
  const form = h('div');
  function drawForm() {
    put(form, card(h('form', { novalidate: true, onsubmit: async (e) => {
      e.preventDefault();
      try { await api('POST', '/jobs', { title: st.title, field: st.field, location: st.location, description: st.description, skills: st.skills.split(',').map((s) => s.trim()).filter(Boolean) });
        toast('Job posted.'); Object.assign(st, { title: '', location: '', skills: '', description: '', err: '' }); drawForm(); loadMine(); } catch (x) { st.err = x.message; drawForm(); }
    } }, h('h2', { style: 'margin-bottom:14px' }, 'Post a job'),
      field('Title', h('input', { id: 'jt', value: st.title, maxlength: 100, oninput: (e) => { st.title = e.target.value; } }), { id: 'jt' }),
      field('Field', h('select', { id: 'jfield', onchange: (e) => { st.field = e.target.value; } }, ctx.meta.fields.map((x) => option(x, x, x === st.field))), { id: 'jfield' }),
      field('Location', h('input', { id: 'jl', value: st.location, maxlength: 80, oninput: (e) => { st.location = e.target.value; } }), { id: 'jl' }),
      field('Skills (comma separated)', h('input', { id: 'js', value: st.skills, oninput: (e) => { st.skills = e.target.value; } }), { id: 'js', help: 'Candidates see a skill-match percentage.' }),
      field('Description', h('textarea', { id: 'jd', maxlength: 2000, oninput: (e) => { st.description = e.target.value; } }, st.description), { id: 'jd' }),
      st.err && h('div', { class: 'banner bad', role: 'alert' }, st.err), h('button', { class: 'btn', type: 'submit' }, 'Post job'))));
  }
  drawForm(); await loadMine();
  return h('div', null, pageHead('Jobs', 'Listings you post are visible to candidates.'), h('div', { class: 'grid2', style: 'align-items:start' }, form, h('div', null, h('h2', { style: 'margin-bottom:12px' }, 'Your listings'), mine)));
}

// ------------------------------------------------------------------ sent messages
export async function messages() {
  const list = await api('GET', '/recruiter/messages');
  const byCand = new Map();
  list.forEach((m) => { if (!byCand.has(m.candidate_id)) byCand.set(m.candidate_id, { name: m.candidate_name, field: m.field, items: [] }); byCand.get(m.candidate_id).items.push(m); });
  return h('div', null, pageHead('Messages', 'Every message you have sent to candidates. Candidates see them in their own Messages tab.'),
    list.length ? h('div', { class: 'stack' }, [...byCand.entries()].map(([id, c]) => card([
      h('div', { class: 'row between' }, h('div', null, h('a', { href: `#/recruiter/candidate/${id}` }, h('strong', null, c.name)), h('div', { class: 'small mute' }, c.field)),
        h('a', { class: 'btn ghost small', href: `#/recruiter/candidate/${id}` }, icon('message', 13), 'Send another')),
      h('div', { class: 'stack', style: 'margin-top:12px' }, c.items.map((m) => h('div', { class: 'item-card' }, h('div', { class: 'small mute' }, fmtDateTime(m.sent_at)), h('p', { style: 'white-space:pre-wrap;margin-top:4px' }, m.message))))])))
      : empty('No messages sent yet. Open a candidate profile and choose Contact.', h('a', { class: 'btn', href: '#/recruiter/search', style: 'margin-top:12px' }, 'Find candidates')));
}
