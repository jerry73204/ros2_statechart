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


"""The patrol example covered by a scenario and by property tests (P4)."""

import os

from hypothesis import HealthCheck, settings, strategies as st
from hypothesis.stateful import run_state_machine_as_test
import pytest
from statechart_ros_testing import run_scenario
from statechart_ros_testing.properties import chart_machine, InvariantViolated

HERE = os.path.dirname(os.path.abspath(__file__))


def patrol_runs_here():
    """Check for statechart_ros_nav2 and Nav2 with docking (Jazzy on)."""
    try:
        import statechart_ros_nav2.kinds  # noqa: F401
        from nav2_msgs.action import DockRobot  # noqa: F401
    except ImportError:
        return False
    return True


pytestmark = pytest.mark.skipif(not patrol_runs_here(),
                                reason='needs statechart_ros_nav2 and Nav2 docking')
PATROL = os.path.join(HERE, '..', '..', 'statechart_ros_nav2', 'examples', 'patrol.scxml')
LEGS = {'TO_A', 'TO_B', 'TO_C'}
MOVING = LEGS | {'DOCKING', 'UNDOCKING'}
PARAMS = {'battery_low': 0.3, 'battery_full': 0.9}
BATTERY = {'battery': st.fixed_dictionaries(
    {'percentage': st.sampled_from([0.05, 0.25, 0.5, 0.95])})}


def still_while_paused_or_stopped(config):
    """Never send the robot anywhere while paused or stopped."""
    held = 'PAUSED' in config or 'STOPPED' in config
    return not (held and MOVING & config)


def patrols_only_with_power(config):
    """Run no patrol leg on a low battery."""
    return not (LEGS & config and 'POWER_LOW' in config)


def one_task_state(config):
    """Keep the task region in exactly one of its top states."""
    return len({'WAIT_NAV2', 'IDLE', 'WORK', 'HOLD'} & config) == 1


def charging_output_follows_charging(config, outputs):
    """Publish on 'charging' whether the robot is CHARGING."""
    values = [o.value for o in outputs if o.target == 'charging']
    return (values[-1] if values else False) == ('CHARGING' in config)


INVARIANTS = [still_while_paused_or_stopped, patrols_only_with_power, one_task_state,
              charging_output_follows_charging]
SETTINGS = settings(max_examples=60, stateful_step_count=40, deadline=None,
                    suppress_health_check=list(HealthCheck), derandomize=True)


def test_patrol_scenario():
    if not os.path.exists(PATROL):
        pytest.skip('the patrol example is not in the source tree')
    run_scenario(os.path.join(HERE, 'scenarios', 'patrol.yaml'))


def test_patrol_properties():
    if not os.path.exists(PATROL):
        pytest.skip('the patrol example is not in the source tree')
    machine = chart_machine(PATROL, INVARIANTS, event_data=BATTERY, params=PARAMS,
                            outcomes={'WAIT_NAV2': ['succeeded']})
    run_state_machine_as_test(machine, settings=SETTINGS)


def test_a_broken_patrol_is_caught(tmp_path):
    if not os.path.exists(PATROL):
        pytest.skip('the patrol example is not in the source tree')
    with open(PATROL) as f:
        text = f.read()
    hold = """<transition cond="In('PAUSED') or In('STOPPED')" target="HOLD"/>"""
    assert hold in text
    broken = tmp_path / 'patrol_broken.scxml'
    broken.write_text(text.replace(hold, ''))
    machine = chart_machine(str(broken), INVARIANTS, event_data=BATTERY, params=PARAMS,
                            outcomes={'WAIT_NAV2': ['succeeded']})
    with pytest.raises(InvariantViolated, match='still_while_paused_or_stopped'):
        run_state_machine_as_test(machine, settings=SETTINGS)
