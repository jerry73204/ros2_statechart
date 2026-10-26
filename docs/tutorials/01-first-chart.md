# Tutorial 1: a first chart

A chart that makes turtlesim's turtle draw a square when it is told "go".
It shows the parts every chart has: states, events, transitions, data, what
a state does on entry, a timeout, and how a chart answers a command it
cannot take.

## Install

With the released packages, on Ubuntu 24.04 with ROS 2 Jazzy:

```bash
sudo apt install ros-jazzy-statechart-ros ros-jazzy-statechart-ros-cli ros-jazzy-turtlesim
source /opt/ros/jazzy/setup.bash
```

From source, clone this repository into a workspace, then
`rosdep install --from-paths src --ignore-src -y` and `colcon build`, and
source `install/setup.bash`. Humble and Rolling work the same way.

## The chart

The chart is installed with the package as
`statechart_ros/examples/tutorial/square.scxml`:

<!-- check: file statechart_ros/examples/tutorial/square.scxml -->
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Tutorial 1: the turtle draws a square on "go". Turtlesim moves the turtle
     for one second after each velocity command, so each state sends one
     command on entry and waits with a timeout before the next. -->
<scxml xmlns="http://www.w3.org/2005/07/scxml"
       xmlns:ros="https://github.com/jerry73204/ros2_statechart/ns/1"
       version="1.0" datamodel="python" initial="IDLE" name="square">

  <ros:service_server name="~/command" type="statechart_ros_msgs/srv/SendEvent"/>

  <datamodel>
    <data id="sides" expr="0"/>
  </datamodel>

  <state id="IDLE">
    <transition event="go" target="FORWARD">
      <assign location="sides" expr="0"/>
    </transition>
    <ros:ignore event="stop" reason="already idle"/>
  </state>

  <state id="FORWARD">
    <ros:on_entry publish="turtle1/cmd_vel" type="geometry_msgs/msg/Twist"
                  value="{linear: {x: 2.0}}"/>
    <ros:after delay="1.5" event="moved"/>
    <transition event="moved" target="TURN"/>
    <transition event="stop" target="IDLE"/>
    <ros:refuse event="go" reason="already drawing"/>
  </state>

  <state id="TURN">
    <onentry><assign location="sides" expr="sides + 1"/></onentry>
    <ros:on_entry publish="turtle1/cmd_vel" type="geometry_msgs/msg/Twist"
                  value="{angular: {z: 1.5708}}"/>
    <ros:after delay="1.5" event="turned"/>
    <transition event="turned" cond="sides &lt; 4" target="FORWARD"/>
    <transition event="turned" target="IDLE"/>
    <transition event="stop" target="IDLE"/>
    <ros:refuse event="go" reason="already drawing"/>
  </state>
</scxml>
```

Read it from the top:

- **The document is SCXML**, the W3C statechart format; the `ros:` elements
  are this project's extension and say what the chart does in ROS. Any SCXML
  tool can read the states and transitions.
- **`ros:service_server`** makes the node answer the service `~/command`
  (here `/square/command`) of type `statechart_ros_msgs/srv/SendEvent`: each
  request is an event for the chart, and the reply says whether the chart
  took it.
- **`<datamodel>`** holds the chart's data: `sides` counts the sides drawn.
  Expressions such as `sides + 1` and `sides < 4` are a small, checked subset
  of Python ([FORMAT.md](../FORMAT.md) section 8). In XML, `<` is written
  `&lt;`.
- **States** are `IDLE`, `FORWARD` and `TURN`. The chart is in exactly one
  of them; it starts in `IDLE` (the `initial` attribute).
- **Transitions** move the chart on an event: `go` in `IDLE` goes to
  `FORWARD` and resets `sides` on the way. `turned` has two transitions; the
  first whose condition holds is taken, so the fourth turn ends in `IDLE`.
- **`ros:on_entry`** publishes one message when the state is entered. The
  turtle moves for one second after each velocity command.
- **`ros:after`** sends the event `moved` 1.5 s after `FORWARD` is entered,
  unless the chart has left `FORWARD` by then: a timeout belongs to its
  state.
- **`ros:refuse` and `ros:ignore`** answer events a state does not take.
  A robot must answer every command: the validator reports any command event
  that some state neither handles, refuses nor ignores.

## Check it

<!-- check: run -->
```bash
ros2 statechart validate package://statechart_ros/examples/tutorial/square.scxml
```

prints `...square.scxml: ok`. The validator checks the document against the
schema, that every state can be reached and none is a trap, that the
message and service types exist, and that every command is answered.
Try removing the `ros:refuse` from `TURN`: it reports
`event "go" is neither handled, refused nor ignored in {TURN}`.

## Run it

In a first terminal, start turtlesim:

<!-- check: start -->
```bash
ros2 run turtlesim turtlesim_node
```

In a second one, the node that runs the chart (`statechart_node`, named
`square` here), publishing `sides` with its status:

<!-- check: start -->
```bash
ros2 run statechart_ros statechart_node --ros-args -r __node:=square \
  -p chart:=package://statechart_ros/examples/tutorial/square.scxml \
  -p "datamodel_publish:=[sides]"
```

In a third one, look at the chart, then tell it to go:

<!-- check: run expect "* IDLE" within 30 -->
```bash
ros2 statechart show /square
```

<!-- check: run expect "handled=True" within 10 -->
```bash
ros2 service call /square/command statechart_ros_msgs/srv/SendEvent "{event: go}"
```

The turtle draws a square. Asked again while it draws, the chart refuses and
says why:

<!-- check: run expect "already drawing" -->
```bash
ros2 service call /square/command statechart_ros_msgs/srv/SendEvent "{event: go}"
```

`ros2 statechart show /square` prints the states, the active one marked
with `*`, the last event and the data. About 12 s after `go` the square is
done:

<!-- check: run expect "sides = 4" within 30 -->
```bash
ros2 statechart show /square
```

```text
square (/square)
* IDLE
  FORWARD
  TURN
last event: turned
  sides = 4
```

`ros2 statechart echo /square` prints each event as it happens, with the
transition it took; `ros2 run statechart_ros_viewer viewer` serves the chart
as a diagram with the active state lit at <http://localhost:8095/#/square>
([VIEWER.md](../VIEWER.md)).

## What to remember

- The chart says what the robot does in each situation; ROS work is
  attached to states (`ros:on_entry`, `ros:after`) and stops when the state
  is left.
- Commands are events; every event is handled, refused with a reason or
  ignored, in every state.
- `ros2 statechart validate` runs before the robot does; the node refuses to
  start a chart that does not pass.

Next: [nesting and history](02-nesting-and-history.md).
