# P8: Interfaces

## Goal

Let packages maintained by different parties work with one chart without
drifting from it. The chart stays the single writer of the state: other
nodes publish facts and send commands, the chart decides. What they share
is the chart's interface (the topics it reads, the services and actions it
serves, the ones it calls and what it publishes), so that interface must be
written down, versioned, checked in each party's CI and checked again on
the robot.

## Delivers

- **The interface of a chart, as data.** `statechart_ros.interface` reads a
  chart (child charts included) and returns its interface:
  - inputs: subscribed topics (`ros:subscribe`, `ros:wait_for`), served
    services and actions, with types, QoS and the events they send; the
    command events when a service has no fixed event;
  - outputs: published topics (`ros:on_entry`/`ros:on_exit publish`), called
    services and actions (outputs and invokes, user kinds included through
    a new `InvokeKind.endpoints`), parameters set on other nodes.

  Names are as written (relative names resolve at run time, rule 5).
- **`doc` on every `ros:` element.** An optional attribute saying what the
  element means for the other party: when a producer publishes, what a
  command does. The interface carries it; the chart is where it is
  reviewed.
- **`ros2 statechart interface CHART`.** Prints the interface as YAML
  (`statechart_interface: 1`). With `--check FILE` it compares the chart with
  a committed interface file and exits 1 if they differ, naming each change
  as breaking (an endpoint removed or its type, QoS or events changed) or
  additive (an endpoint added). CI runs it so an interface change cannot be
  merged without the file changing in the same review.
- **Contract checks for other parties** (`statechart_ros_testing.contract`).
  - `load_interface(path)` reads an interface file, so a party needs the file,
    not the chart or its model.
  - `check_graph(node, interface, ...)` compares the running ROS graph with
    the file. A party launches its own nodes in a launch test and asserts
    that they publish what the chart subscribes to, serve what it calls and
    call what it serves, with matching types and compatible QoS.
- **A check on the robot.** The node parameter `check_interface` (seconds,
  default 5.0, 0 disables) warns once per endpoint that is still missing that
  long after activation: an input topic with no publisher, a called service
  or action with no server. `~/status` does not change; this is a log line
  for whoever starts the robot.
- **Guidance** ([INTERFACES.md](../INTERFACES.md)): single writer; facts and
  commands, not state names; no free-text events from other packages; the
  interface file and its versioning; a timeout on inputs that must keep
  arriving (a state with `ros:after` re-entered on each message).

## Checks

- Unit tests: the interface of the example charts, child charts and a user
  kind; the YAML round trip; `--check` reporting breaking and additive
  changes.
- A launch test: `check_graph` passes with the matching nodes running and
  reports a missing publisher, a wrong type and an incompatible QoS.
- The node test: a missing publisher is warned about once, after the delay.
- The validator accepts `doc` on every `ros:` element.

## Leaves out

- Generating code (stubs, message definitions) from the interface.
- Rate and latency contracts: the interface says what and where, `doc`
  says when; a rate is checked by the chart's own timeouts.
- Distributed charts: a chart remains one node (P6).
