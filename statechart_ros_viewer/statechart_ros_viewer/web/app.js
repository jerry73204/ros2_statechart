// Copyright 2026 The ros2_statechart Authors. SPDX-License-Identifier: Apache-2.0
//
// The statechart viewer: draws a chart's structure with dagre, lights the
// active states from ~/status, logs ~/transitions, and sends debug events.
// Everything it needs comes from the viewer node (no external assets).
'use strict';

const SVG = 'http://www.w3.org/2000/svg';
const view = {
  charts: [], node: null, structure: null, status: null, statusWall: 0,
  transitions: [], past: null, layout: null, viewBox: null,
  collapsed: new Set(), notes: true,
};

// A chart with more states than this opens without the notes under each name.
const NOTES_UP_TO = 25;

const $ = (id) => document.getElementById(id);
const el = (tag, attrs = {}, parent = null) => {
  const e = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
};

// ---------------------------------------------------------------- notes

function notesOf(state) {
  const notes = [];
  const inv = state.invoke;
  if (inv) notes.push(`${inv.kind} ${inv.target || ''}`.trim());
  for (const o of state.outputs || []) notes.push(o);
  for (const a of state.after || []) notes.push(`after: ${a}`);
  for (const r of state.refuses || []) {
    notes.push(`${r.ignore ? 'ignore' : 'refuse'} ${r.event}${r.reason ? ': ' + r.reason : ''}`);
  }
  return notes;
}

const measure = (() => {
  const ctx = document.createElement('canvas').getContext('2d');
  return (text, bold) => {
    ctx.font = `${bold ? '600 ' : ''}12px system-ui, sans-serif`;
    return ctx.measureText(text).width;
  };
})();

function truncate(text, max = 60) {
  return text.length > max ? text.slice(0, max - 1) + '…' : text;
}

// ---------------------------------------------------------------- layout

function layoutChart(structure) {
  const states = new Map(structure.states.map((s) => [s.id, s]));
  const children = new Map();
  for (const s of structure.states) {
    const p = s.parent || '';
    if (!children.has(p)) children.set(p, []);
    children.get(p).push(s.id);
  }
  const hasChildren = (id) => (children.get(id) || []).length > 0;
  const collapsed = (id) => hasChildren(id) && view.collapsed.has(id);
  // A state inside a collapsed one is drawn as the outermost collapsed ancestor.
  const rep = (id) => {
    let shown = id;
    for (let s = states.get(id); s && s.parent; s = states.get(s.parent)) {
      if (collapsed(s.parent)) shown = s.parent;
    }
    return shown;
  };
  const visible = structure.states.filter((s) => rep(s.id) === s.id);
  const isCluster = (id) => hasChildren(id) && !collapsed(id);
  const title = (id) => `${id}::title`;
  const entry = (id) => (isCluster(id) ? title(id) : id);
  const countInside = (id) => (children.get(id) || [])
    .reduce((n, k) => n + 1 + countInside(k), 0);

  const g = new dagre.graphlib.Graph({ compound: true, multigraph: true });
  g.setGraph({ rankdir: 'TB', nodesep: 26, ranksep: 34, edgesep: 12, marginx: 24, marginy: 24 });
  g.setDefaultEdgeLabel(() => ({}));

  for (const s of visible) {
    const notes = view.notes ? notesOf(s).map((n) => truncate(n)) : [];
    if (collapsed(s.id)) notes.unshift(`+ ${countInside(s.id)} states inside`);
    const width = Math.max(measure(s.id, true), ...notes.map((n) => measure(n) * 0.95), 30) + 22;
    const height = 24 + notes.length * 14;
    if (isCluster(s.id)) {
      g.setNode(s.id, { cluster: true });
      g.setNode(title(s.id), { width, height, titleOf: s.id, notes });
      g.setParent(title(s.id), s.id);
    } else if (s.kind === 'history') {
      g.setNode(s.id, { width: 26, height: 26, history: true });
    } else {
      g.setNode(s.id, { width, height, notes });
    }
    if (s.parent) g.setParent(s.id, s.parent);
  }
  for (const s of visible) {
    if (!isCluster(s.id)) continue;
    const kids = children.get(s.id).filter((k) => states.get(k).kind !== 'history');
    const initial = s.kind === 'parallel' ? [] : (s.initial.length ? s.initial : kids.slice(0, 1));
    for (const k of kids) {
      const isInitial = initial.includes(k);
      g.setEdge(title(s.id), entry(k), { initial: isInitial, invisible: !isInitial,
                                        minlen: 1, weight: isInitial ? 2 : 1 },
                `structure:${s.id}:${k}`);
    }
  }
  const drawn = new Set();
  structure.transitions.forEach((t, i) => {
    if (!t.targets.length || !states.has(t.source)) return;
    const source = rep(t.source);
    for (const real of t.targets) {
      if (!states.has(real)) continue;
      const target = rep(real);
      // an arrow that stays inside a folded state (a real self-loop is kept)
      if (source === target && (source !== t.source || target !== real)) continue;
      const label = truncate(t.origin === 'outcome' ? t.label
                                                     : t.event + (t.cond ? ` [${t.cond}]` : ''), 40);
      const key = `${source}|${target}|${label}`;
      if (drawn.has(key)) continue;
      drawn.add(key);
      g.setEdge(entry(source), entry(target),
                { label, width: measure(label) * 0.9 + 6, height: 14, labelpos: 'c',
                  index: i, source, target, origin: t.origin },
                `t${i}:${real}`);
    }
  });
  const initial = structure.initial[0];
  if (initial && states.has(initial)) {
    g.setNode('::start', { width: 12, height: 12, start: true });
    g.setEdge('::start', entry(rep(initial)), { initial: true }, 'start');
  }
  dagre.layout(g);
  return { g, states, children, isCluster, visible, rep, collapsed, hasChildren };
}

// ---------------------------------------------------------------- drawing

function pathOf(points) {
  if (!points || !points.length) return '';
  let d = `M${points[0].x},${points[0].y}`;
  for (let i = 1; i < points.length - 1; i++) {
    const p = points[i];
    const n = points[i + 1];
    const mx = (p.x + n.x) / 2;
    const my = (p.y + n.y) / 2;
    d += ` Q${p.x},${p.y} ${i === points.length - 2 ? n.x : mx},${i === points.length - 2 ? n.y : my}`;
  }
  if (points.length === 2) d += ` L${points[1].x},${points[1].y}`;
  return d;
}

function depthOf(states, id) {
  let d = 0;
  for (let s = states.get(id); s && s.parent; s = states.get(s.parent)) d++;
  return d;
}

function drawChart(structure) {
  const svg = $('diagram');
  svg.innerHTML = '';
  $('empty').hidden = !!structure;
  if (!structure) return;
  const layout = layoutChart(structure);
  view.layout = layout;
  const { g, states, isCluster, visible, collapsed } = layout;

  const defs = el('defs', {}, svg);
  const marker = el('marker', { id: 'arrow', viewBox: '0 0 10 10', refX: 9, refY: 5,
                                markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse' }, defs);
  el('path', { d: 'M0,0 L10,5 L0,10 z', fill: 'var(--edge)' }, marker);
  const root = el('g', { id: 'root' }, svg);
  const clusters = el('g', {}, root);
  const edges = el('g', {}, root);
  const nodes = el('g', {}, root);

  const clusterIds = visible.filter((s) => isCluster(s.id))
    .sort((a, b) => depthOf(states, a.id) - depthOf(states, b.id));
  for (const s of clusterIds) {
    const n = g.node(s.id);
    const chartCls = s.invoke && s.invoke.type === 'chart' ? ' child-chart' : '';
    const grp = el('g', { class: `cluster ${s.kind}${chartCls}`, 'data-id': s.id }, clusters);
    el('rect', { x: n.x - n.width / 2, y: n.y - n.height / 2, width: n.width,
                 height: n.height, rx: 10 }, grp);
    const t = g.node(`${s.id}::title`);
    const name = el('text', { x: t.x, y: t.y - t.height / 2 + 15, 'text-anchor': 'middle',
                              class: 'name' }, grp);
    name.textContent = s.kind === 'parallel' ? `${s.id} ∥` : s.id;
    t.notes.forEach((note, i) => {
      const tx = el('text', { x: t.x, y: t.y - t.height / 2 + 30 + i * 14,
                              'text-anchor': 'middle', class: 'note' }, grp);
      tx.textContent = note;
    });
  }

  for (const e of g.edges()) {
    const data = g.edge(e);
    if (data.invisible) continue;
    const cls = ['edge'];
    if (data.initial) cls.push('initial');
    if (data.origin === 'outcome') cls.push('outcome');
    const grp = el('g', { class: cls.join(' '), 'data-source': data.source || '',
                          'data-target': data.target || '' }, edges);
    el('path', { d: pathOf(data.points), 'marker-end': 'url(#arrow)' }, grp);
    if (data.label) {
      const tx = el('text', { x: data.x, y: data.y + 4, 'text-anchor': 'middle' }, grp);
      tx.textContent = data.label;
    }
  }

  for (const s of visible) {
    if (isCluster(s.id)) continue;
    const n = g.node(s.id);
    if (s.kind === 'history') {
      const grp = el('g', { class: 'state history', 'data-id': s.id }, nodes);
      el('circle', { cx: n.x, cy: n.y, r: 12 }, grp);
      const tx = el('text', { x: n.x, y: n.y + 4, 'text-anchor': 'middle' }, grp);
      tx.textContent = s.history === 'deep' ? 'H*' : 'H';
      continue;
    }
    const folded = collapsed(s.id) ? ' collapsed' : '';
    const grp = el('g', { class: `state ${s.kind}${folded}`, 'data-id': s.id }, nodes);
    el('rect', { x: n.x - n.width / 2, y: n.y - n.height / 2, width: n.width,
                 height: n.height, rx: 7 }, grp);
    const name = el('text', { x: n.x, y: n.y - n.height / 2 + 16, 'text-anchor': 'middle',
                              class: 'name' }, grp);
    name.textContent = s.id;
    n.notes.forEach((note, i) => {
      const tx = el('text', { x: n.x, y: n.y - n.height / 2 + 31 + i * 14,
                              'text-anchor': 'middle', class: 'note' }, grp);
      tx.textContent = note;
    });
  }
  const start = g.node('::start');
  if (start) el('circle', { cx: start.x, cy: start.y, r: 6, class: 'initial-dot' }, nodes);

  const graph = g.graph();
  view.viewBox = { x: 0, y: 0, w: Math.max(graph.width, 100), h: Math.max(graph.height, 100) };
  applyViewBox();
  highlight(currentConfiguration());
}

function applyViewBox() {
  const v = view.viewBox;
  if (v) $('diagram').setAttribute('viewBox', `${v.x} ${v.y} ${v.w} ${v.h}`);
}

function currentConfiguration() {
  if (view.past) return view.past.target;
  return view.status ? view.status.active : [];
}

function highlight(active) {
  const set = new Set(active || []);
  for (const node of document.querySelectorAll('#diagram [data-id]')) {
    node.classList.toggle('active', set.has(node.getAttribute('data-id')));
  }
}

function flash(record) {
  const rep = view.layout ? view.layout.rep : (id) => id;
  for (const taken of record.taken || []) {
    const [source, targets] = taken.split(' -> ');
    for (const target of (targets || '').split(', ')) {
      if (!target.trim()) continue;
      for (const edge of document.querySelectorAll('#diagram .edge')) {
        if (edge.getAttribute('data-source') === rep(source.trim()) &&
            edge.getAttribute('data-target') === rep(target.trim())) {
          edge.classList.add('flash');
          setTimeout(() => edge.classList.remove('flash'), 1500);
        }
      }
    }
  }
}

// ---------------------------------------------------------------- panels

function fmtTime(seconds) {
  const d = new Date(seconds * 1000);
  return d.toISOString().slice(11, 23);
}

function renderStatus() {
  const s = view.status;
  const list = $('active-list');
  list.innerHTML = '';
  if (!s) return;
  const leaves = new Set(s.active);
  if (view.structure) {
    for (const st of view.structure.states) if (st.parent && leaves.has(st.id)) leaves.delete(st.parent);
  }
  for (const id of s.active) {
    if (!leaves.has(id)) continue;
    const li = document.createElement('li');
    li.textContent = id;
    li.className = 'active-state';
    list.appendChild(li);
  }
  $('last-event').textContent = s.running
    ? `last event: ${s.last_event || '-'}${s.refusal ? ` (refused: ${s.refusal})` : ''}${s.ignored ? ` (ignored: ${s.ignored})` : ''}`
    : 'not running';
  const data = $('data');
  data.innerHTML = '';
  for (const [k, v] of Object.entries(s.data || {})) {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td></td><td></td>';
    tr.children[0].textContent = k;
    tr.children[1].textContent = v;
    data.appendChild(tr);
  }
  renderInvokes();
}

function renderInvokes() {
  const s = view.status;
  const ul = $('invokes');
  ul.innerHTML = '';
  if (!s) return;
  const nowRos = s.stamp + (Date.now() / 1000 - view.statusWall);
  for (const inv of s.invokes || []) {
    const li = document.createElement('li');
    li.className = 'invoke';
    const elapsed = Math.max(0, nowRos - inv.since);
    li.textContent = `${inv.state}: ${inv.kind} ${inv.target} (${elapsed.toFixed(1)} s)`;
    const fb = Object.entries(inv.feedback || {});
    if (fb.length) {
      const div = document.createElement('div');
      div.className = 'feedback';
      div.textContent = fb.map(([k, v]) => `${k} ${v}`).join(', ');
      li.appendChild(div);
    }
    ul.appendChild(li);
  }
}

function logItem(record) {
  const li = document.createElement('li');
  li.dataset.sequence = record.sequence;
  if (record.refusal) li.classList.add('refused');
  else if (!record.handled) li.classList.add('unhandled');
  else if (record.ignored) li.classList.add('ignored');
  const t = document.createElement('span');
  t.className = 't';
  t.textContent = fmtTime(record.stamp);
  li.appendChild(t);
  let text = record.event;
  if (record.refusal) text += ` refused: ${record.refusal}`;
  else if (!record.handled) text += ' (not handled)';
  else if (record.ignored) text += ` ignored: ${record.ignored}`;
  else text += ` → ${(record.taken || []).map((x) => x.split(' -> ')[1] || '(stays)').join(', ')}`;
  li.appendChild(document.createTextNode(text));
  li.title = record.data ? `data: ${record.data}` : '';
  li.addEventListener('click', () => showPast(record, li));
  return li;
}

function renderLog() {
  const ol = $('log');
  ol.innerHTML = '';
  for (const r of view.transitions.slice(-300).reverse()) ol.appendChild(logItem(r));
}

function showPast(record, li) {
  view.past = record;
  for (const x of document.querySelectorAll('#log li.selected')) x.classList.remove('selected');
  if (li) li.classList.add('selected');
  $('past-event').textContent = record.event;
  $('past-time').textContent = fmtTime(record.stamp);
  $('past-banner').hidden = false;
  highlight(record.target);
}

function goLive() {
  view.past = null;
  $('past-banner').hidden = true;
  for (const x of document.querySelectorAll('#log li.selected')) x.classList.remove('selected');
  highlight(currentConfiguration());
}

function renderSend() {
  const st = view.structure;
  const section = $('send-section');
  section.hidden = !(st && st.debug_events);
  if (section.hidden) return;
  const select = $('send-event');
  select.innerHTML = '';
  for (const ev of st.input_events || []) {
    const o = document.createElement('option');
    o.value = o.textContent = ev;
    select.appendChild(o);
  }
}

function renderCharts() {
  const select = $('chart-select');
  select.innerHTML = '';
  for (const c of view.charts) {
    const o = document.createElement('option');
    o.value = c.node;
    o.textContent = `${c.node}${c.name ? ' (' + c.name + ')' : ''}`;
    select.appendChild(o);
  }
  if (view.node) select.value = view.node;
}

// ---------------------------------------------------------------- options

// What the viewer remembers per chart in this browser: folded states and notes.
function optionsKey() {
  return `statechart-viewer:${view.node}`;
}

function loadOptions() {
  const count = view.structure ? view.structure.states.length : 0;
  view.collapsed = new Set();
  view.notes = count <= NOTES_UP_TO;
  try {
    const saved = JSON.parse(localStorage.getItem(optionsKey()) || 'null');
    if (saved) {
      view.collapsed = new Set(saved.collapsed || []);
      view.notes = !!saved.notes;
    }
  } catch (err) { /* storage may be unavailable */ }
  $('notes-toggle').checked = view.notes;
}

function saveOptions() {
  try {
    localStorage.setItem(optionsKey(), JSON.stringify(
      { collapsed: [...view.collapsed], notes: view.notes }));
  } catch (err) { /* storage may be unavailable */ }
}

function redraw() {
  saveOptions();
  drawChart(view.structure);
}

function toggleCollapsed(id) {
  if (!view.layout || !view.layout.hasChildren(id)) return;
  if (view.collapsed.has(id)) view.collapsed.delete(id);
  else view.collapsed.add(id);
  redraw();
}

function fit() {
  if (!view.layout) return;
  const graph = view.layout.g.graph();
  view.viewBox = { x: 0, y: 0, w: Math.max(graph.width, 100), h: Math.max(graph.height, 100) };
  applyViewBox();
}

// ---------------------------------------------------------------- data flow

async function selectChart(node) {
  if (view.node !== node) {
    view.structure = null;
    view.status = null;
    view.transitions = [];
  }
  view.node = node;
  view.past = null;
  $('past-banner').hidden = true;
  if (location.hash !== `#${node}`) history.replaceState(null, '', `#${node}`);
  const r = await fetch(`/api/chart?node=${encodeURIComponent(node)}`);
  if (!r.ok) return;
  const snap = await r.json();
  if (view.node !== node) return;
  // Events may have arrived while the snapshot was on its way: keep the newer.
  if (snap.structure) view.structure = snap.structure;
  if (snap.status && (!view.status || snap.status.sequence >= view.status.sequence)) {
    view.status = snap.status;
    view.statusWall = Date.now() / 1000;
  }
  if ((snap.transitions || []).length >= view.transitions.length) {
    view.transitions = snap.transitions || [];
  }
  $('chart-source').textContent = view.structure ? view.structure.source : '';
  loadOptions();
  drawChart(view.structure);
  renderStatus();
  renderLog();
  renderSend();
}

function onCharts(list) {
  view.charts = list;
  renderCharts();
  if (view.node && !view.structure && list.some((c) => c.node === view.node && c.name)) {
    selectChart(view.node);
    return;
  }
  if (!view.node && list.length) {
    const wanted = decodeURIComponent(location.hash.slice(1));
    selectChart(list.some((c) => c.node === wanted) ? wanted : list[0].node);
  }
}

function connect() {
  const source = new EventSource('/api/events');
  source.addEventListener('open', () => {
    $('connection').textContent = 'live';
    $('connection').className = 'pill on';
  });
  source.addEventListener('error', () => {
    $('connection').textContent = 'offline';
    $('connection').className = 'pill off';
  });
  source.addEventListener('charts', (e) => onCharts(JSON.parse(e.data).payload));
  source.addEventListener('structure', (e) => {
    const m = JSON.parse(e.data);
    if (m.node !== view.node) return;
    const first = !view.structure;
    view.structure = m.payload;
    if (first) loadOptions();
    drawChart(view.structure);
    renderSend();
  });
  source.addEventListener('status', (e) => {
    const m = JSON.parse(e.data);
    if (m.node !== view.node) return;
    view.status = m.payload;
    view.statusWall = Date.now() / 1000;
    renderStatus();
    if (!view.past) highlight(view.status.active);
  });
  source.addEventListener('run', (e) => {
    // The chart counts from the start again (restarted, or a bag played again).
    if (JSON.parse(e.data).node !== view.node) return;
    view.transitions = [];
    renderLog();
    goLive();
  });
  source.addEventListener('transition', (e) => {
    const m = JSON.parse(e.data);
    if (m.node !== view.node) return;
    view.transitions.push(m.payload);
    if (view.transitions.length > 1000) view.transitions.shift();
    $('log').prepend(logItem(m.payload));
    if (!view.past) flash(m.payload);
  });
}

// ---------------------------------------------------------------- interaction

function setupPanZoom() {
  const svg = $('diagram');
  let drag = null;
  svg.addEventListener('wheel', (e) => {
    if (!view.viewBox) return;
    e.preventDefault();
    const v = view.viewBox;
    const rect = svg.getBoundingClientRect();
    const fx = (e.clientX - rect.left) / rect.width;
    const fy = (e.clientY - rect.top) / rect.height;
    const k = e.deltaY > 0 ? 1.15 : 1 / 1.15;
    const w = v.w * k;
    const h = v.h * k;
    view.viewBox = { x: v.x + (v.w - w) * fx, y: v.y + (v.h - h) * fy, w, h };
    applyViewBox();
  }, { passive: false });
  svg.addEventListener('mousedown', (e) => {
    drag = { x: e.clientX, y: e.clientY, v: { ...view.viewBox } };
  });
  // Double-click a compound state to fold it into one box, or to open it again.
  svg.addEventListener('dblclick', (e) => {
    const target = e.target.closest('[data-id]');
    if (target) toggleCollapsed(target.getAttribute('data-id'));
  });
  window.addEventListener('mouseup', () => { drag = null; });
  window.addEventListener('mousemove', (e) => {
    if (!drag || !view.viewBox) return;
    const rect = svg.getBoundingClientRect();
    const sx = drag.v.w / rect.width;
    const sy = drag.v.h / rect.height;
    const s = Math.max(sx, sy);
    view.viewBox = { ...drag.v, x: drag.v.x - (e.clientX - drag.x) * s,
                     y: drag.v.y - (e.clientY - drag.y) * s };
    applyViewBox();
  });
}

function setupSend() {
  $('send-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    let data = {};
    const text = $('send-data').value.trim();
    try {
      data = text ? JSON.parse(text) : {};
    } catch (err) {
      $('send-answer').textContent = `data is not JSON: ${err.message}`;
      return;
    }
    const r = await fetch('/api/send', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node: view.node, event: $('send-event').value, data }),
    });
    const a = await r.json();
    $('send-answer').textContent = a.error ? a.error
      : (a.refusal ? `refused: ${a.refusal}`
        : (a.ignored ? `ignored: ${a.ignored}` : (a.handled ? 'handled' : 'not handled')));
  });
}

window.addEventListener('DOMContentLoaded', async () => {
  $('chart-select').addEventListener('change', (e) => selectChart(e.target.value));
  $('live-button').addEventListener('click', goLive);
  $('notes-toggle').addEventListener('change', (e) => { view.notes = e.target.checked; redraw(); });
  $('fit-button').addEventListener('click', fit);
  $('expand-button').addEventListener('click', () => { view.collapsed.clear(); redraw(); });
  setupPanZoom();
  setupSend();
  setInterval(renderInvokes, 1000);
  connect();
  const r = await fetch('/api/charts');
  if (r.ok) onCharts(await r.json());
});

// For tests and debugging in a browser console.
window.statechartViewer = { view, highlight, selectChart, goLive, toggleCollapsed, fit };
