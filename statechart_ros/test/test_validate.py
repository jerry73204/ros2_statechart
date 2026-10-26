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


"""The validator: one passing and at least one failing chart per rule of FORMAT.md 6."""

from charts_util import chart_path, spec_of
import pytest
from statechart_ros.loader import load_chart
from statechart_ros.validate import errors, validate

ACTION = '<ros:action server="dock" type="nav2_msgs/action/DockRobot" goal="goal"/>'
ALL_OUTCOMES = '<ros:outcome status="*" target="a"/>'


def rules(body, **kwargs):
    """Return {rule: [messages]} of the errors of an inline chart."""
    found = {}
    for f in errors(validate(spec_of(body, **kwargs))):
        found.setdefault(f.rule, []).append(f.message)
    return found


def has_docking():
    try:
        from nav2_msgs.action import DockRobot  # noqa: F401
    except ImportError:
        return False
    return True


@pytest.mark.skipif(not has_docking(), reason='the README example docks (Nav2 Jazzy on)')
def test_readme_example_is_valid():
    findings = validate(load_chart(chart_path('readme_example.scxml')))
    assert findings == []


@pytest.mark.parametrize('name', ['minimal.scxml', 'nested_history.scxml'])
def test_sample_charts_have_no_schema_or_structure_errors(name):
    findings = validate(load_chart(chart_path(name)), check_model=False)
    assert [f for f in findings if f.rule in (1, 2, 5, 7, 8, 9)] == []


GOOD = '<state id="a"><transition event="go" target="b"/></state><state id="b">' \
       '<transition event="back" target="a"/></state>'


def test_a_plain_good_chart_has_no_findings():
    assert validate(spec_of(GOOD)) == []


# Rule 1 -------------------------------------------------------------------------------

@pytest.mark.parametrize('body, text', [
    ('<state id="a"><ros:action server="x" type="nav2_msgs/action/DockRobot" srv="y"/>'
     f'{ALL_OUTCOMES}</state>', 'srv'),
    ('<state id="a"><ros:action type="nav2_msgs/action/DockRobot"/>'
     f'{ALL_OUTCOMES}</state>', 'server'),
    ('<ros:action server="x" type="nav2_msgs/action/DockRobot"/><state id="a"/>',
     'belongs in a state'),
    ('<state id="a"><ros:timer period="1" event="t"/></state>', 'directly under <scxml>'),
    ('<state id="a"><ros:frobnicate/></state>', 'unknown element'),
    ('<state id="a"><onentry><log label="x" expr="1" foo="2"/></onentry></state>', 'foo'),
])
def test_rule_1_schema_and_placement(body, text):
    found = rules(body)
    assert 1 in found
    assert any(text in m for m in found[1])


# Rule 2 -------------------------------------------------------------------------------

def test_rule_2_engine_refusal():
    found = rules('<state id="a"><transition event="go" target="nowhere"/></state>')
    assert any('engine refused' in m for m in found[2])


def test_rule_2_unreachable_state():
    found = rules(GOOD + '<state id="orphan"><transition event="x" target="a"/></state>')
    assert any('"orphan" is unreachable' in m for m in found[2])


def test_rule_2_trap_state():
    found = rules('<state id="a"><transition event="go" target="b"/></state><state id="b"/>')
    assert any('"b" is a trap' in m for m in found[2])


def test_rule_2_final_states_and_parent_transitions_are_not_traps():
    found = rules('<state id="p" initial="a"><state id="a"/>'
                  '<transition event="go" target="f"/></state><final id="f"/>', initial='p')
    assert 2 not in found


# Rule 3 -------------------------------------------------------------------------------

def test_rule_3_types_exist():
    found = rules('<ros:subscribe topic="x" type="std_msgs/msg/Nope" event="go"/>' + GOOD)
    assert any('std_msgs/msg/Nope' in m for m in found[3])
    found = rules(f'<state id="a">{ACTION}{ALL_OUTCOMES}</state>'.replace(
        'nav2_msgs/action/DockRobot', 'no_such_pkg/action/Dock'))
    assert any('no_such_pkg/action/Dock' in m for m in found[3])
    assert 3 not in rules('<ros:subscribe topic="x" type="std_msgs/msg/Bool" event="go"/>'
                          '<state id="a"><transition event="go" target="a"/></state>')


# Rule 4 -------------------------------------------------------------------------------

def test_rule_4_model_names():
    found = rules('<ros:subscribe topic="x" type="std_msgs/msg/Bool" event="go" '
                  'when="no_such_guard"/><state id="a"><transition event="go" target="a"/>'
                  '</state>')
    assert any('no method "no_such_guard"' in m for m in found[4])
    found = rules('<state id="a"><transition event="go" cond="nobody_knows" target="a"/>'
                  '</state>')
    assert any('"nobody_knows"' in m for m in found[4])
    found = rules('<ros:subscribe topic="x" type="std_msgs/msg/Bool" event="go" when="ok"/>'
                  '<state id="a"><transition event="go" target="a"/></state>', model=False)
    assert any('has no ros:model' in m for m in found[4])
    found = rules('<state id="a"><transition event="go" cond="not_callable" target="a"/>'
                  '</state>')
    assert 4 not in found


def test_rule_4_run_outputs_and_refusal_conditions_name_model_methods():
    found = rules('<state id="a"><ros:on_entry run="no_such_hook"/>'
                  '<transition event="go" target="a"/></state>')
    assert any('no method "no_such_hook"' in m for m in found[4])
    found = rules('<state id="a"><ros:refuse event="go" cond="nobody_knows" reason="no"/>'
                  '<transition event="go" target="a"/></state>')
    assert any('"nobody_knows"' in m for m in found[4])
    assert rules('<state id="a"><ros:on_entry run="ok"/>'
                 '<ros:refuse event="go" cond="ok" reason="no"/>'
                 '<transition event="go" target="a"/></state>') == {}


def test_rule_4_model_import_failure():
    spec = spec_of('<state id="a"/>', model=False)
    spec.model_class = 'my_robot.nothing:Here'
    assert any(f.rule == 4 and 'cannot import' in f.message for f in validate(spec))


def test_rule_4_conditions_on_datamodel_values_and_in():
    assert 4 not in rules('<datamodel><data id="n" expr="0"/></datamodel>'
                          '<state id="a"><transition event="go" cond="n &gt; 1 and In(\'a\')" '
                          'target="a"/></state>')


# Rule 5 -------------------------------------------------------------------------------

def test_rule_5_statuses_covered():
    found = rules(f'<state id="a">{ACTION}<ros:outcome status="succeeded" target="a"/></state>')
    assert any('"aborted"' in m and '"unavailable"' in m for m in found[5])
    assert 5 not in rules(f'<state id="a">{ACTION}{ALL_OUTCOMES}</state>')
    found = rules(f'<state id="a">{ACTION}<ros:outcome status="exploded" target="a"/>'
                  f'{ALL_OUTCOMES}</state>')
    assert any('"exploded" is not a status' in m for m in found[5])
    found = rules('<state id="a"><ros:outcome status="succeeded" target="a"/></state>')
    assert any('has no invoke' in m for m in found[5])


# Rule 6 -------------------------------------------------------------------------------

SUB = '<ros:subscribe topic="x" type="std_msgs/msg/Bool" event="stop"/>'


def test_rule_6_input_event_handled_everywhere():
    found = rules(SUB + '<state id="a"><transition event="stop" target="b"/></state>'
                  '<state id="b"><transition event="go" target="a"/></state>')
    assert any('"stop"' in m and '{b}' in m for m in found[6])
    assert 6 not in rules(SUB + '<state id="a"><transition event="stop" target="b"/></state>'
                          '<state id="b"><transition event="go" target="a"/>'
                          '<ros:ignore event="stop"/></state>')
    assert 6 not in rules(SUB + '<state id="a"><transition event="stop" target="b"/></state>'
                          '<state id="b"><transition event="go" target="a"/>'
                          '<ros:refuse event="stop" reason="stopped"/></state>')


def test_rule_6_parallel_regions_and_descriptors():
    body = (SUB + '<parallel id="p"><state id="r1" initial="x"><state id="x">'
            '<transition event="stop" target="y"/></state><state id="y">'
            '<transition event="go" target="x"/></state></state>'
            '<state id="r2"><transition event="stop.*"/></state></parallel>')
    assert 6 not in rules(body, initial='p')


def test_rule_6_command_events_of_a_generic_service():
    srv = '<ros:service_server name="~/command" type="statechart_ros_msgs/srv/SendEvent"/>'
    found = rules(srv + GOOD)
    assert any('"go"' in m for m in found[6])
    assert any('"back"' in m for m in found[6])


# Rule 7 -------------------------------------------------------------------------------

def test_rule_7_placement_in_executable_content_and_two_invokes():
    found = rules('<state id="a"><onentry><ros:on_entry publish="x" type="std_msgs/msg/Bool" '
                  'value="1"/></onentry></state>')
    assert any('executable content' in m for m in found[7])
    found = rules(f'<state id="a">{ACTION}<ros:wait_for topic="t" type="std_msgs/msg/Bool"/>'
                  f'{ALL_OUTCOMES}</state>')
    assert any('already has an invoke' in m for m in found[7])


# Rule 8 -------------------------------------------------------------------------------

def test_rule_8_params_match_data():
    found = rules('<ros:param name="speed"/>' + GOOD)
    assert any('"speed"' in m for m in found[8])
    assert 8 not in rules('<datamodel><data id="speed" expr="1.0"/></datamodel>'
                          '<ros:param name="speed"/>' + GOOD)
    # a ros:after delay given by name names a <data> item too
    after = '<state id="a"><ros:after delay="patience" event="t"/>' \
            '<transition event="t" target="a"/></state>'
    assert any('"patience"' in m for m in rules(after)[8])
    assert rules('<datamodel><data id="patience" expr="2.0"/></datamodel>' + after) == {}


# Rule 9 -------------------------------------------------------------------------------

def test_rule_9_restrictions():
    found = rules('<state id="a"><onentry><send event="t" delay="1s"/></onentry>'
                  '<transition event="t" target="a"/></state>')
    assert any('ros:after' in m for m in found[9])
    found = rules('<datamodel><data id="state" expr="1"/><data id="sc_ros_x" expr="1"/>'
                  '<data id="target" expr="1"/></datamodel>' + GOOD)
    assert len(found[9]) == 3
    found = rules('<state id="a-b"><transition event="go" target="a-b"/></state>',
                  initial='a-b')
    assert any('not a Python identifier' in m for m in found[9])


def test_findings_carry_file_line_and_rule():
    spec = load_chart(chart_path('readme_example.scxml'))
    spec.text = spec.text.replace('type="std_msgs/msg/Bool" event="e_stop"',
                                  'type="std_msgs/msg/Bol" event="e_stop"')
    spec.inputs[0].attrs['type'] = 'std_msgs/msg/Bol'
    found = [f for f in validate(spec) if f.rule == 3]
    assert found and found[0].line == 6
    assert str(found[0]).startswith(chart_path('readme_example.scxml') + ':6: [rule 3]')
