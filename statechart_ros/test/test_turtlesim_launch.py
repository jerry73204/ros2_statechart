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


"""The turtlesim example runs: launch turtlesim and the chart, send "go", see a lap (P2)."""

import os
import threading
import time
import unittest

from launch import LaunchDescription
from launch_ros.actions import Node
import launch_testing
import launch_testing.actions
import pytest
import rclpy
from rclpy.qos import DurabilityPolicy, QoSProfile
from statechart_ros.spin import spin
from statechart_ros_msgs.msg import StatechartStatus, Transition
from statechart_ros_msgs.srv import SendEvent

HERE = os.path.dirname(os.path.abspath(__file__))

def has_turtlesim_msgs():
    from ament_index_python.packages import get_package_share_directory, PackageNotFoundError
    try:
        get_package_share_directory('turtlesim_msgs')
        return True
    except PackageNotFoundError:
        return False


CHART = os.path.join(HERE, '..', 'examples', 'turtlesim_demo_msgs.scxml'
                     if has_turtlesim_msgs() else 'turtlesim_demo.scxml')


@pytest.mark.launch_test
def generate_test_description():
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    return LaunchDescription([
        Node(package='turtlesim', executable='turtlesim_node', name='turtlesim',
             additional_env=env),
        Node(package='statechart_ros', executable='statechart_node', name='turtle_demo',
             output='screen',
             parameters=[{'chart': os.path.abspath(CHART), 'datamodel_publish': ['laps']}]),
        launch_testing.actions.ReadyToTest(),
    ])


class TestTurtlesimDemo(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        rclpy.init()
        cls.node = rclpy.create_node('turtlesim_demo_test')
        cls.statuses = []
        cls.transitions = []
        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        cls.node.create_subscription(StatechartStatus, '/turtle_demo/status',
                                     cls.statuses.append, latched)
        cls.node.create_subscription(Transition, '/turtle_demo/transitions',
                                     cls.transitions.append, 100)
        cls.executor = rclpy.executors.MultiThreadedExecutor()
        cls.executor.add_node(cls.node)
        cls.thread = threading.Thread(target=spin, args=(cls.executor,), daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.executor.shutdown()
        cls.node.destroy_node()
        rclpy.shutdown()

    def wait(self, predicate, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.05)
        return predicate()

    def test_a_lap(self):
        self.assertTrue(self.wait(lambda: any(s.running and list(s.active) == ['IDLE']
                                              for s in self.statuses), 30.0))
        client = self.node.create_client(SendEvent, '/turtle_demo/command')
        self.assertTrue(client.wait_for_service(timeout_sec=10.0))
        self.assertTrue(self.wait(lambda: True, 1.0))
        request = SendEvent.Request()
        request.event = 'go'
        future = client.call_async(request)
        self.assertTrue(self.wait(future.done, 10.0))
        self.assertTrue(future.result().handled)
        self.assertEqual(list(future.result().configuration), ['RUN', 'TURN'])
        self.assertTrue(self.wait(
            lambda: any(d.key == 'laps' and d.json == '1'
                        for s in self.statuses for d in s.data), 30.0))
        self.assertTrue(self.wait(lambda: list(self.statuses[-1].active) == ['IDLE'], 10.0))
        visited = [list(t.target_configuration) for t in self.transitions]
        for expected in (['RUN', 'TURN'], ['RUN', 'DRIVE'], ['RUN', 'HOME'], ['IDLE']):
            self.assertIn(expected, visited)
        request.event = 'stop'
        future = client.call_async(request)
        self.assertTrue(self.wait(future.done, 10.0))
        self.assertTrue(future.result().handled)


@launch_testing.post_shutdown_test()
class TestShutdown(unittest.TestCase):

    def test_exit_codes(self, proc_info):
        launch_testing.asserts.assertExitCodes(
            proc_info, allowable_exit_codes=[0, -2, -15, 2])
