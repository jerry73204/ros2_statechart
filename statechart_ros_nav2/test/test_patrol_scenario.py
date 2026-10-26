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
The patrol example's scenario against fake Nav2 servers (P3).

Patrol, low battery, dock, charge, undock and continue the same leg; pause
during navigation and resume the same goal; emergency stop; cancel ends the
task.
"""

import os

from nav2_util import Env, Script, wait_for
import pytest
from rclpy.qos import QoSProfile
from sensor_msgs.msg import BatteryState
from statechart_ros.loader import load_chart
from statechart_ros.validate import validate
from std_msgs.msg import Bool

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLES = os.path.join(HERE, '..', 'examples')
CHART = os.path.join(EXAMPLES, 'patrol.scxml')
POSES = os.path.join(EXAMPLES, 'sandbox_poses.yaml')
WP = {'wp_a': (-2.0, -0.5), 'wp_b': (0.55, -1.65), 'wp_c': (0.55, 1.65)}


@pytest.fixture(scope='module')
def env():
    e = Env()
    yield e
    e.close()


def xy(goal):
    return (round(goal.pose.pose.position.x, 2), round(goal.pose.pose.position.y, 2))


def test_the_example_chart_is_valid():
    assert validate(load_chart(CHART)) == []


def test_patrol_scenario(env):
    fake = env.fake
    fake.active['lifecycle_manager_navigation'] = True
    params = [('named_poses', POSES), ('battery_low', 0.3), ('battery_full', 0.9)]
    h = env.chart_node(CHART, 'patrol', params)
    battery = h.client_node.create_publisher(BatteryState, '/battery_state', 10)
    e_stop = h.client_node.create_publisher(Bool, '/e_stop', 10)
    charging = []
    h.client_node.create_subscription(Bool, '/charging', lambda m: charging.append(m.data),
                                      QoSProfile(depth=10))

    def publish_battery(percentage):
        battery.publish(BatteryState(percentage=percentage))

    def nav_goals():
        with fake.lock:
            return list(fake.goals['navigate_to_pose'])

    def leaf():
        task = [s for s in h.node.runner.configuration()
                if s in ('WAIT_NAV2', 'IDLE', 'HOLD', 'TO_A', 'TO_B', 'TO_C', 'DOCKING',
                         'CHARGING', 'UNDOCKING', 'DOCK_FAILED')]
        return task[0] if task else None

    # Patrol: legs in order, each a navigate_to_pose goal to its named pose.
    assert wait_for(lambda: battery.get_subscription_count() > 0)
    publish_battery(1.0)
    assert wait_for(lambda: h.config() >= {'IDLE', 'AUTO', 'CLEAR', 'POWER_OK'}, 10.0)
    for _ in range(3):
        fake.scripts['navigate_to_pose'].append(Script(duration=0.2))
    fake.scripts['navigate_to_pose'].append(Script(duration=30.0))
    result = h.send('start')
    assert result.handled
    assert wait_for(lambda: len(nav_goals()) >= 4, 10.0)
    legs = [WP['wp_a'], WP['wp_b'], WP['wp_c'], WP['wp_a']]
    assert [xy(g) for g in nav_goals()[:4]] == legs
    assert h.node.runner.model.laps == 1
    assert leaf() == 'TO_A'
    refused = h.send('start')
    assert not refused.handled and refused.refusal == 'a patrol is running'

    # Low battery: the navigation goal is cancelled and the robot docks.
    cancels = fake.cancels['navigate_to_pose']
    fake.scripts['dock_robot'].append(Script(duration=0.2))
    publish_battery(0.2)
    assert wait_for(lambda: leaf() == 'CHARGING', 10.0)
    assert fake.cancels['navigate_to_pose'] == cancels + 1
    assert fake.goals['dock_robot'][-1].dock_id == 'home_dock'
    assert wait_for(lambda: charging and charging[-1] is True)

    # Charged: undock, then back to the leg that was interrupted.
    fake.scripts['undock_robot'].append(Script(duration=0.2))
    fake.scripts['navigate_to_pose'].append(Script(duration=30.0))
    publish_battery(0.95)
    assert wait_for(lambda: leaf() == 'TO_A', 10.0)
    assert wait_for(lambda: charging[-1] is False)
    assert len(fake.goals['undock_robot']) == 1
    assert wait_for(lambda: len(nav_goals()) == 5)
    assert xy(nav_goals()[-1]) == WP['wp_a']

    # Pause during navigation: the goal is cancelled; resume sends the same goal again.
    cancels = fake.cancels['navigate_to_pose']
    fake.scripts['navigate_to_pose'].append(Script(duration=30.0))
    assert h.send('pause').handled
    assert wait_for(lambda: leaf() == 'HOLD')
    assert wait_for(lambda: fake.cancels['navigate_to_pose'] == cancels + 1)
    assert not h.send('start').handled
    assert h.send('resume').handled
    assert wait_for(lambda: leaf() == 'TO_A')
    assert wait_for(lambda: len(nav_goals()) == 6)
    assert xy(nav_goals()[-1]) == xy(nav_goals()[-2])

    # Emergency stop holds the task the same way; release resumes it.
    fake.scripts['navigate_to_pose'].append(Script(duration=30.0))
    e_stop.publish(Bool(data=True))
    assert wait_for(lambda: leaf() == 'HOLD')
    e_stop.publish(Bool(data=False))
    assert wait_for(lambda: leaf() == 'TO_A')
    assert wait_for(lambda: len(nav_goals()) == 7)

    # Cancel ends the task and cancels the goal.
    cancels = fake.cancels['navigate_to_pose']
    assert h.send('cancel').handled
    assert wait_for(lambda: leaf() == 'IDLE')
    assert wait_for(lambda: fake.cancels['navigate_to_pose'] == cancels + 1)
    refused = h.send('cancel')
    assert not refused.handled and refused.refusal == 'no task'
    assert h.node.runner.engine_threads == {h.node.runner._worker_ident}
