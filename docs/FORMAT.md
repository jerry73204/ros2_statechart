# The `ros:` extension to SCXML, version 1

A chart is a standard SCXML 1.0 document with `datamodel="python"` and
elements from one extra namespace:

```xml
xmlns:ros="https://github.com/jerry73204/ros2_statechart/ns/1"
```

The extension says what a state does in ROS. Everything about states,
transitions, nesting, parallel regions, history and guards stays standard
SCXML.

## 1. Rules

1. **Placement.** `ros:` elements appear only as direct children of
   `<scxml>` (declarations and inputs) or of `<state>`, `<parallel>`,
   `<final>` (what that state does). Never inside `<onentry>`, `<onexit>`,
   `<transition>` or other executable content. The W3C schema allows foreign
   elements in all of these places; the engine accepts them only in the
   first group ([ENGINE.md](ENGINE.md) E1, E2).
2. **No ROS work on transitions.** Something to do when moving from A to B
   belongs to B's entry (`ros:on_entry`) or to A's exit (`ros:on_exit`).
3. **One invoke per state.** A state has at most one of `ros:action`,
   `ros:service_call`, `ros:wait_for`, `ros:invoke`. Two concurrent pieces of
   work are two regions of a `<parallel>`.
4. **ROS work never transitions by itself.** It ends with an outcome; the
   chart's transitions (written directly or as `ros:outcome`) decide what
   follows (SCXML section 4.10).
5. **Names are ROS names.** Topic, service and action names follow ROS rules:
   relative names resolve in the node's namespace, `~/` in its private
   namespace, and launch-time remapping applies. A chart never hard-codes a
   robot's namespace.
6. **Code by name only.** Guards, builders and handlers are names of methods
   on the model object (`ros:model`). Expressions in the document stay in the
   restricted datamodel: comparisons of datamodel values, `In(...)`, no
   function calls.
7. **Expansion.** The loader expands the extension into plain SCXML plus
   listener callbacks before the engine sees the document. `ros2 statechart
   export --plain` writes the expanded document, which any SCXML tool can
   read.

## 2. Declarations (children of `<scxml>`)

### `ros:model`

```xml
<ros:model class="my_robot.mission:Mission"/>
```

The Python class providing guards and builders. Instantiated once by the node
as `Mission(node)`; it may declare ROS parameters on the node and keep
publishers or clients of its own. Exactly one per chart (child charts have
their own).

### `ros:param`

```xml
<datamodel><data id="max_retries" expr="3"/></datamodel>
<ros:param name="max_retries"/>
```

Declares a ROS parameter of the node whose value initialises the datamodel
variable of the same name; the `<data>` expression is the default. The
validator requires the `<data>` element to exist.

## 3. Inputs: ROS to events (children of `<scxml>`)

| Element | Attributes | Event sent |
|---|---|---|
| `ros:subscribe` | `topic`, `type`, `event`, optional `when` (guard on the message), `data` (builder of event data), `qos` (`default`, `sensor`, `latched`) | `event` with `msg` (and builder data) for each message that passes `when` |
| `ros:service_server` | `name`, `type`, optional `event` (fixed name, or `{field}` to take it from a request field), `reply` (builder) | the event, then the reply after the macrostep (below) |
| `ros:action_server` | `name`, `type`, `event`, optional `accept` (guard), `feedback` (builder), `result_on` (event name), `result` (builder), `cancel_event` | `event` with `goal` when accepted; `cancel_event` on a cancel request |
| `ros:timer` | `period` (s), `event` | `event` every period |

**Service replies.** A request becomes an event; after the event is
processed, the node replies with `handled` (whether a transition was taken),
`refusal` (the reason, when a `ros:refuse` matched) and the active states.
The package provides a generic `statechart_ros_msgs/srv/SendEvent`
(event name and JSON data in, the three fields out); a user service type
gets them through the `reply` builder.

**Action servers.** A chart that accepts long tasks (a mission accepting
jobs) declares one: the goal becomes an event, feedback is built from the
chart's state on every change, and the result is sent when `result_on` occurs
(typically `done.state.<task>`). The chart decides when a goal is refused
(`accept`) and what a cancel means (`cancel_event`).

## 4. What a state does (children of `<state>`, `<parallel>`, `<final>`)

### Invokes: work owned by the state

Started on entry, cancelled on exit, started again on re-entry.

| Element | Attributes | Outcome statuses |
|---|---|---|
| `ros:action` | `server`, `type`, `goal` (builder), optional `feedback` (handler), `feedback_event`, `server_timeout` (s, default 5), `cancel_timeout` (s, default 5) | `succeeded`, `aborted`, `canceled` (by the server), `rejected`, `unavailable` |
| `ros:service_call` | `service`, `type`, `request` (builder), optional `response` (handler), `timeout` | `succeeded`, `failed`, `timeout`, `unavailable` |
| `ros:wait_for` | `topic`, `type`, optional `when` (guard), `timeout` | `succeeded`, `timeout` |
| `ros:invoke` | `kind` (`package/name`, from an entry point), any attributes the kind declares | declared by the kind |

**Builders and handlers.** The node calls them with what they need:

```python
class Mission:
    def dock_goal(self, goal, datamodel):        # goal: an empty Goal message
        goal.dock_id = datamodel.station
        return goal
    def dock_feedback(self, feedback, datamodel): # stored, or turned into an event
        datamodel.dock_state = feedback.state
```

**Cancellation.** When the state is left, the node cancels the goal (or
abandons the call) and waits up to `cancel_timeout` for the server to
confirm before another goal is sent to the same server, so a new goal never
races the cancel of the old one.

### Outcomes

```xml
<state id="DOCKING">
  <ros:action server="dock_robot" type="nav2_msgs/action/DockRobot" goal="dock_goal"/>
  <ros:outcome status="succeeded" target="DOCKED"/>
  <ros:outcome status="aborted" cond="retries_left" target="RETRY"/>
  <ros:outcome status="aborted" target="FAILED"/>
  <ros:outcome status="*" target="FAILED"/>
</state>
```

`status` is one status, a space-separated list, or `*` for the rest. `cond`
names an extra guard on the model. The result, error code and message are
in the event data for guards and handlers (`result`, `error_code`,
`error_msg`). Each outcome expands into:

```xml
<transition event="done.invoke.DOCKING" cond="sc_ros_outcome_DOCKING_1" target="DOCKED"/>
```

with a generated model callback that checks the status, so a chart never
depends on how the engine wraps invoke data. Generated names start with
`sc_ros_` (the engine never resolves names starting with `_`, ENGINE.md
E15); model methods and data ids must not use that prefix. The validator requires every
status of the invoke kind to be covered.

### Outputs: done once

```xml
<state id="DOCKED">
  <ros:on_entry publish="dock/hold" type="std_msgs/msg/Bool" value="true"/>
  <ros:on_exit  publish="dock/hold" type="std_msgs/msg/Bool" value="false"/>
  <ros:on_entry call="led/set" type="my_interfaces/srv/SetColor" request="green_request"/>
</state>
```

`ros:on_entry` and `ros:on_exit` take one of `publish` (with `value`, a
literal, or `message`, a builder), `call` (a service, fire and forget, with
`request`) or `set_param` (`node`, `name`, `value`). They run in document
order, after the standard `<onentry>` and before the standard `<onexit>`
respectively. Publishers to the same topic in several states share one
publisher (latched if any of them says `qos="latched"`).

### Timeouts

```xml
<state id="WAITING_FOR_DOOR">
  <ros:after delay="30" event="door_timeout"/>
  <transition event="door_timeout" target="REPORT"/>
</state>
```

`ros:after` sends `event` once, `delay` seconds (ROS time, so simulation
time under `use_sim_time`) after the state is entered, unless the state is
left first. A state may declare several. It is not an invoke: it has no
outcome and does not count against rule 3. Standard `<send delay>` is
refused by the validator, because the engine holds the caller of `send`
until a delayed event is due ([ENGINE.md](ENGINE.md) E13).

### Refusals

```xml
<state id="MANUAL">
  <ros:refuse event="start_job" reason="mode is MANUAL: switch to automatic first"/>
</state>
```

Expands into a standard targetless transition (without `type`, ENGINE.md
E17) that handles the event without changing state and records the reason
(an `<assign>` to the datamodel variable `sc_ros_refusal`, which the loader
declares), which the service or action reply returns.

```xml
<state id="OK">
  <ros:ignore event="e_stop_released" reason="nothing to release"/>
</state>
```

`ros:ignore` marks an event as deliberately without effect in that state, so
the validator does not report it; unlike a refusal, the reply says
`handled`. The validator treats refused and ignored events as handled; any
other unhandled input event is an error, because a command that vanishes
without an answer is a defect on a robot. Transition selection is standard
SCXML (innermost state first), so a refusal in a child overrides a
transition of its parent for the same event.

## 5. Child charts

```xml
<state id="DOCK_PROCEDURE">
  <ros:chart src="package://my_robot/charts/dock.scxml"/>
  <ros:outcome status="succeeded" target="DOCKED"/>
</state>
```

`ros:chart` runs another chart in the same node as the state's invoke: it
starts on entry, is stopped (with all its invokes) on exit, and its final
state's `donedata` is the outcome. `ros:action` on a `statechart_ros_msgs/action/RunStatechart`
server runs a chart hosted by another node the same way.

## 6. Validation (`ros2 statechart validate`)

Errors stop the node from starting and fail CI:

1. the document is well-formed SCXML 1.0 (W3C schema) and every `ros:`
   element is in an allowed place with its required attributes;
2. engine checks: no unreachable or trap states;
3. every message, service and action type exists in the environment;
4. every name used as guard, builder or handler exists on the model class;
5. every invoke's statuses are covered by outcomes;
6. every input event is handled or refused in every reachable configuration
   of the region that receives it;
7. no state has two invokes; no `ros:` element in executable content;
8. `ros:param` names match `<data>` ids;
9. no `<send>` with `delay` or `delayexpr` (use `ros:after`); no `<data>` id
   `state` (the engine's own attribute, ENGINE.md E18) and no name starting
   `sc_ros_`; state ids are Python identifiers (the engine derives callback
   names such as `on_invoke_<state>` from them).

## 7. Compatibility with other SCXML tools

The extension follows SCXML's extension rules: its own namespace, and no
transitions caused by extension content. The W3C schema accepts the
elements in the places of rule 1 (its extension points validate them
`lax`ly; `statechart_ros/schema/scxml_ros.xsd` adds this namespace's schema).
What other tools do with foreign elements is undefined by the standard
(Appendix A.2). Measured on 2026-10-26 (phase P0) with the three charts of
[compat/charts](../compat/charts/) (a minimal chart, nested states with deep
history, and the README example as it stood in P0); the scripts and exact
versions are in [compat/tools](../compat/tools/README.md). To separate the
effect of `ros:` elements from that of `datamodel="python"`, which no other
tool knows, each chart also ran with `datamodel` set to `null` or
`ecmascript`, with and without its `ros:` elements.

| Tool | Loads | `ros:` elements | Rejects | Keeps `ros:` on save |
|---|---|---|---|---|
| W3C schema (xmllint, libxml2) | all three validate | validated by our schema when it is loaded, else skipped (`lax`) | n/a | n/a |
| Qt SCXML 6.4.2 (`qscxmlc`, `QScxmlStateMachine::fromFile`) | not with `datamodel="python"`; yes with `null` or `ecmascript` | ignored silently; the charts run as their plain controls do | `Unsupported data model 'python' in scxml` (datamodel only) | n/a (no writer) |
| Qt Creator SCXML editor | not tested: graphical only, no command-line load or save | | | |
| Apache Commons SCXML 2.0-SNAPSHOT (no 2.0 release exists) | lenient reader: all variants | lenient: ignored with one warning per element; runs as the plain controls | strict reader: `Ignoring unknown or invalid element <model> in namespace ...`; executor: `Unsupported SCXML document datamodel "python"` | no: elements dropped, `xmlns:ros` kept |
| Apache Commons SCXML 0.9 (2008) | only without a `datamodel` attribute (any value fails; 0.9 predates it) | ignored with one warning per element | n/a | no: elements dropped |
| scxmlgui (git `1e09202`, `fsm-editor.jar` 2016) | all three, `python` included | kept as each state's other content | none | yes, and the result validates; but `datamodel` is dropped, and `ros:` elements move after the transitions of their state |
| AS2FM (git `3252344`, 0.0.1, not on PyPI) | none of the three | under `<scxml>`: dropped; inside states: rejected (`unexpected tag on_entry`: it strips namespaces) | also, independent of `ros:`: no `<history>`, no `<parallel>`, requires `name` on `<scxml>` and `type` on `<data>` | no |

For a tool that rejects the extension or the datamodel, use
`ros2 statechart export --plain`, which writes the expanded document without
`ros:` elements (the `datamodel` attribute still has to be changed for Qt and
Commons SCXML, whose guards are then evaluated in their own datamodels).
