# Interfaces: one chart, many packages

A robot's behaviour is in one chart, but the nodes around it come from many
packages, often maintained by different people: a driver publishes the
emergency stop, a perception package reports obstacles, a cell controller
serves the action the chart calls. This page says how they stay consistent
with the chart.

## The chart is the only writer of the state

Only the chart node changes the state. Other nodes do two things:

| Other nodes | The chart |
|---|---|
| publish **facts**: `e_stop`, `battery`, `health` | reads them with `ros:subscribe`; a `when` guard decides whether a message matters |
| send **commands**: a service call, an action goal | handles each, or refuses it with a reason (`ros:refuse`) |
| need to know the state | read `~/status` and `~/transitions`; they do not keep a copy of the state machine |

Two things to avoid:

- **A node that publishes a state name** ("go to ERROR"). The decision is
  then made outside the chart, and two packages make it. Publish the fact
  (the reading, the fault) and let the chart decide.
- **Free-text events from other packages** through the generic
  `SendEvent` service. The event name is a string nobody checks against the
  chart. Give other packages typed topics, services and actions; keep
  `SendEvent` (and `debug_events`) for people and tests.

Because every event goes through the chart's one queue and is processed to
completion before the next, two nodes reporting at once cannot race.

## The interface is the contract, not the states

What other packages depend on is the chart's interface: the topics it
subscribes to and publishes, the services and actions it serves and calls,
and the parameters it sets on other nodes, with their types and QoS. States
can be renamed, split or nested without touching any other package as long
as the interface stays the same.

`ros2 statechart interface CHART` writes it as YAML (child charts and user
invoke kinds included):

```yaml
statechart_interface: 1
chart: mission
subscribes:
- name: e_stop
  type: std_msgs/msg/Bool
  qos: latched
  doc: true while a stop button is pressed; published on change
services_served:
- name: mission/command
  type: statechart_ros_msgs/srv/SendEvent
  commands: [pause, resume, stop]
actions_called:
- name: dock_robot
  type: nav2_msgs/action/DockRobot
```

| Section | Other packages |
|---|---|
| `subscribes` | publish these topics, with this type and a QoS the chart's subscription accepts |
| `publishes` | may subscribe to these |
| `services_served`, `actions_served` | may call these; `commands` lists the events a service accepts when its request names them |
| `services_called`, `actions_called` | serve these |
| `parameters_set` | the chart sets these parameters on these nodes |

Names are as written in the chart: a relative name resolves in the chart
node's namespace, and launch-time remapping applies, so the file says what
the chart expects before remapping.

### Say what each input means

A type does not say when a message is sent. Write it in the element's `doc`
attribute, which every `ros:` element accepts and the interface carries:

```xml
<ros:subscribe topic="health" type="diagnostic_msgs/msg/DiagnosticStatus" event="health"
               doc="level ERROR when a drive fault stops the wheels; at least 1 Hz"/>
```

The chart is reviewed with its `doc`, so the meaning changes in the same
review as the chart.

## Keep the file in the repository

1. Commit the interface next to the chart (`mission.interface.yaml`) and
   install both.
2. In CI, after `validate`:

   ```bash
   ros2 statechart interface charts/mission.scxml --check charts/mission.interface.yaml
   ```

   It exits 1 if the chart's interface differs from the file and names each
   difference: `breaking` (an endpoint removed, a type or QoS changed, a
   command removed), `additive` (an endpoint or command added) or `doc`. A
   change to the interface cannot be merged without the file changing in
   the same review, where the other parties see it.
3. Version the package that holds the chart and the file: a breaking change
   is a major version, an additive one a minor version, a change inside the
   chart only a patch. Put messages, services and actions that belong to the
   chart in an interfaces package released with it.

## Each party checks its own nodes

Another party does not need the chart, its model or its invoke kinds to
test against it: the interface file is enough. In a launch test that starts
their own nodes:

```python
from statechart_ros_testing import assert_provides, load_interface

def test_driver_provides_the_mission_inputs(test_node):
    iface = load_interface(os.path.join(share, 'charts', 'mission.interface.yaml'))
    assert_provides(test_node, iface, names=['e_stop', 'health'], namespace='/robot1')
```

`check_graph` returns the problems instead of failing: no publisher, the
wrong type, a QoS the chart cannot receive (a best-effort publisher for a
reliable subscription, a volatile one for a latched subscription), a missing
server, client or node. A renamed topic or a forgotten remap then fails in
that party's CI, not on the robot.

## The robot checks at start

The chart node checks its interface once after activation: after
`check_interface` seconds (default 5, 0 turns it off), it warns once about
each input topic without a publisher, each service or action it calls
without a server and each node it sets parameters on that is not running.
It uses the node's own name resolution, so remappings apply. The check only
logs; the state is the chart's business.

## Inputs that must keep coming

A fact that stops arriving is silence, not an event. When an input must
keep coming (a heartbeat, a localization fix), make its absence an event
with `ros:after` in a state that is re-entered on each message:

```xml
<state id="LOCALIZED">
  <ros:after delay="1.0" event="fix_lost"/>
  <transition event="fix" target="LOCALIZED"/>   <!-- re-entry restarts the timeout -->
  <transition event="fix_lost" target="LOST"/>
</state>
```

The chart then handles a dead producer like any other condition.
