# Nav2 with statecharts (`statechart_ros_nav2`)

A chart drives Nav2 through its actions; recoveries, replanning and the
docking procedure stay in Nav2 (DESIGN.md section 8). This package adds one
invoke kind per Nav2 action, so a state says what it wants in attributes and
needs no goal-building code:

```xml
<state id="TO_KITCHEN">
  <ros:invoke kind="nav2/navigate_to_pose" pose="kitchen"/>
  <ros:outcome status="succeeded" target="SERVE"/>
  <ros:outcome status="aborted" cond="path_blocked" target="WAIT_AND_RETRY"/>
  <ros:outcome status="*" target="FAILED"/>
</state>
```

```python
class Mission:
    def path_blocked(self, error_name):          # outcome data by argument name
        return error_name in ('no_valid_path', 'goal_occupied')
```

## Poses

`pose` (and each name of `poses`) is looked up first in the datamodel (a
`geometry_msgs/PoseStamped`, a `Pose`, a mapping `{x, y, yaw, frame_id}` or a
list `[x, y, yaw]`), then in the YAML file named by the node parameter
`named_poses` (a path or `package://` URL). Chart expressions have no list
literals (FORMAT.md section 8), so a pose reaches the datamodel from a
parameter (`<data id="goal_pose" expr="None"/>` with
`<ros:param name="goal_pose"/>`, set to `[x, y, yaw]` in a parameter file),
from event data (`<assign location="goal_pose" expr="msg.pose"/>`), or from
the named poses:

```yaml
frame_id: map
poses:
  kitchen: {x: 1.0, y: 2.0, yaw: 1.57}
  dock_area: [0.5, -1.0, 0.0]
```

## Outcomes

Every action kind ends with `succeeded`, `aborted`, `canceled` (by the
server), `rejected` or `unavailable` (no server within `server_timeout`);
`nav2/active` with `succeeded` or `timeout`. The outcome data, available to
outcome guards by argument name, are `status`, `result` (the Nav2 result
message), `error_code`, `error_msg`, and two names read from the installed
`nav2_msgs`: `error_name`, the lowercase name of the code's constant, and
`error_source`, the action that declares it. A navigator reports the code of
the action that failed inside its behavior tree, so `navigate_to_pose` can
end with `no_valid_path` from `compute_path_to_pose`. `nav2/dock` and
`nav2/undock` turn a result with `success` false into `aborted`, and the dock
kind adds `num_retries`.

## Feedback

Feedback is summarised into the status (`~/status`, `invokes[].feedback`)
for the viewer: `distance_remaining`, `number_of_recoveries` and
`estimated_time_remaining` for navigation, `current_waypoint`, the docking
`state` by name (`nav_to_staging_pose`, `controlling`, ...), the distance or
angle travelled by behaviors. `feedback` (a model method) and
`feedback_event` (an event) work as for `ros:action`.

## Kinds

Every action kind also takes `server` (the default is Nav2's), `goal` (a
model method completing the goal after the kind filled it), `feedback`,
`feedback_event`, `server_timeout` and `cancel_timeout` (seconds, default 5).

### `nav2/navigate_to_pose`

Navigate to one pose with bt_navigator.
Action `nav2_msgs/action/NavigateToPose` on `navigate_to_pose`.

| Attribute | Required | Default | Meaning |
|---|---|---|---|
| `pose` | yes |  | name of the goal pose |
| `behavior_tree` |  |  | behavior tree file (default: the navigator's) |

### `nav2/navigate_through_poses`

Navigate through several poses with bt_navigator.
Action `nav2_msgs/action/NavigateThroughPoses` on `navigate_through_poses`.

| Attribute | Required | Default | Meaning |
|---|---|---|---|
| `poses` | yes |  | names of the poses, space-separated, or one datamodel list |
| `behavior_tree` |  |  | behavior tree file |

### `nav2/follow_waypoints`

Visit waypoints with the waypoint follower.
Action `nav2_msgs/action/FollowWaypoints` on `follow_waypoints`.

| Attribute | Required | Default | Meaning |
|---|---|---|---|
| `poses` | yes |  | names of the waypoints, space-separated, or one datamodel list |
| `loops` |  | `0` | number of extra loops |

### `nav2/dock`

Dock with the docking server, at a dock of its database or at a pose.
Action `nav2_msgs/action/DockRobot` on `dock_robot`.

| Attribute | Required | Default | Meaning |
|---|---|---|---|
| `dock_id` |  |  | dock in the docking server's database |
| `dock_pose` |  |  | name of the dock pose (instead of dock_id) |
| `dock_type` |  |  | dock plugin, with dock_pose |
| `staging` |  | `True` | navigate to the staging pose first |
| `max_staging_time` |  | `1000.0` | seconds to reach staging |

### `nav2/undock`

Undock with the docking server.
Action `nav2_msgs/action/UndockRobot` on `undock_robot`.

| Attribute | Required | Default | Meaning |
|---|---|---|---|
| `dock_type` |  |  | dock plugin (needed when the server has several) |
| `max_undocking_time` |  | `30.0` | seconds to undock |

### `nav2/spin`

Turn in place with the behavior server.
Action `nav2_msgs/action/Spin` on `spin`.

| Attribute | Required | Default | Meaning |
|---|---|---|---|
| `angle` | yes |  | angle to turn, in radians |
| `time_allowance` |  | `10.0` | seconds allowed |

### `nav2/back_up`

Drive backwards in a straight line with the behavior server.
Action `nav2_msgs/action/BackUp` on `backup`.

| Attribute | Required | Default | Meaning |
|---|---|---|---|
| `distance` | yes |  | metres to back up |
| `speed` |  | `0.1` | metres per second |
| `time_allowance` |  | `10.0` | seconds allowed |

### `nav2/wait`

Wait with the behavior server.
Action `nav2_msgs/action/Wait` on `wait`.

| Attribute | Required | Default | Meaning |
|---|---|---|---|
| `duration` | yes |  | seconds to wait |

### `nav2/active`

Succeed once the named Nav2 lifecycle managers report their nodes active.

| Attribute | Required | Default | Meaning |
|---|---|---|---|
| `managers` |  | `lifecycle_manager_navigation` | lifecycle manager node names, space-separated |
| `timeout` |  | `60.0` | seconds to wait |
| `period` |  | `0.5` | seconds between checks |

## Example: patrol, dock, pause

`examples/patrol.scxml` is one chart with four regions: `mode` (pause and
resume), `safety` (an emergency-stop topic), `power` (a battery topic with
thresholds as parameters) and `task`. The task waits for Nav2 with
`nav2/active`, patrols three named poses, docks with `nav2/dock` when power
is low and undocks when charged, returning to the interrupted leg through
shallow history; it holds while paused or stopped and resumes the same leg
through deep history. It runs on Nav2's TurtleBot3 loopback simulation
(no Gazebo) with one dock added to the docking server:

```bash
sudo apt install ros-jazzy-nav2-bringup ros-jazzy-nav2-loopback-sim
ros2 launch statechart_ros_nav2 patrol_sim.launch.py      # use_rviz:=True to watch
ros2 service call /patrol/command statechart_ros_msgs/srv/SendEvent "{event: start}"
ros2 service call /patrol/command statechart_ros_msgs/srv/SendEvent "{event: pause}"
```

Its scenario is tested on every push against fake Nav2 servers
(`test/test_patrol_scenario.py`) and nightly against Nav2 in the simulation
(`test_sim/`), which also runs every kind once against the real servers.

## Error names (nav2_msgs, Jazzy)

Generated from the `nav2_msgs` the package was tested with; the kinds read
the installed package at run time, so a newer Nav2's codes are named too.

| Code | error_name | error_source |
|---|---|---|
| 100 | `unknown` | `follow_path` |
| 101 | `invalid_controller` | `follow_path` |
| 102 | `tf_error` | `follow_path` |
| 103 | `invalid_path` | `follow_path` |
| 104 | `patience_exceeded` | `follow_path` |
| 105 | `failed_to_make_progress` | `follow_path` |
| 106 | `no_valid_control` | `follow_path` |
| 107 | `controller_timed_out` | `follow_path` |
| 200 | `unknown` | `compute_path_to_pose` |
| 201 | `invalid_planner` | `compute_path_to_pose` |
| 202 | `tf_error` | `compute_path_to_pose` |
| 203 | `start_outside_map` | `compute_path_to_pose` |
| 204 | `goal_outside_map` | `compute_path_to_pose` |
| 205 | `start_occupied` | `compute_path_to_pose` |
| 206 | `goal_occupied` | `compute_path_to_pose` |
| 207 | `timeout` | `compute_path_to_pose` |
| 208 | `no_valid_path` | `compute_path_to_pose` |
| 300 | `unknown` | `compute_path_through_poses` |
| 301 | `invalid_planner` | `compute_path_through_poses` |
| 302 | `tf_error` | `compute_path_through_poses` |
| 303 | `start_outside_map` | `compute_path_through_poses` |
| 304 | `goal_outside_map` | `compute_path_through_poses` |
| 305 | `start_occupied` | `compute_path_through_poses` |
| 306 | `goal_occupied` | `compute_path_through_poses` |
| 307 | `timeout` | `compute_path_through_poses` |
| 308 | `no_valid_path` | `compute_path_through_poses` |
| 309 | `no_viapoints_given` | `compute_path_through_poses` |
| 400 | `unknown` | `compute_and_track_route` |
| 401 | `tf_error` | `compute_and_track_route` |
| 402 | `no_valid_graph` | `compute_and_track_route` |
| 403 | `indeterminant_nodes_on_graph` | `compute_and_track_route` |
| 404 | `timeout` | `compute_and_track_route` |
| 405 | `no_valid_route` | `compute_and_track_route` |
| 406 | `operation_failed` | `compute_and_track_route` |
| 407 | `invalid_edge_scorer_use` | `compute_and_track_route` |
| 500 | `unknown` | `smooth_path` |
| 501 | `invalid_smoother` | `smooth_path` |
| 502 | `timeout` | `smooth_path` |
| 503 | `smoothed_path_in_collision` | `smooth_path` |
| 504 | `failed_to_smooth_path` | `smooth_path` |
| 505 | `invalid_path` | `smooth_path` |
| 600 | `unknown` | `follow_g_p_s_waypoints` |
| 601 | `task_executor_failed` | `follow_g_p_s_waypoints` |
| 700 | `unknown` | `spin` |
| 701 | `timeout` | `spin` |
| 702 | `tf_error` | `spin` |
| 703 | `collision_ahead` | `spin` |
| 710 | `unknown` | `back_up` |
| 711 | `timeout` | `back_up` |
| 712 | `tf_error` | `back_up` |
| 713 | `invalid_input` | `back_up` |
| 714 | `collision_ahead` | `back_up` |
| 720 | `unknown` | `drive_on_heading` |
| 721 | `timeout` | `drive_on_heading` |
| 722 | `tf_error` | `drive_on_heading` |
| 723 | `collision_ahead` | `drive_on_heading` |
| 724 | `invalid_input` | `drive_on_heading` |
| 730 | `unknown` | `assisted_teleop` |
| 731 | `timeout` | `assisted_teleop` |
| 732 | `tf_error` | `assisted_teleop` |
| 901 | `dock_not_in_db` | `dock_robot` |
| 902 | `dock_not_valid` | `dock_robot` |
| 903 | `failed_to_stage` | `dock_robot` |
| 904 | `failed_to_detect_dock` | `dock_robot` |
| 905 | `failed_to_control` | `dock_robot` |
| 906 | `failed_to_charge` | `dock_robot` |
| 999 | `unknown` | `dock_robot` |
