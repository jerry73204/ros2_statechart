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
Engine facts E1 to E12 of docs/ENGINE.md, and the facts found in phase P0 (E13 to E18).

Each test pins one behaviour of python-statemachine that the design relies on.
A release of the engine that changes any of them fails here first.
"""

import threading
import time

from engine_util import config, load_chart, wait_until
import pytest
import statemachine
from statemachine.exceptions import InvalidDefinition


def test_engine_version_is_the_pinned_release():
    assert statemachine.__version__ == '3.2.2'


class Recorder:
    """Listener recording transitions, invokes and the threads they ran on."""

    def __init__(self, invoke=None):
        self.events = []
        self.threads = []
        self.contexts = []
        self.calls = 0
        self.invoke = invoke

    def after_transition(self, event=None, **kwargs):
        self.events.append(str(event))
        self.threads.append(threading.current_thread())


# --- E1, E2: foreign elements -------------------------------------------------

def test_e1_foreign_elements_under_scxml_and_state_are_ignored():
    cls = load_chart(
        '<ros:model class="pkg.mod:Model"/>'
        '<ros:subscribe topic="e_stop" type="std_msgs/msg/Bool" event="e_stop"/>'
        '<state id="a">'
        '  <ros:action server="dock" type="nav2_msgs/action/DockRobot" goal="g"/>'
        '  <ros:outcome status="succeeded" target="b"/>'
        '  <transition event="go" target="b"/>'
        '</state>'
        '<parallel id="b"><ros:on_entry publish="x" type="std_msgs/msg/Bool" value="true"/>'
        '  <state id="r1"/><state id="r2"/></parallel>')
    sm = cls()
    assert config(sm) == {'a'}
    sm.send('go')
    assert config(sm) == {'b', 'r1', 'r2'}


def test_e1_foreign_element_with_an_scxml_local_name_is_read_as_scxml():
    # The reader strips namespaces before reading: ros:invoke becomes <invoke>
    # and ros:transition becomes <transition>. The loader of statechart_ros
    # removes every ros: element before the engine reads the document.
    cls = load_chart(
        '<state id="a"><ros:transition event="go" target="b"/></state><state id="b"/>')
    sm = cls()
    sm.send('go')
    assert config(sm) == {'b'}


@pytest.mark.parametrize('body', [
    '<state id="a"><onentry><ros:publish topic="x" value="1"/></onentry></state>',
    '<state id="a"><onexit><ros:publish topic="x" value="1"/></onexit></state>',
    '<state id="a"><transition event="go" target="a"><ros:publish topic="x"/></transition>'
    '</state>',
])
def test_e2_foreign_elements_in_executable_content_are_refused(body):
    with pytest.raises(ValueError, match='Unknown tag'):
        load_chart(body)


# --- E3: custom invoke and send types -----------------------------------------

@pytest.mark.parametrize('content', [
    '<invoke id="dock" type="ros2:action"/>',
    '<onentry><send event="x" type="ros2:topic" target="/dock/hold"/></onentry>',
])
def test_e3_custom_invoke_and_send_types_fail_at_run_time(content):
    cls = load_chart(
        '<state id="a"><transition event="go" target="b"/></state>'
        f'<state id="b">{content}'
        '  <transition event="error.execution" target="failed"/>'
        '  <transition event="error.communication" target="failed"/></state>'
        '<state id="failed"/>')
    sm = cls()
    sm.send('go')
    assert wait_until(lambda: config(sm) == {'failed'})


# --- E4, E5, E8: listener invokes ---------------------------------------------

def _invoke_chart():
    return load_chart(
        '<state id="a"><transition event="go" target="b"/></state>'
        '<state id="b">'
        '  <transition event="done.invoke.b" target="done"/>'
        '  <transition event="error.execution" target="err"/>'
        '  <transition event="leave" target="p"/>'
        '</state>'
        '<state id="p"><transition event="back" target="b"/></state>'
        '<state id="done"/><state id="err"/>')


class SlowInvoke(Recorder):

    def __init__(self, duration=0.3, result='ok', error=None):
        super().__init__()
        self.duration = duration
        self.result = result
        self.error = error
        self.saw_cancel = []

    def on_invoke_b(self, ctx=None, **kwargs):
        self.calls += 1
        self.contexts.append(ctx)
        if ctx.cancelled.wait(self.duration):
            self.saw_cancel.append(True)
            return 'discarded'
        if self.error is not None:
            raise self.error
        return self.result


def test_e4_listener_invoke_is_called_on_entry_with_a_context():
    rec = SlowInvoke(duration=0.05)
    sm = _invoke_chart()(listeners=[rec])
    sm.send('go')
    assert wait_until(lambda: config(sm) == {'done'})
    assert rec.calls == 1
    ctx = rec.contexts[0]
    assert ctx.state_id == 'b'
    assert isinstance(ctx.cancelled, threading.Event)
    assert callable(ctx.send)


def test_e5_leaving_the_state_sets_cancelled_and_discards_the_return():
    rec = SlowInvoke(duration=5.0)
    sm = _invoke_chart()(listeners=[rec])
    sm.send('go')
    assert wait_until(lambda: rec.calls == 1)
    sm.send('leave')
    assert config(sm) == {'p'}
    assert wait_until(lambda: rec.saw_cancel == [True])
    assert rec.contexts[0].cancelled.is_set()
    time.sleep(0.1)
    assert config(sm) == {'p'}
    assert not any(e.startswith('done.invoke') for e in rec.events)


def test_e8_reentering_the_state_invokes_again():
    rec = SlowInvoke(duration=5.0)
    sm = _invoke_chart()(listeners=[rec])
    sm.send('go')
    assert wait_until(lambda: rec.calls == 1)
    sm.send('leave')
    sm.send('back')
    assert wait_until(lambda: rec.calls == 2)
    assert rec.contexts[0] is not rec.contexts[1]
    assert not rec.contexts[1].cancelled.is_set()
    sm.send('leave')


# --- E6, E7: what an invoke's end produces --------------------------------------

def test_e6_a_returned_value_becomes_done_invoke_with_a_data_wrapper():
    rec = SlowInvoke(duration=0.01, result={'status': 'succeeded'})
    cls = load_chart(
        '<datamodel><data id="seen" expr="None"/></datamodel>'
        '<state id="a"><transition event="go" target="b"/></state>'
        '<state id="b"><transition event="done.invoke.b" target="done">'
        '  <assign location="seen" expr="_event.data"/></transition></state>'
        '<state id="done"/>')
    sm = cls(listeners=[rec])
    sm.send('go')
    assert wait_until(lambda: config(sm) == {'done'})
    done = [e for e in rec.events if e.startswith('done.invoke')]
    assert len(done) == 1
    assert done[0].startswith('done.invoke.b.')
    assert len(done[0]) > len('done.invoke.b.')
    assert sm.model.seen.data == {'status': 'succeeded'}
    assert not isinstance(sm.model.seen, dict)


def test_e7_an_exception_in_the_invoke_becomes_error_execution():
    rec = SlowInvoke(duration=0.01, error=RuntimeError('boom'))
    sm = _invoke_chart()(listeners=[rec])
    sm.send('go')
    assert wait_until(lambda: config(sm) == {'err'})
    assert 'error.execution' in rec.events


# --- E9: unhandled events --------------------------------------------------------

def test_e9_an_event_no_state_handles_is_silently_ignored():
    cls = load_chart('<state id="a"><transition event="go" target="b"/></state><state id="b"/>')
    sm = cls()
    assert cls.allow_event_without_transition is True
    assert sm.send('nonsense') is None
    assert config(sm) == {'a'}


# --- E10, E11, E12: guards --------------------------------------------------------

class GuardModel:

    def __init__(self, answer=True):
        self.answer = answer
        self.seen = []

    def ready(self, speed=None, **kwargs):
        self.seen.append(speed)
        return self.answer


def _guard_chart(cond, trusted=False):
    return load_chart(
        '<datamodel><data id="station" expr="\'s1\'"/></datamodel>'
        f'<state id="a"><transition event="go" cond="{cond}" target="b"/>'
        '  <transition event="error.execution" target="err"/></state>'
        '<state id="b"/><state id="err"/>', trusted=trusted)


@pytest.mark.parametrize('answer, expected', [(True, {'b'}), (False, {'a'})])
def test_e10_a_bare_name_guard_is_a_model_callback_with_injected_arguments(answer, expected):
    model = GuardModel(answer)
    sm = _guard_chart('ready')(model=model)
    sm.send('go', speed=3)
    assert model.seen == [3]
    assert config(sm) == expected


def test_e10_a_bare_name_guard_is_not_resolved_on_listeners():
    sm = _guard_chart('ready')(listeners=[GuardModel(True)])
    sm.send('go')
    assert config(sm) == {'err'}


def test_e11_a_call_in_a_guard_is_refused_by_the_restricted_datamodel():
    with pytest.raises(InvalidDefinition, match='not allowed by the restricted'):
        _guard_chart('ready(station)')


def test_e12_a_call_in_a_trusted_guard_loads_but_does_not_reach_the_model():
    model = GuardModel(True)
    sm = _guard_chart('ready(station)', trusted=True)(model=model)
    sm.send('go')
    assert model.seen == []
    assert config(sm) == {'err'}


# --- Facts found in P0 ------------------------------------------------------------

def test_e13_a_delayed_send_holds_the_caller_of_send_until_it_is_due():
    cls = load_chart(
        '<state id="a"><transition event="go" target="b"/></state>'
        '<state id="b"><onentry><send event="t" delay="300ms"/></onentry>'
        '  <transition event="t" target="c"/></state><state id="c"/>')
    sm = cls()
    start = time.monotonic()
    sm.send('go')
    elapsed = time.monotonic() - start
    assert elapsed >= 0.28
    assert config(sm) == {'c'}


def test_e14_send_from_an_idle_thread_runs_the_macrostep_on_that_thread():
    rec = Recorder()
    cls = load_chart('<state id="a"><transition event="go" target="b"/></state><state id="b"/>')
    sm = cls(listeners=[rec])
    thread = threading.Thread(target=sm.send, args=('go',), name='other')
    thread.start()
    thread.join()
    assert config(sm) == {'b'}
    assert rec.threads[-1].name == 'other'


def test_e14_done_invoke_runs_on_the_invoke_thread_when_nothing_else_is_processing():
    rec = SlowInvoke(duration=0.2)
    sm = _invoke_chart()(listeners=[rec])
    sm.send('go')
    assert wait_until(lambda: config(sm) == {'done'})
    index = rec.events.index(next(e for e in rec.events if e.startswith('done.invoke')))
    assert rec.threads[index] is not threading.main_thread()


def test_e15_names_starting_with_an_underscore_never_resolve_on_the_model():
    class Model:

        def _hidden(self):
            return True

    sm = _guard_chart('_hidden')(model=Model())
    sm.send('go')
    assert config(sm) == {'err'}


def test_e16_loading_scxml_skips_the_unreachable_and_trap_state_checks():
    cls = load_chart('<state id="a"/><state id="orphan"><transition event="x" target="trap"/>'
                     '</state><state id="trap"/>')
    assert config(cls()) == {'a'}


@pytest.mark.parametrize('body', [
    '<state id="a"><transition event="x" type="internal"/></state>',
    '<state id="a" initial="a1"><transition event="x" type="internal"/><state id="a1"/></state>',
])
def test_e17_a_targetless_transition_of_type_internal_is_refused(body):
    with pytest.raises(InvalidDefinition, match='Not a valid internal transition'):
        load_chart(body)


def test_e17_a_targetless_transition_without_type_handles_the_event_in_place():
    cls = load_chart(
        '<datamodel><data id="reason" expr="\'\'"/></datamodel>'
        '<state id="a"><onentry><assign location="reason" expr="\'entered\'"/></onentry>'
        '  <transition event="x"><assign location="reason" expr="\'refused\'"/></transition>'
        '</state>')
    sm = cls()
    rec = Recorder()
    sm.add_listener(rec)
    sm.send('x')
    assert sm.model.reason == 'refused'
    assert rec.events == ['x']


def test_e18_a_data_item_named_state_is_overwritten_by_the_engine():
    cls = load_chart('<datamodel><data id="state" expr="1"/></datamodel>'
                     '<state id="a"><transition event="go" target="b"/></state><state id="b"/>')
    sm = cls()
    sm.send('go')
    assert sm.model.state == 'b'


def test_e23_the_datamodel_is_set_up_only_for_the_first_instance_of_a_class():
    cls = load_chart('<datamodel><data id="n" expr="1"/></datamodel>'
                     '<state id="a"/>')

    class Data:
        pass

    first, second = Data(), Data()
    cls(model=first)
    assert first.n == 1
    cls(model=second)
    assert not hasattr(second, 'n')
