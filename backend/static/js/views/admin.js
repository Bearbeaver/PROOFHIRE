import { api } from '../api.js';
import { ago, askReason, confirmBox, countUp, field, fmtDateTime, h, icon, option, put, toast } from '../dom.js';
import { card, empty, pageHead, statusChip } from '../components.js';
import { barChart } from '../charts.js';

const tile = (n, label, cls = '') => { const num = h('div', { class: 'n ' + cls }, String(n)); countUp(num, Number(n)); return h('div', { class: 'card tile' }, num, h('div', { class: 'l' }, label)); };

// ------------------------------------------------------------------ S9 dashboard
export async function dashboard(_p, ctx) {
  const root = h('div');
  async function draw() {
    const s = await api('GET', '/admin/stats');
    const up = s.engine && s.engine.status === 'up';
    put(root, 
      pageHead('Control room', 'Usage, scoring queue and engine health.', h('button', { class: 'btn ghost small', type: 'button', onclick: draw }, icon('refresh', 13), 'Refresh')),
      (s.failing > 0 || !up) && h('div', { class: 'banner bad', role: 'alert' }, h('span', null, icon('alert', 14), up ? ` ${s.failing} submission(s) keep failing to score.` : ' The ProofScore Engine is unreachable. Submissions are being queued and retried automatically.'),
        h('button', { class: 'btn small', type: 'button', onclick: async (e) => { e.target.disabled = true; try { const r = await api('POST', '/admin/queue/requeue'); toast(`Re-queued ${r.requeued} submission(s).`); draw(); } catch (x) { toast(x.message, { error: true }); } } }, 'Re-queue unscored submissions')),
      h('div', { class: 'grid3', style: 'margin-bottom:20px' }, tile(s.active_users.CANDIDATE, 'Active candidates'), tile(s.active_users.RECRUITER, 'Active recruiters'), tile(s.submissions_total, 'Submissions'),
        tile(s.unscored, 'Waiting to be scored'), tile(s.queue_length, 'In scoring queue'), tile(s.flagged, 'Flagged for review', s.flagged ? 'bad' : '')),
      h('div', { class: 'grid2' },
        card([h('h2', { style: 'margin-bottom:10px' }, 'Submissions per day (last 7 days)'), barChart(s.per_day)]),
        card([h('h2', { style: 'margin-bottom:10px' }, 'ProofScore Engine'),
          h('div', { class: 'row', style: 'margin-bottom:10px' }, h('span', { class: 'chip ' + (up ? '' : 'bad') }, icon(up ? 'check' : 'alert', 12), up ? 'Engine up' : 'Engine down')),
          up && h('dl', { class: 'small', style: 'margin:0;display:grid;grid-template-columns:auto 1fr;gap:6px 14px' },
            h('dt', { class: 'mute' }, 'Model'), h('dd', { style: 'margin:0' }, s.engine.model_version || '-'), h('dt', { class: 'mute' }, 'Algorithm'), h('dd', { style: 'margin:0' }, s.engine.selected_algorithm || '-'),
            h('dt', { class: 'mute' }, 'Trained on'), h('dd', { style: 'margin:0' }, s.engine.trained_on || '-')),
          up && s.engine.note && h('p', { class: 'footer-note' }, s.engine.note),
          h('div', { class: 'spacer' }), h('h3', { style: 'margin-bottom:6px' }, 'Submission states'), h('div', { class: 'row' }, ['PENDING', 'QUEUED', 'SCORED', 'RESUBMITTED'].map((k) => h('span', { class: 'row', style: 'gap:6px' }, statusChip(k), h('b', { class: 'mono' }, s.submissions_by_status[k] || 0)))),
          h('p', { class: 'small mute', style: 'margin-top:10px' }, `${s.active_users.suspended} suspended account(s).`)])));
  }
  await draw();
  const t = setInterval(() => draw().catch(() => {}), 15000);
  ctx.onCleanup(() => clearInterval(t));
  return root;
}

// ------------------------------------------------------------------ S10 registers
export async function registers() {
  const root = h('div'), body = h('div');
  const st = { tab: 'users', q: '', role: '', status: '', moderation: '' };
  let timer;
  async function userTable() {
    const qs = new URLSearchParams(); ['q', 'role', 'status'].forEach((k) => st[k] && qs.set(k, st[k]));
    const rows = await api('GET', '/admin/users?' + qs);
    const act = async (u, status) => {
      const reason = status === 'ACTIVE' ? '' : await askReason({ title: `${status === 'SUSPENDED' ? 'Suspend' : 'Remove'} ${u.name}?`, text: 'The reason is written to the audit log.', confirm: status === 'SUSPENDED' ? 'Suspend' : 'Remove', danger: true });
      if (reason === null) return;
      try { await api('POST', `/admin/users/${u.id}/status`, { status, reason }); toast(`${u.name}: ${status.toLowerCase()}.`); load(); } catch (e) { toast(e.message, { error: true }); }
    };
    return rows.length ? h('div', { class: 'table-wrap' }, h('table', null, h('thead', null, h('tr', null, ['Name', 'Email', 'Role', 'Status', 'Joined', 'Actions'].map((t) => h('th', null, t)))),
      h('tbody', null, rows.map((u) => h('tr', null, h('td', null, u.name), h('td', { class: 'small' }, u.email), h('td', null, u.role.toLowerCase()),
        h('td', null, h('span', { class: 'chip ' + (u.status === 'ACTIVE' ? '' : 'bad') }, u.status.toLowerCase())), h('td', { class: 'small mute' }, ago(u.created_at)),
        h('td', null, u.role === 'ADMIN' ? h('span', { class: 'small mute' }, 'protected') : h('div', { class: 'row', style: 'gap:6px' },
          u.status !== 'ACTIVE' && h('button', { class: 'btn small ghost', type: 'button', onclick: () => act(u, 'ACTIVE') }, 'Restore'),
          u.status === 'ACTIVE' && h('button', { class: 'btn small ghost', type: 'button', onclick: () => act(u, 'SUSPENDED') }, 'Suspend'),
          u.status !== 'REMOVED' && h('button', { class: 'btn small danger', type: 'button', onclick: () => act(u, 'REMOVED') }, 'Remove'))))))))
      : empty('No users match these filters.');
  }
  async function subTable() {
    const qs = new URLSearchParams(); ['q', 'moderation'].forEach((k) => st[k] && qs.set(k, st[k]));
    const rows = await api('GET', '/admin/submissions?' + qs);
    const act = async (s, action) => {
      const labels = { dismiss: 'Dismiss flag', remove: 'Remove submission', restore: 'Restore submission' };
      const reason = await askReason({ title: `${labels[action]}: ${s.title}`, text: 'The reason is written to the audit log.', confirm: labels[action], danger: action === 'remove' });
      if (!reason) return;
      try { await api('POST', `/admin/submissions/${s.id}/moderate`, { action, reason }); toast('Done.'); load(); } catch (e) { toast(e.message, { error: true }); }
    };
    return rows.length ? h('div', { class: 'table-wrap' }, h('table', null, h('thead', null, h('tr', null, ['Exhibit', 'Candidate', 'Status', 'Moderation', 'Submitted', 'Actions'].map((t) => h('th', null, t)))),
      h('tbody', null, rows.map((s) => h('tr', null, h('td', null, h('div', null, s.title), s.flag_reason && h('div', { class: 'small', style: 'color:var(--warn)' }, 'Flag: ' + s.flag_reason)), h('td', null, s.candidate_name), h('td', null, statusChip(s.status)),
        h('td', null, h('span', { class: 'chip ' + (s.moderation === 'NONE' ? 'grey' : s.moderation === 'FLAGGED' ? 'warn' : 'bad') }, s.moderation.toLowerCase())), h('td', { class: 'small mute' }, ago(s.date_submitted)),
        h('td', null, h('div', { class: 'row', style: 'gap:6px' }, s.moderation === 'FLAGGED' && h('button', { class: 'btn small ghost', type: 'button', onclick: () => act(s, 'dismiss') }, 'Dismiss flag'),
          s.moderation !== 'REMOVED' && h('button', { class: 'btn small danger', type: 'button', onclick: () => act(s, 'remove') }, 'Remove'),
          s.moderation === 'REMOVED' && h('button', { class: 'btn small ghost', type: 'button', onclick: () => act(s, 'restore') }, 'Restore'))))))))
      : empty('No submissions match these filters.');
  }
  async function load() { try { put(body, st.tab === 'users' ? await userTable() : await subTable()); } catch (e) { put(body, h('div', { class: 'banner bad', role: 'alert' }, e.message)); } }
  function draw() {
    const tab = (id, label) => h('button', { role: 'tab', type: 'button', 'aria-selected': String(st.tab === id), onclick: () => { st.tab = id; st.q = ''; draw(); } }, label);
    put(root, pageHead('Registers', 'Accounts and submissions with status flags. Every action is recorded in the audit log.'),
      h('div', { class: 'tabs', role: 'tablist' }, tab('users', 'Users'), tab('submissions', 'Submissions')),
      h('div', { class: 'row', style: 'margin-bottom:14px' },
        h('div', { class: 'grow' }, h('label', { class: 'sr-only', for: 'rq' }, 'Search'), h('input', { id: 'rq', type: 'search', value: st.q, placeholder: st.tab === 'users' ? 'Search name or email' : 'Search title or candidate', oninput: (e) => { st.q = e.target.value; clearTimeout(timer); timer = setTimeout(load, 300); } })),
        st.tab === 'users' ? [h('select', { 'aria-label': 'Role', onchange: (e) => { st.role = e.target.value; load(); } }, option('', 'All roles', !st.role), option('CANDIDATE', 'Candidates', st.role === 'CANDIDATE'), option('RECRUITER', 'Recruiters', st.role === 'RECRUITER')),
          h('select', { 'aria-label': 'Status', onchange: (e) => { st.status = e.target.value; load(); } }, option('', 'All statuses', !st.status), option('ACTIVE', 'Active', st.status === 'ACTIVE'), option('SUSPENDED', 'Suspended', st.status === 'SUSPENDED'), option('REMOVED', 'Removed', st.status === 'REMOVED'))]
          : h('select', { 'aria-label': 'Moderation', onchange: (e) => { st.moderation = e.target.value; load(); } }, option('', 'All', !st.moderation), option('FLAGGED', 'Flagged', st.moderation === 'FLAGGED'), option('REMOVED', 'Removed', st.moderation === 'REMOVED'))),
      body);
    load();
  }
  draw();
  return root;
}

// ------------------------------------------------------------------ S11 audit log
export async function audit() {
  const rows = await api('GET', '/admin/audit');
  return h('div', null, pageHead('Audit log', 'Chronological record of administrator actions. Entries are written in the same transaction as the action itself.'),
    rows.length ? card(h('div', { class: 'table-wrap' }, h('table', null, h('thead', null, h('tr', null, ['When', 'Administrator', 'Action', 'Target', 'Detail'].map((t) => h('th', null, t)))),
      h('tbody', null, rows.map((r) => h('tr', null, h('td', { class: 'small' }, fmtDateTime(r.timestamp)), h('td', null, r.actor_name), h('td', { class: 'mono small' }, r.action), h('td', { class: 'small mute' }, `${r.target_type || ''} ${(r.target_id || '').slice(0, 8)}`), h('td', { class: 'small' }, r.detail || '-')))))))
      : empty('No administrator actions have been recorded yet.'));
}

// ------------------------------------------------------------------ settings
export async function settings() {
  const cfg = await api('GET', '/admin/config');
  const root = h('div', { style: 'max-width:520px' });
  let err = '';
  function draw() {
    const input = h('input', { id: 'maxr', type: 'number', min: 0, max: 10, value: cfg.MAX_RESUBMISSIONS });
    put(root, pageHead('Settings', 'Configuration, not code: changes apply immediately and are audited.'),
      card(h('form', { onsubmit: async (e) => {
        e.preventDefault();
        const v = Number(input.value);
        const ok = await confirmBox({ title: 'Change resubmission limit?', text: `Candidates will be allowed ${v} resubmission(s) per exhibit (currently ${cfg.MAX_RESUBMISSIONS}).`, confirm: 'Apply' });
        if (!ok) return;
        try { Object.assign(cfg, await api('PUT', '/admin/config', { MAX_RESUBMISSIONS: v })); err = ''; toast('Saved.'); } catch (x) { err = x.message; }
        draw();
      } }, field('Maximum resubmissions per exhibit', input, { id: 'maxr', help: 'Between 0 and 10. Existing counts are kept.', error: err }), h('button', { class: 'btn', type: 'submit' }, 'Save'))));
  }
  draw();
  return root;
}
