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


"""The runner without ROS: queue, worker, invokes, outputs, timeouts, stop (P2)."""

import threading
import time

from charts_util import spec_of
import pytest
from statechart_ros.kinds import Attr, InvokeKind, Outcome, STRING
from statechart_ros.runtime import ChartRunner, Host


class FakeHost(Host):

    def __init__(self):
        self.outputs = []

    def output(self, out, model, runner=None):
        self.outputs.append((out.state, out.when, out.attrs.get('publish'),
                             dict(model.values())))


class Scripted(InvokeKind):
    """A kind whose runs end as the test says."""

    name = 'test/scripted'
    attributes = {'label': Attr(STRING)}
    statuses = ('succeeded', 'aborted')
    script = {}
    runs = []
    cancelled = []

    def run(self, invocation):
        Scripted.runs.append(self.state_id)
        behaviour = Scripted.script.get(self.state_id, ('succeeded', 0.0))
        status, delay = behaviour
        if invocation.cancelled.wait(delay):
            Scripted.cancelled.append(self.state_id)
            return None
        if status == 'raise':
            raise RuntimeError('boom')
        return Outcome(status, result={'state': self.state_id})


@pytest.fixture(autouse=True)
def reset_scripted():
    Scripted.script = {}
    Scripted.runs = []
    Scripted.cancelled = []
    from statechart_ros import kinds
    kinds.register(Scripted)
    yield


def runner_of(body, model=None, check=True, **kwargs):
    spec = spec_of(body, **kwargs)
    assert spec.engine_class is not None, spec.findings
    host = FakeHost()
    runner = ChartRunner(spec, model, host)
    runner.start()
    return runner, host


def wait_config(runner, expected, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if set(runner.configuration()) == set(expected):
            return True
        time.sleep(0.01)
    return set(runner.configuration())


INVOKE = '<ros:invoke kind="test/scripted"/>'


def test_events_answers_handled_refused_ignored_unhandled():
    runner, _ = runner_of(
        '<state id="a"><transition event="go" target="b"/>'
        '<ros:refuse event="halt" reason="nothing to halt"/><ros:ignore event="noise"/></state>'
        '<state id="b"><transition event="back" target="a"/></state>')
    try:
        assert runner.configuration() == ['a']
        result = runner.send('halt')
        assert (result.handled, result.refusal) == (False, 'nothing to halt')
        result = runner.send('noise')
        assert (result.handled, result.refusal) == (True, '')
        result = runner.send('nonsense')
        assert (result.handled, result.refusal) == (False, '')
        result = runner.send('go')
        assert result.handled and result.configuration == ['b']
        assert result.taken == ['a -> b']
    finally:
        runner.shutdown()


def test_event_data_may_not_use_engine_names():
    runner, _ = runner_of('<state id="a"><transition event="go" target="a"/></state>')
    try:
        result = runner.send('go', {'state': 1})
        assert not result.handled and 'state' in result.refusal
    finally:
        runner.shutdown()


def test_outputs_run_after_onentry_and_before_onexit():
    runner, host = runner_of(
        '<datamodel><data id="entered" expr="0"/><data id="left" expr="0"/></datamodel>'
        '<state id="a"><transition event="go" target="b"/></state>'
        '<state id="b"><onentry><assign location="entered" expr="entered + 1"/></onentry>'
        '<onexit><assign location="left" expr="left + 1"/></onexit>'
        '<ros:on_entry publish="t" type="std_msgs/msg/Bool" value="true"/>'
        '<ros:on_exit publish="t" type="std_msgs/msg/Bool" value="false"/>'
        '<transition event="back" target="a"/></state>')
    try:
        runner.send('go')
        runner.send('back')
        assert [(o[0], o[1]) for o in host.outputs] == [('b', 'entry'), ('b', 'exit')]
        assert host.outputs[0][3]['entered'] == 1
        assert host.outputs[1][3]['left'] == 0
    finally:
        runner.shutdown()


def test_invoke_outcome_routes_to_the_outcome_transition():
    Scripted.script = {'b': ('aborted', 0.05)}
    runner, _ = runner_of(
        f'<state id="a"><transition event="go" target="b"/></state>'
        f'<state id="b">{INVOKE}<ros:outcome status="succeeded" target="ok"/>'
        f'<ros:outcome status="aborted" target="failed"/></state>'
        '<state id="ok"/><state id="failed"/>')
    try:
        runner.send('go')
        assert wait_config(runner, ['failed']) is True
    finally:
        runner.shutdown()


def test_leaving_the_state_cancels_the_invoke_and_drops_its_outcome():
    Scripted.script = {'b': ('succeeded', 5.0)}
    runner, _ = runner_of(
        f'<state id="a"><transition event="go" target="b"/></state>'
        f'<state id="b">{INVOKE}<ros:outcome status="*" target="ok"/>'
        '<transition event="leave" target="a"/></state><state id="ok"/>')
    try:
        runner.send('go')
        deadline = time.monotonic() + 2
        while not Scripted.runs and time.monotonic() < deadline:
            time.sleep(0.01)
        runner.send('leave')
        deadline = time.monotonic() + 2
        while not Scripted.cancelled and time.monotonic() < deadline:
            time.sleep(0.01)
        assert Scripted.cancelled == ['b']
        time.sleep(0.1)
        assert runner.configuration() == ['a']
    finally:
        runner.shutdown()


def test_an_exception_in_the_invoke_is_error_execution():
    Scripted.script = {'b': ('raise', 0.0)}
    runner, _ = runner_of(
        f'<state id="a"><transition event="go" target="b"/></state>'
        f'<state id="b">{INVOKE}<ros:outcome status="*" target="a"/>'
        '<transition event="error.execution" target="fault"/></state><state id="fault"/>')
    try:
        runner.send('go')
        assert wait_config(runner, ['fault']) is True
    finally:
        runner.shutdown()


def test_outcome_guard_on_the_model_gets_the_outcome():
    class Model:

        def __init__(self):
            self.seen = []

        def retry(self, status, result, datamodel):
            self.seen.append((status, result))
            return datamodel.tries < 2

    model = Model()
    Scripted.script = {'b': ('aborted', 0.0)}
    runner, _ = runner_of(
        '<datamodel><data id="tries" expr="0"/></datamodel>'
        f'<state id="a"><transition event="go" target="b"/></state>'
        f'<state id="b"><onentry><assign location="tries" expr="tries + 1"/></onentry>'
        f'{INVOKE}<ros:outcome status="succeeded" target="a"/>'
        '<ros:outcome status="aborted" cond="retry" target="b"/>'
        '<ros:outcome status="aborted" target="gave_up"/></state><state id="gave_up"/>',
        model=model)
    try:
        runner.send('go')
        assert wait_config(runner, ['gave_up']) is True
        assert [s for s, _ in model.seen] == ['aborted', 'aborted']
        assert model.seen[0][1] == {'state': 'b'}
        assert Scripted.runs == ['b', 'b']
    finally:
        runner.shutdown()


def test_after_fires_in_the_state_and_is_cancelled_when_left():
    runner, _ = runner_of(
        '<state id="a"><transition event="go" target="b"/><transition event="slow" target="c"/>'
        '</state><state id="b"><ros:after delay="0.1" event="timeout"/>'
        '<transition event="timeout" target="late"/></state>'
        '<state id="c"><ros:after delay="0.2" event="timeout"/>'
        '<transition event="leave" target="a"/><transition event="timeout" target="late"/>'
        '</state><state id="late"/>')
    try:
        runner.send('go')
        assert wait_config(runner, ['late']) is True
        runner2, _ = runner_of(
            '<state id="c"><ros:after delay="0.2" event="timeout"/>'
            '<transition event="leave" target="a"/><transition event="timeout" target="late"/>'
            '</state><state id="a"/><state id="late"/>', initial='c')
        try:
            runner2.send('leave')
            time.sleep(0.4)
            assert runner2.configuration() == ['a']
        finally:
            runner2.shutdown()
    finally:
        runner.shutdown()


def test_the_engine_is_only_entered_from_the_worker():
    Scripted.script = {'b': ('succeeded', 0.01)}
    runner, _ = runner_of(
        f'<state id="a"><transition event="go" target="b"/></state>'
        f'<state id="b">{INVOKE}<ros:outcome status="*" target="a"/>'
        '<ros:after delay="0.01" event="tick"/><transition event="tick"/></state>')
    try:
        def hammer():
            for _ in range(50):
                runner.post('go')
                time.sleep(0.002)
        threads = [threading.Thread(target=hammer) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        time.sleep(0.3)
        assert len(Scripted.runs) > 5
        assert runner.engine_threads == {runner._worker_ident}
    finally:
        runner.shutdown()


def test_stop_exits_every_state_and_cancels_invokes_then_start_restarts():
    Scripted.script = {'x': ('succeeded', 5.0), 'y': ('succeeded', 5.0)}
    runner, host = runner_of(
        f'<parallel id="p"><state id="r1" initial="x"><state id="x">{INVOKE}'
        '<ros:outcome status="*" target="x"/></state></state>'
        f'<state id="r2" initial="y"><state id="y">{INVOKE}<ros:outcome status="*" target="y"/>'
        '<ros:on_exit publish="t" type="std_msgs/msg/Bool" value="false"/></state></state>'
        '</parallel>', initial='p')
    try:
        deadline = time.monotonic() + 2
        while len(Scripted.runs) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        runner.stop()
        assert runner.configuration() == []
        assert not runner.running
        assert sorted(Scripted.cancelled) == ['x', 'y']
        assert [o[:2] for o in host.outputs] == [('y', 'exit')]
        runner.start()
        assert set(runner.configuration()) == {'p', 'r1', 'x', 'r2', 'y'}
        deadline = time.monotonic() + 2
        while len(Scripted.runs) < 4 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(Scripted.runs) == 4
    finally:
        runner.shutdown()


def test_every_run_starts_with_the_initial_datamodel():
    runner, _ = runner_of(
        '<datamodel><data id="n" expr="1"/></datamodel>'
        '<state id="a"><transition event="go" target="a">'
        '<assign location="n" expr="n + 1"/></transition></state>')
    try:
        runner.send('go')
        assert runner.model.n == 2
        for _ in range(2):
            runner.stop()
            runner.start()
            assert runner.model.n == 1
    finally:
        runner.shutdown()


def test_reaching_a_top_level_final_ends_the_run_with_its_data():
    runner, _ = runner_of(
        '<state id="a"><transition event="go" target="done"/></state>'
        '<final id="done"><donedata><param name="code" expr="7"/></donedata></final>')
    try:
        runner.send('go')
        assert not runner.running
        assert runner.final == ('done', {'code': 7})
    finally:
        runner.shutdown()


def test_a_guard_must_return_a_bool():
    class Model:

        def __init__(self):
            self.answer = 1

        def ready(self):
            return self.answer

    model = Model()
    runner, _ = runner_of(
        '<state id="a"><transition event="go" cond="ready" target="b"/>'
        '<transition event="error.execution" target="fault"/></state>'
        '<state id="b"/><state id="fault"/>', model=model, check=False)
    try:
        runner.send('go')
        assert runner.configuration() == ['fault']
    finally:
        runner.shutdown()
    model.answer = True
    runner, _ = runner_of(
        '<state id="a"><transition event="go" cond="ready" target="b"/></state>'
        '<state id="b"/>', model=model, check=False)
    try:
        runner.send('go')
        assert runner.configuration() == ['b']
    finally:
        runner.shutdown()
