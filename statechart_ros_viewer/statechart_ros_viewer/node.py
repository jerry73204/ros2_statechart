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
``viewer``: a node serving the web page that shows running charts.

Parameters: ``port`` (default 8095), ``address`` (default ``0.0.0.0``, every
interface of the robot), ``history`` (transitions kept per chart, default
1000), ``discovery_period`` (seconds between looks for new charts).
"""

import rclpy
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from statechart_ros.spin import spin
from statechart_ros_viewer.server import ViewerServer
from statechart_ros_viewer.tracker import ChartTracker


class ViewerNode(Node):
    """Discover charts and serve the viewer."""

    def __init__(self, **kwargs):
        super().__init__('statechart_viewer', **kwargs)
        self.declare_parameter('port', 8095)
        self.declare_parameter('address', '0.0.0.0')
        self.declare_parameter('history', 1000)
        self.declare_parameter('discovery_period', 1.0)
        self.tracker = ChartTracker(self, int(self.get_parameter('history').value))
        port = int(self.get_parameter('port').value)
        address = self.get_parameter('address').value
        self.server = ViewerServer(address, port, self.tracker, self.get_logger())
        self.port = self.server.server_address[1]
        self.server.start()
        self.tracker.discover()
        self.create_timer(float(self.get_parameter('discovery_period').value),
                          self.tracker.discover)
        self.get_logger().info(f'statechart viewer on http://{address}:{self.port}/')

    def destroy_node(self):
        self.server.stop()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = ViewerNode()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        spin(executor)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
