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
The interface of a chart: what other packages must provide or may use (docs/INTERFACES.md).

``chart_interface`` reads a chart, its child charts included, and returns the
topics it subscribes to and publishes, the services and actions it serves and
calls, and the parameters it sets on other nodes, as a plain dict that
``dump`` writes as YAML (``statechart_interface: 1``). ``compare`` names the
differences between two interfaces, each breaking, additive or doc only.
``check_graph`` compares an interface with a running ROS graph. Nothing here
starts ROS except ``check_graph``, which receives a node.
"""

import os
import re
import time

from statechart_ros import kinds as kinds_mod
from statechart_ros.loader import ChartError, CHILD_PATH, DOC, load_chart
import yaml

VERSION = 1
# section -> (what other packages do, the fields whose change breaks them)
SECTIONS = {
    'subscribes': ('publish these topics for the chart', ('type', 'qos')),
    'publishes': ('the chart publishes these topics', ('type', 'qos')),
    'services_served': ('the chart serves these services', ('type',)),
    'actions_served': ('the chart serves these actions', ('type',)),
    'services_called': ('serve these services for the chart', ('type',)),
    'actions_called': ('serve these actions for the chart', ('type',)),
    'parameters_set': ('the chart sets these parameters of other nodes', ()),
}
MAX_DEPTH = 8


def chart_interface(source):
    """
    Return the interface of a chart file (or ``package://`` URL) as a dict.

    Raises ``ChartError`` when the chart cannot be read. Problems that do not
    stop reading, such as one topic subscribed with two types, are listed
    under ``warnings`` of the returned dict and are not part of the file.
    """
    spec = load_chart(source, load_engine=False)
    result = {section: {} for section in SECTIONS}
    warnings = []
    _collect(spec, result, warnings, 0)
    interface = {'statechart_interface': VERSION, 'chart': spec.name}
    for section in SECTIONS:
        entries = [result[section][key] for key in sorted(result[section])]
        if entries:
            interface[section] = entries
    interface['warnings'] = warnings
    return interface


def _collect(spec, result, warnings, depth):
    for el in spec.inputs:
        doc = el.get(DOC, '')
        if el.tag == 'subscribe':
            _add(result, warnings, 'subscribes', {
                'name': el.get('topic'), 'type': el.get('type'),
                'qos': el.get('qos', 'default'), 'doc': doc})
        elif el.tag == 'service_server':
            entry = {'name': el.get('name'), 'type': el.get('type'), 'doc': doc}
            event = el.get('event')
            if not event or '{' in event:
                # the request names the event: the commands are part of the contract
                entry['commands'] = commands(event, spec.command_events())
            _add(result, warnings, 'services_served', entry)
        elif el.tag == 'action_server':
            _add(result, warnings, 'actions_served', {
                'name': el.get('name'), 'type': el.get('type'), 'doc': doc})
    for outs in spec.outputs.values():
        for out in outs:
            doc = out.attrs.get(DOC, '')
            if out.action == 'publish':
                topic = out.attrs['publish']
                latched = any(o.action == 'publish' and o.attrs.get('publish') == topic
                              and o.attrs.get('qos') == 'latched'
                              for os_ in spec.outputs.values() for o in os_)
                _add(result, warnings, 'publishes', {
                    'name': topic, 'type': out.attrs.get('type'),
                    'qos': 'latched' if latched else 'default', 'doc': doc})
            elif out.action == 'call':
                _add(result, warnings, 'services_called', {
                    'name': out.attrs['call'], 'type': out.attrs.get('type'), 'doc': doc})
            elif out.action == 'set_param' and out.attrs.get('node'):
                _add(result, warnings, 'parameters_set', {
                    'name': out.attrs['set_param'], 'node': out.attrs['node'], 'doc': doc})
    for inv in spec.invokes.values():
        if inv.kind == 'ros/chart':
            path = inv.attrs.get(CHILD_PATH)
            if depth >= MAX_DEPTH or not path:
                continue
            try:
                child = load_chart(path, load_engine=False)
            except (ChartError, OSError) as exc:
                warnings.append(f'child chart {path} not read: {exc}')
                continue
            _collect(child, result, warnings, depth + 1)
            continue
        kind = kinds_mod.get_kind(inv.kind)
        if kind is None:
            warnings.append(f'state {inv.state}: unknown invoke kind "{inv.kind}"')
            continue
        for ep in kind.endpoints(inv.attrs):
            section = {'topic': 'subscribes', 'service': 'services_called',
                       'action': 'actions_called'}[ep['kind']]
            entry = {'name': ep['name'], 'type': ep['type'], 'doc': inv.doc}
            if ep['kind'] == 'topic':
                entry['qos'] = ep.get('qos', 'default')
            _add(result, warnings, section, entry)


def commands(template, events):
    """
    Return what callers of a service may send, given its event template.

    Without a template (``SendEvent``) every command event; with one field
    (``control.{command}``) the field's values of the events that match it;
    with several fields the matching event names.
    """
    if not template:
        return list(events)
    fields = re.findall(r'\{(\w+)\}', template)
    pattern = re.compile('^' + re.sub(r'\\\{\w+\\\}', '([^ ]+)', re.escape(template)) + '$')
    found = []
    for ev in events:
        m = pattern.match(ev)
        if m:
            found.append(m.group(1) if len(fields) == 1 else ev)
    return sorted(set(found))


def _key(section, entry):
    return f'{entry["node"]} {entry["name"]}' if section == 'parameters_set' else entry['name']


def _add(result, warnings, section, entry):
    """Add an endpoint; the same name twice keeps the first and warns if they disagree."""
    entry = {k: v for k, v in entry.items() if v not in (None, '')}
    key = _key(section, entry)
    old = result[section].get(key)
    if old is None:
        result[section][key] = _ordered(entry)
        return
    for field in SECTIONS[section][1]:
        if old.get(field) != entry.get(field):
            warnings.append(f'{section} {key}: {field} {old.get(field)} and '
                            f'{entry.get(field)}; the interface keeps {old.get(field)}')
    if entry.get('doc') and entry['doc'] not in old.get('doc', '').split('\n'):
        old['doc'] = (old['doc'] + '\n' + entry['doc']) if old.get('doc') else entry['doc']
        result[section][key] = _ordered(old)


def _ordered(entry):
    order = ('name', 'node', 'type', 'qos', 'commands', 'doc')
    return {k: entry[k] for k in order if k in entry}


def dump(interface, source=''):
    """Return an interface as the YAML text of an interface file."""
    data = {k: v for k, v in interface.items() if k != 'warnings'}
    head = '# The interface of a statechart'
    if source:
        head += f', generated from {os.path.basename(source)}'
    head += (' by `ros2 statechart interface`.\n'
             '# Do not edit; regenerate it when the chart changes.\n')
    return head + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=88)


def load(path):
    """Read an interface file; raise ``ValueError`` if it is not one."""
    with open(path, encoding='utf-8') as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or 'statechart_interface' not in data:
        raise ValueError(f'{path} is not a statechart interface file')
    if data['statechart_interface'] != VERSION:
        raise ValueError(f'{path}: interface version {data["statechart_interface"]}, '
                         f'this tool reads version {VERSION}')
    return data


def endpoints(interface, section):
    """Return the entries of a section by key."""
    return {_key(section, e): e for e in interface.get(section) or []}


def compare(old, new):
    """
    Return the differences between two interfaces as (severity, message) pairs.

    Severity is ``breaking`` (an endpoint removed, a type or QoS changed, a
    command removed), ``additive`` (an endpoint or command added) or ``doc``.
    """
    changes = []
    for section, (_, fields) in SECTIONS.items():
        before, after = endpoints(old, section), endpoints(new, section)
        for key in sorted(set(before) | set(after)):
            a, b = before.get(key), after.get(key)
            if b is None:
                changes.append(('breaking', f'{section} {key}: removed'))
                continue
            if a is None:
                changes.append(('additive', f'{section} {key}: added'))
                continue
            for field in fields:
                if a.get(field) != b.get(field):
                    changes.append(('breaking', f'{section} {key}: {field} '
                                                f'{a.get(field)} -> {b.get(field)}'))
            ca, cb = set(a.get('commands') or []), set(b.get('commands') or [])
            for ev in sorted(ca - cb):
                changes.append(('breaking', f'{section} {key}: command {ev} removed'))
            for ev in sorted(cb - ca):
                changes.append(('additive', f'{section} {key}: command {ev} added'))
            if (a.get('doc') or '') != (b.get('doc') or ''):
                changes.append(('doc', f'{section} {key}: doc changed'))
    return changes


# --- the running graph ---------------------------------------------------------------

def resolve(name, namespace='/', node_name='statechart'):
    """Resolve a name as written in a chart against the chart node's namespace."""
    if name.startswith('/'):
        return name
    ns = '/' + namespace.strip('/') if namespace.strip('/') else ''
    if name.startswith('~/'):
        return f'{ns}/{node_name}/{name[2:]}'
    return f'{ns}/{name}'


def check_graph(node, interface, sections=None, names=None, namespace='/',
                node_name='statechart', timeout=5.0):
    """
    Compare the running graph with an interface; return the problems as strings.

    For each endpoint (of ``sections``, by default all, and of ``names``, by
    default all) the counterpart must exist: a publisher of each subscribed
    topic, with its type and a QoS the chart's subscription accepts; a
    subscriber of each published topic; a server of each called service or
    action; a client of each served service or action; the node of each set
    parameter. Names written relative resolve against ``namespace`` and the
    chart node's name ``node_name``. Discovery takes time, so the check
    repeats until it passes or ``timeout`` seconds have passed.
    """
    def resolver(section, name):
        return resolve(name, namespace, node_name)

    deadline = time.monotonic() + timeout
    while True:
        problems = check_once(node, interface, resolver, sections, names)
        if not problems or time.monotonic() >= deadline:
            return problems
        time.sleep(0.2)


def check_once(node, interface, resolver, sections=None, names=None):
    """
    Compare the graph with an interface once; ``check_graph`` without the waiting.

    ``resolver(section, name)`` returns the full name of an endpoint (the
    chart node passes its own resolution, which applies its remappings).
    """
    problems = []
    others = [(n, ns) for n, ns in node.get_node_names_and_namespaces()]
    for section in sections or SECTIONS:
        for key, entry in endpoints(interface, section).items():
            if names is not None and entry['name'] not in names:
                continue
            if section == 'parameters_set':
                target = resolver(section, entry['node'])
                full = {(ns.rstrip('/') + '/' + n) for n, ns in others}
                if target not in full:
                    problems.append(f'{section} {key}: no node {target}')
                continue
            name = resolver(section, entry['name'])
            problem = _CHECKS[section](node, others, name, entry)
            if problem:
                problems.append(f'{section} {entry["name"]} ({name}): {problem}')
    return problems


def _topic_check(peer):
    def check(node, others, name, entry):
        infos = (node.get_publishers_info_by_topic(name) if peer == 'publisher'
                 else node.get_subscriptions_info_by_topic(name))
        if not infos:
            return f'no {peer}'
        typed = [i for i in infos if i.topic_type == entry['type']]
        if not typed:
            return f'{peer}s have type {", ".join(sorted({i.topic_type for i in infos}))}, ' \
                   f'not {entry["type"]}'
        qos = entry.get('qos', 'default')
        ok = [i for i in typed if _qos_compatible(i.qos_profile, qos, peer)]
        if not ok:
            return f'no {peer} with QoS compatible with "{qos}"'
        return None
    return check


def _qos_compatible(profile, chart_qos, peer):
    """Whether a peer's QoS matches the chart's QoS profile ``chart_qos``."""
    from rclpy.qos import DurabilityPolicy, ReliabilityPolicy
    from statechart_ros.host import qos_profile
    mine = qos_profile(chart_qos)
    if peer == 'publisher':   # the chart subscribes: the publisher must offer at least as much
        pub, sub = profile, mine
    else:                     # the chart publishes: the subscriber must request no more
        pub, sub = mine, profile
    if sub.reliability == ReliabilityPolicy.RELIABLE and \
            pub.reliability == ReliabilityPolicy.BEST_EFFORT:
        return False
    if sub.durability == DurabilityPolicy.TRANSIENT_LOCAL and \
            pub.durability == DurabilityPolicy.VOLATILE:
        return False
    return True


def _by_node(node, others, getter):
    found = {}
    for n, ns in others:
        try:
            for name, types in getter(n, ns):
                found.setdefault(name, set()).update(types)
        except Exception:  # noqa: B902 - a node that left between the two calls
            continue
    return found


def _service_check(peer):
    def check(node, others, name, entry):
        getter = (node.get_service_names_and_types_by_node if peer == 'server'
                  else node.get_client_names_and_types_by_node)
        return _typed(_by_node(node, others, getter), name, entry['type'], peer)
    return check


def _action_check(peer):
    def check(node, others, name, entry):
        from rclpy.action import graph
        fn = (graph.get_action_server_names_and_types_by_node if peer == 'server'
              else graph.get_action_client_names_and_types_by_node)
        found = _by_node(node, others, lambda n, ns: fn(node, n, ns))
        return _typed(found, name, entry['type'], f'action {peer}')
    return check


def _typed(found, name, type_name, peer):
    if name not in found:
        return f'no {peer}'
    if type_name not in found[name]:
        return f'{peer} has type {", ".join(sorted(found[name]))}, not {type_name}'
    return None


_CHECKS = {
    'subscribes': _topic_check('publisher'),
    'publishes': _topic_check('subscriber'),
    'services_served': _service_check('client'),
    'actions_served': _action_check('client'),
    'services_called': _service_check('server'),
    'actions_called': _action_check('server'),
}
