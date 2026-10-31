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


"""Slots: options registered by packages, picked by the datamodel (P9); data for children."""

import os
import threading

from charts_util import doc
import pytest
import rclpy
from rclpy.executors import MultiThreadedExecutor
from statechart_ros.loader import load_chart
from statechart_ros.slots import options_for
from statechart_ros.spin import spin
from statechart_ros.validate import errors, validate
from test_node import wait_for
from test_node_composition import send, start_node, stop_node
import yaml

SLOT = 'test.step'
# The options: A succeeds when its data says n == 7, B fails, W waits for `finish`
OPTION_A = ('<datamodel><data id="n" expr="0"/></datamodel>'
            '<state id="CHECK"><transition cond="n == 7" target="succeeded"/>'
            '<transition target="failed"/></state>'
            '<final id="succeeded"/><final id="failed"/>')
OPTION_B = '<state id="S"><transition target="failed"/></state><final id="failed"/>'
OPTION_W = ('<state id="WAITING"><transition event="finish" target="succeeded"/></state>'
            '<final id="succeeded"/>')
OPTION_ODD = '<state id="S"><transition target="odd"/></state><final id="odd"/>'
GO = ''.join(f'<transition event="go_{k.lower()}" target="PROC">'
             f'<assign location="kind" expr="\'{k}\'"/></transition>' for k in 'ABWX')
PARENT = ('<datamodel><data id="kind" expr="\'\'"/></datamodel>'
          '<state id="top" initial="IDLE">'
          '<ros:ignore event="go_a go_b go_w go_x leave finish"/>'
          f'<state id="IDLE">{GO}</state>'
          '<state id="PROC">'
          f'<ros:slot name="{SLOT}" select="kind" data="step_data" '
          'outcomes="succeeded failed" autoforward="true"/>'
          '<ros:outcome status="succeeded" target="OK"/>'
          '<ros:outcome status="failed" target="FAILED"/>'
          '<ros:outcome status="*" cond="note_error" target="ERROR"/>'
          '<transition event="leave" target="IDLE"/></state>'
          + ''.join(f'<state id="{s}"><transition event="leave" target="IDLE"/></state>'
                    for s in ('OK', 'FAILED', 'ERROR'))
          + '</state>')
SERVICE = '<ros:service_server name="~/command" type="statechart_ros_msgs/srv/SendEvent"/>'


class SlotModel:
    """Builders and guards of the parent charts."""

    errors = []

    def __init__(self, node=None):
        pass

    def step_data(self, datamodel):
        return {'n': 7} if datamodel.kind == 'A' else {}

    def child_data(self):
        return {'n': 7}

    def bad_data(self):
        return {'bogus': 1}

    def note_error(self, error_msg):
        SlotModel.errors.append(error_msg)
        return True


def first_state(body):
    """Return the id of the first <state> in a chart body."""
    return body.split('<state id="', 1)[1].split('"', 1)[0]


def register(root, monkeypatch, options, package='fake_steps'):
    """Install charts and their registration into a prefix on AMENT_PREFIX_PATH."""
    share = root / 'share' / package
    (share / 'charts').mkdir(parents=True, exist_ok=True)
    table = {}
    for name, body in options.items():
        (share / 'charts' / f'{name.lower()}.scxml').write_text(
            doc(body, initial=first_state(body), model=False))
        table[name] = f'charts/{name.lower()}.scxml'
    index = root / 'share' / 'ament_index' / 'resource_index'
    (index / 'statechart_slots').mkdir(parents=True, exist_ok=True)
    (index / 'statechart_slots' / package).write_text(yaml.safe_dump({SLOT: table}))
    (index / 'packages').mkdir(parents=True, exist_ok=True)
    (index / 'packages' / package).write_text('')
    paths = [str(root)] + [p for p in os.environ.get('AMENT_PREFIX_PATH', '').split(os.pathsep)
                           if p and p != str(root)]
    monkeypatch.setenv('AMENT_PREFIX_PATH', os.pathsep.join(paths))


@pytest.fixture(scope='module')
def ros():
    rclpy.init()
    executor = MultiThreadedExecutor(num_threads=8)
    threading.Thread(target=spin, args=(executor,), daemon=True).start()
    yield executor
    executor.shutdown()
    rclpy.shutdown()


@pytest.fixture
def parent(tmp_path, monkeypatch):
    register(tmp_path / 'prefix', monkeypatch, {'A': OPTION_A, 'B': OPTION_B, 'W': OPTION_W})
    path = tmp_path / 'parent.scxml'
    path.write_text(doc('<ros:model class="test_node_slots:SlotModel"/>' + SERVICE + PARENT,
                        initial='top', model=False))
    return path


def test_options_come_from_the_ament_index(parent):
    found, problems = options_for(SLOT)
    assert sorted(found) == ['A', 'B', 'W'] and not problems
    assert found['A'].package == 'fake_steps'
    assert found['A'].path.endswith('share/fake_steps/charts/a.scxml')


def test_a_chart_with_a_slot_validates_with_its_options(parent):
    spec = load_chart(str(parent))
    assert not errors(validate(spec)), validate(spec)


def test_the_selected_option_runs_with_its_data_and_ends_the_slot(ros, parent):
    node = start_node(ros, 'slots1', parent)
    try:
        send(node, 'go_a')
        assert wait_for(lambda: node.runner.configuration() == ['top', 'OK'])
        send(node, 'leave')
        send(node, 'go_b')
        assert wait_for(lambda: node.runner.configuration() == ['top', 'FAILED'])
    finally:
        stop_node(ros, node)


def test_an_option_nobody_registered_ends_the_slot_with_an_error(ros, parent):
    SlotModel.errors.clear()
    node = start_node(ros, 'slots2', parent)
    try:
        send(node, 'go_x')
        assert wait_for(lambda: node.runner.configuration() == ['top', 'ERROR'])
        assert SlotModel.errors == ['no option "X" in slot "test.step"']
    finally:
        stop_node(ros, node)


def test_the_running_option_is_seen_inside_its_state_and_stopped_on_leaving(ros, parent):
    node = start_node(ros, 'slots3', parent)
    try:
        structure = node.runner.spec.structure()
        ids = {s['id'] for s in structure['states']}
        assert {'PROC/A/CHECK', 'PROC/B/S', 'PROC/W/WAITING'} <= ids
        send(node, 'go_w')
        assert wait_for(lambda: 'PROC/W/WAITING' in node.runner.snapshot()['active'])
        send(node, 'leave')
        assert node.runner.configuration() == ['top', 'IDLE']
        assert wait_for(lambda: not any(s.startswith('PROC/')
                                        for s in node.runner.snapshot()['active']))
        send(node, 'go_w')
        assert wait_for(lambda: 'PROC/W/WAITING' in node.runner.snapshot()['active'])
        send(node, 'finish')
        assert wait_for(lambda: node.runner.configuration() == ['top', 'OK'])
    finally:
        stop_node(ros, node)


def test_an_option_registered_twice_is_an_error(parent, tmp_path, monkeypatch):
    register(tmp_path / 'other', monkeypatch, {'A': OPTION_A}, package='other_steps')
    spec = load_chart(str(parent))
    messages = [f.message for f in errors(validate(spec))]
    assert any('option "A" is registered by more than one package (fake_steps, other_steps)'
               in m for m in messages), messages


def test_an_option_ending_outside_the_outcomes_is_an_error(parent, tmp_path, monkeypatch):
    register(tmp_path / 'odd', monkeypatch, {'ODD': OPTION_ODD}, package='odd_steps')
    messages = [f.message for f in errors(validate(load_chart(str(parent))))]
    assert any("option ODD ends in odd, not among the slot's outcomes" in m
               for m in messages), messages


def test_a_slot_without_options_is_a_warning(tmp_path):
    path = tmp_path / 'lonely.scxml'
    path.write_text(doc('<ros:model class="test_node_slots:SlotModel"/>' + SERVICE
                        + PARENT.replace(SLOT, 'nobody.registers.this'),
                        initial='top', model=False))
    findings = validate(load_chart(str(path)))
    assert not errors(findings)
    assert any(f.severity == 'warning' and 'has no options' in f.message for f in findings)


CHART_PARENT = ('<state id="top" initial="IDLE"><ros:ignore event="go"/>'
                '<state id="IDLE"><transition event="go" target="PROC"/></state>'
                '<state id="PROC"><ros:chart src="a.scxml" data="{builder}"/>'
                '<ros:outcome status="succeeded" target="OK"/>'
                '<ros:outcome status="failed" target="FAILED"/>'
                '<ros:outcome status="*" cond="note_error" target="ERROR"/></state>'
                '<state id="OK"/><state id="FAILED"/><state id="ERROR"/></state>')


@pytest.mark.parametrize('builder, final', [('child_data', 'OK'), ('bad_data', 'ERROR')])
def test_a_child_chart_starts_with_the_data_of_its_builder(ros, tmp_path, builder, final):
    SlotModel.errors.clear()
    (tmp_path / 'a.scxml').write_text(doc(OPTION_A, initial=first_state(OPTION_A), model=False))
    path = tmp_path / f'parent_{builder}.scxml'
    path.write_text(doc('<ros:model class="test_node_slots:SlotModel"/>' + SERVICE
                        + CHART_PARENT.format(builder=builder), initial='top', model=False))
    node = start_node(ros, f'chart_{builder}', path)
    try:
        send(node, 'go')
        assert wait_for(lambda: node.runner.configuration() == ['top', final])
        if final == 'ERROR':
            assert SlotModel.errors == [
                'data for values the child chart does not declare: bogus']
    finally:
        stop_node(ros, node)
