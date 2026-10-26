# Copyright 2026 The ros2_statechart Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""
Diagrams of a chart with its ``ros:`` annotations: Mermaid, Graphviz, Markdown.

All three are drawn from ``ChartSpec.structure()``, so they show the chart as
written (outcomes labelled by status, refusals and outputs as notes), not the
engine's expanded form.
"""

import re
import subprocess


def _states(structure):
    return {s['id']: s for s in structure['states']}


def _annotations(state):
    notes = []
    inv = state.get('invoke')
    if inv:
        target = inv.get('target', '')
        type_ = inv.get('type', '')
        notes.append(f"{inv['kind']} {target}" + (f' ({type_})' if type_ else ''))
    notes += state.get('outputs', [])
    notes += [f'after: {a}' for a in state.get('after', [])]
    for r in state.get('refuses', []):
        notes.append(('ignore ' if r['ignore'] else 'refuse ') + r['event']
                     + (f': {r["reason"]}' if r['reason'] else ''))
    return notes


def _edge_label(t):
    if t['origin'] == 'outcome':
        return t['label']
    label = t['event']
    if t['cond']:
        label += f" [{t['cond']}]"
    return label


_MERMAID_ENTITIES = {'"': '#quot;', '<': '#lt;', '>': '#gt;', '|': '#124;', '#': '#35;'}


def _mermaid_text(text):
    return re.sub(r'["<>|#]', lambda m: _MERMAID_ENTITIES[m.group(0)], str(text))


_MERMAID_WORDS = {'end', 'graph', 'subgraph', 'flowchart', 'direction', 'style', 'class',
                  'classdef', 'click', 'linkstyle', 'init', 'default'}


def _mermaid_ids(states):
    """Node ids: the state id where Mermaid accepts it, else a variant of it."""
    ids, used = {}, set()
    for sid in states:
        nid = re.sub(r'\W', '_', sid)
        if nid.lower() in _MERMAID_WORDS or nid.lower().endswith('_init') or nid in used:
            nid += f'_{len(used)}'
        ids[sid] = nid
        used.add(nid)
    return ids


def mermaid(structure):
    """
    Return a Mermaid flowchart: a subgraph per compound or parallel state.

    A flowchart, not a stateDiagram: Mermaid's state diagrams cannot draw a
    transition that crosses a composite state's border (their layout then
    moves states out of their parents), and a statechart has many such
    transitions; flowchart subgraphs keep every state inside its parent.
    """
    states = _states(structure)
    by_parent = {}
    for s in structure['states']:
        by_parent.setdefault(s['parent'], []).append(s)
    ids = _mermaid_ids(states)
    lines = ['flowchart TB',
             '  classDef start fill:#333,stroke:#333',
             '  classDef history fill:#fff,stroke:#333']

    def label(state, title):
        text = f'<b>{_mermaid_text(title)}</b>'
        for note in _annotations(state):
            text += f'<br/><small>{_mermaid_text(note)}</small>'
        return text

    def start(owner, initials, pad):
        dot = f'{ids[owner]}_init' if owner else 'init'
        lines.append(f'{pad}{dot}(( )):::start')
        for init in initials:
            lines.append(f'{pad}{dot} --> {ids[init]}')

    def emit(state, indent):
        pad = '  ' * indent
        sid, kind, nid = state['id'], state['kind'], ids[state['id']]
        if kind == 'history':
            text = 'H*' if state['history'] == 'deep' else 'H'
            lines.append(f'{pad}{nid}(("{text}")):::history')
            return
        children = by_parent.get(sid, [])
        if children:
            title = sid + (' (parallel)' if kind == 'parallel' else '')
            lines.append(f'{pad}subgraph {nid}["{label(state, title)}"]')
            lines.append(f'{pad}  direction TB')
            if kind != 'parallel':
                start(sid, state['initial'], pad + '  ')
            for child in children:
                emit(child, indent + 1)
            lines.append(f'{pad}end')
            if kind == 'parallel':
                lines.append(f'{pad}style {nid} stroke-dasharray: 5 5')
            return
        shape = ('((("', '")))') if kind == 'final' else ('("', '")')
        lines.append(f'{pad}{nid}{shape[0]}{label(state, sid)}{shape[1]}')

    for state in by_parent.get('', []):
        emit(state, 1)
    start('', structure['initial'], '  ')
    for t in structure['transitions']:
        if not t['targets'] or t['source'] not in states:
            continue
        arrow = '==>' if t['origin'] == 'outcome' else '-->'
        text = _edge_label(t)
        for target in t['targets']:
            if target not in ids:
                continue
            edge = f'{arrow}|"{_mermaid_text(text)}"|' if text else arrow
            lines.append(f"  {ids[t['source']]} {edge} {ids[target]}")
    return '\n'.join(lines) + '\n'


def _dot_id(sid):
    return '"' + sid.replace('"', '\\"') + '"'


def _dot_text(text):
    return text.replace('\\', '\\\\').replace('"', '\\"')


def graphviz(structure):
    """Return a Graphviz digraph with one cluster per compound or parallel state."""
    states = _states(structure)
    by_parent = {}
    for s in structure['states']:
        by_parent.setdefault(s['parent'], []).append(s)
    lines = ['digraph statechart {', '  compound=true;', '  rankdir=TB;',
             '  graph [fontname="Helvetica", fontsize=12];',
             '  node [shape=box, style=rounded, fontname="Helvetica", fontsize=11];',
             '  edge [fontname="Helvetica", fontsize=9];',
             f'  label="{_dot_text(structure["name"])}"; labelloc=t;']

    def anchor(sid):
        return _dot_id(sid + '#anchor') if by_parent.get(sid) else _dot_id(sid)

    def emit(state, indent):
        pad = '  ' * indent
        sid = state['id']
        notes = _annotations(state)
        if by_parent.get(sid):
            style = 'dashed' if state['kind'] == 'parallel' else 'rounded'
            lines.append(f'{pad}subgraph {_dot_id("cluster_" + sid)} {{')
            label = _dot_text(sid + (' (parallel)' if state['kind'] == 'parallel' else ''))
            label += ''.join('\\n' + _dot_text(n) for n in notes)
            lines.append(f'{pad}  label="{label}"; style={style};')
            lines.append(f'{pad}  {anchor(sid)} [shape=point, style=invis, width=0];')
            for child in by_parent[sid]:
                emit(child, indent + 1)
            # After the children: an edge names its nodes, and a node belongs to
            # the cluster it is first named in.
            if state['kind'] != 'parallel':
                for init in state['initial']:
                    lines.append(f'{pad}  {_dot_id(sid + "#init")} [shape=point, width=0.1];')
                    lines.append(f'{pad}  {_dot_id(sid + "#init")} -> {anchor(init)}'
                                 + _lhead(init, by_parent) + ';')
            lines.append(f'{pad}}}')
            return
        if state['kind'] == 'history':
            text = 'H*' if state['history'] == 'deep' else 'H'
            lines.append(f'{pad}{_dot_id(sid)} [shape=circle, label="{text}"];')
            return
        label = _dot_text(sid)
        if notes:
            label += '\\n' + '\\n'.join(_dot_text(n) for n in notes)
        shape = ', peripheries=2' if state['kind'] == 'final' else ''
        lines.append(f'{pad}{_dot_id(sid)} [label="{label}"{shape}];')

    for state in by_parent.get('', []):
        emit(state, 1)
    for init in structure['initial']:
        lines.append('  "#init" [shape=point, width=0.15];')
        lines.append(f'  "#init" -> {anchor(init)}' + _lhead(init, by_parent) + ';')

    def inside(sid, ancestor):
        while sid:
            sid = states[sid]['parent'] if sid in states else ''
            if sid == ancestor:
                return True
        return False

    for t in structure['transitions']:
        if not t['targets'] or t['source'] not in states:
            continue
        for target in t['targets']:
            source = t['source']
            attrs = [f'label="{_dot_text(_edge_label(t))}"']
            # Clip an edge at a cluster's border only when the other end is
            # outside it: dot cannot clip at a cluster that holds both ends.
            if by_parent.get(source) and target != source and not inside(target, source):
                attrs.append(f'ltail={_dot_id("cluster_" + source)}')
            if by_parent.get(target) and target != source and not inside(source, target):
                attrs.append(f'lhead={_dot_id("cluster_" + target)}')
            if t['origin'] == 'outcome':
                attrs.append('style=bold')
            lines.append(f"  {anchor(t['source'])} -> {anchor(target)} [{', '.join(attrs)}];")
    lines.append('}')
    return '\n'.join(lines) + '\n'


def _lhead(target, by_parent):
    return f' [lhead={_dot_id("cluster_" + target)}]' if by_parent.get(target) else ''


def _md(text):
    return str(text).replace('|', '\\|')


def markdown(structure):
    """Return Markdown tables: what each state does, and every transition."""
    lines = [f"# {structure['name']}", '', '## States', '',
             '| State | Kind | Parent | Does in ROS |', '|---|---|---|---|']
    for s in structure['states']:
        notes = '; '.join(_md(n) for n in _annotations(s))
        lines.append(f"| {s['id']} | {s['kind']} | {s['parent']} | {notes} |")
    lines += ['', '## Transitions', '', '| Source | Event | Guard | Target | From |',
              '|---|---|---|---|---|']
    for t in structure['transitions']:
        event = t['event'] if t['origin'] != 'outcome' else f"outcome: {t['label']}"
        cond = t['cond'] if t['origin'] != 'outcome' else ''
        target = ', '.join(t['targets']) or '(stays)'
        lines.append(f"| {t['source']} | {_md(event)} | {_md(cond)} | {target} | "
                     f"{t['origin']} |")
    if structure.get('input_events'):
        lines += ['', '## Input events', '', ', '.join(structure['input_events'])]
    return '\n'.join(lines) + '\n'


def render(structure, fmt):
    """Render to 'mermaid', 'dot', 'md', or an image format through Graphviz's dot."""
    if fmt in ('mermaid', 'mmd'):
        return mermaid(structure)
    if fmt in ('dot', 'gv'):
        return graphviz(structure)
    if fmt in ('md', 'markdown'):
        return markdown(structure)
    result = subprocess.run(['dot', f'-T{fmt}'], input=graphviz(structure).encode('utf-8'),
                            capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f'dot -T{fmt} failed: {result.stderr.decode(errors="replace")}')
    return result.stdout
