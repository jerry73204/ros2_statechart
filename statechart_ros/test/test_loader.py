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


"""The loader: parsing, collecting ros: elements, expansion, structure (P1)."""

import os

from charts_util import chart_path, doc, spec_of
from lxml import etree
import pytest
from statechart_ros.loader import ChartError, load_chart, REFUSAL_VAR, SCXML_NS

ACTION = ('<ros:action server="dock" type="nav2_msgs/action/DockRobot" goal="goal" '
          'feedback="on_feedback" server_timeout="2" cancel_timeout="3"/>')


def _el(xml, path):
    return etree.fromstring(xml.encode()).findall(path, {'s': SCXML_NS})


def test_well_formed_chart_loads_into_an_engine_class():
    spec = spec_of('<state id="a"><transition event="go" target="b"/></state><state id="b"/>')
    assert spec.findings == []
    assert spec.engine_class is not None
    sm = spec.engine_class()
    sm.send('go')
    assert set(sm.configuration_values) == {'sc_ros_root', 'b'}


def test_the_engine_document_wraps_the_states_so_the_node_can_stop_the_chart():
    spec = spec_of('<state id="a"><onexit><assign location="left" expr="True"/></onexit>'
                   '<transition event="go" target="f"/></state><final id="f"/>'
                   '<datamodel><data id="left" expr="False"/></datamodel>')
    sm = spec.engine_class()
    sm.send('sc_ros.stop')
    assert set(sm.configuration_values) == {'sc_ros_stopped'}
    assert sm.model.left is True
    assert sm.is_terminated
    sm = spec.engine_class()
    sm.send('go')
    assert set(sm.configuration_values) == {'sc_ros_stopped'}
    assert 'sc_ros_root' not in spec.plain_doc


def test_not_well_formed_xml_is_a_chart_error():
    with pytest.raises(ChartError, match='not well-formed'):
        load_chart(None, text='<scxml><state></scxml>')


def test_dtd_is_refused():
    text = ('<?xml version="1.0"?><!DOCTYPE scxml [<!ENTITY x "y">]>'
            '<scxml xmlns="http://www.w3.org/2005/07/scxml" version="1.0"/>')
    with pytest.raises(ChartError, match='DTD'):
        load_chart(None, text=text)


def test_root_must_be_scxml():
    with pytest.raises(ChartError, match='root element'):
        load_chart(None, text='<state xmlns="http://www.w3.org/2005/07/scxml"/>')


def test_name_comes_from_the_file():
    spec = load_chart(chart_path('readme_example.scxml'))
    assert spec.name == 'readme_example'


# Declarations and inputs ----------------------------------------------------------

def test_model_and_params():
    spec = spec_of('<datamodel><data id="n" expr="3"/></datamodel><ros:param name="n"/>'
                   '<state id="a"/>')
    assert spec.model_class == 'my_robot.testmodel:TestModel'
    assert spec.params == ['n']
    assert spec.data == {'n': '3'}


def test_param_values_replace_data_defaults():
    spec = spec_of('<datamodel><data id="n" expr="3"/></datamodel><ros:param name="n"/>'
                   '<state id="a"/>', params={'n': 7})
    sm = spec.engine_class()
    assert sm.model.n == 7


def test_inputs_and_their_events():
    spec = spec_of(
        '<ros:subscribe topic="e" type="std_msgs/msg/Bool" event="e_stop" when="msg_true"/>'
        '<ros:timer period="0.5" event="tick"/>'
        '<ros:action_server name="jobs" type="nav2_msgs/action/DockRobot" event="job" '
        '  cancel_event="job_cancel"/>'
        '<ros:service_server name="~/command" type="statechart_ros_msgs/srv/SendEvent"/>'
        '<state id="a"><transition event="go" target="a"/><transition event="e_stop"/>'
        '  <transition event="done.state.a"/></state>')
    assert [i.tag for i in spec.inputs] == ['subscribe', 'timer', 'action_server',
                                            'service_server']
    assert set(spec.input_events()) == {'e_stop', 'tick', 'job', 'job_cancel'}
    assert spec.command_events() == ['go']


def test_unknown_element_and_attributes_are_findings():
    spec = spec_of('<ros:subscrbe topic="x"/><state id="a">'
                   '<ros:action server="x" type="nav2_msgs/action/DockRobot" srv="y"/></state>')
    messages = [f.message for f in spec.findings]
    assert any('unknown element ros:subscrbe' in m for m in messages)
    assert any('has no attribute "srv"' in m for m in messages)


def test_attribute_values_are_checked_by_role():
    spec = spec_of('<ros:timer period="fast" event="t"/>'
                   '<ros:subscribe topic="x" type="std_msgs/Bool" event="e" qos="best"/>'
                   '<state id="a"/>')
    messages = ' '.join(f.message for f in spec.findings)
    assert '"period"' in messages
    assert 'pkg/msg/Name' in messages
    assert 'must be one of default, sensor, latched' in messages


# Invokes and outcomes ---------------------------------------------------------------

def test_each_invoke_element_maps_to_its_kind():
    spec = spec_of(
        f'<state id="a">{ACTION}</state>'
        '<state id="b"><ros:service_call service="s" type="std_srvs/srv/Trigger"/></state>'
        '<state id="c"><ros:wait_for topic="t" type="std_msgs/msg/Bool"/></state>'
        '<state id="d"><ros:chart src="child.scxml"/></state>')
    assert {s: i.kind for s, i in spec.invokes.items()} == {
        'a': 'ros/action', 'b': 'ros/service_call', 'c': 'ros/wait_for', 'd': 'ros/chart'}
    assert spec.invokes['a'].attrs['server'] == 'dock'


def test_ros_invoke_names_a_registered_kind():
    spec = spec_of('<state id="a"><ros:invoke kind="ros/wait_for" topic="t" '
                   'type="std_msgs/msg/Bool"/></state>')
    assert spec.invokes['a'].kind == 'ros/wait_for'
    assert 'kind' not in spec.invokes['a'].attrs
    spec = spec_of('<state id="a"><ros:invoke kind="nope/none"/></state>')
    assert any('unknown invoke kind "nope/none"' in f.message for f in spec.findings)


def test_outcomes_expand_into_done_invoke_transitions_with_generated_conditions():
    spec = spec_of(
        f'<state id="a">{ACTION}'
        '  <ros:outcome status="succeeded" target="b"/>'
        '  <ros:outcome status="aborted canceled" cond="retries_left" target="a"/>'
        '  <ros:outcome status="*" target="c"/>'
        '</state><state id="b"/><state id="c"/>')
    transitions = _el(spec.engine_doc, './/s:state[@id="a"]/s:transition')
    assert [(t.get('event'), t.get('cond'), t.get('target')) for t in transitions] == [
        ('done.invoke.a', 'sc_ros_outcome_a_1', 'b'),
        ('done.invoke.a', 'sc_ros_outcome_a_2', 'a'),
        ('done.invoke.a', 'sc_ros_outcome_a_3', 'c')]
    out = spec.conditions['sc_ros_outcome_a_2']
    assert out.statuses == ('aborted', 'canceled')
    assert out.cond == 'retries_left'
    assert 'ros' not in spec.engine_doc.split('>', 1)[0] or 'xmlns:ros' not in spec.engine_doc


def test_refuse_and_ignore_expand_into_targetless_transitions():
    spec = spec_of('<state id="a"><ros:refuse event="go" reason="it\'s busy"/>'
                   '<ros:ignore event="noise"/></state>')
    transitions = _el(spec.engine_doc, './/s:state[@id="a"]/s:transition')
    assert [t.get('event') for t in transitions] == ['go', 'noise']
    assert all(t.get('target') is None and t.get('type') is None for t in transitions)
    assign = transitions[0].find(f'{{{SCXML_NS}}}assign')
    assert assign.get('location') == REFUSAL_VAR
    sm = spec.engine_class()
    sm.send('go')
    assert sm.model.sc_ros_refusal == "it's busy"


def test_outputs_are_collected_in_document_order():
    spec = spec_of(
        '<state id="a">'
        '<ros:on_entry publish="hold" type="std_msgs/msg/Bool" value="true"/>'
        '<ros:on_entry call="led" type="std_srvs/srv/Trigger" request="request"/>'
        '<ros:on_exit set_param="max_speed" node="controller" value="0.5"/>'
        '</state>')
    outs = spec.outputs['a']
    assert [(o.when, o.action) for o in outs] == [
        ('entry', 'publish'), ('entry', 'call'), ('exit', 'set_param')]


def test_output_needs_exactly_one_action():
    spec = spec_of('<state id="a"><ros:on_entry type="std_msgs/msg/Bool" value="1"/></state>')
    assert any('exactly one of publish, call, set_param' in f.message for f in spec.findings)
    spec = spec_of('<state id="a"><ros:on_entry publish="x" type="std_msgs/msg/Bool"/></state>')
    assert any('needs "value" or "message"' in f.message for f in spec.findings)


def test_after_is_kept_out_of_the_engine_and_becomes_send_and_cancel_in_plain():
    spec = spec_of('<state id="a"><ros:after delay="2.5" event="timeout"/>'
                   '<transition event="timeout" target="b"/></state><state id="b"/>')
    assert spec.afters['a'][0].delay == 2.5
    assert 'send' not in spec.engine_doc
    sends = _el(spec.plain_doc, './/s:state[@id="a"]/s:onentry/s:send')
    assert [(s.get('event'), s.get('delay')) for s in sends] == [('timeout', '2.5s')]
    cancels = _el(spec.plain_doc, './/s:state[@id="a"]/s:onexit/s:cancel')
    assert cancels[0].get('sendid') == sends[0].get('id')


def test_no_ros_elements_remain_after_expansion():
    spec = load_chart(chart_path('readme_example.scxml'))
    assert 'ros:' not in spec.engine_doc
    assert 'ros:' not in spec.plain_doc


# Structure ------------------------------------------------------------------------

def test_structure_of_the_readme_example():
    spec = load_chart(chart_path('readme_example.scxml'))
    structure = spec.structure()
    states = {s['id']: s for s in structure['states']}
    assert structure['initial'] == ['run']
    assert states['run']['kind'] == 'parallel'
    assert states['safety']['children'] == ['OK', 'STOPPED']
    assert states['DOCKING']['invoke'] == {'kind': 'ros/action', 'target': 'dock_robot',
                                           'type': 'nav2_msgs/action/DockRobot'}
    assert states['DOCKED']['outputs'] == ['entry: publish dock/hold true',
                                           'exit: publish dock/hold false']
    assert {'event': 'go', 'reason': 'a docking task is running or done',
            'ignore': False} in states['task']['refuses']
    outcomes = [t for t in structure['transitions'] if t['origin'] == 'outcome']
    assert ('DOCKING', 'succeeded', ['DOCKED']) in [
        (t['source'], t['label'], t['targets']) for t in outcomes]
    assert structure['input_events'] == ['e_stop', 'go', 'resume', 'undock']


def test_history_and_initial_children():
    spec = load_chart(chart_path('nested_history.scxml'))
    assert spec.states['ACTIVE_H'].tag == 'history'
    assert spec.states['ACTIVE_H'].history == 'deep'
    assert spec.states['PATROL'].initial == ('LEG_A',)


def test_export_is_stable():
    first = load_chart(chart_path('readme_example.scxml')).plain_doc
    second = load_chart(None, text=first, name='readme_example').plain_doc
    assert first == second


def test_plain_document_loads_in_the_engine():
    from statemachine.io import load
    for name in ('readme_example.scxml', 'nested_history.scxml', 'minimal.scxml'):
        plain = load_chart(chart_path(name)).plain_doc
        assert load(plain, format='scxml') is not None


def test_package_url_resolves_to_the_share_directory(tmp_path, monkeypatch):
    import ament_index_python.packages as packages
    monkeypatch.setattr(packages, 'get_package_share_directory', lambda pkg: str(tmp_path))
    (tmp_path / 'charts').mkdir()
    (tmp_path / 'charts' / 'x.scxml').write_text(doc('<state id="a"/>', model=False))
    spec = load_chart('package://some_pkg/charts/x.scxml')
    assert spec.path == str(tmp_path / 'charts' / 'x.scxml')


def test_the_two_turtlesim_examples_differ_only_in_the_interface_package():
    examples = os.path.join(os.path.dirname(chart_path('x')), '..', '..', 'examples')
    with open(os.path.join(examples, 'turtlesim_demo.scxml')) as f:
        old = f.read()
    with open(os.path.join(examples, 'turtlesim_demo_msgs.scxml')) as f:
        new = f.read()
    new = new.replace('turtlesim_msgs/', 'turtlesim/').replace(
        'Kilted and Rolling (interfaces in turtlesim_msgs). ', '')
    assert new == old
