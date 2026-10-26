# Tutorial 2: nesting and history

Tutorial 1 repeated the answers to `stop` and `go` in `FORWARD` and in
`TURN`. Here the drawing states move into one compound state, `DRAWING`,
which answers them once, and a pause returns to the step it interrupted.

## The chart

`statechart_ros/examples/tutorial/square_pause.scxml`:

<!-- check: file statechart_ros/examples/tutorial/square_pause.scxml -->
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Tutorial 2: the square of tutorial 1 with its drawing states nested in
     DRAWING, which answers "stop" and "go" once for both, and a pause that
     returns to the state it left through a history state. -->
<scxml xmlns="http://www.w3.org/2005/07/scxml"
       xmlns:ros="https://github.com/jerry73204/ros2_statechart/ns/1"
       version="1.0" datamodel="python" initial="IDLE" name="square">

  <ros:service_server name="~/command" type="statechart_ros_msgs/srv/SendEvent"/>

  <datamodel>
    <data id="sides" expr="0"/>
  </datamodel>

  <state id="IDLE">
    <transition event="go" target="DRAWING">
      <assign location="sides" expr="0"/>
    </transition>
    <ros:ignore event="stop" reason="already idle"/>
    <ros:refuse event="pause" reason="not drawing"/>
    <ros:ignore event="resume" reason="not paused"/>
  </state>

  <state id="DRAWING" initial="FORWARD">
    <history id="DRAWING_H" type="shallow">
      <transition target="FORWARD"/>
    </history>
    <transition event="stop" target="IDLE"/>
    <transition event="pause" target="PAUSED"/>
    <ros:refuse event="go" reason="already drawing"/>
    <ros:ignore event="resume" reason="not paused"/>

    <state id="FORWARD">
      <ros:on_entry publish="turtle1/cmd_vel" type="geometry_msgs/msg/Twist"
                    value="{linear: {x: 2.0}}"/>
      <ros:after delay="1.5" event="moved"/>
      <transition event="moved" target="TURN"/>
    </state>

    <state id="TURN">
      <onentry><assign location="sides" expr="sides + 1"/></onentry>
      <ros:on_entry publish="turtle1/cmd_vel" type="geometry_msgs/msg/Twist"
                    value="{angular: {z: 1.5708}}"/>
      <ros:after delay="1.5" event="turned"/>
      <transition event="turned" cond="sides &lt; 4" target="FORWARD"/>
      <transition event="turned" target="IDLE"/>
    </state>
  </state>

  <state id="PAUSED">
    <ros:on_entry publish="turtle1/cmd_vel" type="geometry_msgs/msg/Twist" value="{}"/>
    <transition event="resume" target="DRAWING_H"/>
    <transition event="stop" target="IDLE"/>
    <ros:refuse event="go" reason="paused: resume or stop first"/>
    <ros:ignore event="pause" reason="already paused"/>
  </state>
</scxml>
```

- **A compound state** (`DRAWING`) contains states; while the chart is in
  `FORWARD` it is also in `DRAWING`. An event is offered to the innermost
  active state first, then to its parents: `stop` and `pause` are written
  once, on `DRAWING`, and apply in both children. `moved` and `turned` stay
  where they mean something.
- **Leaving a compound state leaves its children**: on `pause` the chart
  exits `FORWARD` (or `TURN`) and then `DRAWING`. Work owned by the child
  stops with it: the pending `ros:after` timeout is cancelled. `PAUSED`
  publishes a zero velocity on entry.
- **A history state** (`DRAWING_H`, `type="shallow"`) remembers which child
  of `DRAWING` was active when the chart last left it. `resume` targets the
  history state, so the chart goes back to `FORWARD` or `TURN`, entering it
  again (its entry output and timeout start over). The transition inside
  `<history>` is where to go the first time, when there is nothing to
  remember. A `deep` history remembers the active states at every level
  below, as the patrol of [tutorial 3](03-nav2-patrol.md) does.
- `sides` is data, not state: pausing keeps it, so the square still has four
  sides.

How many states and transitions this saves grows with the chart: every state
added inside `DRAWING` gets `stop` and `pause` without writing them again,
and the validator still checks that `go` and `resume` are answered
everywhere.

## Run it

<!-- check: run -->
```bash
ros2 statechart validate package://statechart_ros/examples/tutorial/square_pause.scxml
```

Start turtlesim and the chart as in tutorial 1, with the new file:

<!-- check: start -->
```bash
ros2 run turtlesim turtlesim_node
```

<!-- check: start -->
```bash
ros2 run statechart_ros statechart_node --ros-args -r __node:=square \
  -p chart:=package://statechart_ros/examples/tutorial/square_pause.scxml \
  -p "datamodel_publish:=[sides]"
```

<!-- check: run expect "handled=True" within 30 -->
```bash
ros2 service call /square/command statechart_ros_msgs/srv/SendEvent "{event: go}"
```

Pause while it draws; `show` prints the nesting and the active state:

<!-- check: run expect "handled=True" -->
```bash
ros2 service call /square/command statechart_ros_msgs/srv/SendEvent "{event: pause}"
```

<!-- check: run expect "* PAUSED" within 5 -->
```bash
ros2 statechart show /square
```

```text
square (/square)
  IDLE
  DRAWING
    DRAWING_H (history shallow)
    FORWARD
    TURN
* PAUSED
last event: pause
  sides = 0
```

(`sides` depends on when you pause.) While paused, `go` is refused with
its reason, and `resume` returns to the remembered step:

<!-- check: run expect "paused: resume or stop first" -->
```bash
ros2 service call /square/command statechart_ros_msgs/srv/SendEvent "{event: go}"
```

<!-- check: run expect "handled=True" -->
```bash
ros2 service call /square/command statechart_ros_msgs/srv/SendEvent "{event: resume}"
```

<!-- check: run expect "sides = 4" within 30 -->
```bash
ros2 statechart show /square
```

## What to remember

- Put an answer on the state where it holds for every child; the innermost
  state still overrides it.
- Leaving a state stops what it owns, children included; history brings the
  chart back to where it was, not to the work it was doing (that starts
  again).
- Data survives state changes; state does not survive leaving, except
  through history.

Next: [Nav2 patrol and docking](03-nav2-patrol.md).
