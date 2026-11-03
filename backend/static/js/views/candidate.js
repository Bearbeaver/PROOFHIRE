import { api, upload } from '../api.js';
import { ago, askReason, confirmBox, field, fmtDate, fmtDateTime, h, icon, option, put, s10, toast } from '../dom.js';
import { assessmentChip, card, chips, empty, evidenceList, pageHead, scorePill, scoreView, spinner, statusChip, typeIcon, typeLabel } from '../components.js';
import { bandLabel } from '../charts.js';
import { jobBrowser } from './shared.js';

const IN_FLIGHT = new Set(['PENDING', 'RESUBMITTED', 'QUEUED']);
const GITHUB_RE = /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+?(\.git)?\/?$/;
const URL_RE = /^https?:\/\/[^\s/$.?#][^\s]{2,500}$/;

// ------------------------------------------------------------------ S2 portfolio
function assessmentBanner(a, field) {
  if (a.verified && a.status === 'valid') return null;
  const due = a.status === 'due_soon';
  const text = due ? `Your ${field} assessment expires on ${fmtDate(a.valid_until)}. Retake it to keep your ProofScore verified.`
    : a.status === 'expired' ? `Your ${field} assessment has expired. Your ProofScore shows as provisional until you pass it again.`
    : a.status === 'failed' ? `You have not passed the ${field} assessment yet. Your ProofScore shows as provisional until you do.`
    : `Take the ${field} assessment to verify your ProofScore. Until then it shows as provisional to recruiters.`;
  return h('div', { class: 'banner' + (due ? '' : ' bad'), role: 'status' }, h('span', null, icon('alert', 14), ' ', text), h('a', { class: 'btn small', href: '#/candidate/assessments' }, 'Go to assessments'));
}

function exhibitCard(s) {
  const l = s.latest;
  const scoreLine = l ? h('div', { class: 'row' }, scorePill(l.out_of_10), h('span', { class: 'small mute' }, bandLabel(l.out_of_10, 'candidate')),
    s.status === 'RESUBMITTED' && h('span', { class: 'small mute' }, '- rescoring...'))
    : h('div', { class: 'row small mute', role: 'status' }, icon('refresh', 14), s.status === 'QUEUED' ? 'Queued - saved and will be scored shortly' : 'Scoring...');
  return h('a', { class: 'card exhibit', href: `#/candidate/exhibit/${s.id}` },
    h('div', { class: 'row between' }, h('span', { class: 'row', style: 'gap:6px;color:var(--mute)' }, [...new Set(s.evidence_types)].map((t) => h('span', { title: typeLabel(t) }, typeIcon(t)))), statusChip(s.status)),
    h('h2', { style: 'font-size:15px' }, s.title), h('div', { class: 'small mute' }, s.skill_area), scoreLine,
    h('div', { class: 'small mute', style: 'margin-top:auto' }, `Submitted ${fmtDate(s.date_submitted)} - ${s.resubmissions_remaining} resubmission${s.resubmissions_remaining === 1 ? '' : 's'} left`));
}

export async function portfolio(_p, ctx) {
  const root = h('div');
  let profile = await api('GET', '/candidate/profile');
  let subs = await api('GET', '/candidate/submissions');
  function draw() {
    put(root, 
      assessmentBanner(profile.assessment, profile.field),
      card([h('div', { class: 'row between', style: 'align-items:flex-start' },
        h('div', null, h('div', { class: 'mono small', style: 'color:var(--accent)' }, `~/${profile.field.toLowerCase().replace(/[^a-z]+/g, '-')}`), h('h1', { style: 'margin:4px 0' }, profile.name),
          profile.bio && h('p', { class: 'mute', style: 'max-width:640px;margin-bottom:10px' }, profile.bio), chips(profile.skills)),
        h('div', { class: 'stack', style: 'align-items:flex-end' }, assessmentChip(profile.assessment), h('a', { class: 'btn ghost small', href: '#/candidate/profile' }, 'Edit profile')))], { chrome: 'profile.json' }),
      h('div', { class: 'spacer' }),
      h('div', { class: 'row between', style: 'margin-bottom:12px' }, h('h2', { class: 'cm' }, 'Exhibits'), h('span', { class: 'small mute', 'aria-live': 'polite' }, `${subs.length} exhibit${subs.length === 1 ? '' : 's'}`)),
      h('div', { class: 'grid3' }, subs.map(exhibitCard),
        h('a', { class: 'add-card', href: '#/candidate/add' }, h('div', null, icon('plus', 22), h('div', null, 'Add evidence'), h('div', { class: 'small' }, 'GitHub, portfolio or certificate')))));
  }
  draw();
  let timer;
  const poll = async () => {
    if (!subs.some((s) => IN_FLIGHT.has(s.status))) return;
    try { subs = await api('GET', '/candidate/submissions'); draw(); } catch { /* retry next tick */ }
    timer = setTimeout(poll, 3000);
  };
  timer = setTimeout(poll, 3000);
  ctx.onCleanup(() => clearTimeout(timer));
  return root;
}

// ------------------------------------------------------------------ S3 add / resubmit evidence
const blank = () => ({ type: 'GITHUB', url: '', description: '', file: null, keepId: null, keepName: null });

export async function evidenceForm(params, ctx) {
  const resubmitId = params.id;
  let detail = null;
  if (resubmitId) {
    detail = await api('GET', `/candidate/submissions/${resubmitId}`);
    if (!detail.can_resubmit) {
      return card([h('h2', null, 'Resubmission unavailable'), h('p', { class: 'mute', style: 'margin:8px 0 14px' }, detail.status !== 'SCORED' ? 'You can resubmit once the current version has been scored.' : `You have used all ${detail.resubmission_limit} resubmissions for this exhibit.`),
        h('a', { class: 'btn', href: `#/candidate/exhibit/${resubmitId}` }, 'Back to exhibit')]);
    }
  }
  const profile = await api('GET', '/candidate/profile');
  const st = { title: detail ? detail.title : '', area: detail ? detail.skill_area : profile.field, items: detail ? detail.evidence.map((e) => ({ type: e.type, url: e.url || '', description: e.description || '', file: null, keepId: e.has_file ? e.id : null, keepName: e.file_name })) : [blank()],
    errors: {}, formError: '', busy: false, progress: null };
  const root = h('div');

  function validate() {
    const errs = {};
    if (!detail && (st.title.trim().length < 3 || st.title.trim().length > 100)) errs.title = 'Give the exhibit a title (3-100 characters).';
    st.items.forEach((it, i) => {
      const e = {};
      const url = it.url.trim();
      if (it.type === 'GITHUB' && !GITHUB_RE.test(url)) e.url = 'Enter a GitHub repository link like https://github.com/owner/repo.';
      if (it.type === 'PORTFOLIO' && !URL_RE.test(url)) e.url = 'Enter a valid http(s) link to your portfolio.';
      if (it.type === 'CERTIFICATE') {
        if (url && !URL_RE.test(url)) e.url = 'The credential link must be a valid http(s) URL.';
        if (!url && !it.file && !it.keepId) e.file = 'Attach a certificate file or add a credential link.';
        if (it.file && it.file.size > ctx.meta.max_upload_mb * 1024 * 1024) e.file = `Files can be at most ${ctx.meta.max_upload_mb} MB.`;
      }
      if (it.description.length > 2000) e.description = 'Description must be at most 2000 characters.';
      if (Object.keys(e).length) errs[i] = e;
    });
    return errs;
  }

  async function submit(ev) {
    ev.preventDefault();
    st.errors = validate(); st.formError = '';
    if (Object.keys(st.errors).length) { draw(); const bad = root.querySelector('[aria-invalid="true"]'); bad && bad.focus(); return; }
    if (detail) {
      const left = detail.resubmissions_remaining - 1;
      const ok = await confirmBox({ title: 'Use a resubmission?', text: `This uses 1 of your ${detail.resubmission_limit} resubmissions for "${detail.title}". You will have ${left} left afterwards.`, confirm: 'Resubmit' });
      if (!ok) return;
    }
    const fd = new FormData();
    const items = st.items.map((it, i) => {
      const out = { type: it.type, url: it.url.trim() || null, description: it.description.trim() };
      if (it.type === 'CERTIFICATE') { if (it.file) { out.file_key = 'f' + i; fd.append('f' + i, it.file); } else if (it.keepId) out.keep_evidence_id = it.keepId; }
      return out;
    });
    fd.append('payload', JSON.stringify({ title: st.title.trim(), skill_area: st.area, items }));
    st.busy = true; st.progress = 0; draw();
    try {
      const res = await upload(detail ? `/candidate/submissions/${resubmitId}/resubmit` : '/candidate/submissions', fd, (p) => { st.progress = p; const bar = root.querySelector('.progress > i'); if (bar) bar.style.width = Math.round(p * 100) + '%'; });
      toast(detail ? 'Resubmitted - scoring now.' : 'Evidence submitted - scoring now.');
      ctx.navigate(`#/candidate/exhibit/${res.id}`);
    } catch (err) {
      st.busy = false; st.progress = null;
      const d = err.details || {};
      if (typeof d.item === 'number') st.errors = { [d.item]: { [d.field || 'url']: err.message } };
      else if (d.field === 'title') st.errors = { title: err.message };
      else st.formError = err.message;
      draw();
    }
  }

  function itemCard(it, i) {
    const e = st.errors[i] || {};
    const urlLabel = it.type === 'GITHUB' ? 'Repository link' : it.type === 'PORTFOLIO' ? 'Portfolio link' : 'Credential link (optional if you attach a file)';
    return h('div', { class: 'item-card', role: 'group', 'aria-label': `Evidence item ${i + 1}` },
      h('div', { class: 'row between', style: 'margin-bottom:10px' }, h('strong', null, `Evidence ${i + 1}`),
        st.items.length > 1 && h('button', { class: 'btn ghost small', type: 'button', onclick: () => { st.items.splice(i, 1); st.errors = {}; draw(); } }, icon('x', 12), 'Remove')),
      field('Type', h('select', { id: `type${i}`, onchange: (ev) => { it.type = ev.target.value; st.errors = {}; draw(); } }, ['GITHUB', 'PORTFOLIO', 'CERTIFICATE'].map((t) => option(t, typeLabel(t), t === it.type))), { id: `type${i}` }),
      field(urlLabel, h('input', { id: `url${i}`, type: 'url', value: it.url, placeholder: it.type === 'GITHUB' ? 'https://github.com/owner/repo' : 'https://', oninput: (ev) => { it.url = ev.target.value; } }),
        { id: `url${i}`, error: e.url, help: it.type === 'GITHUB' ? 'The repository must be public so it can be analysed.' : null }),
      it.type === 'CERTIFICATE' && field('Certificate file (PDF, PNG, JPG or TXT)', h('input', { id: `file${i}`, type: 'file', accept: '.pdf,.png,.jpg,.jpeg,.txt', onchange: (ev) => { it.file = ev.target.files[0] || null; if (it.file) it.keepId = null; } }),
        { id: `file${i}`, error: e.file, help: it.keepId && !it.file ? `Keeping your earlier file: ${it.keepName}` : `Up to ${ctx.meta.max_upload_mb} MB.` }),
      field('Short description (optional)', h('textarea', { id: `desc${i}`, maxlength: 2000, placeholder: 'What does it show? What was your role?', oninput: (ev) => { it.description = ev.target.value; } }, it.description), { id: `desc${i}`, error: e.description }));
  }

  function draw() {
    const focusId = document.activeElement && document.activeElement.id;
    put(root, 
      detail && h('a', { href: `#/candidate/exhibit/${resubmitId}`, class: 'small mute' }, '← Back to exhibit'),
      pageHead(detail ? 'Resubmit improved evidence' : 'Add evidence', detail ? `${detail.resubmissions_remaining} of ${detail.resubmission_limit} resubmissions remaining. Update anything you improved, then resubmit.`
        : 'Point ProofHire at your work. It reads the code, tests and docs, so you do not need to write anything up.'),
      h('form', { onsubmit: submit, novalidate: true, style: 'max-width:640px' },
        field('Exhibit title', h('input', { id: 'title', value: st.title, maxlength: 100, readonly: !!detail, placeholder: 'e.g. Distributed task queue in Go', oninput: (ev) => { st.title = ev.target.value; } }), { id: 'title', error: st.errors.title }),
        field('Skill area', h('select', { id: 'area', disabled: !!detail, onchange: (ev) => { st.area = ev.target.value; } }, ctx.meta.fields.map((f) => option(f, f, f === st.area))), { id: 'area', help: 'Relevance is judged against this field.' }),
        st.items.map(itemCard),
        st.items.length < 6 && h('button', { class: 'btn ghost', type: 'button', style: 'margin-bottom:16px', onclick: () => { st.items.push(blank()); draw(); } }, icon('plus', 14), 'Add another piece of evidence'),
        st.formError && h('div', { class: 'banner bad', role: 'alert' }, st.formError),
        st.busy && h('div', { style: 'margin-bottom:12px' }, h('div', { class: 'small mute', role: 'status' }, st.progress < 1 ? 'Uploading...' : 'Saving and queuing for scoring...'),
          h('div', { class: 'progress' + (st.progress === null ? ' indeterminate' : '') }, h('i', { style: `width:${Math.round((st.progress || 0) * 100)}%` }))),
        h('button', { class: 'btn', type: 'submit', disabled: st.busy }, st.busy ? 'Submitting...' : detail ? 'Resubmit for scoring' : 'Submit for scoring')));
    if (focusId) { const el = root.querySelector('#' + focusId); el && el.focus(); }
  }
  draw();
  return root;
}

// ------------------------------------------------------------------ S4 score and feedback
export async function exhibit(params, ctx) {
  const root = h('div');
  let d = await api('GET', `/candidate/submissions/${params.id}`);
  let timer, animatedAttempt = null;
  function draw() {
    const inflight = IN_FLIGHT.has(d.status);
    const reveal = d.latest && d.latest.attempt_no !== animatedAttempt;
    const history = d.history || [];
    const resubmitBox = d.can_resubmit
      ? h('a', { class: 'btn', href: `#/candidate/exhibit/${d.id}/resubmit` }, icon('refresh', 14), `Resubmit improved evidence (${d.resubmissions_remaining} of ${d.resubmission_limit} remaining)`)
      : h('div', { class: 'row' }, h('button', { class: 'btn', disabled: true, 'aria-disabled': 'true', 'aria-describedby': 'why-no' }, icon('refresh', 14), 'Resubmit improved evidence'),
        h('span', { id: 'why-no', class: 'small mute' }, inflight ? 'You can resubmit once scoring finishes.' : `You have used all ${d.resubmission_limit} resubmissions for this exhibit.`));
    put(root, 
      h('a', { href: '#/candidate/portfolio', class: 'small mute' }, '← Portfolio'),
      pageHead(d.title, `${d.skill_area} - submitted ${fmtDate(d.date_submitted)}`, statusChip(d.status)),
      inflight && h('div', { class: 'banner info', role: 'status', 'aria-live': 'polite' },
        h('div', { style: 'width:100%' }, spinner(d.message || 'Scoring...'), h('div', { class: 'progress indeterminate', style: 'margin-top:10px' }, h('i')),
          d.latest && h('p', { class: 'small mute', style: 'margin-top:8px' }, 'Showing your previous score until the new one arrives.'))),
      d.latest && card(scoreView(d.latest, { animate: reveal }), { chrome: `exhibit/${d.id.slice(0, 8)}/score.json` }),
      h('div', { class: 'spacer' }),
      h('div', { class: 'grid2' },
        card([h('h2', { class: 'cm', style: 'margin-bottom:12px' }, 'Evidence'), evidenceList(d.evidence)]),
        card([h('h2', { class: 'cm', style: 'margin-bottom:12px' }, 'Score history'), history.length ? h('table', null, h('thead', null, h('tr', null, ['Attempt', 'Score', 'Change', 'Scored'].map((t) => h('th', null, t)))),
          h('tbody', null, history.map((x, i) => { const dl = i ? x.out_of_10 - history[i - 1].out_of_10 : null;
            return h('tr', null, h('td', null, `#${x.attempt_no}`), h('td', { class: 'mono' }, s10(x.out_of_10)),
              h('td', { class: 'mono', style: dl == null ? '' : `color:var(${dl >= 0 ? '--accent' : '--bad'})` }, dl == null ? '-' : (dl >= 0 ? '+' : '') + dl.toFixed(1)), h('td', { class: 'small mute' }, ago(x.scored_at))); })))
          : h('p', { class: 'mute' }, 'No scores yet.')])),
      h('div', { class: 'spacer' }), card(h('div', { class: 'row between' }, h('div', null, h('h3', null, 'Improve this exhibit'), h('p', { class: 'small mute' }, 'Act on the recommendations, then resubmit. Every attempt is kept in your history.')), resubmitBox)));
  }
  draw();
  if (d.latest) animatedAttempt = d.latest.attempt_no;
  if (IN_FLIGHT.has(d.status)) {
    const tick = async () => {
      try { d = await api('GET', `/candidate/submissions/${params.id}`); draw(); if (d.latest) animatedAttempt = d.latest.attempt_no; if (!IN_FLIGHT.has(d.status)) { ctx.refreshNotifications(); return; } } catch { /* retry */ }
      timer = setTimeout(tick, d.status === 'QUEUED' ? 4000 : 2000);
    };
    timer = setTimeout(tick, 2000);
    ctx.onCleanup(() => clearTimeout(timer));
  }
  return root;
}

// ------------------------------------------------------------------ assessments
export async function assessments() {
  const list = await api('GET', '/candidate/assessments');
  return h('div', null, pageHead('Standardised assessments', 'Pass the assessment for your own field to keep your ProofScore verified. It stays valid for 180 days. Other fields are optional.'),
    h('div', { class: 'stack' }, list.map((a) => card(h('div', { class: 'row between' },
      h('div', null, h('div', { class: 'row' }, h('h2', null, a.field), a.required && h('span', { class: 'chip' }, 'required')),
        h('p', { class: 'small mute', style: 'margin-top:4px' }, `${a.questions} questions - about ${a.duration_min} min - pass mark ${a.pass_mark}/${a.questions}${a.valid_until ? ' - valid until ' + fmtDate(a.valid_until) : ''}`),
        a.last && h('p', { class: 'small mute' }, `Last attempt: ${a.last.correct}/${a.last.total} (${a.last.passed ? 'passed' : 'not passed'}) ${ago(a.last.taken_at)}`)),
      h('div', { class: 'row' }, a.status === 'not_started' ? h('span', { class: 'chip grey' }, 'Not taken') : assessmentChip({ ...a, days_left: a.days_left }),
        h('a', { class: 'btn' + (a.status === 'valid' ? ' ghost' : ''), href: `#/candidate/assessments/take/${encodeURIComponent(a.field)}` }, a.status === 'not_started' ? 'Start' : 'Retake')))))));
}

export async function takeAssessment(params, ctx) {
  const fieldName = decodeURIComponent(params.field);
  const quiz = await api('POST', `/candidate/assessments/${encodeURIComponent(fieldName)}/start`);
  const answers = {};
  const root = h('div', { style: 'max-width:680px' });
  let result = null, busy = false;
  async function finish(e) {
    e.preventDefault();
    if (busy) return;
    busy = true; draw();
    try { result = await api('POST', `/candidate/assessments/${encodeURIComponent(fieldName)}/submit`, { answers }); ctx.refreshNotifications(); } catch (err) { toast(err.message, { error: true }); }
    busy = false; draw();
  }
  function draw() {
    if (result) {
      put(root, card([h('div', { class: 'mono small', style: `color:var(--${result.passed ? 'accent' : 'bad'})` }, result.passed ? 'PASSED' : 'NOT PASSED'),
        h('h1', { style: 'margin:6px 0' }, `${result.correct} / ${result.total} correct`),
        h('p', { class: 'mute', style: 'margin-bottom:14px' }, result.passed ? `Your ${fieldName} assessment is valid until ${fmtDate(result.valid_until)}. Your ProofScore stays verified.` : `You needed ${result.pass_mark}. You can retake it - it does not affect your ProofScore until your current assessment expires.`),
        result.topics_to_review.length > 0 && h('div', { style: 'margin-bottom:14px' }, h('div', { class: 'small mute' }, 'Topics to review'), chips(result.topics_to_review, 'warn')),
        h('a', { class: 'btn', href: '#/candidate/assessments' }, 'Back to assessments')], { chrome: 'result.json' }));
      return;
    }
    const n = Object.keys(answers).length;
    put(root, h('a', { class: 'small mute', href: '#/candidate/assessments' }, '← Assessments'), pageHead(`${fieldName} assessment`, `Pass mark ${quiz.pass_mark}/${quiz.questions.length}. Take your time - about ${quiz.duration_min} minutes.`),
      h('form', { onsubmit: finish }, quiz.questions.map((q, i) => h('div', { class: 'q' }, h('fieldset', null, h('legend', null, h('strong', null, `${i + 1}. `), q.q),
        q.options.map((o, oi) => h('label', { class: 'opt', style: 'color:var(--text);font-size:14px;margin:0 0 6px' }, h('input', { type: 'radio', name: q.id, required: true, checked: answers[q.id] === oi, onchange: () => { answers[q.id] = oi; update(); } }), h('span', null, o)))))),
        h('div', { class: 'row' }, h('button', { class: 'btn', type: 'submit', id: 'submit-quiz', disabled: busy || n < quiz.questions.length }, busy ? 'Marking...' : 'Submit assessment'),
          h('span', { class: 'small mute', id: 'quiz-progress', 'aria-live': 'polite' }, `${n} of ${quiz.questions.length} answered`))));
  }
  function update() {
    const n = Object.keys(answers).length;
    root.querySelector('#quiz-progress').textContent = `${n} of ${quiz.questions.length} answered`;
    root.querySelector('#submit-quiz').disabled = n < quiz.questions.length;
  }
  draw();
  return root;
}

// ------------------------------------------------------------------ S5 jobs, messages, profile
export async function jobs(_p, ctx) {
  return h('div', null, pageHead('Job listings', 'Listings are ranked by how many of the required skills appear on your profile.'), await jobBrowser(ctx, { showMatch: true }));
}

export async function messages() {
  const list = await api('GET', '/candidate/contact-requests');
  return h('div', null, pageHead('Messages from recruiters', 'Recruiters can only contact you after one of your exhibits has been scored.'),
    list.length ? h('div', { class: 'stack' }, list.map((m) => card([h('div', { class: 'row between' }, h('strong', null, `${m.recruiter_name} - ${m.company}`), h('span', { class: 'small mute' }, fmtDateTime(m.sent_at))), h('p', { style: 'margin-top:8px;white-space:pre-wrap' }, m.message)])))
      : empty('No messages yet. Keep improving your ProofScore - recruiters search by it.'));
}

export async function profile(_p, ctx) {
  const p = await api('GET', '/candidate/profile');
  const st = { name: p.name, bio: p.bio, field: p.field, skills: p.skills.join(', '), links: p.portfolio_links.join('\n'), errors: {}, busy: false };
  const root = h('div', { style: 'max-width:640px' });
  async function save(e) {
    e.preventDefault(); st.busy = true; st.errors = {}; draw();
    try {
      await api('PUT', '/candidate/profile', { name: st.name, bio: st.bio, field: st.field, skills: st.skills.split(',').map((s) => s.trim()).filter(Boolean), portfolio_links: st.links.split('\n').map((s) => s.trim()).filter(Boolean) });
      toast('Profile saved.');
      const s = JSON.parse(localStorage.getItem('ph_session')); s.user.name = st.name.trim(); localStorage.setItem('ph_session', JSON.stringify(s));
    } catch (err) { st.errors[(err.details && err.details.field) || 'form'] = err.message; }
    st.busy = false; draw();
  }
  function draw() {
    put(root, pageHead('Profile', 'Skills and field help recruiters find you and decide which assessment is required.'),
      h('form', { onsubmit: save, novalidate: true },
        field('Full name', h('input', { id: 'name', value: st.name, maxlength: 80, oninput: (e) => { st.name = e.target.value; } }), { id: 'name', error: st.errors.name }),
        field('Field', h('select', { id: 'pfield', onchange: (e) => { st.field = e.target.value; } }, ctx.meta.fields.map((f) => option(f, f, f === st.field))), { id: 'pfield', error: st.errors.field, help: 'Changing your field changes which assessment is required.' }),
        field('Bio', h('textarea', { id: 'bio', maxlength: 600, oninput: (e) => { st.bio = e.target.value; } }, st.bio), { id: 'bio', error: st.errors.bio }),
        field('Skills (comma separated)', h('input', { id: 'skills', value: st.skills, oninput: (e) => { st.skills = e.target.value; } }), { id: 'skills', error: st.errors.skills, help: 'Recruiters can filter by these.' }),
        field('Portfolio links (one per line)', h('textarea', { id: 'links', oninput: (e) => { st.links = e.target.value; } }, st.links), { id: 'links', error: st.errors.portfolio_links }),
        st.errors.form && h('div', { class: 'banner bad', role: 'alert' }, st.errors.form),
        h('button', { class: 'btn', type: 'submit', disabled: st.busy }, st.busy ? 'Saving...' : 'Save profile')));
  }
  draw();
  return root;
}

// ------------------------------------------------------------------ workspace overview (home)
export function profileStrength(p, subs) {
  const scored = subs.filter((s) => s.status === 'SCORED').length;
  const checks = [
    [15, (p.bio || '').trim().length >= 20, 'Write a short bio so recruiters know who you are.', '#/candidate/profile'],
    [15, p.skills.length >= 3, 'List at least three skills on your profile.', '#/candidate/profile'],
    [10, p.portfolio_links.length > 0, 'Link your portfolio or GitHub profile.', '#/candidate/profile'],
    [25, scored >= 1, 'Add your first piece of evidence to earn a ProofScore.', '#/candidate/add'],
    [10, scored >= 2, 'Add a second exhibit to show range.', '#/candidate/add'],
    [25, p.assessment.verified && p.assessment.status === 'valid', 'Pass your assessment to verify your ProofScore.', '#/candidate/assessments'],
  ];
  return { pct: checks.reduce((n, [w, ok]) => n + (ok ? w : 0), 0), next: checks.find((c) => !c[1]) || null };
}

const SANDBOX = {
  REPOSITORY: { label: 'Repository', icon: 'code', base: 4.6, signals: ['Tests', 'Documentation', 'Live demo', 'CI pipeline', 'Clean commits'] },
  PORTFOLIO: { label: 'Portfolio', icon: 'globe', base: 4.4, signals: ['Case studies', 'Live demo', 'Responsive', 'Accessibility', 'Metrics shown'] },
  CERTIFICATE: { label: 'Certificate', icon: 'file', base: 4.0, signals: ['Issuer verified', 'Recent', 'Hands-on lab', 'Proctored', 'Linked project'] },
};

function sandbox() {
  const st = { type: 'REPOSITORY', on: new Set(['Tests']), score: null };
  const root = h('section', { class: 'card ws-card sandbox', 'aria-labelledby': 'sb-t' });
  const result = h('div', { class: 'est', 'aria-live': 'polite' });
  function showResult() {
    const t = SANDBOX[st.type], n = Math.min(10, +(t.base + st.on.size * 1.05).toFixed(1));
    const dims = [['Completeness', .9], ['Quality', 1], ['Documentation', st.on.has('Documentation') || st.on.has('Case studies') ? 1.15 : .6], ['Verification', st.on.size > 2 ? 1.1 : .75]];
    const out = h('div', { class: 'est-num' }, '0.0');
    put(result, h('div', { class: 'est-label' }, 'ESTIMATED SCORE'), h('div', { class: 'row', style: 'gap:18px;justify-content:center;flex-wrap:wrap' }, out, h('span', { class: 'chip' }, bandLabel(n, 'candidate')),
      h('div', { class: 'est-bars' }, dims.map(([l, k]) => h('div', null, h('span', { class: 'small' }, l), h('div', { class: 'bar' }, h('i', { style: `width:${Math.min(100, n * 10 * k)}%` })))))));
    const t0 = performance.now();
    (function tick(now) { const p = Math.min(1, (now - t0) / 700); out.textContent = (n * (1 - Math.pow(1 - p, 3))).toFixed(1); if (p < 1 && out.isConnected) requestAnimationFrame(tick); })(t0);
  }
  function draw() {
    const t = SANDBOX[st.type];
    put(root,
      h('div', { class: 'mono eyebrow' }, '>_ INTERACTIVE DEMO'),
      h('div', { class: 'sb-grid' },
        h('div', null, h('h2', { id: 'sb-t', class: 'big' }, 'ProofScore sandbox'), h('p', { class: 'mute', style: 'margin:10px 0 16px' }, 'Choose an evidence type and its strongest signals to preview how the engine evaluates proof.'),
          h('div', { class: 'pills', role: 'radiogroup', 'aria-label': 'Evidence type' }, Object.entries(SANDBOX).map(([k, v]) => h('button', { class: 'pill-btn', type: 'button', role: 'radio', 'aria-checked': String(k === st.type), onclick: () => { st.type = k; st.on = new Set(); result.replaceChildren(); draw(); } }, icon(v.icon, 14), v.label)))),
        h('div', { class: 'sb-right' }, h('div', { class: 'mono small mute', style: 'letter-spacing:1px;margin-bottom:10px' }, 'EVIDENCE SIGNALS'),
          h('div', { class: 'pills', role: 'group', 'aria-label': 'Evidence signals' }, t.signals.map((s) => h('button', { class: 'pill-btn', type: 'button', 'aria-pressed': String(st.on.has(s)), onclick: () => { st.on.has(s) ? st.on.delete(s) : st.on.add(s); draw(); } }, icon(st.on.has(s) ? 'check' : 'plus', 13), s))),
          h('button', { class: 'btn gen', type: 'button', onclick: showResult }, icon('sparkles', 15), 'Generate demo score'))),
      result);
  }
  draw();
  return root;
}

export async function overview(_p, ctx) {
  const [profile, subs, stats] = await Promise.all([api('GET', '/candidate/profile'), api('GET', '/candidate/submissions'), api('GET', '/candidate/stats')]);
  const hr = new Date().getHours(), greet = hr < 12 ? 'Good morning' : hr < 18 ? 'Good afternoon' : 'Good evening';
  const verified = subs.filter((s) => s.status === 'SCORED').length;
  const a = profile.assessment, ok = a.verified && a.status === 'valid';
  const strength = profileStrength(profile, subs);
  const recent = subs.slice(0, 3);
  return h('div', { class: 'ws' },
    h('div', { class: 'mono eyebrow' }, '>_ CANDIDATE WORKSPACE'),
    h('h1', { class: 'greet' }, `${greet}, ${profile.name.split(' ')[0]}`),
    h('div', { class: 'status-strip', role: 'status' },
      h('span', { class: 'mono' }, h('i', { class: 'live-dot' + (ok ? '' : ' warn') }), ok ? 'assessment_verified' : 'assessment_pending'),
      h('span', { class: 'mono' }, icon('check', 13), h('b', null, verified), ' verified_artifacts'),
      h('span', { class: 'mono' }, icon('search', 13), h('b', null, stats.views_today), ' recruiter_views_today'),
      h('span', { class: 'mono grow-end' }, icon('code', 13), `main / ${profile.field.toLowerCase().replace(/[^a-z]+/g, '-')}`)),
    sandbox(),
    h('div', { class: 'ws-two' },
      card([h('div', { class: 'row between' }, h('h2', { class: 'cm' }, 'Profile strength'), h('span', { class: 'mono accent' }, strength.pct + '%')),
        h('div', { class: 'bar', style: 'margin:10px 0' }, h('i', { style: `width:${strength.pct}%` })),
        strength.next ? h('p', { class: 'small mute' }, strength.next[2], ' ', h('a', { href: strength.next[3] }, 'Do it now')) : h('p', { class: 'small mute' }, 'Profile complete. Recruiters can see everything.')]),
      card([h('div', { class: 'row between' }, h('h2', { class: 'cm' }, 'Evidence locker'), h('a', { class: 'small', href: '#/candidate/portfolio' }, 'Open all')),
        recent.length ? h('div', { class: 'stack', style: 'margin-top:10px' }, recent.map((s) => h('a', { class: 'row between small', href: `#/candidate/exhibit/${s.id}` }, h('span', null, s.title), s.latest ? scorePill(s.latest.out_of_10) : statusChip(s.status))))
          : h('p', { class: 'small mute', style: 'margin-top:10px' }, 'Nothing here yet. Add a repository, portfolio or certificate.')])));
}
