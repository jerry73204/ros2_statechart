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


"""ChartWatcher in a launch test: the turtlesim example of statechart_ros (P4)."""

import os
import threading
import unittest

from ament_index_python.packages import get_package_share_directory, PackageNotFoundError
from launch import LaunchDescription
from launch_ros.actions import Node
import launch_testing
import launch_testing.actions
import pytest
import rclpy
from statechart_ros.spin import spin
from statechart_ros_testing.launch import ChartWatcher


@pytest.mark.launch_test
def generate_test_description():
    try:
        get_package_share_directory('turtlesim_msgs')
        name = 'turtlesim_demo_msgs.scxml'
    except PackageNotFoundError:
        name = 'turtlesim_demo.scxml'
    chart = os.path.join(get_package_share_directory('statechart_ros'), 'examples', name)
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    return LaunchDescription([
        Node(package='turtlesim', executable='turtlesim_node', name='turtlesim',
             additional_env=env),
        Node(package='statechart_ros', executable='statechart_node', name='turtle_demo',
             parameters=[{'chart': chart, 'debug_events': True}]),
        launch_testing.actions.ReadyToTest(),
    ])


class TestWatcher(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        rclpy.init()
        cls.node = rclpy.create_node('watcher_test')
        cls.watcher = ChartWatcher(cls.node, '/turtle_demo')
        cls.executor = rclpy.executors.MultiThreadedExecutor()
        cls.executor.add_node(cls.node)
        threading.Thread(target=spin, args=(cls.executor,), daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.executor.shutdown()
        cls.node.destroy_node()
        rclpy.shutdown()

    def test_wait_send_and_outcomes(self):
        self.assertTrue(self.watcher.wait_for_configuration({'IDLE'}, timeout=30.0))
        response = self.watcher.send('go')
        self.assertTrue(response.handled)
        self.assertTrue(self.watcher.wait_for(lambda: self.watcher.outcomes('HOME'), 30.0))
        self.assertEqual(self.watcher.outcomes('TURN'), ['succeeded'])
        self.assertEqual(self.watcher.outcomes('DRIVE'), ['succeeded'])
        self.assertTrue(self.watcher.wait_for_configuration({'IDLE'}, timeout=10.0))
        ignored = self.watcher.send('stop')
        self.assertTrue(ignored.handled)
