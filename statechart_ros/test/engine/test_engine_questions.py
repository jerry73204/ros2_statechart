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


"""The open questions of docs/ENGINE.md, answered by tests (phase P0)."""

import threading
import time

from engine_util import config, load_chart, wait_until


class Log:
    """Listener recording events, exits and invokes."""

    def __init__(self):
        self.events = []
        self.exits = []

    def after_transition(self, event=None, **kwargs):
        self.events.append(str(event))

    def on_exit_state(self, source=None, state=None, **kwargs):
        self.exits.append(state.id)


def test_q1_events_sent_by_an_invoke_come_before_its_done_invoke():
    class Invoke(Log):

        def on_invoke_b(self, ctx=None, **kwargs):
            ctx.send('progress')
            return 'result'

    log = Invoke()
    cls = load_chart(
        '<state id="a"><transition event="go" target="b"/></state>'
        '<state id="b"><transition event="progress" target="p"/>'
        '  <transition event="done.invoke.b" target="d"/></state>'
        '<state id="p"/><state id="d"/>')
    sm = cls(listeners=[log])
    sm.send('go')
    assert wait_until(lambda: config(sm) == {'p'})
    time.sleep(0.05)
    assert config(sm) == {'p'}
    assert log.events == ['go', 'progress']


def test_q2_deep_history_reenters_the_remembered_leaf_and_invokes_it_again():
    class Invoke(Log):

        def __init__(self):
            super().__init__()
            self.contexts = []

        def on_invoke_a2(self, ctx=None, **kwargs):
            self.contexts.append(ctx)
            ctx.cancelled.wait(5.0)

    log = Invoke()
    cls = load_chart(
        '<state id="a" initial="a1">'
        '  <history id="h" type="deep"><transition target="a1"/></history>'
        '  <state id="a1"><transition event="next" target="a2"/></state>'
        '  <state id="a2"/>'
        '  <transition event="pause" target="p"/>'
        '</state>'
        '<state id="p"><transition event="resume" target="h"/></state>')
    sm = cls(listeners=[log])
    sm.send('next')
    assert wait_until(lambda: len(log.contexts) == 1)
    sm.send('pause')
    assert log.contexts[0].cancelled.is_set()
    sm.send('resume')
    assert config(sm) == {'a', 'a2'}
    assert wait_until(lambda: len(log.contexts) == 2)
    assert not log.contexts[1].cancelled.is_set()
    sm.send('pause')


def test_q3_leaving_a_parallel_state_exits_innermost_first_and_cancels_every_region():
    class Invoke(Log):

        def __init__(self):
            super().__init__()
            self.contexts = {}

        def on_invoke_x(self, ctx=None, **kwargs):
            self.contexts['x'] = ctx
            ctx.cancelled.wait(5.0)

        def on_invoke_y(self, ctx=None, **kwargs):
            self.contexts['y'] = ctx
            ctx.cancelled.wait(5.0)

    log = Invoke()
    cls = load_chart(
        '<parallel id="P">'
        '  <state id="r1" initial="x"><state id="x"/></state>'
        '  <state id="r2" initial="y"><state id="y"/></state>'
        '  <transition event="leave" target="out"/>'
        '</parallel>'
        '<state id="out"/>', initial='P')
    sm = cls(listeners=[log])
    assert wait_until(lambda: len(log.contexts) == 2)
    sm.send('leave')
    assert config(sm) == {'out'}
    assert log.contexts['x'].cancelled.is_set()
    assert log.contexts['y'].cancelled.is_set()
    # Descendants before ancestors (SCXML exitOrder), later document order
    # first among states of the same depth: leaves, then regions, then P.
    assert log.exits == ['y', 'x', 'r2', 'r1', 'P']


def test_q4_each_invocation_runs_in_its_own_thread_and_the_threads_end():
    class Invoke:

        def __init__(self):
            self.threads = []

        def on_invoke_b(self, ctx=None, **kwargs):
            self.threads.append(threading.current_thread())
            return None

    rec = Invoke()
    cls = load_chart(
        '<state id="a"><transition event="go" target="b"/></state>'
        '<state id="b"><transition event="done.invoke.b" target="a"/>'
        '  <transition event="go" target="a"/></state>')
    sm = cls(listeners=[rec])
    baseline = threading.active_count()
    cycles = 200
    for _ in range(cycles):
        sm.send('go')
        wait_until(lambda: config(sm) == {'a'}, timeout=1.0)
    assert len(rec.threads) == cycles
    assert len({id(t) for t in rec.threads}) == cycles
    assert all(t.daemon for t in rec.threads)
    assert wait_until(lambda: threading.active_count() <= baseline)


def test_q4_a_chart_with_synchronous_callbacks_runs_on_the_sync_engine():
    cls = load_chart('<state id="a"/>')
    assert type(cls()._engine).__name__ == 'SyncEngine'
