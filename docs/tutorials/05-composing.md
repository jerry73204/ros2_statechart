# Tutorial 5: composing charts

A procedure with its own states (dock, recover, draw a square) can become a
chart of its own that a parent runs as one step. This tutorial runs the same
child chart two ways: inside the parent's node, and hosted by another node
as an action.

## When to split, and how

| Parts share | Use | Because |
|---|---|---|
| data, guards (`In(...)`) or events | one chart: nested states, parallel regions | two charts share nothing but events |
| nothing; one is a step of the other | a child chart in the same node (`ros:chart`) | reusable and testable alone, stopped with the parent's state, no transport |
| nothing; the step belongs to other software | a chart in another node (`run_as_action`, `ros:action`) | another computer, process or lifecycle, or several parents |

[DESIGN.md](../DESIGN.md) section 4 and [FORMAT.md](../FORMAT.md) section 5
give the rules.

## The child

`statechart_ros/examples/tutorial/square_child.scxml` draws one square and
ends:

<!-- check: file statechart_ros/examples/tutorial/square_child.scxml -->
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Tutorial 5: one square as a chart that ends. It declares no inputs: a
     parent runs it (ros:chart) or a node hosts it as an action
     (run_as_action). Its final state "drawn" is the outcome. -->
<scxml xmlns="http://www.w3.org/2005/07/scxml"
       xmlns:ros="https://github.com/jerry73204/ros2_statechart/ns/1"
       version="1.0" datamodel="python" initial="FORWARD" name="square_child">

  <datamodel>
    <data id="sides" expr="0"/>
  </datamodel>

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
    <transition event="turned" target="drawn"/>
  </state>

  <final id="drawn">
    <donedata><param name="sides" expr="sides"/></donedata>
  </final>
</scxml>
```

A child chart has a top-level `<final>` for each way it can end; their ids
are the statuses its parent routes. It declares no inputs (no
`ros:service_server`, no `ros:subscribe`): its parent decides what reaches
it (`autoforward="true"` passes on every event the parent processes).

## In the same node: `ros:chart`

`statechart_ros/examples/tutorial/shapes.scxml` draws two squares, clearing
the screen in between (turtlesim's `clear` service, `std_srvs/srv/Empty`):

<!-- check: file statechart_ros/examples/tutorial/shapes.scxml -->
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Tutorial 5: a parent that draws two squares with a child chart, clearing
     the screen between them. Leaving DRAW (on "stop") stops the child. -->
<scxml xmlns="http://www.w3.org/2005/07/scxml"
       xmlns:ros="https://github.com/jerry73204/ros2_statechart/ns/1"
       version="1.0" datamodel="python" initial="IDLE" name="shapes">

  <ros:service_server name="~/command" type="statechart_ros_msgs/srv/SendEvent"/>

  <datamodel>
    <data id="squares" expr="0"/>
  </datamodel>

  <state id="IDLE">
    <transition event="go" target="WORKING">
      <assign location="squares" expr="0"/>
    </transition>
    <ros:ignore event="stop" reason="already idle"/>
  </state>

  <state id="WORKING" initial="DRAW">
    <transition event="stop" target="IDLE"/>
    <ros:refuse event="go" reason="already drawing"/>

    <state id="DRAW">
      <ros:chart src="square_child.scxml"/>
      <ros:outcome status="drawn" target="CLEAR"/>
    </state>

    <state id="CLEAR">
      <onentry><assign location="squares" expr="squares + 1"/></onentry>
      <ros:service_call service="clear" type="std_srvs/srv/Empty"/>
      <ros:outcome status="*" target="NEXT"/>
    </state>

    <!-- Passed through at once: eventless transitions, the first that holds. -->
    <state id="NEXT">
      <transition cond="squares &lt; 2" target="DRAW"/>
      <transition target="IDLE"/>
    </state>
  </state>
</scxml>
```

`DRAW` runs the child as its invoke: the child starts on entry, and its
final state `drawn` is the outcome. On `stop` the chart leaves `WORKING`
and with it `DRAW`, which stops the child: its states are exited and its
work cancelled before the parent's transition completes. The validator
checks the child too, and that the parent's outcomes cover the child's final
states.

<!-- check: run -->
```bash
ros2 statechart validate package://statechart_ros/examples/tutorial/shapes.scxml
```

<!-- check: start -->
```bash
ros2 run turtlesim turtlesim_node
```

<!-- check: start -->
```bash
ros2 run statechart_ros statechart_node --ros-args -r __node:=shapes \
  -p chart:=package://statechart_ros/examples/tutorial/shapes.scxml \
  -p "datamodel_publish:=[squares]"
```

<!-- check: run expect "handled=True" within 30 -->
```bash
ros2 service call /shapes/command statechart_ros_msgs/srv/SendEvent "{event: go}"
```

The parent's structure and status include the child's states under `DRAW`,
named `DRAW/FORWARD`, `DRAW/TURN`, so `show`, `echo` and the viewer show the
child live inside its parent:

<!-- check: run expect "* DRAW/" within 5 -->
```bash
ros2 statechart show /shapes
```

```text
shapes (/shapes)
  IDLE
* WORKING
  * DRAW
      > ros/chart square_child.scxml, 0.1 s
    * DRAW/FORWARD
      DRAW/TURN
      DRAW/drawn (final)
    CLEAR
    NEXT
last event: go
  squares = 0
```

Two squares take about 25 s:

<!-- check: run expect "squares = 2" within 60 -->
```bash
ros2 statechart show /shapes
```

## In another node: `run_as_action`

The same child, hosted by its own node. With the parameter `run_as_action`
the node does not start its chart on activation: it serves a
`statechart_ros_msgs/action/RunStatechart` action and runs the chart once
per goal. The goal's `data` (a JSON object) sets datamodel values, the
feedback is the chart's status, and the result holds the final state and
its donedata. Cancelling the goal exits the chart.

<!-- check: start -->
```bash
ros2 run statechart_ros statechart_node --ros-args -r __node:=square_server \
  -p chart:=package://statechart_ros/examples/tutorial/square_child.scxml \
  -p run_as_action:=~/run
```

The parent runs it with an ordinary `ros:action`
(`statechart_ros/examples/tutorial/shapes_remote.scxml`):

```xml
  <state id="DRAW">
    <ros:action server="/square_server/run" type="statechart_ros_msgs/action/RunStatechart"/>
    <ros:outcome status="succeeded" target="DONE"/>
    <ros:outcome status="*" target="IDLE"/>
    <transition event="stop" target="IDLE"/>
    <ros:refuse event="go" reason="already drawing"/>
  </state>
```

<!-- check: start -->
```bash
ros2 run statechart_ros statechart_node --ros-args -r __node:=shapes_remote \
  -p chart:=package://statechart_ros/examples/tutorial/shapes_remote.scxml
```

<!-- check: run expect "handled=True" within 30 -->
```bash
ros2 service call /shapes_remote/command statechart_ros_msgs/srv/SendEvent "{event: go}"
```

<!-- check: run expect "* FORWARD" within 5 -->
```bash
ros2 statechart show /square_server
```

Leaving the parent's state cancels the goal, and the hosted chart exits:

<!-- check: run expect "handled=True" -->
```bash
ros2 service call /shapes_remote/command statechart_ros_msgs/srv/SendEvent "{event: stop}"
```

<!-- check: run expect "[not running]" within 10 -->
```bash
ros2 statechart show /square_server
```

Let a second run finish, and the parent ends in `DONE`:

<!-- check: run expect "* DONE" within 40 -->
```bash
ros2 service call /shapes_remote/command statechart_ros_msgs/srv/SendEvent "{event: go}" \
  && sleep 15 && ros2 statechart show /shapes_remote
```

What the action costs: a goal round trip, an action server that may be
absent (the parent's outcome is then `rejected` or `unavailable`), and two
charts that share nothing but the goal and its result. What it gives: the
procedure runs where it belongs, with its own lifecycle and viewer entry.

## What to remember

- Split by what the parts share: shared data and guards stay one chart.
- A child chart is a state's invoke: started on entry, stopped on exit, its
  final states are the outcomes.
- The same chart can run in the same node or behind an action, unchanged.
