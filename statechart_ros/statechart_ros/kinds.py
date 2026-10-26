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
Invoke kinds: the work a state owns, described for the loader and run by the node.

A kind declares its attributes (with the role of each, so the validator knows
which are ROS names, interface types or model names), the statuses its
outcomes can have, and how it runs. ``ros:action``, ``ros:service_call``,
``ros:wait_for`` and ``ros:chart`` are the built-in kinds ``ros/action``,
``ros/service_call``, ``ros/wait_for`` and ``ros/chart``; ``ros:invoke
kind="..."`` names a kind registered by any package in the entry point group
``statechart_ros.invokes``.
"""

from dataclasses import dataclass, field
from importlib.metadata import entry_points
import threading

ENTRY_POINT_GROUP = 'statechart_ros.invokes'

# Roles of attributes. The validator checks each by its role.
NAME = 'name'                # a ROS topic, service or action name
MSG_TYPE = 'msg_type'        # pkg/msg/Type
SRV_TYPE = 'srv_type'        # pkg/srv/Type
ACTION_TYPE = 'action_type'  # pkg/action/Type
BUILDER = 'builder'          # a model method building a message
HANDLER = 'handler'          # a model method receiving a message
GUARD = 'guard'              # a model method returning a bool
FLOAT = 'float'
INT = 'int'
BOOL = 'bool'
EVENT = 'event'              # an event name the kind sends
STRING = 'string'
DATA = 'data'                # the name of a datamodel value
SECONDS = 'seconds'          # a duration: a number, or the name of a datamodel value
ENUM = 'enum'
PATH = 'path'                # a file path or package:// URL

QOS_CHOICES = ('default', 'sensor', 'latched')
MODEL_ROLES = (BUILDER, HANDLER, GUARD)
TYPE_ROLES = {MSG_TYPE: 'msg', SRV_TYPE: 'srv', ACTION_TYPE: 'action'}


@dataclass(frozen=True)
class Attr:
    """One attribute of an element or invoke kind."""

    role: str
    required: bool = False
    default: object = None
    choices: tuple = ()
    doc: str = ''


@dataclass
class Outcome:
    """How a piece of work ended; the data of its ``done.invoke`` event."""

    status: str
    result: object = None
    error_code: int = 0
    error_name: str = ''
    error_msg: str = ''
    data: dict = field(default_factory=dict)

    def event_data(self):
        """Return the keyword arguments of the ``done.invoke`` event."""
        data = dict(self.data)
        data.update(status=self.status, result=self.result, error_code=self.error_code,
                    error_name=self.error_name, error_msg=self.error_msg)
        return data


class Invocation:
    """One run of an invoke: what a kind's ``run`` sees of the node and the engine."""

    def __init__(self, state_id, cancelled=None, post=None, feedback=None):
        self.state_id = state_id
        self.cancelled = cancelled if cancelled is not None else threading.Event()
        self._post = post
        self._feedback = feedback

    def send(self, event, **data):
        """Put an event on the node's queue (never directly on the engine)."""
        if self._post is not None and not self.cancelled.is_set():
            self._post(event, data)

    def feedback(self, summary):
        """Report a feedback summary (a dict of short values) for the status."""
        if self._feedback is not None:
            self._feedback(summary)


class InvokeKind:
    """
    Base class of invoke kinds.

    Subclasses set ``name``, ``attributes`` and ``statuses`` and implement
    ``run``. The class-level methods are used without ROS by the loader and the
    validator; an instance is created by the node for each state that uses the
    kind, with the host that gives access to the node.
    """

    name = ''
    attributes = {}
    statuses = ()
    description = ''

    @classmethod
    def interfaces(cls, attrs):
        """Return the ROS interfaces this use needs, as (kind, type) pairs."""
        found = []
        for key, spec in cls.attributes.items():
            if spec.role in TYPE_ROLES and attrs.get(key):
                found.append((TYPE_ROLES[spec.role], attrs[key]))
        return found

    @classmethod
    def check(cls, attrs):
        """Return messages about this use beyond the attribute table (none by default)."""
        return []

    @classmethod
    def statuses_for(cls, attrs):
        """Return the statuses this use can end with (the class's, unless they vary)."""
        return tuple(cls.statuses)

    @classmethod
    def summary(cls, attrs):
        """Return the target and type shown in the structure and the viewer."""
        target = ''
        type_ = ''
        for key, spec in cls.attributes.items():
            if spec.role == NAME and not target:
                target = attrs.get(key, '')
            if spec.role in TYPE_ROLES and not type_:
                type_ = attrs.get(key, '')
        return {'target': target, 'type': type_}

    def __init__(self, host, state_id, attrs):
        self.host = host
        self.state_id = state_id
        self.attrs = attrs
        self.statuses = self.statuses_for(attrs)

    def setup(self):
        """Create clients and other resources once, when the chart is activated."""

    def teardown(self):
        """Release what ``setup`` created."""

    def run(self, invocation):
        """Do the work; return an ``Outcome``. Runs in the invocation's own thread."""
        raise NotImplementedError

    def attr(self, key):
        """Return an attribute's value, converted by its role, or its default."""
        spec = self.attributes[key]
        raw = self.attrs.get(key)
        if raw is None:
            return spec.default
        return convert(spec, raw)


def convert(spec, raw):
    """Convert an attribute string by its role."""
    if spec.role == FLOAT:
        return float(raw)
    if spec.role == INT:
        return int(raw)
    if spec.role == BOOL:
        return raw.strip().lower() in ('true', '1', 'yes')
    return raw


def check_value(spec, raw):
    """Return an error message if the attribute string does not fit its role."""
    try:
        if spec.role == FLOAT:
            if float(raw) < 0:
                return 'must not be negative'
        elif spec.role == SECONDS:
            try:
                if float(raw) < 0:
                    return 'must not be negative'
            except ValueError:
                if not raw.isidentifier():
                    return 'must be a number of seconds or the name of a datamodel value'
        elif spec.role == INT:
            int(raw)
        elif spec.role == BOOL:
            if raw.strip().lower() not in ('true', 'false', '1', '0', 'yes', 'no'):
                return 'must be true or false'
        elif spec.role == ENUM:
            if raw not in spec.choices:
                return 'must be one of ' + ', '.join(spec.choices)
        elif spec.role in TYPE_ROLES:
            parts = raw.split('/')
            if len(parts) != 3 or parts[1] != TYPE_ROLES[spec.role] or not all(parts):
                return f'must be a type like pkg/{TYPE_ROLES[spec.role]}/Name'
    except ValueError:
        return f'is not a valid {spec.role}'
    return None


_registry_lock = threading.Lock()
_registry = None


def builtin_kinds():
    """Return the kinds of statechart_ros itself, by name."""
    from statechart_ros import builtin_invokes
    return {k.name: k for k in builtin_invokes.KINDS}


def registry(reload=False):
    """Return every known kind by name: built-ins and entry points."""
    global _registry
    with _registry_lock:
        if _registry is None or reload:
            kinds = builtin_kinds()
            for ep in entry_points(group=ENTRY_POINT_GROUP):
                if ep.name in kinds:
                    continue
                kinds[ep.name] = ep
            _registry = kinds
        return _registry


def get_kind(name):
    """Return the kind class registered under name, or None."""
    kinds = registry()
    kind = kinds.get(name)
    if kind is None:
        return None
    if not isinstance(kind, type):
        kind = kind.load()
        with _registry_lock:
            _registry[name] = kind
    return kind


def register(kind):
    """Register a kind class directly (tests and in-process extensions)."""
    registry()
    with _registry_lock:
        _registry[kind.name] = kind
    return kind
