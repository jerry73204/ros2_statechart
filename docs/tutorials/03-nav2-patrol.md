# Tutorial 3: a Nav2 patrol with docking

The patrol example of `statechart_ros_nav2` on Nav2's own simulation: a
TurtleBot3 visits three poses in turn, docks when its battery is low,
undocks when it is charged and resumes the leg it left; a command pauses it,
an emergency stop topic holds it. It runs without Gazebo, on Nav2's loopback
simulation, so any laptop runs it.

## Install

```bash
sudo apt install ros-jazzy-statechart-ros-nav2 ros-jazzy-statechart-ros-cli \
  ros-jazzy-nav2-bringup ros-jazzy-nav2-loopback-sim
```

Humble works too, except docking (Humble's Nav2 has no docking server).

## The chart

`statechart_ros_nav2/examples/patrol.scxml` is the whole behaviour; read it
next to this page. Four concerns run side by side as the four regions of the
parallel state `run`:

| Region | States | Changes on |
|---|---|---|
| `mode` | `AUTO`, `PAUSED` | the commands `pause`, `resume` |
| `safety` | `CLEAR`, `STOPPED` | the topic `e_stop` (`std_msgs/Bool`) |
| `power` | `POWER_OK`, `POWER_LOW` | the topic `battery_state`, thresholds `battery_low`, `battery_full` |
| `task` | `WAIT_NAV2`, `IDLE`, `WORK`, `HOLD` | Nav2, `start`, `cancel`, and the other three regions |

What it shows:

- **Parallel regions** keep independent concerns apart: the battery logic
  does not know about legs, and the pause does not know about docking. The
  task region follows the others with guards: `In('PAUSED') or
  In('STOPPED')` sends it to `HOLD`, `In('POWER_LOW')` to `CHARGE`. All four
  share one datamodel and one event queue, which is why they are one chart
  ([DESIGN.md](../DESIGN.md), section 4, composition).
- **Nav2 work as invokes**: `<ros:invoke kind="nav2/navigate_to_pose"
  pose="wp_b"/>` sends a goal on entry to `TO_B` and cancels it when the
  state is left, whatever the reason (pause, emergency stop, low battery,
  cancel). `nav2/active` waits until Nav2's lifecycle manager reports
  active; `nav2/dock` and `nav2/undock` use the docking server.
- **Outcomes** route the result: `<ros:outcome status="*" target="TO_C"/>`
  goes on after any result; `DOCKING` goes to `CHARGING` on `succeeded`,
  to `DOCK_FAILED` otherwise, which retries after `ros:after` 5 s.
- **Named poses** come from a parameter file
  (`examples/sandbox_poses.yaml`, the parameter `named_poses`), not from the
  chart: the same chart runs on another map with another file.
- **Deep history** (`WORK_H`) returns the task to the exact leg, or the
  exact docking step, after a hold; the shallow `PATROL_H` returns to the
  leg after charging.
- **`ros:on_entry` / `ros:on_exit`** publish `charging` true and false
  around `CHARGING`.

[NAV2.md](../NAV2.md) lists every Nav2 kind, its attributes and statuses,
and the error names.

## Run it

`patrol_sim.launch.py` starts Nav2's TurtleBot3 loopback simulation with one
dock, sets the initial pose, starts a fake battery (it drains 1 % per second
and charges while `charging` is true) and the chart (add `use_rviz:=True`
to watch the robot in RViz):

<!-- check(nightly): start -->
```bash
ros2 launch statechart_ros_nav2 patrol_sim.launch.py
```

The chart waits in `WAIT_NAV2` until Nav2 is active, then in `IDLE`:

<!-- check(nightly): run expect "* IDLE" within 240 -->
```bash
ros2 statechart show /patrol
```

<!-- check(nightly): run expect "handled=True" -->
```bash
ros2 service call /patrol/command statechart_ros_msgs/srv/SendEvent "{event: start}"
```

<!-- check(nightly): run expect "* TO_" within 10 -->
```bash
ros2 statechart show /patrol
```

`show` prints the running goal under its state, with the elapsed time and
the last feedback (distance remaining). Pause, and the goal is cancelled and
the task holds; resume, and the same leg starts again:

<!-- check(nightly): run expect "handled=True" -->
```bash
ros2 service call /patrol/command statechart_ros_msgs/srv/SendEvent "{event: pause}"
```

<!-- check(nightly): run expect "* HOLD" within 10 -->
```bash
ros2 statechart show /patrol
```

<!-- check(nightly): run expect "handled=True" -->
```bash
ros2 service call /patrol/command statechart_ros_msgs/srv/SendEvent "{event: resume}"
```

When the battery falls below 30 % the robot drives to the dock and charges:

<!-- check(nightly): run expect "* CHARGING" within 300 -->
```bash
ros2 statechart show /patrol
```

An emergency stop holds whatever the task was doing:

<!-- check(nightly): run expect "* STOPPED" within 10 -->
```bash
ros2 topic pub --once -w 1 /e_stop std_msgs/msg/Bool "{data: true}" && sleep 1 && \
  ros2 statechart show /patrol
```

<!-- check(nightly): run expect "* IDLE" within 10 -->
```bash
ros2 topic pub --once -w 1 /e_stop std_msgs/msg/Bool "{data: false}" && \
  ros2 service call /patrol/command statechart_ros_msgs/srv/SendEvent "{event: cancel}" && \
  ros2 statechart show /patrol
```

The viewer (`ros2 run statechart_ros_viewer viewer`, then
<http://localhost:8095/#/patrol>) shows the four regions side by side, the
running goal with its feedback, and the transition log; `ros2 bag record
/patrol/structure /patrol/status /patrol/transitions` records a run the
viewer replays later ([VIEWER.md](../VIEWER.md)).

## What to remember

- One region per concern; regions that must agree read each other with
  `In(...)` and stay in one chart.
- Nav2 goals are invokes: entering the state sends the goal, leaving it
  cancels it, the result picks the next state.
- Robot-specific values (poses, thresholds) are parameters; the chart is the
  behaviour.

Next: [testing a chart](04-testing.md).
