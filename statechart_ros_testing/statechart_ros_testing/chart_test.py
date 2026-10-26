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
Load a chart for a test, with fake invokes, a manual clock and recorded outputs.

``chart_under_test`` returns a ``ChartTest``: send events, complete invokes,
advance time and assert on the configuration, the datamodel and the outputs,
without ROS. Each call returns once the chart is settled: every queued event
and every invoke outcome has been processed.

    t = chart_under_test('patrol.scxml', outcomes={'DOCKING': ['aborted', 'succeeded']})
    t.send('start')
    assert t.active('TO_A')
    t.complete('TO_A', 'succeeded')
"""

import threading
import time

from statechart_ros.kinds import get_kind, InvokeKind, Outcome
from statechart_ros.loader import load_chart
from statechart_ros.runtime import ChartRunner, Host
from statechart_ros.validate import errors, import_model, validate
import yaml

PENDING = 'pending'


class ChartTestError(AssertionError):
    """A chart under test did something the test did not allow."""


class ManualClock:
    """Time that moves only when the test says so."""

    def __init__(self, start=0.0):
        self.now = start
        self.timers = []
        self.lock = threading.Lock()

    def schedule(self, delay, callback):
        timer = _Timer(self.now + delay, callback)
        with self.lock:
            self.timers.append(timer)
        return timer

    def due(self, until):
        with self.lock:
            ready = sorted((t for t in self.timers if not t.cancelled and t.at <= until),
                           key=lambda t: t.at)
            self.timers = [t for t in self.timers if t not in ready and not t.cancelled]
        return ready


class _Timer:

    def __init__(self, at, callback):
        self.at = at
        self.callback = callback
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class FakeHost(Host):
    """A host that records outputs and runs timers on a manual clock."""

    def __init__(self, clock=None):
        self.clock = clock or ManualClock()
        self.outputs = []

    def now(self):
        return self.clock.now

    def schedule(self, delay, callback):
        return self.clock.schedule(delay, callback)

    def wait(self, event, seconds):
        return event.is_set()

    def output(self, out, model, runner=None):
        runner = runner or self.runner
        value = out.attrs.get('value')
        if value is not None:
            value = yaml.safe_load(value)
        builder = out.attrs.get('message') or out.attrs.get('request')
        if builder:
            value = _built_output(out, runner, builder, value)
        target = out.attrs.get(out.action)
        self.outputs.append(Output(out.state, out.when, out.action, target, value))


def _built_output(out, runner, builder, value):
    """
    Call a ``message=`` / ``request=`` builder as the node does, with a message of the type.

    The recorded value is in the form ``value=`` uses: the ``data`` field alone
    for a message whose only field it is, else a dictionary of the fields.
    """
    type_name = out.attrs.get('type')
    if not type_name:
        return runner.call_model(builder, msg=value, request=value)
    from rosidl_runtime_py.convert import message_to_ordereddict
    from statechart_ros.host import fill_message
    from statechart_ros.validate import import_interface
    if out.action == 'publish':
        obj = import_interface('msg', type_name)()
    else:
        obj = import_interface('srv', type_name).Request()
    if value is not None:
        fill_message(obj, value)
    built = runner.call_model(builder, msg=obj, request=obj)
    if built is not None:
        obj = built
    fields = message_to_ordereddict(obj)
    return fields['data'] if list(fields) == ['data'] else dict(fields)


class Output:
    """One recorded ros:on_entry / ros:on_exit output."""

    def __init__(self, state, when, action, target, value):
        self.state = state
        self.when = when
        self.action = action
        self.target = target
        self.value = value

    def __repr__(self):
        return (f'Output({self.state} {self.when}: {self.action} {self.target} '
                f'{self.value!r})')

    def __eq__(self, other):
        if isinstance(other, tuple):
            return (self.action, self.target, self.value) == other[:3]
        return vars(self) == vars(other)


def _to_outcome(entry, attempt):
    if isinstance(entry, Outcome):
        return entry
    if isinstance(entry, str):
        return Outcome(entry)
    if isinstance(entry, dict):
        data = dict(entry)
        status = data.pop('status')
        known = {k: data.pop(k) for k in ('result', 'error_code', 'error_name', 'error_msg')
                 if k in data}
        return Outcome(status, data=data, **known)
    raise ChartTestError(f'cannot read an outcome from {entry!r}')


class FakeKind(InvokeKind):
    """Stands for a real kind: same statuses, outcomes from the test's script."""

    def __init__(self, host, state_id, attrs, real, test):
        super().__init__(host, state_id, attrs)
        self.real = real
        self.statuses = real.statuses_for(attrs) if real is not None else ()
        self.test = test

    def run(self, invocation):
        test = self.test
        attempt = test._attempts.get(self.state_id, 0) + 1
        test._attempts[self.state_id] = attempt
        entry = test._next_entry(self.state_id, attempt)
        if callable(entry) and not isinstance(entry, Outcome):
            entry = entry(attempt, dict(self.attrs))
        if entry == PENDING or entry is None:
            ctx = test.runner.current_ctx.get(self.state_id)
            waiting = _Waiting(invocation, ctx)
            with test._lock:
                test._waiting[self.state_id] = waiting
            test.runner._invoke_settled(ctx)
            while not waiting.done.wait(0.005):
                if invocation.cancelled.is_set():
                    with test._lock:
                        if test._waiting.get(self.state_id) is waiting:
                            del test._waiting[self.state_id]
                    test.cancelled.append(self.state_id)
                    return None
            entry = waiting.entry
        outcome = _to_outcome(entry, attempt)
        if self.statuses and outcome.status not in self.statuses:
            test.errors.append(f'state {self.state_id}: {self.real.name} has no status '
                               f'"{outcome.status}" ({", ".join(self.statuses)})')
            test.runner._invoke_settled(test.runner.current_ctx.get(self.state_id))
            invocation.cancelled.wait()
            return None
        test.finished.append((self.state_id, outcome.status))
        return outcome


class _Waiting:

    def __init__(self, invocation, ctx):
        self.invocation = invocation
        self.ctx = ctx
        self.done = threading.Event()
        self.entry = None


class _TestRunner(ChartRunner):
    """A runner that knows when every invocation has reached its fake."""

    def __init__(self, *args, **kwargs):
        # id -> context: holding the context keeps its id from being reused by a new one.
        self._settled = {}
        self.current_ctx = {}
        super().__init__(*args, **kwargs)

    def _invoke(self, sid, ctx):
        self.current_ctx[sid] = ctx
        return super()._invoke(sid, ctx)

    def _invoke_settled(self, ctx):
        self._settled[id(ctx)] = ctx

    def unsettled(self):
        """
        On the worker: work not yet done, as a count.

        Invocations the engine started whose fake has not decided, plus one if
        items wait in the queue. Checked here, not by the test's thread: an
        invocation is marked settled after its outcome is queued, so an outcome
        seen as settled here is still in the queue behind this call, while the
        test's thread could see the queue empty when the worker has taken the
        outcome and is still processing it.
        """
        count = 1 if not self.queue.empty() else 0
        manager = self.sm._engine._invoke_manager if self.sm is not None else None
        if manager is None:
            return count
        for inv in list(manager._active.values()):
            if inv.ctx.cancelled.is_set() or inv.terminated:
                continue
            if id(inv.ctx) not in self._settled:
                count += 1
        return count


class ChartTest:
    """A chart running without ROS for tests."""

    def __init__(self, spec, model=None, outcomes=None, clock=None, settle_timeout=5.0):
        self.spec = spec
        self.host = FakeHost(clock)
        self.outcomes = {k: (list(v) if isinstance(v, (list, tuple)) else v)
                         for k, v in (outcomes or {}).items()}
        self.finished = []
        self.cancelled = []
        self.errors = []
        self.settle_timeout = settle_timeout
        self._attempts = {}
        self._waiting = {}
        self._lock = threading.Lock()
        self.last = None
        kinds = {}
        for inv in spec.invokes.values():
            real = get_kind(inv.kind)
            kinds[inv.kind] = (lambda real: lambda host, sid, attrs:
                               FakeKind(host, sid, attrs, real, self))(real)
        self.runner = _TestRunner(spec, model, self.host, kinds=kinds)
        self.runner.start()
        self.settle()

    def _next_entry(self, state_id, attempt):
        script = self.outcomes.get(state_id, PENDING)
        if isinstance(script, list):
            return script.pop(0) if script else PENDING
        return script

    # --- driving the chart ------------------------------------------------------------

    def settle(self):
        """Wait until every queued item and every invoke outcome has been processed."""
        deadline = time.monotonic() + self.settle_timeout
        quiet = 0
        while time.monotonic() < deadline:
            busy = self.runner.run_in_worker(self.runner.unsettled)
            if busy == 0:
                quiet += 1
                if quiet >= 2:
                    if self.errors:
                        raise ChartTestError('; '.join(self.errors))
                    return
            else:
                quiet = 0
            time.sleep(0.001)
        raise ChartTestError(f'the chart did not settle in {self.settle_timeout} s')

    def send(self, event, data=None, **kwargs):
        """Send an event; return its EventResult once the chart has settled."""
        data = dict(data or {}, **kwargs)
        self.last = self.runner.send(event, data, timeout=self.settle_timeout)
        self.settle()
        return self.last

    def complete(self, state, status='succeeded', **data):
        """End the running (pending) invoke of a state with an outcome."""
        with self._lock:
            waiting = self._waiting.pop(state, None)
        if waiting is None:
            raise ChartTestError(f'state {state} has no pending invoke (active: '
                                 f'{self.configuration()})')
        entry = dict(data, status=status)
        self.runner._settled.pop(id(waiting.ctx), None)
        waiting.entry = entry
        waiting.done.set()
        self.settle()

    def pending(self):
        """Return the states whose invoke waits for ``complete``."""
        with self._lock:
            return sorted(self._waiting)

    def advance(self, seconds):
        """Move the clock; fire the ros:after timeouts that fall due, in order."""
        target = self.host.clock.now + seconds
        while True:
            due = self.host.clock.due(target)
            if not due:
                break
            for timer in due:
                self.host.clock.now = max(self.host.clock.now, timer.at)
                timer.callback()
                self.settle()
        self.host.clock.now = target
        self.settle()

    def stop(self):
        self.runner.stop()
        self.settle()

    def close(self):
        self.runner.shutdown()

    # --- looking at it -------------------------------------------------------------------

    def configuration(self):
        return self.runner.configuration()

    def active(self, *states):
        """Whether all the given states are active."""
        config = set(self.configuration())
        return all(s in config for s in states)

    @property
    def data(self):
        """Return the datamodel (attribute access)."""
        return self.runner.model

    @property
    def outputs(self):
        return self.host.outputs

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def chart_under_test(path, outcomes=None, model=None, params=None, text=None,
                     check=True, settle_timeout=5.0):
    """
    Load a chart for a test.

    ``outcomes`` scripts the invokes per state: a status (every attempt), a
    list (one entry per attempt, then pending), ``'pending'`` (the default:
    the test ends it with ``complete``), a dict with ``status`` and outcome
    data, or a function ``(attempt, attrs) -> entry``. ``model`` is the model
    instance (default: the chart's ``ros:model`` class, instantiated without a
    node). ``check`` validates the chart first (types and model included).
    """
    spec = load_chart(path, params=params, text=text)
    if check:
        problems = errors(validate(spec))
        if problems:
            raise ChartTestError('the chart is not valid:\n' + '\n'.join(map(str, problems)))
    if model is None and spec.model_class:
        cls = import_model(spec.model_class)
        try:
            model = cls(None)
        except TypeError:
            model = cls()
    return ChartTest(spec, model, outcomes, settle_timeout=settle_timeout)
