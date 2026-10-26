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
Run a loaded chart: one queue, one worker thread, invokes, outputs, timeouts.

``ChartRunner`` is independent of rclpy: everything it does in ROS goes
through a ``Host`` (``statechart_ros.host.RosHost`` in the node, fakes in
tests). Every call into the engine happens on the runner's worker thread
(docs/DESIGN.md section 4): ROS callbacks, invoke threads and timers put items
on the queue; the worker takes them one at a time.
"""

from concurrent.futures import Future
from dataclasses import dataclass, field
import inspect
import json
import logging
import queue
import threading
import time
import traceback

from statechart_ros.kinds import get_kind, Invocation, Outcome
from statechart_ros.loader import PREFIX, REFUSAL_VAR, STOP_EVENT

# Keyword names the engine passes to callbacks itself; event data must not use them.
RESERVED_KEYS = frozenset({'event', 'machine', 'model', 'state', 'source', 'target',
                           'transition', 'event_data', 'error'})


class Cancelled(Exception):
    """The invocation waiting for the worker was cancelled."""


class NotRunning(Exception):
    """The chart is not running."""


def call_with(fn, available):
    """Call fn with the entries of ``available`` its signature names (all of them for **kw)."""
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return fn(**available)
    params = sig.parameters.values()
    if any(p.kind is p.VAR_KEYWORD for p in params):
        return fn(**available)
    kwargs = {p.name: available[p.name] for p in params
              if p.name in available and p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)}
    return fn(**kwargs)


def to_jsonable(value, depth=0):
    """Convert event data and datamodel values (ROS messages included) for JSON."""
    if depth > 8:
        return repr(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): to_jsonable(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v, depth + 1) for v in value]
    if hasattr(value, 'get_fields_and_field_types'):
        try:
            from rosidl_runtime_py.convert import message_to_ordereddict
            return to_jsonable(dict(message_to_ordereddict(value)), depth + 1)
        except Exception:  # noqa: B902 - fall back to repr
            return repr(value)
    if isinstance(value, Outcome):
        return to_jsonable(value.event_data(), depth + 1)
    if isinstance(value, BaseException):
        return f'{type(value).__name__}: {value}'
    return repr(value)


def to_json(value):
    return json.dumps(to_jsonable(value), sort_keys=True)


class GuardTypeError(TypeError):
    """A guard returned something other than a bool (docs/FORMAT.md section 8)."""


def guard_result(fn, value):
    """Return a guard's value, which must be a bool; anything else is an error."""
    if isinstance(value, bool):
        return value
    if type(value).__name__ == 'bool_':  # numpy.bool_
        return bool(value)
    raise GuardTypeError(f'guard {getattr(fn, "__name__", fn)} returned '
                         f'{type(value).__name__} {value!r}, not a bool')


class ChartModel:
    """
    The engine's model object: datamodel values, generated conditions, the user's model.

    The engine resolves guard names only on its model (docs/ENGINE.md E10), so
    this object answers the generated ``sc_ros_outcome_*`` conditions and
    forwards every other public name to the user's ``ros:model`` instance.
    Builders receive it as ``datamodel``.
    """

    def __init__(self, spec, user):
        self.__dict__['_spec'] = spec
        self.__dict__['_user'] = user
        self.__dict__[REFUSAL_VAR] = ''

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        out = self._spec.conditions.get(name)
        if out is not None:
            return self._outcome_condition(out)
        user = self.__dict__.get('_user')
        if user is not None and hasattr(user, name):
            value = getattr(user, name)
            if callable(value):
                return self._with_datamodel(value)
            return value
        raise AttributeError(name)

    def _with_datamodel(self, fn):
        """Wrap a model method for the engine so that it can ask for ``datamodel``."""
        model = self

        def method(*args, **kwargs):
            return guard_result(fn, call_with(fn, dict(kwargs, datamodel=model)))

        method.__name__ = getattr(fn, '__name__', 'method')
        return method

    def _outcome_condition(self, out):
        statuses = set(out.statuses)
        user = self._user

        def condition(status=None, **kwargs):
            if '*' not in statuses and status not in statuses:
                return False
            if out.cond:
                available = dict(kwargs, status=status, datamodel=self)
                fn = getattr(user, out.cond)
                return guard_result(fn, call_with(fn, available))
            return True

        condition.__name__ = out.name
        return condition

    def values(self, names=None):
        """Return the datamodel: every value, or only the named ones."""
        result = {}
        for key, value in self.__dict__.items():
            if key.startswith('_') or key.startswith(PREFIX) or key == 'state':
                continue
            if names is None or key in names:
                result[key] = value
        return result


@dataclass
class EventResult:
    """What one event did: the answer of a service or action request."""

    event: str
    handled: bool
    refusal: str
    configuration: list
    taken: list = field(default_factory=list)


@dataclass
class Record:
    """One processed event, for the transition log."""

    stamp: float
    sequence: int
    event: str
    data: dict
    source: list
    target: list
    taken: list
    handled: bool
    refusal: str
    duration: float
    events: list = field(default_factory=list)   # events of the transitions taken


class Host:
    """What the runner needs from its environment. The node implements it with rclpy."""

    runner = None

    def now(self):
        """Return the current time in seconds (ROS time in the node)."""
        return time.time()

    def schedule(self, delay, callback):
        """Call callback once after delay seconds; return an object with cancel()."""
        timer = threading.Timer(delay, callback)
        timer.daemon = True
        timer.start()
        return timer

    def wait(self, event, seconds):
        """Wait until event is set or seconds pass; return whether it is set."""
        return event.wait(seconds)

    def output(self, out, model):
        """Do a ros:on_entry / ros:on_exit output."""

    def logger(self):
        return logging.getLogger('statechart_ros')


class ChartRunner:
    """Run one chart: the queue, the worker, the engine's listener."""

    def __init__(self, spec, user_model=None, host=None, kinds=None, initial_data=None):
        self.spec = spec
        self.user_model = user_model
        self.host = host or Host()
        self.host.runner = self
        self.model = ChartModel(spec, user_model)
        self.queue = queue.Queue()
        self.sm = None
        self.sequence = 0
        self.observers = []          # called on the worker with each Record
        self.status_observers = []   # called when the status changed (any thread)
        self.engine_threads = set()  # threads engine callbacks ran on (instrumentation)
        self.final = None            # (final state id, donedata) once the chart ended
        self._lock = threading.RLock()
        self._worker = None
        self._worker_ident = None
        self._entry_tokens = {}
        self._invocations = {}
        self._afters = {}
        self._invoke_status = {}
        self._taken = []
        self._last = EventResult('', False, '', [])
        self._initial_data = initial_data or {}
        self._next_token = 0
        self.kinds = {}
        for state, inv in spec.invokes.items():
            factory = (kinds or {}).get(inv.kind) or get_kind(inv.kind)
            if factory is None:
                raise ValueError(f'unknown invoke kind {inv.kind}')
            self.kinds[state] = factory(self.host, state, inv.attrs)
        self.listener = self._make_listener()

    # --- the worker -----------------------------------------------------------------

    @property
    def log(self):
        return self.host.logger()

    def start_worker(self):
        if self._worker is not None and self._worker.is_alive():
            return
        self._worker = threading.Thread(target=self._loop, name=f'statechart-{self.spec.name}',
                                        daemon=True)
        self._worker.start()

    def shutdown(self, timeout=5.0):
        """Stop the chart if it runs, then end the worker."""
        if self._worker is None:
            return
        try:
            self.stop(timeout=timeout)
        finally:
            self.queue.put(None)
            self._worker.join(timeout)
            self._worker = None

    def in_worker(self):
        return threading.get_ident() == self._worker_ident

    def submit(self, fn, *args, **kwargs):
        """Run fn on the worker; return a Future of its result."""
        future = Future()
        self.queue.put(('call', (fn, args, kwargs), future))
        return future

    def run_in_worker(self, fn, *args, cancelled=None, timeout=None, **kwargs):
        """Run fn on the worker and wait for its result (directly when on the worker)."""
        if self.in_worker():
            return fn(*args, **kwargs)
        future = self.submit(fn, *args, **kwargs)
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            try:
                return future.result(timeout=0.02)
            except TimeoutError:
                pass
            if cancelled is not None and cancelled.is_set():
                future.cancel()
                raise Cancelled()
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError(f'the worker did not run {fn} in {timeout} s')

    def call_model(self, name, cancelled=None, **available):
        """Call a model method by name on the worker, with the arguments it names."""
        fn = getattr(self.user_model, name)
        available.setdefault('datamodel', self.model)
        return self.run_in_worker(call_with, fn, available, cancelled=cancelled)

    def _loop(self):
        self._worker_ident = threading.get_ident()
        while True:
            item = self.queue.get()
            if item is None:
                return
            kind, payload, future = item
            if future is not None and not future.set_running_or_notify_cancel():
                continue
            try:
                result = self._handle(kind, payload)
            except BaseException as exc:  # noqa: B902 - reported to the waiting caller
                self.log.error(f'statechart worker: {exc}\n{traceback.format_exc()}')
                if future is not None:
                    future.set_exception(exc)
                continue
            if future is not None:
                future.set_result(result)

    def _handle(self, kind, payload):
        if kind == 'call':
            fn, args, kwargs = payload
            return fn(*args, **kwargs)
        if kind == 'event':
            event, data, prepare = payload
            if prepare is not None:
                prepared = prepare()
                if prepared is None:
                    return None
                event, data = prepared
            return self._process(event, data)
        if kind == 'outcome':
            state, token, outcome, error = payload
            current = self._invocations.get(state)
            if current is None or current[0] != token or current[1].cancelled.is_set():
                return None
            if error is not None:
                self.log.error(f'invoke of state {state} failed: {error!r}')
                return self._process('error.execution', {'error': error})
            return self._process(f'done.invoke.{state}', outcome.event_data())
        if kind == 'after':
            state, token, event = payload
            if self._entry_tokens.get(state) != token or not self._active(state):
                return None
            return self._process(event, {})
        raise ValueError(kind)

    # --- control and events (any thread) --------------------------------------------

    def start(self, timeout=10.0):
        """Create the engine instance (entering the initial states) on the worker."""
        self.start_worker()
        return self.run_in_worker(self._create, timeout=timeout)

    def stop(self, timeout=10.0):
        """Exit every state (outputs and invokes included) and end the run."""
        if self._worker is None:
            return None
        return self.run_in_worker(self._stop, timeout=timeout)

    def post(self, event, data=None, prepare=None):
        """
        Queue an event; return a Future of its EventResult.

        ``prepare`` runs on the worker first and returns ``(event, data)`` or None
        to drop the item (used to run a subscription's guard on the worker).
        """
        future = Future()
        self.queue.put(('event', (event, dict(data or {}), prepare), future))
        return future

    def send(self, event, data=None, timeout=10.0):
        """Post an event and wait for its result."""
        return self.post(event, data).result(timeout=timeout)

    @property
    def running(self):
        return self.sm is not None and not self.sm.is_terminated

    # --- on the worker --------------------------------------------------------------

    def _create(self):
        if self.running:
            return self._last
        self.model = ChartModel(self.spec, self.user_model)
        self.final = None
        self._entry_tokens.clear()
        self._taken = []
        source = []
        start = time.monotonic()
        self.sm = self.spec.engine_class(model=self.model, listeners=[self.listener])
        for key, value in self._initial_data.items():
            setattr(self.model, key, value)
        record = self._record('__initial__', {}, source, start, True, '')
        self._last = EventResult('__initial__', True, '', record.target, record.taken)
        self._notify(record)
        return self._last

    def _stop(self):
        if not self.running:
            return None
        result = self._process(STOP_EVENT, {})
        return result

    def _active(self, state):
        return self.sm is not None and state in self.sm.configuration_values

    def configuration(self):
        """Return the active user states in document order."""
        if self.sm is None:
            return []
        active = set(self.sm.configuration_values)
        return [s for s in self.spec.states if s in active]

    def _process(self, event, data):
        if not self.running:
            return EventResult(event, False, 'the chart is not running', self.configuration())
        allowed = {'error'} if event == 'error.execution' else set()
        bad = RESERVED_KEYS.intersection(data) - allowed
        if bad:
            return EventResult(event, False, 'event data may not use the names '
                               + ', '.join(sorted(bad)), self.configuration())
        self.model.__dict__[REFUSAL_VAR] = ''
        self._taken = []
        source = self.configuration()
        start = time.monotonic()
        self.sm.send(event, **data)
        refusal = self.model.__dict__.get(REFUSAL_VAR, '')
        handled = any(not t['refusal'] for t in self._taken if t['event'] == event)
        if not handled and not refusal and event != STOP_EVENT:
            self.log.warning(f'event "{event}" was not handled in configuration '
                             f'{{{", ".join(source)}}}')
        record = self._record(event, data, source, start, handled, refusal)
        self._last = EventResult(event, handled, refusal, record.target, record.taken)
        self._notify(record)
        return self._last

    def _record(self, event, data, source, start, handled, refusal):
        self.sequence += 1
        return Record(stamp=self.host.now(), sequence=self.sequence, event=event, data=data,
                      source=source, target=self.configuration(),
                      taken=[t['label'] for t in self._taken], handled=handled,
                      refusal=refusal, duration=time.monotonic() - start,
                      events=[t['event'] for t in self._taken])

    def _notify(self, record):
        for observer in list(self.observers):
            try:
                observer(record)
            except Exception as exc:  # noqa: B902 - an observer must not stop the chart
                self.log.error(f'statechart observer failed: {exc!r}')
        self._status_changed()

    def _status_changed(self):
        for observer in list(self.status_observers):
            try:
                observer()
            except Exception as exc:  # noqa: B902
                self.log.error(f'statechart status observer failed: {exc!r}')

    def snapshot(self):
        """Return the status: configuration, last event, invokes (any thread)."""
        with self._lock:
            invokes = [dict(v, state=k) for k, v in self._invoke_status.items()]
        last = self._last
        return {'active': list(last.configuration), 'last_event': last.event,
                'handled': last.handled, 'refusal': last.refusal, 'invokes': invokes,
                'sequence': self.sequence, 'running': self.running}

    # --- the engine's listener (called on the worker) -------------------------------

    def _make_listener(self):
        runner = self
        methods = {}

        def track():
            runner.engine_threads.add(threading.get_ident())

        def after_transition(self, event=None, transition=None, **kwargs):
            track()
            source = transition.source.id if transition is not None else ''
            if source == PREFIX + 'root' and str(event) == f'done.state.{PREFIX}root':
                runner.final = (runner._last_final, {k: v for k, v in kwargs.items()
                                                     if k not in _ENGINE_KWARGS})
            if source.startswith(PREFIX):
                return
            targets = [t.id for t in (transition.targets or [])] if transition else []
            refusal = (not targets and (source, str(event)) in runner._refusal_keys)
            runner._taken.append({'event': str(event), 'refusal': refusal,
                                  'label': f'{source} -> {", ".join(targets)}'.rstrip()})

        def on_exit_state(self, state=None, **kwargs):
            track()
            if state is not None and not state.id.startswith(PREFIX):
                runner._exited(state.id)

        methods['after_transition'] = after_transition
        methods['on_exit_state'] = on_exit_state

        def entry(sid):
            def on_enter(self, **kwargs):
                track()
                runner._entered(sid)
            return on_enter

        for sid, info in self.spec.states.items():
            if info.tag == 'history':
                continue
            methods[f'on_enter_{sid}'] = entry(sid)

        def invoker(sid):
            def on_invoke(self, ctx=None, **kwargs):
                return runner._invoke(sid, ctx)
            return on_invoke

        for sid in self.spec.invokes:
            methods[f'on_invoke_{sid}'] = invoker(sid)
        self._refusal_keys = {(r.state, r.event) for rs in self.spec.refusals.values()
                              for r in rs if not r.ignore}
        self._last_final = None
        return type('StatechartListener', (), methods)()

    def _entered(self, sid):
        self._next_token += 1
        token = self._next_token
        self._entry_tokens[sid] = token
        info = self.spec.states[sid]
        if info.tag == 'final' and info.parent is None:
            self._last_final = sid
        for out in self.spec.outputs.get(sid, []):
            if out.when == 'entry':
                self._output(out)
        handles = []
        for after in self.spec.afters.get(sid, []):
            def fire(after=after, token=token):
                self.queue.put(('after', (sid, token, after.event), None))
            handles.append(self.host.schedule(after.delay, fire))
        if handles:
            self._afters[sid] = handles
        if sid in self.spec.invokes:
            inv = self.spec.invokes[sid]
            kind = get_kind(inv.kind)
            summary = kind.summary(inv.attrs) if kind else {}
            with self._lock:
                self._invoke_status[sid] = {'kind': inv.kind,
                                            'target': summary.get('target', ''),
                                            'since': self.host.now(), 'feedback': {}}

    def _exited(self, sid):
        self._entry_tokens.pop(sid, None)
        for handle in self._afters.pop(sid, []):
            handle.cancel()
        for out in self.spec.outputs.get(sid, []):
            if out.when == 'exit':
                self._output(out)
        with self._lock:
            self._invoke_status.pop(sid, None)

    def _output(self, out):
        try:
            self.host.output(out, self.model)
        except Exception as exc:  # noqa: B902 - an output failure is logged, not fatal
            self.log.error(f'output of state {out.state} (line {out.line}) failed: {exc!r}')

    def _feedback(self, sid, token, summary):
        with self._lock:
            status = self._invoke_status.get(sid)
            current = self._invocations.get(sid)
            if status is None or current is None or current[0] != token:
                return
            status['feedback'] = to_jsonable(summary)
        self._status_changed()

    def _invoke(self, sid, ctx):
        """Run on the engine's invoke thread: do the work, hand the outcome to the worker."""
        with self._lock:
            self._next_token += 1
            token = self._next_token
            self._invocations[sid] = (token, ctx)
        invocation = Invocation(sid, cancelled=ctx.cancelled,
                                post=lambda event, data: self.post(event, data),
                                feedback=lambda summary: self._feedback(sid, token, summary))
        outcome = None
        error = None
        try:
            outcome = self.kinds[sid].run(invocation)
            if outcome is None:
                outcome = Outcome('succeeded')
        except Cancelled:
            pass
        except Exception as exc:  # noqa: B902 - becomes error.execution on the worker
            error = exc
        if not ctx.cancelled.is_set():
            self.queue.put(('outcome', (sid, token, outcome, error), None))
        ctx.cancelled.wait()
        return None


_ENGINE_KWARGS = frozenset({'event_data', 'machine', 'model', 'state', 'source', 'target',
                            '_name', '_sessionid', '_ioprocessors', '_event', 'transition',
                            'event'})
