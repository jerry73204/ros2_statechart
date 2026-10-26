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


"""Introspection messages of a chart: structure, status, transitions."""

import json

from builtin_interfaces.msg import Time
from statechart_ros.runtime import to_json
from statechart_ros_msgs.msg import (DataValue, InvokeStatus, StatechartStatus,
                                     StatechartStructure, StateInfo, Transition, TransitionInfo)

KINDS = {'atomic': StateInfo.ATOMIC, 'compound': StateInfo.COMPOUND,
         'parallel': StateInfo.PARALLEL, 'final': StateInfo.FINAL,
         'history': StateInfo.HISTORY}
KIND_NAMES = {v: k for k, v in KINDS.items()}


def stamp(seconds):
    t = Time()
    t.sec = int(seconds)
    t.nanosec = int(round((seconds - int(seconds)) * 1e9)) % 1000000000
    return t


def structure_msg(structure, node_name='', now=0.0, debug_events=False):
    """Build a StatechartStructure from ``ChartSpec.structure()``."""
    msg = StatechartStructure()
    msg.stamp = stamp(now)
    msg.name = structure['name']
    msg.source = structure['source']
    msg.node = node_name
    msg.initial = list(structure['initial'])
    for s in structure['states']:
        info = StateInfo()
        info.id = s['id']
        info.parent = s['parent']
        info.kind = KINDS[s['kind']]
        info.initial = list(s['initial'])
        info.history = s['history']
        info.children = list(s['children'])
        info.chart = s.get('chart', '')
        inv = s.get('invoke')
        if inv:
            info.invoke_kind = inv['kind']
            info.invoke_target = inv.get('target', '')
            info.invoke_type = inv.get('type', '')
        info.outputs = list(s.get('outputs', []))
        info.timeouts = list(s.get('after', []))
        for r in s.get('refuses', []):
            text = r['event'] + (f': {r["reason"]}' if r['reason'] else '')
            (info.ignores if r['ignore'] else info.refuses).append(text)
        info.line = int(s.get('line', 0))
        msg.states.append(info)
    for t in structure['transitions']:
        tr = TransitionInfo()
        tr.source = t['source']
        tr.event = t['event']
        tr.cond = t['cond']
        tr.targets = list(t['targets'])
        tr.type = t['type']
        tr.origin = t['origin']
        tr.label = t['label']
        tr.line = int(t.get('line', 0))
        msg.transitions.append(tr)
    msg.input_events = list(structure['input_events'])
    msg.debug_events = debug_events
    return msg


def structure_dict(msg):
    """Convert a StatechartStructure back into the structure dict (viewer, CLI)."""
    states = []
    for s in msg.states:
        entry = {'id': s.id, 'parent': s.parent, 'kind': KIND_NAMES.get(s.kind, 'atomic'),
                 'initial': list(s.initial), 'history': s.history,
                 'children': list(s.children), 'chart': s.chart, 'line': s.line}
        if s.invoke_kind:
            entry['invoke'] = {'kind': s.invoke_kind, 'target': s.invoke_target,
                               'type': s.invoke_type}
        if s.outputs:
            entry['outputs'] = list(s.outputs)
        if s.timeouts:
            entry['after'] = list(s.timeouts)
        refuses = [{'event': r.split(': ', 1)[0], 'reason': r.split(': ', 1)[1]
                    if ': ' in r else '', 'ignore': False} for r in s.refuses]
        refuses += [{'event': r.split(': ', 1)[0], 'reason': r.split(': ', 1)[1]
                     if ': ' in r else '', 'ignore': True} for r in s.ignores]
        if refuses:
            entry['refuses'] = refuses
        states.append(entry)
    transitions = [{'source': t.source, 'event': t.event, 'cond': t.cond,
                    'targets': list(t.targets), 'type': t.type, 'origin': t.origin,
                    'label': t.label, 'line': t.line} for t in msg.transitions]
    return {'name': msg.name, 'source': msg.source, 'node': msg.node,
            'initial': list(msg.initial), 'states': states, 'transitions': transitions,
            'input_events': list(msg.input_events), 'debug_events': msg.debug_events}


def status_msg(name, snapshot, data, now):
    """Build a StatechartStatus from ``ChartRunner.snapshot()`` and datamodel values."""
    msg = StatechartStatus()
    msg.stamp = stamp(now)
    msg.name = name
    msg.sequence = snapshot['sequence']
    msg.active = list(snapshot['active'])
    msg.last_event = snapshot['last_event']
    msg.handled = snapshot['handled']
    msg.refusal = snapshot['refusal']
    msg.running = snapshot['running']
    for key, value in sorted(data.items()):
        item = DataValue()
        item.key = key
        item.json = value
        msg.data.append(item)
    for inv in snapshot['invokes']:
        item = InvokeStatus()
        item.state = inv['state']
        item.kind = inv['kind']
        item.target = inv['target']
        item.since = stamp(inv['since'])
        item.feedback = json.dumps(inv['feedback'], sort_keys=True) if inv['feedback'] else ''
        msg.invokes.append(item)
    return msg


def transition_msg(name, record):
    """Build a Transition message from a runner Record."""
    msg = Transition()
    msg.stamp = stamp(record.stamp)
    msg.name = name
    msg.sequence = record.sequence
    msg.event = record.event
    msg.data = to_json(record.data) if record.data else ''
    msg.source_configuration = list(record.source)
    msg.target_configuration = list(record.target)
    msg.taken = list(record.taken)
    msg.handled = record.handled
    msg.refusal = record.refusal
    msg.duration = float(record.duration)
    return msg
