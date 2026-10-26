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


"""
The patrol example against real Nav2 in simulation (nightly CI job).

Launches launch/patrol_sim.launch.py (Nav2's TurtleBot3 loopback simulation,
the docking server with one dock, the patrol chart) and drives the scenario:
patrol legs reached by Nav2, low battery, docking and undocking by the
docking server, pause during navigation and resume, cancel. Each nav2 kind
of the chart (navigate_to_pose, dock, undock, active) runs against the real
server here.
"""

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
from sensor_msgs.msg import BatteryState
from statechart_ros.spin import spin
from statechart_ros_msgs.msg import StatechartStatus, Transition
from statechart_ros_msgs.srv import SendEvent


@pytest.mark.launch_test
def generate_test_description():
    share = get_package_share_directory('statechart_ros_nav2')
    return LaunchDescription([
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(share, 'launch',
                                                       'patrol_sim.launch.py')),
            launch_arguments={'fake_battery': 'False'}.items()),
        launch_testing.actions.ReadyToTest(),
    ])


class TestPatrolInSimulation(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        rclpy.init()
        cls.node = rclpy.create_node('patrol_sim_test')
        cls.status = None
        cls.transitions = []
        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)

        def on_status(msg):
            cls.status = msg
        cls.node.create_subscription(StatechartStatus, '/patrol/status', on_status, latched)
        cls.node.create_subscription(Transition, '/patrol/transitions',
                                     cls.transitions.append, 100)
        cls.battery = cls.node.create_publisher(BatteryState, '/battery_state', 10)
        cls.client = cls.node.create_client(SendEvent, '/patrol/command')
        cls.executor = rclpy.executors.MultiThreadedExecutor()
        cls.executor.add_node(cls.node)
        cls.thread = threading.Thread(target=spin, args=(cls.executor,), daemon=True)
        cls.thread.start()
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

    def active(self, state):
        return self.status is not None and state in self.status.active

    def send(self, event):
        self.assertTrue(self.client.wait_for_service(timeout_sec=30.0))
        request = SendEvent.Request()
        request.event = event
        future = self.client.call_async(request)
        self.assertTrue(self.wait(future.done, 30.0))
        return future.result()

    def outcomes(self, state):
        found = []
        for t in list(self.transitions):
            if t.event == f'done.invoke.{state}':
                found.append(json.loads(t.data).get('status'))
        return found

    def battery_level(self, percentage):
        for _ in range(3):
            self.battery.publish(BatteryState(percentage=percentage))
            time.sleep(0.3)

    def log(self, what):
        print(f'[{time.monotonic() - self.start:6.1f} s] {what}', flush=True)

    def test_patrol_dock_pause_cancel(self):
        self.assertTrue(self.wait(lambda: self.active('IDLE'), 180.0),
                        'Nav2 did not become active')
        self.log('Nav2 active, chart IDLE')
        self.battery_level(1.0)
        self.assertTrue(self.send('start').handled)
        self.assertTrue(self.wait(lambda: 'succeeded' in self.outcomes('TO_B'), 180.0),
                        f'leg to wp_b: {self.outcomes("TO_B")}')
        self.log('wp_b reached')
        self.assertTrue(self.wait(lambda: self.active('TO_C'), 10.0))

        self.battery_level(0.2)
        self.assertTrue(self.wait(lambda: self.active('DOCKING'), 10.0))
        self.assertTrue(self.wait(lambda: self.active('CHARGING'), 180.0),
                        f'dock: {self.outcomes("DOCKING")}')
        self.assertEqual(self.outcomes('DOCKING'), ['succeeded'])
        self.log('docked')

        self.battery_level(0.95)
        self.assertTrue(self.wait(lambda: self.active('TO_C'), 120.0),
                        f'undock: {self.outcomes("UNDOCKING")}')
        self.assertEqual(self.outcomes('UNDOCKING'), ['succeeded'])
        self.log('undocked, back on the leg to wp_c')

        time.sleep(2.0)
        self.assertTrue(self.send('pause').handled)
        self.assertTrue(self.wait(lambda: self.active('HOLD'), 10.0))
        self.assertTrue(self.send('resume').handled)
        self.assertTrue(self.wait(lambda: self.active('TO_C'), 10.0))
        self.log('paused and resumed on the same leg')

        self.assertTrue(self.send('cancel').handled)
        self.assertTrue(self.wait(lambda: self.active('IDLE'), 10.0))
        self.log('cancelled')


@launch_testing.post_shutdown_test()
class TestShutdown(unittest.TestCase):

    def test_chart_node_exit_code(self, proc_info):
        for info in proc_info:
            if 'statechart_node' in info.process_name:
                self.assertIn(info.returncode, (0, -2, -15, 2))
