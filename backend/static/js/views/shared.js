import { api } from '../api.js';
import { h, option, put } from '../dom.js';
import { chips, empty } from '../components.js';

export function jobCards(jobs, { showMatch = false } = {}) {
  if (!jobs.length) return empty('No job listings match these filters.');
  return h('div', { class: 'stack' }, jobs.map((j) => h('article', { class: 'card card-body' },
    h('div', { class: 'row between' }, h('div', null, h('h2', null, j.title), h('div', { class: 'small mute' }, `${j.company}${j.location ? ' - ' + j.location : ''} - ${j.field}`)),
      showMatch && j.match != null && h('span', { class: 'chip ' + (j.match >= 60 ? '' : 'grey'), title: 'Share of the job\'s skills that appear on your profile' }, `${j.match}% skill match`)),
    h('p', { style: 'margin:10px 0' }, j.description), chips(j.skills))));
}

export async function jobBrowser(ctx, { showMatch }) {
  const root = h('div'), list = h('div');
  const state = { field: '', q: '' };
  async function load() {
    const qs = new URLSearchParams(); if (state.field) qs.set('field', state.field); if (state.q) qs.set('q', state.q);
    const jobs = await api('GET', '/jobs?' + qs);
    put(list, jobCards(jobs, { showMatch }));
  }
  let t;
  root.append(h('div', { class: 'row', style: 'margin-bottom:16px' },
    h('div', { class: 'grow' }, h('label', { for: 'jq', class: 'sr-only' }, 'Search jobs'), h('input', { id: 'jq', type: 'search', placeholder: 'Search title, company or description', oninput: (e) => { state.q = e.target.value; clearTimeout(t); t = setTimeout(load, 250); } })),
    h('div', null, h('label', { for: 'jf', class: 'sr-only' }, 'Field'), h('select', { id: 'jf', onchange: (e) => { state.field = e.target.value; load(); } }, option('', 'All fields'), ctx.meta.fields.map((f) => option(f, f))))), list);
  await load();
  return root;
}
