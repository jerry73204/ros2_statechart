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


"""Each Nav2 kind against a fake server: goals, outcomes, error names, feedback (P3)."""

import math
import time

from nav2_util import chart, Env, Model, requires_jazzy_nav2, Script, wait_for
import pytest
from statechart_ros.validate import errors, validate

POSES = 'poses:\n  wp_a: {x: 1.0, y: 2.0, yaw: 1.5707963}\n  wp_b: [3.0, -1.0, 0.0]\n'

pytestmark = requires_jazzy_nav2


@pytest.fixture(scope='module')
def env():
    e = Env()
    yield e
    e.close()


@pytest.fixture
def poses_file(tmp_path):
    path = tmp_path / 'poses.yaml'
    path.write_text(POSES)
    return str(path)


def run_kind(env, tmp_path, name, invoke, poses_file=None, data='', params=(), extra=''):
    Model.outcomes = []
    body = (f'<datamodel>{data}</datamodel>' if data else '') + extra + (
        '<state id="a"><transition event="go" target="b"/></state>'
        f'<state id="b">{invoke}'
        '<ros:outcome status="succeeded" cond="record" target="ok"/>'
        '<ros:outcome status="*" cond="record" target="bad"/></state>'
        '<state id="ok"><transition event="go" target="b"/></state>'
        '<state id="bad"><transition event="go" target="b"/></state>')
    path = tmp_path / f'{name}.scxml'
    path.write_text(chart(body))
    from statechart_ros.loader import load_chart
    assert errors(validate(load_chart(str(path)))) == []
    params = list(params) + ([('named_poses', poses_file)] if poses_file else [])
    handle = env.chart_node(path, name, params)
    handle.send('go')
    return handle


def test_navigate_to_pose_fills_the_goal_from_a_named_pose(env, tmp_path, poses_file):
    h = run_kind(env, tmp_path, 'nav_to', '<ros:invoke kind="nav2/navigate_to_pose" '
                 'pose="wp_a" behavior_tree="bt.xml"/>', poses_file)
    assert h.wait_config({'ok'})
    goal = env.fake.goals['navigate_to_pose'][-1]
    assert (goal.pose.pose.position.x, goal.pose.pose.position.y) == (1.0, 2.0)
    assert goal.pose.header.frame_id == 'map'
    assert math.isclose(2 * math.atan2(goal.pose.pose.orientation.z,
                                       goal.pose.pose.orientation.w), 1.5707963, abs_tol=1e-6)
    assert goal.behavior_tree == 'bt.xml'
    assert Model.outcomes[-1]['status'] == 'succeeded'


def test_navigate_to_pose_from_a_datamodel_value(env, tmp_path):
    h = run_kind(env, tmp_path, 'nav_dm', '<ros:invoke kind="nav2/navigate_to_pose" '
                 'pose="goal_pose"/>', data='<data id="goal_pose" expr="None"/>',
                 extra='<ros:param name="goal_pose"/>', params=[('goal_pose', [4.0, 5.0, 0.0])])
    assert h.wait_config({'ok'})
    goal = env.fake.goals['navigate_to_pose'][-1]
    assert (goal.pose.pose.position.x, goal.pose.pose.position.y) == (4.0, 5.0)


def test_navigation_errors_are_named(env, tmp_path, poses_file):
    env.fake.scripts['navigate_to_pose'].append(Script(status='aborted', error_code=208,
                                                       error_msg='no path'))
    h = run_kind(env, tmp_path, 'nav_err', '<ros:invoke kind="nav2/navigate_to_pose" '
                 'pose="wp_b"/>', poses_file)
    assert h.wait_config({'bad'})
    out = Model.outcomes[-1]
    assert out['status'] == 'aborted'
    assert (out['error_code'], out['error_name'], out['error_source']) == (
        208, 'no_valid_path', 'compute_path_to_pose')
    assert out['error_msg'] == 'no path'


def test_navigate_through_poses_and_follow_waypoints(env, tmp_path, poses_file):
    h = run_kind(env, tmp_path, 'through', '<ros:invoke kind="nav2/navigate_through_poses" '
                 'poses="wp_a wp_b"/>', poses_file)
    assert h.wait_config({'ok'})
    goal = env.fake.goals['navigate_through_poses'][-1]
    assert [p.pose.position.x for p in goal.poses] == [1.0, 3.0]
    h = run_kind(env, tmp_path, 'follow', '<ros:invoke kind="nav2/follow_waypoints" '
                 'poses="wp_a wp_b" loops="2"/>', poses_file)
    assert h.wait_config({'ok'})
    goal = env.fake.goals['follow_waypoints'][-1]
    assert [p.pose.position.x for p in goal.poses] == [1.0, 3.0]
    assert goal.number_of_loops == 2


def test_dock_by_id_and_failure_names(env, tmp_path):
    h = run_kind(env, tmp_path, 'dock', '<ros:invoke kind="nav2/dock" dock_id="home_dock" '
                 'staging="false"/>')
    assert h.wait_config({'ok'})
    goal = env.fake.goals['dock_robot'][-1]
    assert goal.use_dock_id and goal.dock_id == 'home_dock'
    assert not goal.navigate_to_staging_pose
    env.fake.scripts['dock_robot'].append(Script(status='aborted', success=False,
                                                 error_code=904, num_retries=3))
    h.send('go')
    assert h.wait_config({'bad'})
    out = Model.outcomes[-1]
    assert (out['error_name'], out['error_source'], out['num_retries']) == (
        'failed_to_detect_dock', 'dock_robot', 3)


def test_dock_success_false_is_aborted(env, tmp_path, poses_file):
    env.fake.scripts['dock_robot'].append(Script(status='succeeded', success=False))
    h = run_kind(env, tmp_path, 'dock_pose', '<ros:invoke kind="nav2/dock" dock_pose="wp_b" '
                 'dock_type="simple_charging_dock"/>', poses_file)
    assert h.wait_config({'bad'})
    goal = env.fake.goals['dock_robot'][-1]
    assert not goal.use_dock_id and goal.dock_pose.pose.position.x == 3.0
    assert goal.dock_type == 'simple_charging_dock'
    assert Model.outcomes[-1]['status'] == 'aborted'


def test_dock_needs_exactly_one_of_id_and_pose(tmp_path):
    from statechart_ros.loader import load_chart
    path = tmp_path / 'bad_dock.scxml'
    path.write_text(chart('<state id="a"><ros:invoke kind="nav2/dock"/>'
                          '<ros:outcome status="*" target="a"/></state>'))
    found = [f.message for f in validate(load_chart(str(path)))]
    assert any('exactly one of dock_id and dock_pose' in m for m in found)


def test_undock_spin_back_up_wait(env, tmp_path):
    h = run_kind(env, tmp_path, 'undock', '<ros:invoke kind="nav2/undock" '
                 'dock_type="simple_charging_dock" max_undocking_time="12"/>')
    assert h.wait_config({'ok'})
    goal = env.fake.goals['undock_robot'][-1]
    assert (goal.dock_type, goal.max_undocking_time) == ('simple_charging_dock', 12.0)
    h = run_kind(env, tmp_path, 'spin', '<ros:invoke kind="nav2/spin" angle="1.57" '
                 'time_allowance="4"/>')
    assert h.wait_config({'ok'})
    goal = env.fake.goals['spin'][-1]
    assert math.isclose(goal.target_yaw, 1.57, rel_tol=1e-6) and goal.time_allowance.sec == 4
    h = run_kind(env, tmp_path, 'backup', '<ros:invoke kind="nav2/back_up" distance="0.3" '
                 'speed="0.05"/>')
    assert h.wait_config({'ok'})
    goal = env.fake.goals['backup'][-1]
    assert math.isclose(goal.target.x, 0.3, rel_tol=1e-6)
    assert math.isclose(goal.speed, 0.05, rel_tol=1e-6)
    h = run_kind(env, tmp_path, 'wait', '<ros:invoke kind="nav2/wait" duration="1.5"/>')
    assert h.wait_config({'ok'})
    goal = env.fake.goals['wait'][-1]
    assert (goal.time.sec, goal.time.nanosec) == (1, 500000000)


def test_feedback_is_summarised_in_the_status(env, tmp_path, poses_file):
    env.fake.scripts['navigate_to_pose'].append(Script(duration=2.0))
    h = run_kind(env, tmp_path, 'nav_fb', '<ros:invoke kind="nav2/navigate_to_pose" '
                 'pose="wp_a"/>', poses_file)
    assert wait_for(lambda: any(inv['feedback'].get('distance_remaining') == 2.5
                                for inv in h.node.runner.snapshot()['invokes']))
    inv = h.node.runner.snapshot()['invokes'][0]
    assert (inv['state'], inv['kind'], inv['target']) == ('b', 'nav2/navigate_to_pose',
                                                          'navigate_to_pose wp_a')


def test_leaving_cancels_the_nav2_goal(env, tmp_path, poses_file):
    env.fake.scripts['navigate_to_pose'].append(Script(duration=5.0))
    before = env.fake.cancels['navigate_to_pose']
    body = ('<state id="a"><transition event="go" target="b"/></state>'
            '<state id="b"><ros:invoke kind="nav2/navigate_to_pose" pose="wp_a"/>'
            '<ros:outcome status="*" target="a"/><transition event="stop" target="a"/></state>')
    path = tmp_path / 'nav_cancel.scxml'
    path.write_text(chart(body))
    h = env.chart_node(path, 'nav_cancel', [('named_poses', poses_file)])
    h.send('go')
    assert wait_for(lambda: h.node.runner.snapshot()['invokes'])
    time.sleep(0.2)
    h.send('stop')
    assert wait_for(lambda: env.fake.cancels['navigate_to_pose'] == before + 1)


def test_active_waits_for_the_lifecycle_manager(env, tmp_path):
    env.fake.active['lifecycle_manager_navigation'] = False
    body = ('<state id="a"><ros:invoke kind="nav2/active" timeout="10" period="0.1"/>'
            '<ros:outcome status="succeeded" target="ready"/>'
            '<ros:outcome status="timeout" target="a"/></state>'
            '<state id="ready"><transition event="x" target="a"/></state>')
    path = tmp_path / 'active.scxml'
    path.write_text(chart(body))
    h = env.chart_node(path, 'active')
    time.sleep(0.5)
    assert h.config() == {'a'}
    env.fake.active['lifecycle_manager_navigation'] = True
    assert h.wait_config({'ready'})
    body = ('<state id="a"><ros:invoke kind="nav2/active" managers="nobody" timeout="0.5" '
            'period="0.1"/><ros:outcome status="succeeded" target="ready"/>'
            '<ros:outcome status="timeout" target="late"/></state>'
            '<state id="ready"><transition event="x" target="a"/></state>'
            '<state id="late"><transition event="x" target="a"/></state>')
    path = tmp_path / 'active2.scxml'
    path.write_text(chart(body))
    h = env.chart_node(path, 'active2')
    assert h.wait_config({'late'})
