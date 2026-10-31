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
Built-in invoke kinds: ``ros:action``, ``ros:service_call``, ``ros:wait_for``.

Each class declares what the kind accepts and which statuses it ends with
(used by the loader and the validator without ROS), and runs it in the node:
``setup`` creates the client or subscription once, ``run`` does one
invocation on the invocation's own thread and returns an ``Outcome``.
Waiting never blocks the node's worker: model methods (builders, handlers,
guards) are run on the worker through ``host.runner.call_model``.
"""

import queue
import threading

from statechart_ros.kinds import (
    ACTION_TYPE, Attr, BOOL, BUILDER, DATA, ENUM, EVENT, FLOAT, GUARD, HANDLER, InvokeKind,
    MSG_TYPE, NAME, Outcome, PATH, QOS_CHOICES, SRV_TYPE, STRING)
from statechart_ros.runtime import Cancelled, to_jsonable

POLL = 0.02


def wait_future(host, future, invocation, timeout=None):
    """
    Wait for an rclpy future, the invocation's cancellation or a timeout (ROS time).

    Returns 'done', 'cancelled' or 'timeout'.
    """
    done = threading.Event()
    future.add_done_callback(lambda _f: done.set())
    deadline = None if timeout is None else host.now() + timeout
    while True:
        if done.wait(POLL) or future.done():
            return 'done'
        if invocation.cancelled.is_set():
            return 'cancelled'
        if deadline is not None and host.now() >= deadline:
            return 'timeout'


def wait_ready(host, ready, invocation, timeout):
    """Wait until ready() is true; return 'done', 'cancelled' or 'timeout'."""
    deadline = host.now() + timeout
    while not ready():
        if invocation.cancelled.wait(POLL):
            return 'cancelled'
        if host.now() >= deadline:
            return 'done' if ready() else 'timeout'
    return 'done'


def summarize(msg, limit=8):
    """Summarize feedback: the first scalar fields of a message."""
    data = to_jsonable(msg)
    if not isinstance(data, dict):
        return {'value': data}
    summary = {}
    for key, value in data.items():
        if isinstance(value, (int, float, str, bool)):
            summary[key] = value
        if len(summary) >= limit:
            break
    return summary


class ActionKind(InvokeKind):
    """Send a goal to an action server; the goal is cancelled when the state is left."""

    name = 'ros/action'
    attributes = {
        'server': Attr(NAME, required=True, doc='action server name'),
        'type': Attr(ACTION_TYPE, required=True, doc='action type'),
        'goal': Attr(BUILDER, doc='model method filling the goal'),
        'feedback': Attr(HANDLER, doc='model method receiving each feedback message'),
        'feedback_event': Attr(EVENT, doc='event sent with each feedback message'),
        'server_timeout': Attr(FLOAT, default=5.0, doc='seconds to wait for the server'),
        'cancel_timeout': Attr(FLOAT, default=5.0,
                               doc='seconds to wait for a cancel to be confirmed'),
    }
    statuses = ('succeeded', 'aborted', 'canceled', 'rejected', 'unavailable')
    action_type = None

    def setup(self):
        from rclpy.action import ActionClient
        from statechart_ros.validate import import_interface
        self.action_type = import_interface('action', self.attrs['type'])
        self.server = self.host.resolve(self.attrs['server'])
        self.client = ActionClient(self.host.node, self.action_type, self.server,
                                   callback_group=self.host.callback_group)

    def teardown(self):
        client = getattr(self, 'client', None)
        if client is not None:
            from statechart_ros.host import destroy_waitable
            destroy_waitable(self.host.node, client)
            self.client = None

    def make_goal(self, invocation):
        """Return the goal: an empty Goal filled by the builder named in ``goal``."""
        goal = self.action_type.Goal()
        if self.attrs.get('goal'):
            built = self.host.runner.call_model(self.attrs['goal'], cancelled=invocation.cancelled,
                                                goal=goal)
            if built is not None:
                goal = built
        return goal

    def error_name(self, code):
        """Return the name of an error code (none for generic actions)."""
        return ''

    def feedback_summary(self, feedback):
        return summarize(feedback)

    def outcome(self, status, result):
        code = getattr(result, 'error_code', 0) if result is not None else 0
        try:
            code = int(code)
        except (TypeError, ValueError):
            code = 0
        return Outcome(status, result=result, error_code=code,
                       error_name=self.error_name(code) if code else '',
                       error_msg=str(getattr(result, 'error_msg', '') or ''))

    def run(self, invocation):
        from action_msgs.msg import GoalStatus
        host = self.host
        wait = wait_ready(host, self.client.server_is_ready, invocation,
                          self.attr('server_timeout'))
        if wait == 'cancelled':
            return None
        if wait == 'timeout':
            return Outcome('unavailable', error_msg=f'action server {self.server} is not '
                                                    'available')
        gate = host.gate(self.server)
        if not gate.acquire(invocation.cancelled):
            return None
        handed_over = False
        try:
            goal = self.make_goal(invocation)
            send = self.client.send_goal_async(goal,
                                               feedback_callback=self._on_feedback(invocation))
            if wait_future(host, send, invocation) == 'cancelled':
                handed_over = True
                send.add_done_callback(lambda f: self._cancel_later(f, gate))
                return None
            handle = send.result()
            if handle is None or not handle.accepted:
                return Outcome('rejected', error_msg=f'{self.server} rejected the goal')
            result_future = handle.get_result_async()
            if wait_future(host, result_future, invocation) == 'cancelled':
                handed_over = True
                self._cancel(handle, result_future, gate)
                return None
            response = result_future.result()
            status = {GoalStatus.STATUS_SUCCEEDED: 'succeeded',
                      GoalStatus.STATUS_ABORTED: 'aborted',
                      GoalStatus.STATUS_CANCELED: 'canceled'}.get(response.status, 'aborted')
            return self.outcome(status, response.result)
        finally:
            if not handed_over:
                gate.release()

    def _on_feedback(self, invocation):
        def callback(feedback_msg):
            if invocation.cancelled.is_set():
                return
            feedback = feedback_msg.feedback
            invocation.feedback(self.feedback_summary(feedback))
            if self.attrs.get('feedback'):
                self.host.runner.submit(self.host.runner.call_model, self.attrs['feedback'],
                                        feedback=feedback)
            if self.attrs.get('feedback_event'):
                invocation.send(self.attrs['feedback_event'], {'feedback': feedback})
        return callback

    def _cancel_later(self, send_future, gate):
        handle = send_future.result() if not send_future.cancelled() else None
        if handle is None or not handle.accepted:
            gate.release()
            return
        self._cancel(handle, handle.get_result_async(), gate)

    def _cancel(self, handle, result_future, gate):
        """Cancel a goal; release the server's gate once the server confirms or on timeout."""
        timeout = self.attr('cancel_timeout')
        host = self.host

        def wait_and_release():
            try:
                handle.cancel_goal_async()
                deadline = host.now() + timeout
                while not result_future.done() and host.now() < deadline:
                    threading.Event().wait(POLL)
                if not result_future.done():
                    host.logger().warning(f'{self.server}: cancel not confirmed within '
                                          f'{timeout:g} s; sending the next goal anyway')
            finally:
                gate.release()

        threading.Thread(target=wait_and_release, daemon=True,
                         name=f'cancel-{self.server}').start()


class ServiceCallKind(InvokeKind):
    """Call a service; the call is abandoned when the state is left."""

    name = 'ros/service_call'
    attributes = {
        'service': Attr(NAME, required=True, doc='service name'),
        'type': Attr(SRV_TYPE, required=True, doc='service type'),
        'request': Attr(BUILDER, doc='model method filling the request'),
        'response': Attr(HANDLER, doc='model method receiving the response'),
        'success': Attr(GUARD, doc='model method deciding from the response whether the '
                                   'call succeeded (default: every response succeeds)'),
        'timeout': Attr(FLOAT, default=10.0, doc='seconds to wait for the response'),
        'server_timeout': Attr(FLOAT, default=5.0, doc='seconds to wait for the service'),
    }
    statuses = ('succeeded', 'failed', 'timeout', 'unavailable')

    def setup(self):
        from statechart_ros.validate import import_interface
        self.srv_type = import_interface('srv', self.attrs['type'])
        self.service = self.host.resolve(self.attrs['service'])
        self.client = self.host.node.create_client(self.srv_type, self.service,
                                                   callback_group=self.host.callback_group)

    def teardown(self):
        client = getattr(self, 'client', None)
        if client is not None:
            self.host.node.destroy_client(client)
            self.client = None

    def run(self, invocation):
        host = self.host
        wait = wait_ready(host, self.client.service_is_ready, invocation,
                          self.attr('server_timeout'))
        if wait == 'cancelled':
            return None
        if wait == 'timeout':
            return Outcome('unavailable', error_msg=f'service {self.service} is not available')
        request = self.srv_type.Request()
        if self.attrs.get('request'):
            built = host.runner.call_model(self.attrs['request'], cancelled=invocation.cancelled,
                                           request=request)
            if built is not None:
                request = built
        future = self.client.call_async(request)
        result = wait_future(host, future, invocation, self.attr('timeout'))
        if result != 'done':
            self.client.remove_pending_request(future)
            if result == 'cancelled':
                return None
            return Outcome('timeout', error_msg=f'no response from {self.service} within '
                                                f'{self.attr("timeout"):g} s')
        response = future.result()
        if self.attrs.get('response'):
            host.runner.call_model(self.attrs['response'], cancelled=invocation.cancelled,
                                   response=response, request=request)
        if self.attrs.get('success'):
            ok = host.runner.call_model(self.attrs['success'], cancelled=invocation.cancelled,
                                        response=response, request=request)
            if not ok:
                return Outcome('failed', result=response,
                               error_msg=str(getattr(response, 'message', '') or ''))
        return Outcome('succeeded', result=response)


class WaitForKind(InvokeKind):
    """Wait for a message on a topic, optionally one that passes a guard."""

    name = 'ros/wait_for'
    attributes = {
        'topic': Attr(NAME, required=True, doc='topic name'),
        'type': Attr(MSG_TYPE, required=True, doc='message type'),
        'when': Attr(GUARD, doc='model method accepting the message'),
        'timeout': Attr(FLOAT, doc='seconds to wait (default: no limit)'),
        'qos': Attr(ENUM, default='default', choices=QOS_CHOICES, doc='QoS profile'),
    }
    statuses = ('succeeded', 'timeout')

    def setup(self):
        from statechart_ros.validate import import_interface
        self.msg_type = import_interface('msg', self.attrs['type'])
        self._box = None
        self._box_lock = threading.Lock()
        self.subscription = self.host.node.create_subscription(
            self.msg_type, self.host.resolve(self.attrs['topic']), self._on_message,
            self.host.qos(self.attr('qos')), callback_group=self.host.callback_group)

    def teardown(self):
        sub = getattr(self, 'subscription', None)
        if sub is not None:
            self.host.node.destroy_subscription(sub)
            self.subscription = None

    def _on_message(self, msg):
        with self._box_lock:
            box = self._box
        if box is not None:
            box.put(msg)

    def run(self, invocation):
        box = queue.Queue()
        with self._box_lock:
            self._box = box
        timeout = self.attr('timeout')
        deadline = None if timeout is None else self.host.now() + timeout
        try:
            while True:
                if invocation.cancelled.is_set():
                    return None
                if deadline is not None and self.host.now() >= deadline:
                    return Outcome('timeout', error_msg=f'no matching message on '
                                                        f'{self.attrs["topic"]} within '
                                                        f'{timeout:g} s')
                try:
                    msg = box.get(timeout=POLL)
                except queue.Empty:
                    continue
                if self.attrs.get('when'):
                    try:
                        ok = self.host.runner.call_model(self.attrs['when'],
                                                         cancelled=invocation.cancelled, msg=msg)
                    except Cancelled:
                        return None
                    if not ok:
                        continue
                return Outcome('succeeded', result=msg)
        finally:
            with self._box_lock:
                if self._box is box:
                    self._box = None


class ChartKind(InvokeKind):
    """
    Run a child chart in the same node; it is stopped when the state is left.

    The child's top-level ``<final>`` states are the statuses: reaching
    ``<final id="docked">`` ends the invoke with status ``docked``, its
    donedata as ``result`` and as outcome data. The child gets the events its
    parent processes when ``autoforward`` is true, and its initial datamodel
    values from the builder named in ``data``.
    """

    name = 'ros/chart'
    attributes = {
        'src': Attr(PATH, required=True,
                    doc='the child chart: a path (relative to the parent) or package:// URL'),
        'autoforward': Attr(BOOL, default=False,
                            doc="forward the parent's events to the child"),
        'data': Attr(BUILDER, doc="a builder returning the child's initial datamodel values "
                                  'by <data> id'),
    }
    statuses = ()

    @classmethod
    def summary(cls, attrs):
        return {'target': attrs.get('src', ''), 'type': 'chart'}

    @classmethod
    def statuses_for(cls, attrs):
        from statechart_ros.loader import CHILD_PATH
        path = attrs.get(CHILD_PATH)
        return _finals(path) if path else ()

    def child_paths(self):
        """Return the child charts by option name ('' for a ros:chart)."""
        from statechart_ros.loader import CHILD_PATH
        return {'': self.attrs[CHILD_PATH]}

    def setup(self):
        self.children = {}
        self.current = None
        for option, path in self.child_paths().items():
            self.children[option] = self._child_runner(option, path)
        self.autoforward = self.attr('autoforward')

    def _child_runner(self, option, path):
        from statechart_ros.host import ChildHost
        from statechart_ros.loader import load_chart
        from statechart_ros.runtime import ChartRunner
        from statechart_ros.validate import import_model
        parent = self.host.runner
        spec = load_chart(path)
        user = None
        if spec.model_class:
            cls = import_model(spec.model_class)
            try:
                user = cls(self.host.node)
            except TypeError:
                user = cls()
        runner = ChartRunner(spec, user, ChildHost(self.host))
        if hasattr(self.host, 'setup_outputs'):
            self.host.setup_outputs(spec)
        for kind in runner.kinds.values():
            kind.setup()
        prefix = self.state_id + (f'/{option}' if option else '')
        runner.status_observers.append(parent._status_changed)
        runner.observers.append(lambda record: _forward_record(parent, prefix, record))
        return runner

    @property
    def runner(self):
        """Return the child chart's runner; for a slot, the last option's."""
        current = getattr(self, 'current', None)
        if current is not None:
            return current[1]
        children = getattr(self, 'children', {})
        return children.get('') if children else None

    def teardown(self):
        for runner in getattr(self, 'children', {}).values():
            runner.shutdown()
            for kind in runner.kinds.values():
                kind.teardown()
        self.children = {}
        self.current = None

    def child_snapshot(self):
        current = getattr(self, 'current', None)
        if current is None or not current[1].running:
            return None
        option, runner = current
        snapshot = runner.snapshot()
        if option:
            snapshot['active'] = [f'{option}/{s}' for s in snapshot['active']]
            snapshot['invokes'] = [dict(i, state=f'{option}/{i["state"]}')
                                   for i in snapshot['invokes']]
        return snapshot

    def forward(self, event, data):
        current = getattr(self, 'current', None)
        if self.autoforward and current is not None and current[1].running:
            current[1].post(event, data)

    def select(self, invocation):
        """Return the option to run ('' for a ros:chart)."""
        return ''

    def engine_class(self, runner, invocation):
        """Return the child's engine class for this run: its datamodel with ``data``."""
        if not self.attrs.get('data'):
            return None
        from statechart_ros.loader import ChartError, load_chart, load_engine_class
        built = self.host.runner.call_model(self.attrs['data'], cancelled=invocation.cancelled)
        values = dict(built or {})
        if not values:
            return None
        unknown = sorted(set(values) - set(runner.spec.data))
        if unknown:
            raise ValueError(f'data for values the child chart does not declare: '
                             f'{", ".join(unknown)}')
        try:
            variant = load_chart(runner.spec.path, params=values, load_engine=False)
            return load_engine_class(variant)
        except ChartError as exc:
            raise ValueError(f'the child chart with this data: {exc}') from None

    def run(self, invocation):
        option = self.select(invocation)
        runner = self.children.get(option)
        if runner is None:
            return Outcome('', error_msg=f'no option "{option}" in slot "{self.attrs["name"]}"')
        try:
            engine_class = self.engine_class(runner, invocation)
        except ValueError as exc:
            return Outcome('', error_msg=str(exc))
        self.current = (option, runner)
        runner.start(engine_class=engine_class)
        while True:
            if invocation.cancelled.wait(POLL):
                runner.stop()
                return None
            if not runner.running:
                final, donedata = runner.final or ('', {})
                if not final:
                    return Outcome('', error_msg='the child chart stopped without a final '
                                                 'state')
                return Outcome(final, result=dict(donedata), data=dict(donedata))


class SlotKind(ChartKind):
    """
    Run the option of a slot that the datamodel selects; options come from packages.

    Installed packages register charts for the slot (``statechart_ros.slots``);
    on entry the value of the datamodel value named in ``select`` picks one,
    which then runs exactly as a ``ros:chart`` child. The statuses are the
    slot's ``outcomes``; no option of that name ends the invoke with an error.
    """

    name = 'ros/slot'
    attributes = {
        'name': Attr(STRING, required=True, doc='the slot; its options are registered charts'),
        'select': Attr(DATA, required=True,
                       doc='a datamodel value whose value on entry names the option'),
        'outcomes': Attr(STRING, required=True,
                         doc="the slot's statuses; every option's finals are among them"),
        'autoforward': Attr(BOOL, default=False,
                            doc="forward the parent's events to the option"),
        'data': Attr(BUILDER, doc="a builder returning the option's initial datamodel values "
                                  'by <data> id'),
    }

    @classmethod
    def summary(cls, attrs):
        return {'target': attrs.get('name', ''), 'type': 'slot'}

    @classmethod
    def statuses_for(cls, attrs):
        return tuple((attrs.get('outcomes') or '').split())

    def child_paths(self):
        from statechart_ros.loader import SLOT_OPTIONS
        return dict(self.attrs.get(SLOT_OPTIONS) or {})

    def select(self, invocation):
        runner = self.host.runner
        name = self.attrs['select']
        value = runner.run_in_worker(lambda: getattr(runner.model, name, None),
                                     cancelled=invocation.cancelled)
        return '' if value is None else str(value)


def _finals(path):
    """Return the ids of a chart's top-level finals (none if it cannot be read)."""
    from statechart_ros.loader import ChartError, load_chart
    try:
        child = load_chart(path, load_engine=False)
    except (ChartError, OSError):
        return ()
    return tuple(sid for sid, info in child.states.items()
                 if info.tag == 'final' and info.parent is None)


def _forward_record(parent, prefix, record):
    """Publish a child chart's transition with the parent's, ids qualified."""
    from dataclasses import replace
    qualified = replace(
        record, event=f'{prefix}/{record.event}',
        source=[f'{prefix}/{s}' for s in record.source],
        target=[f'{prefix}/{s}' for s in record.target],
        taken=[' -> '.join(', '.join(f'{prefix}/{x}' for x in side.split(', ') if x)
                           for side in label.split(' -> ')) for label in record.taken],
        events=[])
    for observer in list(parent.observers):
        try:
            observer(qualified)
        except Exception as exc:  # noqa: B902
            parent.log.error(f'statechart observer failed: {exc!r}')


KINDS = [ActionKind, ServiceCallKind, WaitForKind, ChartKind, SlotKind]
