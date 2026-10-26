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
Check a chart completely: the rules of docs/FORMAT.md section 6.

``validate(spec)`` returns a list of ``Finding`` (file, line, rule, message).
The same checks run in ``ros2 statechart validate`` and when the node
configures a chart; any error stops the node from starting.
"""

import ast
import importlib
import itertools
import os

from lxml import etree
from statechart_ros import kinds as kinds_mod
from statechart_ros.loader import (
    ELEMENTS, Finding, INVOKE_TAGS, OUTPUT_ATTRS, PREFIX, REFUSAL_VAR)

SCHEMA_DIR = os.path.join(os.path.dirname(__file__), 'schema')
MAX_CONFIGURATIONS = 20000
SYSTEM_NAMES = {'In', '_event', '_name', '_sessionid', '_ioprocessors', 'True', 'False',
                'None', 'true', 'false', 'null'}
# The engine keeps the configuration in `state` and passes the others to callbacks
# itself (ENGINE.md E18); a data item with one of these names is never readable.
RESERVED_DATA = {'state', 'source', 'target', 'event', 'event_data', 'machine', 'model',
                 'transition', 'datamodel'}

_schema = None


def schema():
    """Return the W3C SCXML schema combined with the ros: schema."""
    global _schema
    if _schema is None:
        driver = os.path.join(SCHEMA_DIR, 'scxml_ros.xsd')
        _schema = etree.XMLSchema(etree.parse(driver))
    return _schema


def validate(spec, check_types=True, check_model=True):
    """Return every finding for a loaded ChartSpec, errors first, by line."""
    findings = list(spec.findings)
    findings += check_schema(spec)
    findings += check_engine(spec)
    if check_types:
        findings += check_types_exist(spec)
    if check_model:
        findings += check_model_names(spec)
    findings += check_statuses(spec)
    findings += check_inputs_handled(spec)
    findings += check_params(spec)
    findings += check_restrictions(spec)
    unique = []
    seen = set()
    for f in findings:
        key = (f.line, f.rule, f.message)
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return sorted(unique, key=lambda f: (f.severity != 'error', f.line, f.rule))


def errors(findings):
    return [f for f in findings if f.severity == 'error']


def _f(spec, line, rule, message, severity='error'):
    return Finding(spec.path, line or 0, rule, message, severity)


# Rule 1 --------------------------------------------------------------------------

def check_schema(spec):
    """Rule 1: the document against the W3C SCXML schema and the ros: schema."""
    from statechart_ros.loader import parse
    root = parse(spec.text, spec.path)
    xsd = schema()
    if xsd.validate(root.getroottree()):
        return []
    return [_f(spec, e.line, 1, f'schema: {e.message}') for e in xsd.error_log]


# Rule 2 --------------------------------------------------------------------------

def check_engine(spec):
    """Rule 2: the engine loads the chart; no unreachable or trap states."""
    if spec.engine_class is None:
        return []
    from statemachine.graph import disconnected_states
    cls = spec.engine_class
    found = []
    unreachable = disconnected_states(cls.initial_state, set(cls.states_map.values()))
    for state in sorted(unreachable, key=lambda s: spec.states[s.id].line
                        if s.id in spec.states else 0):
        info = spec.states.get(state.id)
        found.append(_f(spec, info.line if info else 0, 2,
                        f'state "{state.id}" is unreachable from the initial configuration'))
    for info in spec.states.values():
        if not info.atomic or info.tag == 'final':
            continue
        chain = [info.id] + spec.ancestors(info.id)
        if not any(t.source in chain for t in spec.transitions):
            found.append(_f(spec, info.line, 2,
                            f'state "{info.id}" is a trap: neither it nor any ancestor has a '
                            'transition out, and it is not a <final>'))
    return found


# Rule 3 --------------------------------------------------------------------------

def interfaces(spec):
    """Return (line, kind, type) for every ROS interface the chart uses."""
    found = []
    for el in spec.inputs:
        kind = {'subscribe': 'msg', 'service_server': 'srv', 'action_server': 'action'}.get(
            el.tag)
        if kind and el.get('type'):
            found.append((el.line, kind, el.get('type')))
    for inv in spec.invokes.values():
        kind = kinds_mod.get_kind(inv.kind)
        if kind is not None:
            found += [(inv.line, k, t) for k, t in kind.interfaces(inv.attrs)]
    for outs in spec.outputs.values():
        for out in outs:
            if out.action in ('publish', 'call') and out.attrs.get('type'):
                found.append((out.line, 'msg' if out.action == 'publish' else 'srv',
                              out.attrs['type']))
    return found


def import_interface(kind, type_name):
    """Import a message, service or action type by its pkg/kind/Name string."""
    from rosidl_runtime_py import utilities
    getter = {'msg': utilities.get_message, 'srv': utilities.get_service,
              'action': utilities.get_action}[kind]
    return getter(type_name)


def check_types_exist(spec):
    """Rule 3: every message, service and action type exists in the environment."""
    found = []
    for line, kind, type_name in interfaces(spec):
        parts = type_name.split('/')
        if len(parts) != 3 or parts[1] != kind:
            found.append(_f(spec, line, 3, f'"{type_name}" is not a {kind} type '
                                           f'(pkg/{kind}/Name)'))
            continue
        try:
            import_interface(kind, type_name)
        except (ImportError, AttributeError, ValueError, ModuleNotFoundError) as exc:
            found.append(_f(spec, line, 3, f'{kind} type "{type_name}" is not available: '
                                           f'{exc}'))
    return found


# Rule 4 --------------------------------------------------------------------------

def import_model(class_path):
    """Import ``package.module:Class``."""
    module_name, _, class_name = class_path.partition(':')
    if not module_name or not class_name:
        raise ImportError(f'"{class_path}" is not of the form package.module:Class')
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def model_references(spec):
    """Return (line, name, what) for every model name the chart uses."""
    refs = []
    for el in spec.elements:
        table = None
        if el.tag in ELEMENTS:
            table = ELEMENTS[el.tag][1]
        if el.tag in ('on_entry', 'on_exit'):
            action = next((a for a in OUTPUT_ATTRS if a in el.attrs), None)
            table = OUTPUT_ATTRS.get(action)
        if el.tag in INVOKE_TAGS:
            kind = kinds_mod.get_kind(INVOKE_TAGS[el.tag] or el.get('kind'))
            table = kind.attributes if kind else None
        for key, attr in (table or {}).items():
            if attr.role in kinds_mod.MODEL_ROLES and el.get(key):
                refs.append((el.line, el.get(key), f'ros:{el.tag} {key}'))
    return refs


def expression_names(expr):
    """Return the free names of a datamodel expression (empty if it does not parse)."""
    try:
        tree = ast.parse(expr.strip(), mode='eval')
    except SyntaxError:
        return set()
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}


def check_model_names(spec):
    """Rule 4: every guard, builder and handler name exists on the model class."""
    found = []
    model = None
    if spec.model_class:
        line = next((e.line for e in spec.elements if e.tag == 'model'), 0)
        try:
            model = import_model(spec.model_class)
        except Exception as exc:  # noqa: B902 - any import failure is a finding
            found.append(_f(spec, line, 4, f'cannot import the model class '
                                           f'"{spec.model_class}": {exc}'))
            return found
    for line, name, what in model_references(spec):
        if model is None:
            found.append(_f(spec, line, 4, f'{what} names "{name}" but the chart has no '
                                           'ros:model'))
        elif not callable(getattr(model, name, None)):
            found.append(_f(spec, line, 4, f'{what}: the model {spec.model_class} has no '
                                           f'method "{name}"'))
    known = set(spec.data) | {REFUSAL_VAR} | SYSTEM_NAMES
    for t in spec.transitions:
        if not t.cond or t.origin != 'scxml':
            continue
        for name in sorted(expression_names(t.cond) - known):
            if name.startswith('_'):
                continue
            if model is None or not hasattr(model, name):
                found.append(_f(spec, t.line, 4, f'condition "{t.cond}": "{name}" is neither a '
                                                 'datamodel value nor a model method'))
    return found


# Rule 5 --------------------------------------------------------------------------

def check_statuses(spec):
    """Rule 5: every status of every invoke is covered by an outcome."""
    found = []
    for state, outcomes in spec.outcomes.items():
        if state not in spec.invokes:
            for out in outcomes:
                found.append(_f(spec, out.line, 5, f'ros:outcome in state "{state}", which has '
                                                   'no invoke'))
    for state, inv in spec.invokes.items():
        kind = kinds_mod.get_kind(inv.kind)
        if kind is None:
            continue
        statuses = set(kind.statuses)
        covered = set()
        for out in spec.outcomes.get(state, []):
            for status in out.statuses:
                if status == '*':
                    covered |= statuses
                elif status not in statuses:
                    found.append(_f(spec, out.line, 5, f'"{status}" is not a status of '
                                                       f'{inv.kind} ({", ".join(kind.statuses)})'))
                else:
                    covered.add(status)
        missing = [s for s in kind.statuses if s not in covered]
        if missing:
            found.append(_f(spec, inv.line, 5, f'state "{state}": no ros:outcome for status '
                                               + ', '.join(f'"{s}"' for s in missing)))
    return found


# Rule 6 --------------------------------------------------------------------------

def matches(descriptor, event):
    """SCXML event matching: a descriptor matches the event or any event below it."""
    if descriptor == '*':
        return True
    if descriptor.endswith('.*'):
        descriptor = descriptor[:-2]
    return event == descriptor or event.startswith(descriptor + '.')


def configurations(spec, limit=MAX_CONFIGURATIONS):
    """Return every structural configuration (sets of state ids), or None past the limit."""
    def of(sid):
        info = spec.states[sid]
        children = [c for c in info.children if spec.states[c].tag != 'history']
        if not children:
            return [frozenset([sid])]
        if info.tag == 'parallel':
            result = [frozenset([sid])]
            for child in children:
                result = [a | b for a, b in itertools.product(result, of(child))]
                if len(result) > limit:
                    raise OverflowError
            return result
        result = []
        for child in children:
            result += [c | {sid} for c in of(child)]
            if len(result) > limit:
                raise OverflowError
        return result
    try:
        top = [s.id for s in spec.states.values() if s.parent is None and s.tag != 'history']
        result = []
        for sid in top:
            result += of(sid)
        return result
    except OverflowError:
        return None


def receivers(spec):
    """Return {event: line} of the events inputs send that the chart must answer."""
    events = {}
    for event, el in spec.input_events().items():
        events.setdefault(event, el.line)
    generic = [el for el in spec.inputs if el.tag == 'service_server'
               and (not el.get('event') or '{' in el.get('event'))]
    if generic:
        for event in spec.command_events():
            events.setdefault(event, generic[0].line)
    return events


def check_inputs_handled(spec):
    """Rule 6: every input event is handled or refused in every configuration."""
    events = receivers(spec)
    if not events:
        return []
    configs = configurations(spec)
    if configs is None:
        return [_f(spec, 1, 6, f'more than {MAX_CONFIGURATIONS} configurations: input events '
                               'were not checked', 'warning')]
    by_state = {}
    for t in spec.transitions:
        by_state.setdefault(t.source, []).append(t)
    found = []
    for event, line in sorted(events.items()):
        missing = []
        for config in configs:
            handled = any(matches(d, event)
                          for sid in config for t in by_state.get(sid, ()) for d in t.events)
            if not handled:
                missing.append(config)
        if missing:
            shown = '; '.join('{' + ', '.join(sorted(c, key=lambda s: spec.states[s].line))
                              + '}' for c in missing[:3])
            more = f' and {len(missing) - 3} more' if len(missing) > 3 else ''
            found.append(_f(spec, line, 6, f'event "{event}" is neither handled, refused nor '
                                           f'ignored in {shown}{more}'))
    return found


# Rules 8 and 9 -------------------------------------------------------------------

def check_params(spec):
    """Rule 8: every ros:param names a <data> item."""
    found = []
    for el in spec.elements:
        if el.tag == 'param' and el.get('name') and el.get('name') not in spec.data:
            found.append(_f(spec, el.line, 8, f'ros:param "{el.get("name")}" has no <data '
                                              f'id="{el.get("name")}"> to initialise'))
    return found


def check_restrictions(spec):
    """Rule 9: no delayed sends, no reserved names."""
    found = []
    for line, attrs in spec.sends:
        if 'delay' in attrs or 'delayexpr' in attrs:
            found.append(_f(spec, line, 9, "<send> with a delay holds the node's worker until "
                                           'it is due; use ros:after in the state instead'))
    for data_id in spec.data:
        if data_id in RESERVED_DATA or data_id.startswith(PREFIX):
            found.append(_f(spec, 1, 9, f'<data id="{data_id}"> uses a reserved name'))
    for sid, info in spec.states.items():
        if sid.startswith(PREFIX) and 'anonymous' not in sid:
            found.append(_f(spec, info.line, 9, f'state id "{sid}" uses the reserved prefix '
                                                f'{PREFIX}'))
    return found
