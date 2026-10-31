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


"""The interface of a chart: endpoints, the file, comparison (P8)."""

import copy
import os

from charts_util import CHARTS, doc
from statechart_ros import interface
from statechart_ros.kinds import Attr, InvokeKind, NAME, register, SRV_TYPE
from statechart_ros.loader import load_chart

ROBOT = os.path.join(CHARTS, 'interface', 'robot.scxml')


def names(iface, section):
    return [e['name'] for e in iface.get(section, [])]


def test_every_kind_of_endpoint_is_in_the_interface():
    iface = interface.chart_interface(ROBOT)
    assert iface['warnings'] == []
    assert iface['chart'] == 'robot'
    assert iface['subscribes'] == [
        {'name': 'battery', 'type': 'std_msgs/msg/Float32', 'qos': 'sensor'},
        {'name': 'e_stop', 'type': 'std_msgs/msg/Bool', 'qos': 'latched',
         'doc': 'true while the stop button is pressed'},
        {'name': 'odom', 'type': 'std_msgs/msg/Float32', 'qos': 'default', 'doc': 'stopped'},
    ]
    assert iface['publishes'] == [
        {'name': 'lamp', 'type': 'std_msgs/msg/String', 'qos': 'latched'}]
    # a service whose request names the event carries the commands; a fixed event does not
    command, reset = iface['services_served'][1], iface['services_served'][0]
    assert command == {'name': '~/command', 'type': 'statechart_ros_msgs/srv/SendEvent',
                       'commands': ['dock', 'start', 'stop'], 'doc': 'start and stop jobs'}
    assert reset == {'name': 'reset', 'type': 'std_srvs/srv/Trigger'}
    assert names(iface, 'actions_served') == ['run_job']
    # outputs, invokes and the child chart's invoke
    assert iface['services_called'] == [
        {'name': 'arm/hold', 'type': 'std_srvs/srv/Trigger', 'doc': 'hold the arm while driving'},
        {'name': 'charger/enable', 'type': 'std_srvs/srv/Trigger'},
    ]
    assert iface['actions_called'] == [
        {'name': 'drive', 'type': 'example_interfaces/action/Fibonacci'}]
    assert iface['parameters_set'] == [{'name': 'max_speed', 'node': '/controller'}]
    # the timer is the chart's own, not part of the interface
    assert 'tick' not in str(iface)


def test_a_chart_without_ros_endpoints_has_an_empty_interface(tmp_path):
    path = tmp_path / 'plain.scxml'
    path.write_text(doc('<state id="a"/>', model=False))
    iface = interface.chart_interface(str(path))
    assert set(iface) == {'statechart_interface', 'chart', 'warnings'}


def test_two_uses_of_one_topic_with_different_types_warn(tmp_path):
    path = tmp_path / 'clash.scxml'
    path.write_text(doc(
        '<ros:subscribe topic="x" type="std_msgs/msg/Bool" event="x"/>'
        '<state id="a"><ros:wait_for topic="x" type="std_msgs/msg/String"/>'
        '<ros:outcome status="succeeded timeout" target="a"/>'
        '<ros:ignore event="x"/></state>', model=False))
    iface = interface.chart_interface(str(path))
    assert iface['subscribes'] == [{'name': 'x', 'type': 'std_msgs/msg/Bool', 'qos': 'default'}]
    assert iface['warnings'] == [
        'subscribes x: type std_msgs/msg/Bool and std_msgs/msg/String; the interface keeps '
        'std_msgs/msg/Bool']


def test_doc_is_accepted_on_every_element_and_kept_out_of_invoke_attributes(tmp_path):
    spec = load_chart(ROBOT, load_engine=False)
    assert spec.findings == []
    assert 'doc' not in spec.invokes['SETTLE'].attrs
    assert spec.invokes['SETTLE'].doc == 'stopped'


def test_a_user_kind_declares_its_endpoints(tmp_path):
    class Lights(InvokeKind):
        name = 'test/lights'
        attributes = {'service': Attr(NAME, default='lights/set'),
                      'type': Attr(SRV_TYPE, default='std_srvs/srv/SetBool')}
        statuses = ('succeeded',)

        @classmethod
        def endpoints(cls, attrs):
            return [{'kind': 'service', 'name': 'lights/set', 'type': 'std_srvs/srv/SetBool'},
                    {'kind': 'topic', 'name': 'lights/state', 'type': 'std_msgs/msg/Bool',
                     'qos': 'latched'}]

    register(Lights)
    path = tmp_path / 'lights.scxml'
    path.write_text(doc('<state id="a"><ros:invoke kind="test/lights" doc="lamps on"/>'
                        '<ros:outcome status="succeeded" target="a"/></state>', model=False))
    iface = interface.chart_interface(str(path))
    assert iface['services_called'] == [
        {'name': 'lights/set', 'type': 'std_srvs/srv/SetBool', 'doc': 'lamps on'}]
    assert iface['subscribes'] == [
        {'name': 'lights/state', 'type': 'std_msgs/msg/Bool', 'qos': 'latched',
         'doc': 'lamps on'}]


def test_the_default_endpoints_of_a_kind_pair_its_name_and_type():
    from statechart_ros.builtin_invokes import ActionKind, WaitForKind
    assert ActionKind.endpoints({'server': 'go', 'type': 'a/action/B'}) == [
        {'kind': 'action', 'name': 'go', 'type': 'a/action/B'}]
    assert WaitForKind.endpoints({'topic': 't', 'type': 'a/msg/B', 'qos': 'sensor'}) == [
        {'kind': 'topic', 'name': 't', 'type': 'a/msg/B', 'qos': 'sensor'}]


def test_the_file_round_trips(tmp_path):
    iface = interface.chart_interface(ROBOT)
    path = tmp_path / 'robot.interface.yaml'
    path.write_text(interface.dump(iface, ROBOT))
    text = path.read_text()
    assert text.startswith('# The interface of a statechart, generated from robot.scxml')
    assert 'warnings' not in text
    assert interface.compare(interface.load(str(path)), iface) == []


def test_a_file_of_another_version_is_refused(tmp_path):
    path = tmp_path / 'x.yaml'
    path.write_text('statechart_interface: 2\n')
    try:
        interface.load(str(path))
    except ValueError as exc:
        assert 'version 2' in str(exc)
    else:
        raise AssertionError('version 2 accepted')


def test_compare_names_breaking_additive_and_doc_changes():
    old = interface.chart_interface(ROBOT)
    new = copy.deepcopy(old)
    new['subscribes'] = [e for e in new['subscribes'] if e['name'] != 'battery']
    new['subscribes'][0]['qos'] = 'default'                    # e_stop
    new['subscribes'][1]['doc'] = 'zero speed'                 # odom
    new['publishes'].append({'name': 'horn', 'type': 'std_msgs/msg/Empty', 'qos': 'default'})
    new['services_served'][1]['commands'] = ['dock', 'pause', 'stop']
    new['actions_called'][0]['type'] = 'nav2_msgs/action/Spin'
    assert interface.compare(old, new) == [
        ('breaking', 'subscribes battery: removed'),
        ('breaking', 'subscribes e_stop: qos latched -> default'),
        ('doc', 'subscribes odom: doc changed'),
        ('additive', 'publishes horn: added'),
        ('breaking', 'services_served ~/command: command start removed'),
        ('additive', 'services_served ~/command: command pause added'),
        ('breaking', 'actions_called drive: type example_interfaces/action/Fibonacci -> '
                     'nav2_msgs/action/Spin'),
    ]


def test_resolve_follows_the_chart_node_namespace():
    assert interface.resolve('odom') == '/odom'
    assert interface.resolve('odom', '/robot1') == '/robot1/odom'
    assert interface.resolve('/odom', '/robot1') == '/odom'
    assert interface.resolve('~/command', '/robot1', 'mission') == '/robot1/mission/command'


def test_the_interface_test_chart_validates():
    from statechart_ros.validate import errors, validate
    spec = load_chart(ROBOT)
    assert errors(validate(spec)) == []
