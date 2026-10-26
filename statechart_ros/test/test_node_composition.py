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


"""Child charts in the same node and charts hosted as actions in another (P6)."""

import json
import threading

from action_msgs.msg import GoalStatus
from charts_util import doc
import pytest
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import MultiThreadedExecutor
from rclpy.lifecycle import TransitionCallbackReturn
from rclpy.node import Node
from rclpy.parameter import Parameter
from statechart_ros.loader import load_chart
from statechart_ros.node import StatechartNode
from statechart_ros.spin import spin
from statechart_ros.validate import errors, validate
from statechart_ros_msgs.action import RunStatechart
from statechart_ros_msgs.srv import SendEvent
from test_node import Servers, wait_for

FIB = ('<ros:action server="/fib" type="example_interfaces/action/Fibonacci" '
       'cancel_timeout="3"/>')
CHILD = ('<datamodel><data id="tries" expr="0"/></datamodel>'
         '<state id="STEP1"><onentry><assign location="tries" expr="tries + 1"/></onentry>'
         f'{FIB}<ros:outcome status="succeeded" target="STEP2"/>'
         '<ros:outcome status="*" target="failed"/></state>'
         '<state id="STEP2"><transition event="finish" target="done"/>'
         '<transition event="give_up" target="failed"/></state>'
         '<final id="done"><donedata><param name="tries" expr="tries"/></donedata></final>'
         '<final id="failed"/>')
PARENT = ('<datamodel><data id="code" expr="0"/></datamodel>'
          '<state id="IDLE"><transition event="go" target="PROC"/>'
          '<ros:ignore event="finish"/><ros:ignore event="leave"/></state>'
          '<state id="PROC"><ros:chart src="child.scxml" autoforward="true"/>'
          '<ros:outcome status="done" cond="tried_once" target="OK"/>'
          '<ros:outcome status="done failed" target="BAD"/>'
          '<transition event="leave" target="IDLE"/><ros:refuse event="go" reason="busy"/>'
          '<ros:ignore event="finish"/></state>'
          '<state id="OK"><transition event="go" target="PROC"/><ros:ignore event="finish"/>'
          '<ros:ignore event="leave"/></state>'
          '<state id="BAD"><transition event="go" target="PROC"/><ros:ignore event="finish"/>'
          '<ros:ignore event="leave"/></state>')


class ParentModel:
    """Guards of the parent chart."""

    seen = []

    def __init__(self, node=None):
        pass

    def tried_once(self, result):
        ParentModel.seen.append(result)
        return result == {'tries': 1}


@pytest.fixture(scope='module')
def ros():
    rclpy.init()
    executor = MultiThreadedExecutor(num_threads=8)
    servers = Servers()
    executor.add_node(servers)
    threading.Thread(target=spin, args=(executor,), daemon=True).start()
    yield executor, servers
    executor.shutdown()
    servers.destroy_node()
    rclpy.shutdown()


@pytest.fixture
def charts(tmp_path):
    (tmp_path / 'child.scxml').write_text(doc(CHILD, initial='STEP1', model=False))
    (tmp_path / 'parent.scxml').write_text(
        doc('<ros:model class="test_node_composition:ParentModel"/>'
            '<ros:service_server name="~/command" '
            'type="statechart_ros_msgs/srv/SendEvent"/>' + PARENT,
            initial='IDLE', model=False))
    return tmp_path


def start_node(executor, name, path, **params):
    overrides = [Parameter('chart', value=str(path)), Parameter('autostart', value=False),
                 Parameter('debug_events', value=True)]
    overrides += [Parameter(k, value=v) for k, v in params.items()]
    node = StatechartNode(name, parameter_overrides=overrides)
    executor.add_node(node)
    assert node.trigger_configure() == TransitionCallbackReturn.SUCCESS
    assert node.trigger_activate() == TransitionCallbackReturn.SUCCESS
    return node


def stop_node(executor, node):
    node.trigger_deactivate()
    node.trigger_cleanup()
    executor.remove_node(node)
    node.destroy_node()


def send(node, event):
    return node.runner.send(event)


def test_child_chart_statuses_are_its_final_states(charts):
    spec = load_chart(str(charts / 'parent.scxml'))
    assert errors(validate(spec)) == []
    from statechart_ros.kinds import get_kind
    assert get_kind('ros/chart').statuses_for(spec.invokes['PROC'].attrs) == ('done', 'failed')


def test_child_chart_problems_are_found(tmp_path):
    (tmp_path / 'child.scxml').write_text(doc(
        '<ros:subscribe topic="x" type="std_msgs/msg/Bool" event="x"/>'
        '<state id="a"><transition event="x" target="a"/></state>', model=False))
    (tmp_path / 'self.scxml').write_text(doc(
        '<state id="a"><ros:chart src="self.scxml"/><ros:outcome status="*" target="a"/>'
        '</state>', model=False))
    (tmp_path / 'parent.scxml').write_text(doc(
        '<state id="a"><ros:chart src="child.scxml"/><ros:outcome status="*" target="a"/>'
        '</state><state id="b"><ros:chart src="missing.scxml"/>'
        '<ros:outcome status="*" target="a"/></state>', model=False))
    found = [f.message for f in validate(load_chart(str(tmp_path / 'parent.scxml')))]
    assert any('in a child chart' in m for m in found)
    assert any('no top-level <final>' in m for m in found)
    assert any('missing.scxml' in m for m in found)
    found = [f.message for f in validate(load_chart(str(tmp_path / 'self.scxml')))]
    assert any('may not include itself' in m for m in found)


def test_child_chart_runs_in_the_state_and_its_final_is_the_outcome(ros, charts):
    executor, servers = ros
    servers.goal_duration = 0.2
    ParentModel.seen = []
    node = start_node(executor, 'parent1', charts / 'parent.scxml')
    try:
        structure = node.structure
        ids = {s.id: s for s in structure.states}
        assert ids['PROC/STEP1'].parent == 'PROC' and ids['PROC/STEP1'].chart == 'PROC'
        assert 'PROC/STEP1' in ids['PROC'].children
        assert any(t.source == 'PROC/STEP1' and list(t.targets) == ['PROC/STEP2']
                   for t in structure.transitions)
        send(node, 'go')
        assert wait_for(lambda: 'PROC/STEP2' in node.runner.snapshot()['active'])
        send(node, 'finish')          # forwarded to the child, which ends in "done"
        assert wait_for(lambda: node.runner.configuration() == ['OK'])
        assert ParentModel.seen == [{'tries': 1}]
    finally:
        stop_node(executor, node)


def test_leaving_the_state_stops_the_child_and_cancels_its_invokes(ros, charts):
    executor, servers = ros
    servers.goal_duration = 30.0
    with servers.lock:
        servers.events.clear()
    node = start_node(executor, 'parent2', charts / 'parent.scxml')
    try:
        send(node, 'go')
        assert wait_for(lambda: 'goal 0' in servers.names())
        snap = node.runner.snapshot()
        assert 'PROC/STEP1' in snap['active']
        assert [i['state'] for i in snap['invokes']] == ['PROC', 'PROC/STEP1']
        send(node, 'leave')
        assert node.runner.configuration() == ['IDLE']
        assert wait_for(lambda: 'canceled' in servers.names())
        assert not any(s.startswith('PROC/') for s in node.runner.snapshot()['active'])
        kind = node.runner.kinds['PROC']
        assert not kind.runner.running
    finally:
        servers.goal_duration = 0.3
        stop_node(executor, node)


def test_a_chart_hosted_as_an_action_in_another_node(ros, charts):
    executor, servers = ros
    servers.goal_duration = 0.2
    child_node = start_node(executor, 'child_host', charts / 'child.scxml',
                            run_as_action='~/run')
    parent_path = charts / 'remote_parent.scxml'
    parent_path.write_text(doc(
        '<state id="IDLE"><transition event="go" target="REMOTE"/></state>'
        '<state id="REMOTE"><ros:action server="/child_host/run" '
        'type="statechart_ros_msgs/action/RunStatechart" cancel_timeout="5"/>'
        '<ros:outcome status="succeeded" target="DONE"/><ros:outcome status="*" target="IDLE"/>'
        '<transition event="leave" target="IDLE"/></state>'
        '<state id="DONE"><transition event="go" target="REMOTE"/></state>',
        initial='IDLE', model=False))
    parent = start_node(executor, 'remote_parent', parent_path)
    client_node = Node('remote_client')
    executor.add_node(client_node)
    try:
        assert not child_node.runner.running         # waits for a goal
        send(parent, 'go')
        assert wait_for(lambda: child_node.runner.running)
        assert wait_for(lambda: child_node.runner.configuration() == ['STEP2'])
        client = client_node.create_client(SendEvent, '/child_host/send_event')
        assert client.wait_for_service(timeout_sec=5)
        request = SendEvent.Request()
        request.event = 'finish'
        future = client.call_async(request)
        assert wait_for(future.done)
        assert wait_for(lambda: parent.runner.configuration() == ['DONE'])
        assert not child_node.runner.running

        # Leaving the parent's state cancels the goal; the child exits and cancels its work.
        servers.goal_duration = 30.0
        with servers.lock:
            servers.events.clear()
        send(parent, 'go')
        assert wait_for(lambda: 'goal 0' in servers.names())
        send(parent, 'leave')
        assert wait_for(lambda: not child_node.runner.running)
        assert wait_for(lambda: 'canceled' in servers.names())

        # Initial data in the goal, the result carries the final state and donedata.
        servers.goal_duration = 0.1
        action = ActionClient(client_node, RunStatechart, '/child_host/run')
        assert action.wait_for_server(timeout_sec=5)
        goal = RunStatechart.Goal(data=json.dumps({'tries': 10}))
        send_goal = action.send_goal_async(goal)
        assert wait_for(send_goal.done)
        handle = send_goal.result()
        assert handle.accepted
        assert wait_for(lambda: child_node.runner.configuration() == ['STEP2'])
        future = client.call_async(request)
        assert wait_for(future.done)
        result = handle.get_result_async()
        assert wait_for(result.done)
        assert result.result().status == GoalStatus.STATUS_SUCCEEDED
        assert result.result().result.final_state == 'done'
        assert json.loads(result.result().result.donedata) == {'tries': 11}
        action.destroy()
    finally:
        servers.goal_duration = 0.3
        executor.remove_node(client_node)
        client_node.destroy_node()
        stop_node(executor, parent)
        stop_node(executor, child_node)
