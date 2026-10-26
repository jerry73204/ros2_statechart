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
A battery for the patrol example: it drains while driving and charges on a dock.

Publishes ``sensor_msgs/BatteryState`` on ``battery_state``; ``percentage``
falls by ``drain`` per second, and rises by ``charge_rate`` per second while
the last message on ``charging`` (``std_msgs/Bool``) was true.
"""

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import BatteryState
from std_msgs.msg import Bool


class FakeBattery(Node):

    def __init__(self):
        super().__init__('fake_battery')
        self.percentage = float(self.declare_parameter('initial', 1.0).value)
        self.drain = float(self.declare_parameter('drain', 0.01).value)
        self.charge_rate = float(self.declare_parameter('charge_rate', 0.1).value)
        period = float(self.declare_parameter('period', 0.5).value)
        self.charging = False
        self.publisher = self.create_publisher(BatteryState, 'battery_state', 10)
        self.create_subscription(Bool, 'charging', self.on_charging, 10)
        self.create_timer(period, lambda: self.tick(period))

    def on_charging(self, msg):
        self.charging = msg.data

    def tick(self, period):
        rate = self.charge_rate if self.charging else -self.drain
        self.percentage = min(1.0, max(0.0, self.percentage + rate * period))
        msg = BatteryState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.percentage = self.percentage
        msg.power_supply_status = (BatteryState.POWER_SUPPLY_STATUS_CHARGING if self.charging
                                   else BatteryState.POWER_SUPPLY_STATUS_DISCHARGING)
        msg.present = True
        self.publisher.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = FakeBattery()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
