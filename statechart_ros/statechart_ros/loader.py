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
Read a chart: SCXML with the ``ros:`` extension (docs/FORMAT.md).

``load_chart`` parses the document, collects the ``ros:`` elements with their
lines, expands the sugar into standard SCXML (``ros:outcome`` into
``done.invoke`` transitions with generated conditions, ``ros:refuse`` and
``ros:ignore`` into targetless transitions), removes the remaining ``ros:``
elements and loads the result with python-statemachine in its restricted
datamodel. It returns a ``ChartSpec``: the engine class and the description of
what each state does in ROS. It does not start ROS.
"""

import copy
from dataclasses import dataclass, field
import os
import re

from lxml import etree
from statechart_ros import kinds as kinds_mod
from statechart_ros.kinds import (
    Attr, BUILDER, DATA, ENUM, EVENT, FLOAT, GUARD, MSG_TYPE, NAME, QOS_CHOICES, SRV_TYPE,
    STRING)

ROS_NS = 'https://github.com/jerry73204/ros2_statechart/ns/1'
SCXML_NS = 'http://www.w3.org/2005/07/scxml'
PREFIX = 'sc_ros_'
REFUSAL_VAR = 'sc_ros_refusal'
STATE_TAGS = ('state', 'parallel', 'final')
IDENTIFIER = re.compile(r'^[A-Za-z][A-Za-z0-9_]*$')

# Elements other than invokes: where they go and what they accept.
TOP = 'scxml'
IN_STATE = 'state'
ELEMENTS = {
    'model': (TOP, {'class': Attr(STRING, required=True)}),
    'param': (TOP, {'name': Attr(DATA, required=True)}),
    'subscribe': (TOP, {
        'topic': Attr(NAME, required=True), 'type': Attr(MSG_TYPE, required=True),
        'event': Attr(EVENT, required=True), 'when': Attr(GUARD), 'data': Attr(BUILDER),
        'qos': Attr(ENUM, default='default', choices=QOS_CHOICES)}),
    'service_server': (TOP, {
        'name': Attr(NAME, required=True), 'type': Attr(SRV_TYPE, required=True),
        'event': Attr(STRING), 'reply': Attr(BUILDER)}),
    'action_server': (TOP, {
        'name': Attr(NAME, required=True), 'type': Attr(kinds_mod.ACTION_TYPE, required=True),
        'event': Attr(EVENT, required=True), 'accept': Attr(GUARD),
        'feedback': Attr(BUILDER), 'result_on': Attr(STRING), 'result': Attr(BUILDER),
        'cancel_event': Attr(EVENT)}),
    'timer': (TOP, {'period': Attr(FLOAT, required=True), 'event': Attr(EVENT, required=True)}),
    'outcome': (IN_STATE, {
        'status': Attr(STRING, required=True), 'target': Attr(STRING, required=True),
        'cond': Attr(GUARD)}),
    'on_entry': (IN_STATE, None),
    'on_exit': (IN_STATE, None),
    'refuse': (IN_STATE, {'event': Attr(STRING, required=True),
                          'reason': Attr(STRING, required=True)}),
    'ignore': (IN_STATE, {'event': Attr(STRING, required=True), 'reason': Attr(STRING)}),
    'after': (IN_STATE, {'delay': Attr(FLOAT, required=True),
                         'event': Attr(EVENT, required=True)}),
}
OUTPUT_ATTRS = {
    'publish': {'publish': Attr(NAME, required=True), 'type': Attr(MSG_TYPE, required=True),
                'value': Attr(STRING), 'message': Attr(BUILDER),
                'qos': Attr(ENUM, default='default', choices=QOS_CHOICES)},
    'call': {'call': Attr(NAME, required=True), 'type': Attr(SRV_TYPE, required=True),
             'request': Attr(BUILDER)},
    'set_param': {'set_param': Attr(STRING, required=True), 'node': Attr(STRING),
                  'value': Attr(STRING, required=True)},
}
CHILD_PATH = 'sc_ros_path'  # the resolved file of a ros:chart, added by the loader
_REF = 'sc_ros_ref'  # marks a collected ros:outcome with its generated name
INVOKE_TAGS = {
    'action': 'ros/action', 'service_call': 'ros/service_call', 'wait_for': 'ros/wait_for',
    'chart': 'ros/chart', 'invoke': None,
}


class ChartError(Exception):
    """A chart that cannot be read at all; ``findings`` says why."""

    def __init__(self, findings):
        super().__init__('\n'.join(str(f) for f in findings))
        self.findings = findings


@dataclass
class Finding:
    """One problem in a chart: where, which rule of FORMAT.md section 6, what."""

    file: str
    line: int
    rule: int
    message: str
    severity: str = 'error'

    def __str__(self):
        return f'{self.file}:{self.line}: [rule {self.rule}] {self.severity}: {self.message}'


@dataclass
class RosElement:
    """A ``ros:`` element as written: its tag, attributes, line and owner state."""

    tag: str
    attrs: dict
    line: int
    state: str = None      # None for children of <scxml>
    parent_tag: str = ''   # local name of the parent element

    def get(self, key, default=None):
        return self.attrs.get(key, default)


@dataclass
class InvokeSpec:
    state: str
    tag: str
    kind: str
    attrs: dict
    line: int


@dataclass
class OutcomeSpec:
    state: str
    statuses: tuple
    target: str
    cond: str
    line: int
    name: str


@dataclass
class OutputSpec:
    state: str
    when: str     # 'entry' or 'exit'
    action: str   # 'publish', 'call' or 'set_param'
    attrs: dict
    line: int


@dataclass
class AfterSpec:
    state: str
    delay: float
    event: str
    line: int


@dataclass
class RefusalSpec:
    state: str
    event: str
    reason: str
    ignore: bool
    line: int


@dataclass
class StateInfo:
    id: str  # noqa: A003
    tag: str           # state, parallel, final or history
    parent: str
    line: int
    initial: tuple = ()
    children: list = field(default_factory=list)
    history: str = ''  # 'shallow' or 'deep' for history states

    @property
    def atomic(self):
        return self.tag in ('state', 'final') and not self.children


@dataclass
class TransitionInfo:
    source: str
    events: tuple
    cond: str
    targets: tuple
    type: str  # noqa: A003
    line: int
    origin: str = 'scxml'  # scxml, outcome, refuse, ignore
    label: str = ''


@dataclass
class ChartSpec:
    """Everything the node needs to run a chart, read without starting ROS."""

    name: str
    path: str
    text: str
    engine_doc: str = ''
    plain_doc: str = ''
    engine_class: object = None
    model_class: str = None
    params: list = field(default_factory=list)
    data: dict = field(default_factory=dict)        # id -> expr as written
    inputs: list = field(default_factory=list)      # RosElement (subscribe, servers, timer)
    invokes: dict = field(default_factory=dict)     # state -> InvokeSpec
    outcomes: dict = field(default_factory=dict)    # state -> [OutcomeSpec]
    conditions: dict = field(default_factory=dict)  # generated name -> OutcomeSpec
    outputs: dict = field(default_factory=dict)     # state -> [OutputSpec]
    afters: dict = field(default_factory=dict)      # state -> [AfterSpec]
    refusals: dict = field(default_factory=dict)    # state -> [RefusalSpec]
    states: dict = field(default_factory=dict)      # id -> StateInfo, document order
    transitions: list = field(default_factory=list)
    initial: tuple = ()
    elements: list = field(default_factory=list)    # every ros: element
    sends: list = field(default_factory=list)       # (line, attrs) of <send>
    expressions: list = field(default_factory=list)  # (line, role, text, state)
    findings: list = field(default_factory=list)    # problems found while reading

    def finding(self, line, rule, message, severity='error'):
        self.findings.append(Finding(self.path or '<chart>', line or 0, rule, message, severity))

    def input_events(self):
        """Return the events that ROS inputs send, by input element."""
        events = {}
        for el in self.inputs:
            for key in ('event', 'cancel_event'):
                value = el.get(key)
                if value and '{' not in value:
                    events.setdefault(value, el)
        return events

    def internal_events(self):
        """Return events the chart produces itself (raise, send, after, feedback)."""
        produced = set()
        for spec in self.afters.values():
            produced.update(a.event for a in spec)
        for inv in self.invokes.values():
            fe = inv.attrs.get('feedback_event')
            if fe:
                produced.add(fe)
        for _line, attrs in self.sends:
            if attrs.get('event'):
                produced.add(attrs['event'])
        return produced

    def command_events(self):
        """
        Return the events a generic command service may send.

        Every event a transition, refusal or ignore names, except the chart's own
        (done.*, error.*, raised and sent events, timeouts) and the events of
        other inputs.
        """
        named = set()
        for t in self.transitions:
            named.update(t.events)
        skip = self.internal_events() | set(self.input_events())
        result = set()
        for ev in named:
            if ev in skip or ev == '*' or ev.startswith(('done.', 'error.')):
                continue
            result.add(ev)
        return sorted(result)

    def ancestors(self, state_id):
        """Return the ancestors of a state, innermost first."""
        chain = []
        parent = self.states[state_id].parent
        while parent:
            chain.append(parent)
            parent = self.states[parent].parent
        return chain

    def structure(self):
        """Return the chart as a plain dict: the future StatechartStructure."""
        states = []
        for info in self.states.values():
            entry = {
                'id': info.id, 'kind': _kind_of(info), 'parent': info.parent or '',
                'initial': list(info.initial), 'history': info.history,
                'children': list(info.children), 'line': info.line, 'chart': '',
            }
            inv = self.invokes.get(info.id)
            if inv is not None:
                kind = kinds_mod.get_kind(inv.kind)
                summary = kind.summary(inv.attrs) if kind else {'target': '', 'type': ''}
                entry['invoke'] = {'kind': inv.kind, **summary}
            outs = self.outputs.get(info.id, [])
            if outs:
                entry['outputs'] = [_output_label(o) for o in outs]
            if self.afters.get(info.id):
                entry['after'] = [f'{a.event} after {a.delay:g} s' for a in self.afters[info.id]]
            if self.refusals.get(info.id):
                entry['refuses'] = [{'event': r.event, 'reason': r.reason, 'ignore': r.ignore}
                                    for r in self.refusals[info.id]]
            states.append(entry)
        transitions = [{
            'source': t.source, 'event': ' '.join(t.events), 'cond': t.cond or '',
            'targets': list(t.targets), 'type': t.type or 'external', 'origin': t.origin,
            'label': t.label, 'line': t.line,
        } for t in self.transitions]
        result = {
            'name': self.name, 'source': self.path or '', 'initial': list(self.initial),
            'states': states, 'transitions': transitions,
            'input_events': sorted(set(self.input_events()) | set(self.command_events())),
        }
        _nest_children(self, result, depth=0)
        return result


def _nest_children(spec, structure, depth, prefix=''):
    """Add the states of child charts (ros:chart), qualified by their invoking state."""
    if depth > 8:
        return
    by_id = {s['id']: s for s in structure['states']}
    for state, inv in spec.invokes.items():
        if inv.kind != 'ros/chart' or not inv.attrs.get(CHILD_PATH):
            continue
        try:
            child = load_chart(inv.attrs[CHILD_PATH], load_engine=False)
        except (ChartError, OSError):
            continue
        sub = child.structure()
        owner = prefix + state
        qualify = (lambda sid, owner=owner: f'{owner}/{sid}')
        for s in sub['states']:
            entry = dict(s)
            entry['id'] = qualify(s['id'])
            entry['parent'] = qualify(s['parent']) if s['parent'] else owner
            entry['children'] = [qualify(c) for c in s['children']]
            entry['initial'] = [qualify(i) for i in s['initial']]
            entry['chart'] = qualify(s['chart']) if s.get('chart') else owner
            structure['states'].append(entry)
            if not s['parent'] and owner in by_id:
                by_id[owner]['children'].append(entry['id'])
        for t in sub['transitions']:
            entry = dict(t)
            entry['source'] = qualify(t['source'])
            entry['targets'] = [qualify(x) for x in t['targets']]
            structure['transitions'].append(entry)
        if owner in by_id:
            by_id[owner].setdefault('initial', [])
            if not by_id[owner]['initial']:
                by_id[owner]['initial'] = [qualify(i) for i in sub['initial']]


def _kind_of(info):
    if info.tag == 'history':
        return 'history'
    if info.tag == 'parallel':
        return 'parallel'
    if info.tag == 'final':
        return 'final'
    return 'compound' if info.children else 'atomic'


def _output_label(out):
    when = 'entry' if out.when == 'entry' else 'exit'
    target = out.attrs.get(out.action, '')
    if out.action == 'publish':
        value = out.attrs.get('value', out.attrs.get('message', ''))
        return f'{when}: publish {target} {value}'.strip()
    if out.action == 'call':
        return f'{when}: call {target}'
    return f'{when}: set_param {target}={out.attrs.get("value", "")}'


def local(tag):
    """Return the local name of a qualified tag."""
    return tag.split('}', 1)[1] if isinstance(tag, str) and '}' in tag else tag


def namespace(tag):
    """Return the namespace of a qualified tag ('' when none)."""
    return tag[1:].split('}', 1)[0] if isinstance(tag, str) and tag.startswith('{') else ''


def is_ros(el):
    return isinstance(el.tag, str) and namespace(el.tag) == ROS_NS


def is_scxml(el, name=None):
    if not isinstance(el.tag, str) or namespace(el.tag) != SCXML_NS:
        return False
    return name is None or local(el.tag) == name


def child_path(parent_path, src):
    """Resolve a ros:chart src: package:// URLs, absolute paths, or relative to the parent."""
    if src.startswith('package://') or os.path.isabs(src):
        return resolve_path(src)
    base = os.path.dirname(parent_path) if parent_path and parent_path != '<chart>' else '.'
    return os.path.normpath(os.path.join(base, src))


def resolve_path(source):
    """Resolve ``package://pkg/rel/path`` to a file path; other paths unchanged."""
    if source.startswith('package://'):
        from ament_index_python.packages import get_package_share_directory
        pkg, _, rel = source[len('package://'):].partition('/')
        return os.path.join(get_package_share_directory(pkg), rel)
    return source


def parse(text, path='<chart>'):
    """Parse a document with line numbers; refuse DTDs and entities."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False,
                             remove_comments=False, huge_tree=False)
    try:
        root = etree.fromstring(text.encode('utf-8') if isinstance(text, str) else text,
                                parser)
    except etree.XMLSyntaxError as exc:
        raise ChartError([Finding(path, exc.lineno or 0, 1, f'not well-formed XML: {exc.msg}')])
    tree = root.getroottree()
    if tree.docinfo.doctype or tree.docinfo.internalDTD is not None:
        raise ChartError([Finding(path, 1, 1, 'DOCTYPE/DTD is not allowed in a chart')])
    if not is_scxml(root, 'scxml'):
        raise ChartError([Finding(path, root.sourceline or 1, 1,
                                  'the root element must be <scxml> in the SCXML namespace '
                                  f'{SCXML_NS}')])
    return root


def load_chart(source, params=None, name=None, text=None, load_engine=True):
    """
    Read a chart and return its ``ChartSpec``.

    ``source`` is a file path or ``package://`` URL (or, with ``text``, a name
    for messages). ``params`` maps ``ros:param`` names to values that replace
    the ``<data>`` defaults. Problems that do not prevent reading are collected
    in ``spec.findings``; ``validate`` adds the remaining checks.
    """
    path = resolve_path(source) if source else None
    if text is None:
        with open(path, encoding='utf-8') as f:
            text = f.read()
    root = parse(text, path or '<chart>')
    if name is None:
        name = root.get('name') or (os.path.splitext(os.path.basename(path))[0]
                                    if path else 'chart')
    spec = ChartSpec(name=name, path=path or '<chart>', text=text)
    spec.initial = tuple((root.get('initial') or '').split())
    _collect(spec, root)
    engine_root, plain_root = _expand(spec, root, params or {})
    spec.engine_doc = _serialize(engine_root)
    spec.plain_doc = _serialize(plain_root)
    if load_engine:
        load_engine_class(spec)
    return spec


def load_engine_class(spec):
    """Load the expanded document with python-statemachine (restricted datamodel)."""
    from statemachine.exceptions import InvalidDefinition
    from statemachine.io import load
    try:
        spec.engine_class = load(spec.engine_doc, format='scxml', trusted=False,
                                 name=spec.name)
    except (InvalidDefinition, ValueError, KeyError, TypeError) as exc:
        spec.finding(1, 2, f'the engine refused the chart: {exc}')
    return spec.engine_class


def _serialize(root):
    etree.cleanup_namespaces(root)
    return etree.tostring(root, encoding='unicode', pretty_print=False)


def _check_attrs(spec, el, table, what):
    for key, attr in table.items():
        if attr.required and not el.get(key):
            spec.finding(el.sourceline, 1, f'{what} needs the attribute "{key}"')
    for key, value in el.attrib.items():
        if key not in table:
            spec.finding(el.sourceline, 1, f'{what} has no attribute "{key}"')
            continue
        problem = kinds_mod.check_value(table[key], value)
        if problem:
            spec.finding(el.sourceline, 1, f'{what}: "{key}" {problem} (got "{value}")')


def _collect(spec, root):
    """Walk the document: states, transitions, ros: elements, sends."""
    def walk(el, parent_state):
        for child in el:
            if not isinstance(child.tag, str):
                continue
            if is_ros(child):
                _collect_ros(spec, child, el, parent_state)
                continue
            if not is_scxml(child):
                continue
            tag = local(child.tag)
            if tag in STATE_TAGS or tag == 'history':
                sid = child.get('id')
                if not sid:
                    spec.finding(child.sourceline, 9, f'<{tag}> needs an id')
                    sid = f'{PREFIX}anonymous_{child.sourceline}'
                elif not IDENTIFIER.match(sid):
                    spec.finding(child.sourceline, 9,
                                 f'state id "{sid}" is not a Python identifier')
                if sid in spec.states:
                    spec.finding(child.sourceline, 1, f'duplicate state id "{sid}"')
                info = StateInfo(id=sid, tag=tag, parent=parent_state, line=child.sourceline,
                                 history=(child.get('type') or 'shallow')
                                 if tag == 'history' else '')
                initial = child.get('initial')
                if initial:
                    info.initial = tuple(initial.split())
                spec.states[sid] = info
                if parent_state:
                    spec.states[parent_state].children.append(sid)
                walk(child, sid)
                if tag != 'history' and not info.initial and info.children and tag == 'state':
                    init_el = child.find(f'{{{SCXML_NS}}}initial')
                    if init_el is not None:
                        tr = init_el.find(f'{{{SCXML_NS}}}transition')
                        if tr is not None and tr.get('target'):
                            info.initial = tuple(tr.get('target').split())
                    if not info.initial:
                        first = [c for c in info.children
                                 if spec.states[c].tag != 'history']
                        info.initial = tuple(first[:1])
            elif tag == 'transition':
                if child.get('cond') is not None:
                    spec.expressions.append((child.sourceline, 'cond', child.get('cond'),
                                             parent_state))
                if parent_state is not None and local(el.tag) in STATE_TAGS + ('history',):
                    spec.transitions.append(TransitionInfo(
                        source=parent_state, events=tuple((child.get('event') or '').split()),
                        cond=child.get('cond'),
                        targets=tuple((child.get('target') or '').split()),
                        type=child.get('type') or '', line=child.sourceline))
                walk(child, parent_state)
            elif tag == 'data':
                if child.get('id'):
                    spec.data[child.get('id')] = child.get('expr')
                if child.get('expr') is not None:
                    spec.expressions.append((child.sourceline, 'value', child.get('expr'),
                                             parent_state))
            elif tag in ('if', 'elseif'):
                if child.get('cond') is not None:
                    spec.expressions.append((child.sourceline, 'cond', child.get('cond'),
                                             parent_state))
                walk(child, parent_state)
            elif tag == 'assign':
                spec.expressions.append((child.sourceline, 'location',
                                         child.get('location') or '', parent_state))
                if child.get('expr') is not None:
                    spec.expressions.append((child.sourceline, 'value', child.get('expr'),
                                             parent_state))
            elif tag == 'send':
                spec.sends.append((child.sourceline, dict(child.attrib)))
                walk(child, parent_state)
            else:
                walk(child, parent_state)
    walk(root, None)
    if not spec.initial:
        first = [s for s in spec.states.values() if s.parent is None and s.tag != 'history']
        spec.initial = (first[0].id,) if first else ()


def _collect_ros(spec, el, parent, parent_state):
    tag = local(el.tag)
    parent_tag = local(parent.tag) if is_scxml(parent) else '?'
    item = RosElement(tag=tag, attrs=dict(el.attrib), line=el.sourceline, state=parent_state,
                      parent_tag=parent_tag)
    spec.elements.append(item)
    where = None
    if parent_tag == 'scxml':
        where = 'scxml'
    elif parent_tag in STATE_TAGS:
        where = 'state'
    if where is None:
        spec.finding(el.sourceline, 7, f'ros:{tag} is inside <{parent_tag}>: ros: elements go '
                                       'only directly under <scxml>, <state>, <parallel> or '
                                       '<final>, never in executable content')
        return
    if tag in INVOKE_TAGS:
        if where != 'state':
            spec.finding(el.sourceline, 1, f'ros:{tag} belongs in a state, not under <scxml>')
            return
        kind_name = INVOKE_TAGS[tag] or el.get('kind')
        attrs = dict(el.attrib)
        if tag == 'invoke':
            attrs.pop('kind', None)
            if not kind_name:
                spec.finding(el.sourceline, 1, 'ros:invoke needs the attribute "kind"')
                return
        kind = kinds_mod.get_kind(kind_name)
        if kind is None:
            spec.finding(el.sourceline, 1, f'unknown invoke kind "{kind_name}" (no entry point '
                                           f'in {kinds_mod.ENTRY_POINT_GROUP})')
        else:
            _check_attrs(spec, _AttrView(el, attrs), kind.attributes, f'ros:{tag}')
            for msg in kind.check(attrs):
                spec.finding(el.sourceline, 1, f'ros:{tag}: {msg}')
        if parent_state in spec.invokes:
            spec.finding(el.sourceline, 7, f'state "{parent_state}" already has an invoke '
                                           f'(line {spec.invokes[parent_state].line}); two '
                                           'pieces of work are two regions of a <parallel>')
            return
        if kind_name == 'ros/chart' and attrs.get('src'):
            attrs[CHILD_PATH] = child_path(spec.path, attrs['src'])
        spec.invokes[parent_state] = InvokeSpec(parent_state, tag, kind_name, attrs,
                                                el.sourceline)
        return
    if tag not in ELEMENTS:
        spec.finding(el.sourceline, 1, f'unknown element ros:{tag}')
        return
    place, table = ELEMENTS[tag]
    if place != where:
        spec.finding(el.sourceline, 1, f'ros:{tag} belongs '
                     + ('directly under <scxml>' if place == TOP else 'in a state'))
        return
    if tag in ('on_entry', 'on_exit'):
        actions = [a for a in OUTPUT_ATTRS if el.get(a) is not None]
        if len(actions) != 1:
            spec.finding(el.sourceline, 1, f'ros:{tag} takes exactly one of publish, call, '
                                           'set_param')
            return
        action = actions[0]
        _check_attrs(spec, el, OUTPUT_ATTRS[action], f'ros:{tag} {action}')
        if action == 'publish' and el.get('value') is None and el.get('message') is None:
            spec.finding(el.sourceline, 1, f'ros:{tag} publish needs "value" or "message"')
        spec.outputs.setdefault(parent_state, []).append(OutputSpec(
            parent_state, 'entry' if tag == 'on_entry' else 'exit', action, dict(el.attrib),
            el.sourceline))
        return
    _check_attrs(spec, el, table, f'ros:{tag}')
    if tag == 'model':
        if spec.model_class is not None:
            spec.finding(el.sourceline, 1, 'a chart has at most one ros:model')
        spec.model_class = el.get('class')
    elif tag == 'param':
        spec.params.append(el.get('name'))
    elif tag in ('subscribe', 'service_server', 'action_server', 'timer'):
        spec.inputs.append(item)
    elif tag == 'outcome':
        statuses = tuple((el.get('status') or '').split())
        n = sum(len(v) for v in spec.outcomes.values()) + 1
        out = OutcomeSpec(parent_state, statuses, el.get('target'), el.get('cond'),
                          el.sourceline, f'{PREFIX}outcome_{parent_state}_{n}')
        spec.outcomes.setdefault(parent_state, []).append(out)
        spec.conditions[out.name] = out
        el.set(_REF, out.name)
    elif tag in ('refuse', 'ignore'):
        spec.refusals.setdefault(parent_state, []).append(RefusalSpec(
            parent_state, el.get('event'), el.get('reason') or '', tag == 'ignore',
            el.sourceline))
    elif tag == 'after':
        try:
            delay = float(el.get('delay'))
        except (TypeError, ValueError):
            delay = 0.0
        spec.afters.setdefault(parent_state, []).append(
            AfterSpec(parent_state, delay, el.get('event'), el.sourceline))


class _AttrView:
    """An element with a replaced attribute dict, for attribute checks."""

    def __init__(self, el, attrs):
        self.attrib = attrs
        self.sourceline = el.sourceline

    def get(self, key, default=None):
        return self.attrib.get(key, default)


def _q(name):
    return f'{{{SCXML_NS}}}{name}'


def _expand(spec, root, params):
    """Return (engine document, plain document) roots."""
    engine = copy.deepcopy(root)
    for el in list(engine.iter()):
        if not is_ros(el):
            continue
        parent = el.getparent()
        tag = local(el.tag)
        state = parent.get('id')
        replacement = None
        if tag == 'outcome' and state is not None:
            out = spec.conditions.get(el.get(_REF))
            if out is not None:
                replacement = etree.Element(_q('transition'), nsmap={None: SCXML_NS})
                replacement.set('event', f'done.invoke.{state}')
                replacement.set('cond', out.name)
                if out.target:
                    replacement.set('target', out.target)
                spec.transitions.append(TransitionInfo(
                    source=state, events=(f'done.invoke.{state}',), cond=out.name,
                    targets=tuple((out.target or '').split()), type='', line=out.line,
                    origin='outcome', label=' '.join(out.statuses)
                    + (f' [{out.cond}]' if out.cond else '')))
        elif tag in ('refuse', 'ignore') and state is not None and el.get('event'):
            replacement = etree.Element(_q('transition'), nsmap={None: SCXML_NS})
            replacement.set('event', el.get('event'))
            if tag == 'refuse':
                assign = etree.SubElement(replacement, _q('assign'))
                assign.set('location', REFUSAL_VAR)
                assign.set('expr', repr(el.get('reason') or ''))
            spec.transitions.append(TransitionInfo(
                source=state, events=tuple(el.get('event').split()), cond=None, targets=(),
                type='', line=el.sourceline, origin=tag, label=el.get('reason') or ''))
        if replacement is not None:
            replacement.tail = el.tail
            parent.replace(el, replacement)
        else:
            _remove(el)
    _declare_data(engine, REFUSAL_VAR, repr(''))
    for name, value in params.items():
        if name in spec.data:
            _set_data(engine, name, repr(value))
    plain = copy.deepcopy(engine)
    _wrap(engine, spec.initial)
    for state, afters in spec.afters.items():
        el = plain.find(f'.//*[@id="{state}"]')
        if el is None:
            continue
        onentry = etree.Element(_q('onentry'))
        onexit = etree.Element(_q('onexit'))
        for i, after in enumerate(afters):
            send = etree.SubElement(onentry, _q('send'))
            send.set('event', after.event)
            send.set('delay', f'{after.delay:g}s')
            send.set('id', f'{PREFIX}after_{state}_{i + 1}')
            cancel = etree.SubElement(onexit, _q('cancel'))
            cancel.set('sendid', f'{PREFIX}after_{state}_{i + 1}')
        pos = _first_content_index(el)
        el.insert(pos, onexit)
        el.insert(pos, onentry)
    return engine, plain


ROOT = PREFIX + 'root'
STOPPED = PREFIX + 'stopped'
STOP_EVENT = 'sc_ros.stop'


def _wrap(root, initial):
    """
    Put the chart's states in one compound state the node can leave.

    The node stops a chart by sending ``sc_ros.stop``: the engine then exits
    every state the standard way (exit actions, outputs, invokes cancelled),
    which ``engine.stop()`` would not do. A top-level ``<final>`` of the chart
    ends in the same place through ``done.state.sc_ros_root``.
    """
    wrapper = etree.Element(_q('state'))
    wrapper.set('id', ROOT)
    if initial:
        wrapper.set('initial', ' '.join(initial))
    first = None
    for child in list(root):
        if isinstance(child.tag, str) and is_scxml(child) and local(child.tag) in STATE_TAGS:
            if first is None:
                first = root.index(child)
            wrapper.append(child)
    for event in (STOP_EVENT, f'done.state.{ROOT}'):
        tr = etree.SubElement(wrapper, _q('transition'))
        tr.set('event', event)
        tr.set('target', STOPPED)
    stopped = etree.Element(_q('final'))
    stopped.set('id', STOPPED)
    root.insert(first if first is not None else len(root), stopped)
    root.insert(first if first is not None else len(root), wrapper)
    root.set('initial', ROOT)


def _first_content_index(el):
    for i, child in enumerate(el):
        if isinstance(child.tag, str) and local(child.tag) not in ('datamodel', 'onentry',
                                                                   'onexit', 'initial'):
            return i
    return len(el)


def _remove(el):
    """Remove an element together with the line it stood on."""
    parent = el.getparent()
    prev = el.getprevious()
    before = prev.tail if prev is not None else parent.text
    tail = el.tail or ''
    if before is not None and '\n' in before and before.rstrip(' \t').endswith('\n') \
            and tail.startswith('\n'):
        before = before.rstrip(' \t')[:-1]
    joined = (before or '') + tail
    if prev is not None:
        prev.tail = joined
    else:
        parent.text = joined
    parent.remove(el)


def _declare_data(root, name, expr):
    for data in root.iter(_q('data')):
        if data.get('id') == name:
            return
    dm = root.find(_q('datamodel'))
    if dm is None:
        dm = etree.Element(_q('datamodel'))
        dm.tail = root.text
        root.insert(0, dm)
    data = etree.SubElement(dm, _q('data'))
    data.set('id', name)
    data.set('expr', expr)


def _set_data(root, name, expr):
    for data in root.iter(_q('data')):
        if data.get('id') == name:
            data.set('expr', expr)
            data.text = None
            for child in list(data):
                data.remove(child)
            if 'src' in data.attrib:
                del data.attrib['src']
