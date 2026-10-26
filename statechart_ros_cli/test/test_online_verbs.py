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


"""list, show, echo and send against a running chart (P5)."""

import os
import subprocess
import threading
import time

import pytest
import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.lifecycle import TransitionCallbackReturn
from rclpy.parameter import Parameter
from statechart_ros.loader import ROS_NS
from statechart_ros.node import StatechartNode
from statechart_ros.spin import spin

CHART = f"""<scxml xmlns="http://www.w3.org/2005/07/scxml" xmlns:ros="{ROS_NS}"
  version="1.0" datamodel="python" initial="run">
  <datamodel><data id="count" expr="0"/></datamodel>
  <state id="run" initial="a">
    <state id="a"><transition event="go" target="b"/>
      <ros:refuse event="back" reason="already at a"/></state>
    <state id="b"><onentry><assign location="count" expr="count + 1"/></onentry>
      <transition event="back" target="a"/><ros:ignore event="go"/></state>
  </state>
</scxml>"""


@pytest.fixture(scope='module')
def chart(tmp_path_factory):
    path = tmp_path_factory.mktemp('cli') / 'cli_chart.scxml'
    path.write_text(CHART)
    rclpy.init()
    executor = MultiThreadedExecutor()
    node = StatechartNode('cli_chart', parameter_overrides=[
        Parameter('chart', value=str(path)), Parameter('debug_events', value=True),
        Parameter('datamodel_publish', value=['count'])])
    executor.add_node(node)
    thread = threading.Thread(target=spin, args=(executor,), daemon=True)
    thread.start()
    assert node.trigger_configure() == TransitionCallbackReturn.SUCCESS
    assert node.trigger_activate() == TransitionCallbackReturn.SUCCESS
    yield node
    node.trigger_deactivate()
    node.trigger_cleanup()
    executor.shutdown()
    node.destroy_node()
    rclpy.shutdown()


def ros2(*args, timeout=60):
    return subprocess.run(['ros2', 'statechart', *args], capture_output=True, text=True,
                          check=False, timeout=timeout, env=dict(os.environ))


def test_list(chart):
    result = ros2('list', '--wait', '2')
    assert result.returncode == 0, result.stderr
    assert '/cli_chart' in result.stdout.split()


def test_send_and_show(chart):
    result = ros2('send', '/cli_chart', 'go')
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'handled' in result.stdout
    assert 'configuration: run, b' in result.stdout
    result = ros2('send', '/cli_chart', 'back')
    assert result.returncode == 0
    result = ros2('send', '/cli_chart', 'back')
    assert result.returncode == 2
    assert 'refused: already at a' in result.stdout
    result = ros2('show', '/cli_chart')
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert '* run' in lines
    assert '  * a' in lines
    assert '    b' in lines
    assert 'last event: back (refused: already at a)' in result.stdout
    assert 'count = 1' in result.stdout


def test_send_bad_json(chart):
    result = ros2('send', '/cli_chart', 'go', '{not json')
    assert result.returncode == 1
    assert 'error' in result.stdout


def test_echo(chart):
    echo = subprocess.Popen(['ros2', 'statechart', 'echo', '/cli_chart', '-n', '2',
                             '--timeout', '30'], stdout=subprocess.PIPE, text=True)
    time.sleep(2.0)
    assert ros2('send', '/cli_chart', 'go').returncode == 0
    assert ros2('send', '/cli_chart', 'back').returncode == 0
    out, _ = echo.communicate(timeout=40)
    lines = out.strip().splitlines()
    assert len(lines) == 2
    assert lines[0].endswith('go: a -> b')
    assert lines[1].endswith('back: b -> a')


def test_show_unknown_chart():
    result = ros2('show', '/nobody', '--timeout', '1')
    assert result.returncode == 1
