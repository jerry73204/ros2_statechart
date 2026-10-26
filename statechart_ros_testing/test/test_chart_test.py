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


"""The test kit itself: scripted outcomes, pending invokes, time, outputs (P4)."""

import pytest
from statechart_ros.loader import ROS_NS
from statechart_ros_testing import chart_under_test, ChartTestError


def doc(body, initial='a'):
    return (f'<scxml xmlns="http://www.w3.org/2005/07/scxml" xmlns:ros="{ROS_NS}" '
            f'version="1.0" datamodel="python" initial="{initial}">{body}</scxml>')


ACTION = ('<ros:action server="dock" type="example_interfaces/action/Fibonacci"/>'
          '<ros:outcome status="succeeded" target="done"/>'
          '<ros:outcome status="*" target="b"/>')
CHART = doc('<datamodel><data id="tries" expr="0"/></datamodel>'
            '<state id="a"><transition event="go" target="b"/></state>'
            '<state id="b"><onentry><assign location="tries" expr="tries + 1"/></onentry>'
            f'{ACTION}<transition event="stop" target="a"/></state>'
            '<state id="done"><ros:on_entry publish="hold" type="std_msgs/msg/Bool" value="true"/>'
            '<ros:after delay="2" event="timeout"/><transition event="timeout" target="a"/>'
            '</state>')


def test_outcomes_scripted_per_attempt():
    with chart_under_test(None, text=CHART, outcomes={'b': ['aborted', 'rejected',
                                                            'succeeded']}) as t:
        t.send('go')
        assert t.active('done')
        assert t.data.tries == 3
        assert t.finished == [('b', 'aborted'), ('b', 'rejected'), ('b', 'succeeded')]
        assert [(o.action, o.target, o.value) for o in t.outputs] == [
            ('publish', 'hold', True)]


def test_pending_invokes_are_completed_by_the_test():
    with chart_under_test(None, text=CHART) as t:
        t.send('go')
        assert t.pending() == ['b']
        t.complete('b', 'aborted')
        assert t.active('b') and t.data.tries == 2
        t.send('stop')
        assert t.pending() == [] and t.cancelled == ['b']
        with pytest.raises(ChartTestError, match='no pending invoke'):
            t.complete('b')


def test_unknown_status_is_an_error_of_the_test():
    with chart_under_test(None, text=CHART, outcomes={'b': 'exploded'}) as t:
        with pytest.raises(ChartTestError, match='has no status "exploded"'):
            t.send('go')


def test_time_moves_only_when_advanced():
    with chart_under_test(None, text=CHART, outcomes={'b': 'succeeded'}) as t:
        t.send('go')
        assert t.active('done')
        t.advance(1.9)
        assert t.active('done')
        t.advance(0.2)
        assert t.active('a')


def test_an_invalid_chart_is_refused():
    with pytest.raises(ChartTestError, match='not valid'):
        chart_under_test(None, text=doc('<state id="a"><transition event="x" target="z"/>'
                                        '</state>'))


def test_outcome_data_reach_outcome_guards():
    class Model:

        def retryable(self, error_code):
            return error_code == 904

    chart = doc('<ros:model class="builtins:object"/>'
                '<state id="a"><transition event="go" target="b"/></state>'
                '<state id="b">'
                '<ros:action server="dock" type="example_interfaces/action/Fibonacci"/>'
                '<ros:outcome status="aborted" cond="retryable" target="b"/>'
                '<ros:outcome status="*" target="a"/></state>')
    with chart_under_test(None, text=chart, model=Model(), check=False,
                          outcomes={'b': [{'status': 'aborted', 'error_code': 904},
                                          {'status': 'aborted', 'error_code': 1}]}) as t:
        t.send('go')
        assert t.active('a')
        assert t.finished == [('b', 'aborted'), ('b', 'aborted')]


def test_a_child_chart_is_one_invoke_whose_statuses_are_its_finals(tmp_path):
    (tmp_path / 'child.scxml').write_text(doc(
        '<state id="a"><transition event="next" target="ok"/>'
        '<transition event="give_up" target="lost"/></state>'
        '<final id="ok"/><final id="lost"/>'))
    (tmp_path / 'parent.scxml').write_text(doc(
        '<state id="a"><transition event="go" target="b"/></state>'
        '<state id="b"><ros:chart src="child.scxml"/><ros:outcome status="ok" target="c"/>'
        '<ros:outcome status="lost" target="a"/></state>'
        '<state id="c"><transition event="go" target="b"/></state>'))
    with chart_under_test(str(tmp_path / 'parent.scxml')) as t:
        t.send('go')
        assert t.pending() == ['b']
        t.complete('b', 'ok')
        assert t.active('c')
    with chart_under_test(str(tmp_path / 'parent.scxml'), outcomes={'b': 'succeeded'}) as t:
        with pytest.raises(ChartTestError, match='has no status "succeeded" \\(ok, lost\\)'):
            t.send('go')
