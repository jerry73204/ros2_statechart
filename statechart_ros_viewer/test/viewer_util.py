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


"""A chart node and a viewer in one process, for the viewer tests."""

import threading
import time

import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.lifecycle import TransitionCallbackReturn
from rclpy.parameter import Parameter
from statechart_ros.loader import ROS_NS
from statechart_ros.node import StatechartNode
from statechart_ros.spin import spin
from statechart_ros_viewer.node import ViewerNode

CHART = f"""<scxml xmlns="http://www.w3.org/2005/07/scxml" xmlns:ros="{ROS_NS}"
  version="1.0" datamodel="python" initial="run">
  <datamodel><data id="count" expr="0"/></datamodel>
  <parallel id="run">
    <state id="mode" initial="AUTO">
      <state id="AUTO"><transition event="pause" target="PAUSED"/>
        <ros:ignore event="resume"/></state>
      <state id="PAUSED"><transition event="resume" target="AUTO"/>
        <ros:refuse event="pause" reason="already paused"/></state>
    </state>
    <state id="task" initial="IDLE">
      <state id="IDLE"><transition event="go" target="BUSY"/></state>
      <state id="BUSY"><onentry><assign location="count" expr="count + 1"/></onentry>
        <ros:after delay="30" event="timeout"/>
        <transition event="timeout" target="IDLE"/>
        <transition event="go" target="IDLE"/></state>
    </state>
  </parallel>
</scxml>"""


CHILD = f"""<scxml xmlns="http://www.w3.org/2005/07/scxml" xmlns:ros="{ROS_NS}"
  version="1.0" datamodel="python" initial="STEP1">
  <state id="STEP1"><transition event="next" target="STEP2"/></state>
  <state id="STEP2"><transition event="next" target="done"/></state>
  <final id="done"/>
</scxml>"""

PARENT = f"""<scxml xmlns="http://www.w3.org/2005/07/scxml" xmlns:ros="{ROS_NS}"
  version="1.0" datamodel="python" initial="IDLE">
  <state id="IDLE"><transition event="go" target="PROC"/><ros:ignore event="next"/></state>
  <state id="PROC"><ros:chart src="child.scxml" autoforward="true"/>
    <ros:outcome status="done" target="DONE"/>
    <ros:ignore event="next"/><transition event="go" target="IDLE"/></state>
  <state id="DONE"><transition event="go" target="PROC"/><ros:ignore event="next"/></state>
</scxml>"""


def write_composed(directory):
    """Write the parent and child chart; return the parent's path."""
    (directory / 'child.scxml').write_text(CHILD)
    path = directory / 'demo.scxml'
    path.write_text(PARENT)
    return path


def wait_for(predicate, timeout=10.0, period=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(period)
    return predicate()


class Setup:
    """rclpy, a chart node /demo with debug events, a viewer on a free port."""

    def __init__(self, path, debug=True):
        rclpy.init()
        self.executor = MultiThreadedExecutor()
        self.chart = StatechartNode('demo', parameter_overrides=[
            Parameter('chart', value=str(path)), Parameter('debug_events', value=debug),
            Parameter('datamodel_publish', value=['count'])])
        self.viewer = ViewerNode(parameter_overrides=[
            Parameter('port', value=0), Parameter('address', value='127.0.0.1'),
            Parameter('discovery_period', value=0.2)])
        self.executor.add_node(self.chart)
        self.executor.add_node(self.viewer)
        self.thread = threading.Thread(target=spin, args=(self.executor,), daemon=True)
        self.thread.start()
        assert self.chart.trigger_configure() == TransitionCallbackReturn.SUCCESS
        assert self.chart.trigger_activate() == TransitionCallbackReturn.SUCCESS
        self.url = f'http://127.0.0.1:{self.viewer.port}'

    def close(self):
        try:
            self.chart.trigger_deactivate()
            self.chart.trigger_cleanup()
        except Exception:  # noqa: B902
            pass
        self.executor.shutdown()
        self.viewer.destroy_node()
        self.chart.destroy_node()
        rclpy.shutdown()
