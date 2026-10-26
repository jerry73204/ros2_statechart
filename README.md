# ros2_statechart

Statecharts for ROS 2. A robot's behaviour is written as one standard
[SCXML](https://www.w3.org/TR/scxml/) document, with a small `ros:` extension
that says what each state does in ROS: which action it runs, which topic it
publishes on entry, which topics and services turn into events. The chart is
run by [python-statemachine](https://github.com/fgmacedo/python-statemachine),
used as released, inside one ROS 2 node.

Status: in development. Done: P0 (engine pinned by tests), P1 (loader, validator, `validate` / `diagram` / `export`); see [docs/phases](docs/phases/).

## Why statecharts

A flat state machine grows by multiplication: every new mode or interruption
adds arrows out of every state. Statecharts (Harel, 1987; standardised as W3C
SCXML) add what keeps a large machine readable and correct:

- **nesting**: leaving a parent state exits every active child, innermost
  first, so nothing is left running or half reset;
- **parallel regions**: independent concerns (who is in control, may the
  robot move, where it is) are separate regions, not a product of states;
- **history**: a paused task resumes where it was, by declaration;
- **invoke**: work a state starts (an action goal) is cancelled when the
  state is left, by the runtime;
- **one event at a time**: each event runs to completion before the next, so
  there are no races between callbacks.

## What it looks like

```xml
<scxml xmlns="http://www.w3.org/2005/07/scxml"
       xmlns:ros="https://github.com/jerry73204/ros2_statechart/ns/1"
       version="1.0" datamodel="python" initial="run">

  <ros:model class="my_robot.mission:Mission"/>
  <ros:subscribe topic="e_stop" type="std_msgs/msg/Bool" event="e_stop" when="msg_true"/>
  <ros:service_server name="~/command" type="statechart_ros_msgs/srv/SendEvent"/>

  <parallel id="run">
    <state id="safety" initial="OK">
      <state id="OK">
        <transition event="e_stop" target="STOPPED"/>
        <ros:ignore event="resume" reason="not stopped"/>
      </state>
      <state id="STOPPED">
        <transition event="resume" target="OK"/>
        <ros:ignore event="e_stop" reason="already stopped"/>
      </state>
    </state>
    <state id="task" initial="IDLE">
      <ros:refuse event="go" reason="a docking task is running or done"/>
      <ros:refuse event="undock" reason="not docked"/>
      <state id="IDLE">
        <transition event="go" cond="In('OK')" target="DOCKING"/>
        <ros:refuse event="go" reason="stopped: send resume first"/>
      </state>
      <state id="DOCKING">
        <ros:action server="dock_robot" type="nav2_msgs/action/DockRobot" goal="dock_goal"/>
        <ros:outcome status="succeeded" target="DOCKED"/>
        <ros:outcome status="*" target="IDLE"/>
        <transition event="e_stop" target="IDLE"/>  <!-- leaving DOCKING cancels the goal -->
      </state>
      <state id="DOCKED">
        <ros:on_entry publish="dock/hold" type="std_msgs/msg/Bool" value="true"/>
        <ros:on_exit publish="dock/hold" type="std_msgs/msg/Bool" value="false"/>
        <transition event="undock" cond="In('OK')" target="UNDOCKING"/>
        <ros:refuse event="undock" reason="stopped: send resume first"/>
      </state>
      <state id="UNDOCKING">
        <ros:action server="undock_robot" type="nav2_msgs/action/UndockRobot" goal="undock_goal"/>
        <ros:outcome status="succeeded" target="IDLE"/>
        <ros:outcome status="*" target="DOCKED"/>
        <transition event="e_stop" target="DOCKED"/>
      </state>
    </state>
  </parallel>
</scxml>
```

```python
# my_robot/mission.py: the only code; guards and goal builders by name
class Mission:
    def __init__(self, node): self.node = node
    def msg_true(self, msg): return msg.data
    def dock_goal(self, goal): goal.dock_id = 'home'; goal.navigate_to_staging_pose = True; return goal
    def undock_goal(self, goal): goal.dock_type = 'simple_charging_dock'; return goal
```

```bash
ros2 statechart validate mission.scxml       # schema, structure, ROS types, model names
ros2 statechart diagram mission.scxml -o mission.svg
ros2 run statechart_ros statechart_node --ros-args -p chart:=mission.scxml
ros2 run statechart_ros_viewer viewer       # http://localhost:8095, live states
ros2 statechart show /mission               # active states in the terminal
```

## Packages (planned)

| Package | Contents |
|---|---|
| `statechart_ros_msgs` | structure, status and transition messages; debug services; the action to run a chart |
| `statechart_ros` | the node that hosts a chart: loader for the `ros:` extension, one event queue, invokes, outputs, introspection, lifecycle |
| `statechart_ros_nav2` | Nav2 action invokes, error-code names, waiting for Nav2 to be active |
| `statechart_ros_cli` | `ros2 statechart` verbs: validate, diagram, export, list, show, echo, send |
| `statechart_ros_viewer` | web viewer: the diagram with active states lit, data, transition log, bag replay |
| `statechart_ros_testing` | pytest fixtures: fake action servers, scenario runner, random event sequences against invariants |
| `python_statemachine_vendor` | python-statemachine pinned, so the packages can be released through the ROS buildfarm |

## Documents

- [docs/DESIGN.md](docs/DESIGN.md): goals, architecture, execution model, Nav2, viewer, testing, packaging.
- [docs/FORMAT.md](docs/FORMAT.md): the `ros:` extension, element by element, and how it maps onto SCXML.
- [docs/ENGINE.md](docs/ENGINE.md): what python-statemachine does, verified by probes, and what the design relies on.
- [docs/phases/](docs/phases/): the implementation plan, one file per phase.

## Licence

Apache-2.0. python-statemachine is MIT-licensed.
