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


"""Fake Nav2 servers and a harness running a chart in a statechart node."""

import threading
import time

from action_msgs.msg import GoalStatus  # noqa: F401 - re-exported for tests
from nav2_msgs import action as nav2
import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.lifecycle import TransitionCallbackReturn
from rclpy.node import Node
from rclpy.parameter import Parameter
from statechart_ros.node import StatechartNode
from statechart_ros_msgs.srv import SendEvent
from std_srvs.srv import Trigger

ROS_NS = 'https://github.com/jerry73204/ros2_statechart/ns/1'
SERVERS = {
    'navigate_to_pose': nav2.NavigateToPose, 'navigate_through_poses': nav2.NavigateThroughPoses,
    'follow_waypoints': nav2.FollowWaypoints, 'dock_robot': nav2.DockRobot,
    'undock_robot': nav2.UndockRobot, 'spin': nav2.Spin, 'backup': nav2.BackUp,
    'wait': nav2.Wait,
}


def wait_for(predicate, timeout=5.0, period=0.01):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(period)
    return bool(predicate())


class Script:
    """How a fake server answers: duration, final status, result fields."""

    def __init__(self, duration=0.1, status='succeeded', **fields):
        self.duration = duration
        self.status = status
        self.fields = fields


class FakeNav2(Node):
    """One fake action server per Nav2 action, and lifecycle managers' is_active."""

    def __init__(self, name='fake_nav2'):
        super().__init__(name)
        group = ReentrantCallbackGroup()
        self.goals = {k: [] for k in SERVERS}
        self.cancels = {k: 0 for k in SERVERS}
        self.scripts = {k: [] for k in SERVERS}   # consumed in order; default Script()
        self.active = {'lifecycle_manager_navigation': False}
        self.lock = threading.Lock()
        self.servers = []
        for server, action in SERVERS.items():
            self.servers.append(ActionServer(
                self, action, server, execute_callback=self._executor(server, action),
                goal_callback=lambda request: GoalResponse.ACCEPT,
                cancel_callback=self._on_cancel(server), callback_group=group))
        for manager in self.active:
            self.create_service(Trigger, f'{manager}/is_active', self._is_active(manager),
                                callback_group=group)

    def _on_cancel(self, server):
        def callback(handle):
            with self.lock:
                self.cancels[server] += 1
            return CancelResponse.ACCEPT
        return callback

    def _is_active(self, manager):
        def callback(request, response):
            response.success = self.active[manager]
            return response
        return callback

    def _executor(self, server, action):
        def execute(handle):
            with self.lock:
                self.goals[server].append(handle.request)
                script = self.scripts[server].pop(0) if self.scripts[server] else Script()
            feedback = action.Feedback()
            if hasattr(feedback, 'distance_remaining'):
                feedback.distance_remaining = 2.5
            if hasattr(feedback, 'state'):
                feedback.state = 3
            handle.publish_feedback(feedback)
            deadline = time.monotonic() + script.duration
            while time.monotonic() < deadline:
                if handle.is_cancel_requested:
                    handle.canceled()
                    return action.Result()
                time.sleep(0.01)
            result = action.Result()
            for key, value in script.fields.items():
                setattr(result, key, value)
            if script.status == 'succeeded':
                handle.succeed()
            else:
                handle.abort()
            return result
        return execute


class Model:
    """Model of the test charts: records the outcome data."""

    outcomes = []

    def __init__(self, node=None):
        self.node = node

    def record(self, status, error_code, error_name, error_msg, result, **kwargs):
        Model.outcomes.append({'status': status, 'error_code': error_code,
                               'error_name': error_name, 'error_msg': error_msg,
                               'error_source': kwargs.get('error_source', ''),
                               'num_retries': kwargs.get('num_retries')})
        return True

    def low(self, percentage, datamodel):
        return percentage < datamodel.battery_low

    def charged(self, percentage, datamodel):
        return percentage >= datamodel.battery_full


def chart(body, initial='a', model='nav2_util:Model'):
    return ('<?xml version="1.0"?>\n<scxml xmlns="http://www.w3.org/2005/07/scxml" '
            f'xmlns:ros="{ROS_NS}" version="1.0" datamodel="python" initial="{initial}">\n'
            f'<ros:model class="{model}"/>\n{body}\n</scxml>\n')


class Env:
    """rclpy, an executor thread and the fake Nav2."""

    def __init__(self):
        rclpy.init()
        self.executor = MultiThreadedExecutor(num_threads=8)
        self.fake = FakeNav2()
        self.executor.add_node(self.fake)
        self.thread = threading.Thread(target=self.executor.spin, daemon=True)
        self.thread.start()
        self.nodes = []

    def chart_node(self, path, name, params=()):
        overrides = [Parameter('chart', value=str(path)), Parameter('autostart', value=False),
                     Parameter('debug_events', value=True)]
        overrides += [Parameter(k, value=v) for k, v in params]
        node = StatechartNode(name, parameter_overrides=overrides)
        self.executor.add_node(node)
        client_node = Node(f'{name}_client')
        self.executor.add_node(client_node)
        self.nodes += [node, client_node]
        assert node.trigger_configure() == TransitionCallbackReturn.SUCCESS
        assert node.trigger_activate() == TransitionCallbackReturn.SUCCESS
        return ChartHandle(node, client_node, name)

    def close(self):
        for node in self.nodes:
            try:
                if isinstance(node, StatechartNode) and node.runner is not None:
                    node.trigger_deactivate()
                    node.trigger_cleanup()
            except Exception:  # noqa: B902
                pass
            self.executor.remove_node(node)
            node.destroy_node()
        self.executor.shutdown()
        self.fake.destroy_node()
        rclpy.shutdown()


class ChartHandle:

    def __init__(self, node, client_node, name):
        self.node = node
        self.client_node = client_node
        self.client = client_node.create_client(SendEvent, f'/{name}/send_event')

    def config(self):
        return set(self.node.runner.configuration())

    def wait_config(self, expected, timeout=5.0):
        expected = set(expected)
        return wait_for(lambda: expected <= self.config(), timeout)

    def send(self, event):
        assert self.client.wait_for_service(timeout_sec=5.0)
        request = SendEvent.Request()
        request.event = event
        future = self.client.call_async(request)
        assert wait_for(future.done, 10.0)
        return future.result()
