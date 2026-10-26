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

"""Outputs built by the model get a message of their type, as on the robot."""

from statechart_ros_testing import chart_under_test

CHART = """<?xml version="1.0"?>
<scxml xmlns="http://www.w3.org/2005/07/scxml"
       xmlns:ros="https://github.com/jerry73204/ros2_statechart/ns/1"
       version="1.0" datamodel="python" initial="a">
  <state id="a">
    <transition event="go" target="b"/>
  </state>
  <state id="b">
    <ros:on_entry publish="hold" type="std_msgs/msg/Bool" message="hold_message"/>
    <ros:on_entry publish="cmd_vel" type="geometry_msgs/msg/Twist" value="{linear: {x: 0.5}}"
                  message="turn"/>
    <ros:on_exit publish="hold" type="std_msgs/msg/Bool" value="false"/>
    <transition event="back" target="a"/>
  </state>
</scxml>
"""


class Model:

    def hold_message(self, msg):
        msg.data = True
        return msg

    def turn(self, msg):
        msg.angular.z = 1.0          # the value= fields are already set
        return msg


def test_a_builder_gets_a_message_of_the_type():
    with chart_under_test(None, text=CHART, model=Model(), check=False) as t:
        t.send('go')
        hold, twist = t.outputs
        assert (hold.target, hold.value) == ('hold', True)
        assert twist.value['linear']['x'] == 0.5 and twist.value['angular']['z'] == 1.0
        t.send('back')
        assert t.outputs[-1].value is False
