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
   on the model object (`ros:model`). Expressions in the document are chart
   expressions (section 8): a small, validated subset of Python with
   comparisons of datamodel values, `In(...)`, no function calls.
7. **Documentation.** Every `ros:` element accepts an optional `doc`
   attribute: what the element means for the packages around the chart
   (when a producer publishes, what a command does). It has no effect on
   the run; `ros2 statechart interface` carries it ([INTERFACES.md](INTERFACES.md)).
8. **Expansion.** The loader expands the extension into plain SCXML plus
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
publishers or clients of its own. At most one per chart (child charts have
their own); a chart without guards, builders or handlers needs none.

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
| `ros:service_server` | `name`, `type`, optional `event` (fixed name, or a template whose `{field}` parts are taken from the request's fields, such as `{command}` or `command.{command}`), `reply` (builder) | the event, then the reply after the macrostep (below) |
| `ros:action_server` | `name`, `type`, `event`, optional `accept` (guard), `feedback` (builder), `result_on` (event name), `result` (builder), `result_status` (builder), `cancel_event`, `cancel_waits` (bool) | `event` with `goal` when accepted; `cancel_event` on a cancel request |
| `ros:timer` | `period` (s), `event` | `event` every period |

**Service replies.** A request becomes an event; after the event is
processed, the node replies with `handled` (whether a transition was taken),
`refusal` (the reason, when a `ros:refuse` matched) and the active states.
The package provides a generic `statechart_ros_msgs/srv/SendEvent`
(event name and JSON data in, the three fields out); a user service type
gets them through the `reply` builder.

**Action servers.** A chart that accepts long tasks (a mission accepting
jobs) declares one: the goal becomes an event (data `goal`), feedback is
built after every processed event, and the result is sent when a transition
on `result_on` is taken (typically `done.state.<task>`). The chart decides
when a goal is refused (`accept`, or a goal event that is not handled, which
aborts the goal) and what a cancel means (`cancel_event`; without one,
cancel requests are rejected). One goal runs at a time; another is rejected
while it runs.

How the goal ends: by default a goal reaching `result_on` succeeds, and a
cancel request ends it at once as canceled. `result_status` names a model
method returning `succeeded`, `aborted` or `canceled` for the goal reaching
`result_on` (it receives, by argument name, `result`, `configuration` and
`cancel_requested`, as `result` does). With `cancel_waits="true"` a cancel
request only sends `cancel_event`: the goal goes on until the chart reaches
`result_on`, so a chart can finish what a cancel starts (back out, park)
before the goal ends; `result_status` then says whether it ended canceled.

**Event data.** A subscription's event carries `msg`, a service request's
`request`, an action goal's `goal`; builders named in `data` add entries.
The names the engine passes itself (`event`, `machine`, `model`, `state`,
`source`, `target`, `transition`, `event_data`, `error`) cannot be event
data. Guards (`when`, `accept`) and builders run on the worker.

## 4. What a state does (children of `<state>`, `<parallel>`, `<final>`)

### Invokes: work owned by the state

Started on entry, cancelled on exit, started again on re-entry.

| Element | Attributes | Outcome statuses |
|---|---|---|
| `ros:action` | `server`, `type`, `goal` (builder), optional `feedback` (handler), `feedback_event`, `server_timeout` (s, default 5), `cancel_timeout` (s, default 5) | `succeeded`, `aborted`, `canceled` (by the server), `rejected`, `unavailable` |
| `ros:service_call` | `service`, `type`, `request` (builder), optional `response` (handler), `success` (guard on the response; without it every response succeeds), `timeout` (s, default 10), `server_timeout` (s, default 5) | `succeeded`, `failed`, `timeout`, `unavailable` |
| `ros:wait_for` | `topic`, `type`, optional `when` (guard), `timeout` | `succeeded`, `timeout` |
| `ros:invoke` | `kind` (`package/name`, from an entry point), any attributes the kind declares | declared by the kind |

**Builders and handlers.** The node calls them with what they need, by
argument name: a method receives those of `goal`, `request`, `response`,
`feedback`, `msg`, `datamodel` (and, for outcome guards, `status`, `result`,
`error_code`, `error_name`, `error_msg`) that its signature names. Every
model method runs on the node's worker thread, never concurrently with the
engine or with another model method, so models need no locks:

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
`request`), `set_param` (the parameter name, with `value` and optional
`node`, the node whose parameter is set; default this node) or `run` (a
model method).

`run` calls the model method on the worker inside the macrostep, so what it
changes on the model is seen by the guards of the transitions that follow
(an eventless transition out of the state, for example). It receives, by
argument name, `datamodel`, `state` (the state's id), `event` (the name of
the event whose transition entered or left the state, `''` for an eventless
one) and `data` (that event's data). Use it for bookkeeping that belongs to
entering or leaving a state, never for ROS work (rule 2): its return value
is ignored, and an exception is logged like a failed output. A `value` is
read as YAML: a mapping sets the message's fields by name, anything else is
assigned to the field `data` (as in `std_msgs`). They run in document
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
left first. `delay` is a number, or the id of a `<data>` value read when the
state is entered (a `ros:param`, so the timeout is a parameter:
`<ros:after delay="retry_delay" event="retry"/>`). A state may declare several. It is not an invoke: it has no
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
declares), which the service or action reply returns. `event` may name
several events, separated by spaces. An optional `cond` (a chart expression,
section 8) makes the refusal apply only when it holds, so one state can give
different reasons:

```xml
<ros:refuse event="start" cond="In('PAUSED')" reason="paused: resume first"/>
<ros:refuse event="start" reason="stopped: release the stop, then resume"/>
```

```xml
<state id="OK">
  <ros:ignore event="e_stop_released" reason="nothing to release"/>
</state>
```

`ros:ignore` marks an event as deliberately without effect in that state, so
the validator does not report it; unlike a refusal, the reply says
`handled`, with its reason in `ignored` (`"ignored"` when it gives none): the
`SendEvent` reply, the `~/transitions` and `~/status` messages, `ros2
statechart send` and `echo`, and the viewer's log show it. The validator treats refused and ignored events as handled; any
other unhandled input event is an error, because a command that vanishes
without an answer is a defect on a robot. Transition selection is standard
SCXML (innermost state first), so a refusal in a child overrides a
transition of its parent for the same event.

## 5. Child charts

```xml
<state id="DOCK_PROCEDURE">
  <ros:chart src="dock.scxml" autoforward="true"/>
  <ros:outcome status="docked" target="DOCKED"/>
  <ros:outcome status="failed" target="RECOVER"/>
</state>
```

`ros:chart` is the state's invoke: it runs another chart in the same node.

| Attribute | Meaning |
|---|---|
| `src` | the child chart: a path relative to the parent's file, an absolute path or a `package://` URL |
| `autoforward` | `true`: every event the parent processes while the state is active is also posted to the child (default `false`) |
| `data` | a builder returning a dict: the child's initial datamodel values by `<data>` id; a key the child does not declare ends the invoke with an error |

- **Life.** The child starts on entry to the state, on its own queue and
  worker, and is stopped on exit the standard way (`sc_ros.stop`): its
  states are exited, its outputs run their exit side and its invokes are
  cancelled before the parent's exit completes.
- **Statuses.** The child's top-level `<final>` ids are the invoke's
  statuses: reaching `<final id="docked">` ends the invoke with status
  `docked`, so `ros:outcome status="docked"` routes it and rule 5 checks the
  outcomes against those ids. The final state's `<donedata>` is the
  outcome's `result` (guards receive it as `result`) and its event data.
- **Inputs.** A child chart declares no inputs (`ros:subscribe`,
  `ros:timer`, `ros:service_server`, `ros:action_server`): it gets events
  from its parent, through `autoforward`. It may declare its own
  `ros:model`, `ros:param`/`<data>`, invokes and outputs.
- **Introspection.** The parent's structure contains the child's states
  under the invoking state, with qualified ids (`DOCK_PROCEDURE/APPROACH`),
  and the parent's status lists the child's active states and invokes with
  the same ids, so `ros2 statechart show`, `echo` and the viewer show the
  child live inside its parent.
- **In another node.** A node started with the parameter `run_as_action`
  (for example `~/run`) does not start its chart on activation: it serves a
  `statechart_ros_msgs/action/RunStatechart` action there and runs the chart
  once per goal. The goal's `data` (JSON object) overrides datamodel values
  by id, feedback is the status, the result holds the final state id and
  the donedata (JSON). A parent runs it with the ordinary
  `ros:action server="/dock/run" type="statechart_ros_msgs/action/RunStatechart"`;
  leaving the parent's state cancels the goal, which stops the child chart
  and cancels its invokes. The goal's `chart` must be empty or name the
  node's own chart. The outcome statuses are then those of `ros:action`
  (`succeeded` when the child reaches a top-level final).

### Slots: options from other packages

```xml
<state id="RUN_STEP">
  <ros:slot name="step" select="step_kind" data="step_data"
            outcomes="succeeded failed cancelled"/>
  <ros:outcome status="succeeded" target="STEP_DONE"/>
  <ros:outcome status="*" target="STEP_FAILED"/>
</state>
```

`ros:slot` is a `ros:chart` whose child is picked on entry from the charts
that installed packages register for the slot.

| Attribute | Meaning |
|---|---|
| `name` | the slot; its options are the charts registered for it |
| `select` | a datamodel value; its value on entry names the option |
| `outcomes` | the slot's statuses; every option's top-level `<final>` ids must be among them (rule 5) |
| `data` | as for `ros:chart` |
| `autoforward` | as for `ros:chart` |

A package registers options by installing
`share/ament_index/resource_index/statechart_slots/<package>`, a YAML
mapping from slot to option to chart (a path relative to the package's share
directory, or a `package://` URL):

```yaml
step:
  PASS_DOOR: charts/pass_door.scxml
```

- **Loading.** The options are resolved when the parent is loaded and
  validated as its child charts; the set does not change while the node
  runs. Two packages registering the same option is an error naming both;
  a slot without options is a warning.
- **Running.** No option under the selected name ends the invoke at once
  with an empty status and the reason in `error_msg` (`status="*"` routes
  it). Otherwise the option runs exactly as a `ros:chart` child.
- **Introspection.** Each option's states are in the structure under
  `STATE/OPTION` (`RUN_STEP/PASS_DOOR/WAIT_OPEN`), and the running option's
  status and transitions use the same ids.
- **Interface.** A slot's options are not in the parent's interface file
  (they depend on what is installed); each option's package ships its own.
- `ros2 statechart slots [SLOT]` lists the registered options.

## 6. Validation (`ros2 statechart validate`)

Errors stop the node from starting and fail CI:

1. the document is well-formed SCXML 1.0 (W3C schema, plus the schema of
   this namespace, `statechart_ros/schema/scxml_ros.xsd`, which editors can
   use too) and every `ros:` element is known, in an allowed place, with its
   required attributes and values that fit their roles (numbers, types,
   QoS names);
2. engine checks: the engine loads the document; no state is unreachable
   from the initial configuration (the engine's own graph walk); no trap
   state, that is an atomic state that is not `<final>` and neither it nor
   any ancestor has a transition (outcomes and refusals included);
3. every message, service and action type exists in the environment;
4. every name used as guard, builder or handler exists on the model class;
5. every invoke's statuses are covered by outcomes;
6. every input event is handled, refused or ignored in every configuration:
   some active state or one of its ancestors has a transition whose event
   descriptor matches it (guards are not evaluated; a guarded transition
   counts, and at run time an unhandled event is reported). Configurations
   are the structural ones (every combination the nesting allows, which
   includes the reachable ones); past 20000 the rule is skipped with a
   warning. Input events are those of `ros:subscribe`, `ros:timer`,
   `ros:action_server` (`event`, `cancel_event`) and fixed `event`s of
   `ros:service_server`; a service server without a fixed event (such as
   `SendEvent`) adds the chart's command events: every event a transition
   names except `done.*`, `error.*`, events the chart sends or raises,
   `ros:after` and feedback events, and other inputs' events;
7. no state has two invokes; no `ros:` element in executable content;
   no inputs in a child chart and no chart that includes itself (directly
   or through its children); every child chart passes these rules too;
8. `ros:param` names, and `ros:after` delays given by name, match `<data>` ids;
9. no `<send>` with `delay` or `delayexpr` (use `ros:after`); no `<data>` id
   `state` (the engine's own attribute, ENGINE.md E18), `event`, `source`,
   `target`, `transition`, `event_data`, `machine`, `model` (names the engine
   passes to callbacks, which a datamodel value could not be read under) or
   `datamodel`, and no name starting `sc_ros_`; state ids are Python identifiers (the engine derives callback
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

Other tools get `ros2 statechart export --plain`, the only export: the
`ros:` elements removed, the sugar expanded into standard transitions, and
`datamodel="python"` kept, because the chart's expressions are Python
(section 8). Tools without a Python datamodel (Qt SCXML, Commons SCXML 0.9)
will still refuse the exported document; there is deliberately no export
that rewrites the datamodel, since the chart's conditions would then mean
something else. To look at a chart, use `ros2 statechart diagram` or the web
viewer.

## 8. Expressions (chart expressions, ns/1)

Conditions and values in a chart are written in one small subset of Python,
the same on every supported Python (3.10 and later), and checked by the
validator (rule 10) before a chart runs.

**Where.** `cond` of `<transition>` (and of `<if>`/`<elseif>`), `expr` of
`<data>` and `<assign>`. The `location` of `<assign>` is a datamodel name
only (no attribute or item targets). `ros:` attributes are not expressions:
they name model methods, states or events.

**Allowed.**

| Form | Examples |
|---|---|
| names: datamodel values, model guard names, event data (`msg`, `request`, `goal`, and the names a `data` builder adds), with attribute chains, read only | `retries`, `ready`, `msg.data`, `goal.station` |
| literals: `int`, `float`, `str`, `True`, `False`, `None` | `3`, `0.5`, `'home'` |
| comparisons `==` `!=` `<` `<=` `>` `>=`, one per comparison | `retries < max_retries` |
| `and`, `or`, `not`, parentheses | `In('OK') and not paused` |
| arithmetic `+` `-` `*` `/` and unary `-` on numbers | `laps + 1` |
| `In('<state id>')` with a literal id of an existing state | `In('DOCKED')` |

**Refused.** Any other call; indexing and slicing; comprehensions, `lambda`,
f-strings, `:=`, conditional expressions; `**`, `//`, `%` and bitwise
operators; chained comparisons, `is`, `in`; and the JavaScript tokens the
engine would translate (`&&`, `||`, `===`, `!==`, `true`, `false`, `null`,
ENGINE.md E20), so that a chart stays Python.

**Scalars only.** There are no list, tuple, dict or set literals, in
`<data expr>` as anywhere else. Values such as poses, waypoint lists or
tables are configuration and belong in parameter files: a `ros:param`
whose `<data>` default is `None` takes any parameter type, arrays included,
and Nav2 kinds read named poses from a YAML file (NAV2.md). Event data can
still carry structured messages (`msg.pose`), read through attributes.

**No truthiness.** A condition must be boolean: a comparison, a datamodel
value whose initial literal is `True` or `False`, `In(...)`, a guard name, or
`and`, `or`, `not` of those. A guard method must return a `bool`; another
return value raises `error.execution` at run time.

**Reserved names.** Names starting with `_`, names starting with `sc_ros_`,
and Python keywords cannot be datamodel names or guard names.

**Why Python.** Models, guards and builders are Python; ROS launch files
evaluate Python (`$(eval ...)`); one language means one set of rules for
types and comparison. ECMAScript was rejected for its implicit coercions
(`'1' == 1`, truthiness of `[]`). A second language such as CEL could be
added later as generated callbacks without changing this one.

**Versioning.** The subset is part of the format `ns/1`. Additions are
backwards compatible and raise the format's minor version; a removal would
be a new namespace.
