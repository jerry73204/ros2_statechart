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


"""Every Nav2 kind once against real Nav2 in simulation (nightly CI job)."""

import json
import os
import threading
import time
import unittest

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
import launch_testing
import launch_testing.actions
import pytest
import rclpy
from rclpy.qos import DurabilityPolicy, QoSProfile
from statechart_ros_msgs.msg import StatechartStatus, Transition
from statechart_ros_msgs.srv import SendEvent

CHART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'all_kinds.scxml')
ORDER = ['TO_POSE', 'THROUGH', 'FOLLOW', 'SPIN', 'BACK_UP', 'WAIT', 'DOCK', 'UNDOCK']


@pytest.mark.launch_test
def generate_test_description():
    share = get_package_share_directory('statechart_ros_nav2')
    return LaunchDescription([
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(share, 'launch',
                                                       'patrol_sim.launch.py')),
            launch_arguments={'fake_battery': 'False', 'chart': CHART}.items()),
        launch_testing.actions.ReadyToTest(),
    ])


class TestAllKindsInSimulation(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        rclpy.init()
        cls.node = rclpy.create_node('all_kinds_test')
        cls.status = None
        cls.transitions = []
        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)

        def on_status(msg):
            cls.status = msg
        cls.node.create_subscription(StatechartStatus, '/patrol/status', on_status, latched)
        cls.node.create_subscription(Transition, '/patrol/transitions',
                                     cls.transitions.append, 100)
        cls.client = cls.node.create_client(SendEvent, '/patrol/command')
        cls.executor = rclpy.executors.MultiThreadedExecutor()
        cls.executor.add_node(cls.node)
        threading.Thread(target=cls.executor.spin, daemon=True).start()
        cls.start = time.monotonic()

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
            time.sleep(0.1)
        return predicate()

    def active(self, *states):
        return self.status is not None and any(s in self.status.active for s in states)

    def outcome(self, state):
        for t in list(self.transitions):
            if t.event == f'done.invoke.{state}':
                data = json.loads(t.data)
                return data.get('status'), data.get('error_name'), data.get('error_msg')
        return None

    def test_every_kind_succeeds(self):
        self.assertTrue(self.wait(lambda: self.active('READY'), 180.0), 'nav2/active')
        self.assertTrue(self.client.wait_for_service(timeout_sec=30.0))
        request = SendEvent.Request()
        request.event = 'go'
        future = self.client.call_async(request)
        self.assertTrue(self.wait(future.done, 30.0))
        self.assertTrue(self.wait(lambda: self.active('DONE', 'FAILED'), 600.0))
        for state in ORDER:
            outcome = self.outcome(state)
            print(f'{state}: {outcome}', flush=True)
            self.assertIsNotNone(outcome, state)
            self.assertEqual(outcome[0], 'succeeded', f'{state}: {outcome}')
        print(f'all kinds in {time.monotonic() - self.start:.1f} s', flush=True)
