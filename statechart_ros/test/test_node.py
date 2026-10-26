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


"""The node against in-process test servers: inputs, invokes, outputs, lifecycle (P2)."""

import json
import threading
import time

from action_msgs.msg import GoalStatus
from charts_util import doc
from example_interfaces.action import Fibonacci
import pytest
import rclpy
from rclpy.action import ActionClient, ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.lifecycle import TransitionCallbackReturn
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import DurabilityPolicy, QoSProfile
from statechart_ros.node import StatechartNode
from statechart_ros_msgs.msg import StatechartStatus, StatechartStructure, Transition
from statechart_ros_msgs.srv import GetStructure, SendEvent
from std_msgs.msg import Bool, Int32
from std_srvs.srv import Trigger


def wait_for(predicate, timeout=5.0, period=0.01):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(period)
    return bool(predicate())


class Servers(Node):
    """Test servers: a Fibonacci action, a Trigger service, topics, recorders."""

    def __init__(self):
        super().__init__('test_servers')
        group = ReentrantCallbackGroup()
        self.events = []          # (time, what)
        self.lock = threading.Lock()
        self.goal_duration = 0.3
        self.cancel_delay = 0.0
        self.accept = True
        self.trigger_success = True
        self.trigger_calls = 0
        self.received = []
        self.action = ActionServer(
            self, Fibonacci, 'fib', execute_callback=self.execute,
            goal_callback=self.on_goal, cancel_callback=self.on_cancel,
            callback_group=group)
        self.service = self.create_service(Trigger, 'trigger', self.on_trigger,
                                           callback_group=group)
        self.bool_pub = self.create_publisher(Bool, 'flag', 10)
        self.create_subscription(Int32, 'out', lambda m: self.received.append(m.data), 10,
                                 callback_group=group)

    def note(self, what):
        with self.lock:
            self.events.append((time.monotonic(), what))

    def names(self):
        with self.lock:
            return [w for _, w in self.events]

    def on_goal(self, request):
        self.note(f'goal {request.order}')
        return GoalResponse.ACCEPT if self.accept else GoalResponse.REJECT

    def on_cancel(self, handle):
        self.note('cancel requested')
        return CancelResponse.ACCEPT

    def execute(self, handle):
        deadline = time.monotonic() + self.goal_duration
        while time.monotonic() < deadline:
            if handle.is_cancel_requested:
                time.sleep(self.cancel_delay)
                handle.canceled()
                self.note('canceled')
                return Fibonacci.Result()
            time.sleep(0.01)
        handle.succeed()
        self.note('succeeded')
        result = Fibonacci.Result()
        result.sequence = [0, 1, 1]
        return result

    def on_trigger(self, request, response):
        self.trigger_calls += 1
        response.success = self.trigger_success
        response.message = 'ok' if self.trigger_success else 'no'
        return response


class Model:
    """Model of the test charts."""

    def __init__(self, node=None):
        self.node = node
        self.feedback = []

    def goal(self, goal, datamodel):
        goal.order = datamodel.order
        return goal

    def on_feedback(self, feedback):
        self.feedback.append(list(feedback.sequence))

    def success(self, response):
        return response.success

    def is_true(self, msg):
        return msg.data

    def value(self, msg, datamodel):
        msg.data = datamodel.count
        return msg


@pytest.fixture(scope='module')
def ros():
    rclpy.init()
    executor = MultiThreadedExecutor(num_threads=8)
    servers = Servers()
    executor.add_node(servers)
    thread = threading.Thread(target=executor.spin, daemon=True)
    thread.start()
    yield executor, servers
    executor.shutdown()
    servers.destroy_node()
    rclpy.shutdown()


class Harness:
    """A statechart node on a chart written to a file, with recorders of its topics."""

    def __init__(self, ros, tmp_path, body, initial='a', params=(), name='chart'):
        self.executor, self.servers = ros
        path = tmp_path / f'{name}.scxml'
        if '<ros:model' not in body:
            body = '<ros:model class="test_node:Model"/>' + body
        path.write_text(doc(body, initial=initial, model=False))
        overrides = [Parameter('chart', value=str(path)), Parameter('autostart', value=False),
                     Parameter('debug_events', value=True)]
        overrides += [Parameter(k, value=v) for k, v in params]
        self.node = StatechartNode(name, parameter_overrides=overrides)
        self.executor.add_node(self.node)
        self.client_node = Node(f'{name}_client')
        self.executor.add_node(self.client_node)
        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.statuses = []
        self.transitions = []
        self.structures = []
        self.client_node.create_subscription(StatechartStatus, f'/{name}/status',
                                             self.statuses.append, latched)
        self.client_node.create_subscription(StatechartStructure, f'/{name}/structure',
                                             self.structures.append, latched)
        self.client_node.create_subscription(Transition, f'/{name}/transitions',
                                             self.transitions.append, 100)
        self.send_client = self.client_node.create_client(SendEvent, f'/{name}/send_event')

    def up(self):
        assert self.node.trigger_configure() == TransitionCallbackReturn.SUCCESS
        assert self.node.trigger_activate() == TransitionCallbackReturn.SUCCESS
        return self

    def config(self):
        return set(self.node.runner.configuration()) if self.node.runner else set()

    def wait_config(self, expected, timeout=5.0):
        return wait_for(lambda: self.config() == set(expected), timeout)

    def send(self, event, data=None):
        assert self.send_client.wait_for_service(timeout_sec=5.0)
        request = SendEvent.Request()
        request.event = event
        request.data = json.dumps(data) if data else ''
        future = self.send_client.call_async(request)
        assert wait_for(future.done, 10.0)
        return future.result()

    def close(self):
        try:
            if self.node.runner is not None:
                self.node.trigger_deactivate()
            self.node.trigger_cleanup()
        except Exception:  # noqa: B902
            pass
        self.executor.remove_node(self.node)
        self.executor.remove_node(self.client_node)
        self.node.destroy_node()
        self.client_node.destroy_node()


@pytest.fixture
def harness(ros, tmp_path):
    made = []

    def make(body, **kwargs):
        h = Harness(ros, tmp_path, body, **kwargs)
        made.append(h)
        return h.up()
    yield make
    for h in made:
        h.close()


ACTION = ('<ros:action server="/fib" type="example_interfaces/action/Fibonacci" goal="goal" '
          'feedback="on_feedback" cancel_timeout="3"/>')
DATA = '<datamodel><data id="order" expr="3"/><data id="count" expr="0"/></datamodel>'


def test_action_invoke_succeeds_and_routes_its_outcome(harness, ros):
    _, servers = ros
    servers.goal_duration = 0.2
    servers.accept = True
    h = harness(DATA + '<state id="a"><transition event="go" target="b"/></state>'
                f'<state id="b">{ACTION}<ros:outcome status="succeeded" target="ok"/>'
                '<ros:outcome status="*" target="bad"/></state>'
                '<state id="ok"><transition event="go" target="b"/></state>'
                '<state id="bad"><transition event="go" target="b"/></state>', name='act1')
    assert h.send('go').handled
    assert h.wait_config({'ok'})
    assert 'goal 3' in servers.names()


def test_rejected_and_unavailable_actions(harness, ros):
    _, servers = ros
    servers.accept = False
    h = harness(DATA + '<state id="a"><transition event="go" target="b"/>'
                '<transition event="go2" target="c"/></state>'
                f'<state id="b">{ACTION}<ros:outcome status="rejected" target="rej"/>'
                '<ros:outcome status="*" target="a"/></state>'
                '<state id="c"><ros:action server="/nobody" '
                'type="example_interfaces/action/Fibonacci" server_timeout="0.3"/>'
                '<ros:outcome status="unavailable" target="unav"/>'
                '<ros:outcome status="*" target="a"/></state>'
                '<state id="rej"><transition event="go2" target="c"/></state>'
                '<state id="unav"><transition event="go" target="a"/></state>', name='act2')
    try:
        h.send('go')
        assert h.wait_config({'rej'})
        h.send('go2')
        assert h.wait_config({'unav'})
    finally:
        servers.accept = True


def test_leaving_cancels_and_the_next_goal_waits_for_the_confirmation(harness, ros):
    _, servers = ros
    servers.goal_duration = 5.0
    servers.cancel_delay = 0.5
    servers.accept = True
    with servers.lock:
        servers.events.clear()
    h = harness(DATA + '<state id="a"><transition event="go" target="b"/></state>'
                f'<state id="b">{ACTION}<ros:outcome status="*" target="a"/>'
                '<transition event="leave" target="c"/></state>'
                f'<state id="c">{ACTION}<ros:outcome status="*" target="a"/>'
                '<transition event="leave" target="a"/></state>', name='act3')
    try:
        h.send('go')
        assert wait_for(lambda: 'goal 3' in servers.names())
        h.send('leave')
        assert wait_for(lambda: servers.names().count('goal 3') == 2, 5.0)
        with servers.lock:
            events = list(servers.events)
        canceled = next(t for t, w in events if w == 'canceled')
        second = [t for t, w in events if w == 'goal 3'][1]
        assert second >= canceled
        assert second - events[0][0] >= 0.5
    finally:
        servers.goal_duration = 0.3
        servers.cancel_delay = 0.0


def test_service_call_invoke_success_guard_and_failure(harness, ros):
    _, servers = ros
    body = ('<state id="a"><transition event="go" target="b"/></state>'
            '<state id="b"><ros:service_call service="/trigger" type="std_srvs/srv/Trigger" '
            'success="success"/><ros:outcome status="succeeded" target="ok"/>'
            '<ros:outcome status="failed" target="failed"/><ros:outcome status="*" target="a"/>'
            '</state><state id="ok"><transition event="go" target="b"/></state>'
            '<state id="failed"><transition event="go" target="b"/></state>')
    servers.trigger_success = True
    h = harness(body, name='srv1')
    h.send('go')
    assert h.wait_config({'ok'})
    servers.trigger_success = False
    h.send('go')
    assert h.wait_config({'failed'})
    servers.trigger_success = True


def test_service_call_unavailable(harness):
    h = harness('<state id="a"><ros:service_call service="/nobody" type="std_srvs/srv/Trigger" '
                'server_timeout="0.2"/><ros:outcome status="unavailable" target="u"/>'
                '<ros:outcome status="*" target="a"/></state>'
                '<state id="u"><transition event="x" target="a"/></state>', name='srv2')
    assert h.wait_config({'u'})


def test_wait_for_with_guard_and_timeout(harness, ros):
    _, servers = ros
    h = harness('<state id="a"><ros:wait_for topic="/flag" type="std_msgs/msg/Bool" '
                'when="is_true" timeout="5"/><ros:outcome status="succeeded" target="seen"/>'
                '<ros:outcome status="timeout" target="a"/></state>'
                '<state id="seen"><transition event="again" target="t"/></state>'
                '<state id="t"><ros:wait_for topic="/flag" type="std_msgs/msg/Bool" '
                'timeout="0.3"/><ros:outcome status="timeout" target="timed_out"/>'
                '<ros:outcome status="succeeded" target="t"/></state>'
                '<state id="timed_out"><transition event="x" target="a"/></state>', name='wf')
    time.sleep(0.3)
    servers.bool_pub.publish(Bool(data=False))
    time.sleep(0.2)
    assert h.config() == {'a'}
    servers.bool_pub.publish(Bool(data=True))
    assert h.wait_config({'seen'})
    h.send('again')
    assert h.wait_config({'timed_out'})


def test_subscribe_with_guard_timer_and_param(harness, ros):
    _, servers = ros
    h = harness('<datamodel><data id="limit" expr="2"/><data id="ticks" expr="0"/></datamodel>'
                '<ros:param name="limit"/>'
                '<ros:subscribe topic="/flag" type="std_msgs/msg/Bool" event="flag" '
                'when="is_true"/>'
                '<ros:timer period="0.05" event="tick"/>'
                '<state id="a"><transition event="flag" target="b"/>'
                '<transition event="tick"><assign location="ticks" expr="ticks + 1"/>'
                '</transition></state>'
                '<state id="b"><ros:ignore event="flag"/><ros:ignore event="tick"/>'
                '<transition event="x" target="a"/></state>',
                params=[('limit', 5)], name='inp')
    assert h.node.runner.model.limit == 5
    assert wait_for(lambda: h.node.runner.model.ticks >= 3)
    servers.bool_pub.publish(Bool(data=False))
    time.sleep(0.2)
    assert h.config() == {'a'}
    servers.bool_pub.publish(Bool(data=True))
    assert h.wait_config({'b'})


def test_outputs_publish_call_and_set_param(harness, ros):
    _, servers = ros
    servers.received.clear()
    calls = servers.trigger_calls
    h = harness('<datamodel><data id="count" expr="41"/></datamodel>'
                '<state id="a"><transition event="go" target="b"/></state>'
                '<state id="b"><ros:on_entry publish="/out" type="std_msgs/msg/Int32" value="7"/>'
                '<ros:on_entry publish="/out" type="std_msgs/msg/Int32" message="value"/>'
                '<ros:on_entry call="/trigger" type="std_srvs/srv/Trigger"/>'
                '<ros:on_exit set_param="status_rate_max" value="10.0"/>'
                '<transition event="back" target="a"/></state>', name='outs')
    time.sleep(0.3)
    h.send('go')
    assert wait_for(lambda: servers.received[-2:] == [7, 41])
    assert wait_for(lambda: servers.trigger_calls == calls + 1)
    h.send('back')
    assert h.node.get_parameter('status_rate_max').value == 10.0


def test_introspection_topics_and_services(harness):
    h = harness('<ros:service_server name="~/command" type="statechart_ros_msgs/srv/SendEvent"/>'
                '<state id="a"><transition event="go" target="b"/><ros:ignore event="back"/>'
                '</state><state id="b"><ros:refuse event="go" reason="already going"/>'
                '<transition event="back" target="a"/></state>', name='intro')
    assert wait_for(lambda: h.structures)
    structure = h.structures[-1]
    assert [s.id for s in structure.states] == ['a', 'b']
    assert structure.debug_events
    assert set(structure.input_events) == {'go', 'back'}
    result = h.send('go')
    assert result.handled and list(result.configuration) == ['b']
    result = h.send('go')
    assert not result.handled and result.refusal == 'already going'
    assert wait_for(lambda: any(s.active == ['b'] and s.refusal == 'already going'
                                for s in h.statuses))
    assert wait_for(lambda: [t.event for t in h.transitions][-2:] == ['go', 'go'])
    assert h.transitions[-2].taken == ['a -> b']
    client = h.client_node.create_client(GetStructure, '/intro/get_structure')
    assert client.wait_for_service(timeout_sec=5.0)
    future = client.call_async(GetStructure.Request())
    assert wait_for(future.done)
    assert future.result().structure.name == structure.name
    command = h.client_node.create_client(SendEvent, '/intro/command')
    assert command.wait_for_service(timeout_sec=5.0)
    request = SendEvent.Request()
    request.event = 'back'
    future = command.call_async(request)
    assert wait_for(future.done)
    assert future.result().handled
    assert h.config() == {'a'}


def test_deactivate_cancels_invokes_and_activate_restarts(harness, ros):
    _, servers = ros
    servers.goal_duration = 5.0
    with servers.lock:
        servers.events.clear()
    h = harness(DATA + '<state id="a"><transition event="go" target="b"/></state>'
                f'<state id="b">{ACTION}<ros:outcome status="*" target="a"/></state>',
                name='life')
    try:
        h.send('go')
        assert wait_for(lambda: 'goal 3' in servers.names())
        assert h.node.trigger_deactivate() == TransitionCallbackReturn.SUCCESS
        assert h.config() == set()
        assert wait_for(lambda: 'canceled' in servers.names())
        assert h.node.trigger_activate() == TransitionCallbackReturn.SUCCESS
        assert h.config() == {'a'}
        assert h.node.runner.engine_threads == {h.node.runner._worker_ident}
    finally:
        servers.goal_duration = 0.3


def test_action_server_input(harness, ros):
    executor, _ = ros
    h = harness('<ros:model class="test_node:Model"/>'
                '<ros:action_server name="~/run" type="example_interfaces/action/Fibonacci" '
                'event="job" result_on="finish" cancel_event="abort"/>'
                '<state id="a"><transition event="job" target="busy"/>'
                '<ros:ignore event="abort"/></state>'
                '<state id="busy"><ros:refuse event="job" reason="busy"/>'
                '<transition event="finish" target="a"/><transition event="abort" target="a"/>'
                '</state>', name='asrv')
    client = ActionClient(h.client_node, Fibonacci, '/asrv/run')
    assert client.wait_for_server(timeout_sec=5.0)
    send = client.send_goal_async(Fibonacci.Goal(order=1))
    assert wait_for(send.done)
    handle = send.result()
    assert handle.accepted
    assert h.wait_config({'busy'})
    result = handle.get_result_async()
    h.send('finish')
    assert wait_for(result.done)
    assert result.result().status == GoalStatus.STATUS_SUCCEEDED
    send = client.send_goal_async(Fibonacci.Goal(order=1))
    assert wait_for(send.done)
    handle = send.result()
    assert h.wait_config({'busy'})
    cancel = handle.cancel_goal_async()
    assert wait_for(cancel.done)
    result = handle.get_result_async()
    assert wait_for(result.done)
    assert result.result().status == GoalStatus.STATUS_CANCELED
    assert h.wait_config({'a'})
    client.destroy()


def test_an_invalid_chart_fails_configure(ros, tmp_path):
    executor, _ = ros
    path = tmp_path / 'bad.scxml'
    path.write_text(doc('<state id="a"><transition event="go" target="nowhere"/></state>',
                        model=False))
    node = StatechartNode('bad', parameter_overrides=[Parameter('chart', value=str(path))])
    try:
        assert node.trigger_configure() == TransitionCallbackReturn.FAILURE
        assert node.runner is None
    finally:
        node.destroy_node()
