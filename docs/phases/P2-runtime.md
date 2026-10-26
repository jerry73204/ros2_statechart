# P2: Runtime node

## Goal

Run a validated chart on a robot: ROS inputs become events, states run their
invokes and outputs, and the chart's state is published.

## Delivers

- `statechart_ros_msgs`: the messages, services and action of
  [DESIGN.md](../DESIGN.md) section 5.
- `statechart_node` (lifecycle node), parameters `chart`, `debug_events`,
  `status_rate_max`, `datamodel_publish` (variables shown in status):
  - one event queue and one worker thread; multi-threaded executor for
    callbacks and futures;
  - inputs: `ros:subscribe`, `ros:service_server` (with replies after the
    macrostep), `ros:action_server` (accept, feedback, result, cancel),
    `ros:timer`, `ros:param`;
  - invokes: `ros:action`, `ros:service_call`, `ros:wait_for`, and
    `ros:invoke` kinds from the entry point group `statechart_ros.invokes`;
    cancellation with confirmation and `cancel_timeout`;
  - outputs: `ros:on_entry` / `ros:on_exit` publish, call, set_param;
  - introspection: `~/structure`, `~/status`, `~/transitions`,
    `~/get_structure`, `~/send_event` (when enabled);
  - lifecycle: configure validates and loads, activate starts,
    deactivate exits every state and cancels every invoke.
- A launch file and a minimal example chart driving `turtlesim`
  (move, wait for a pose, react to a service), runnable without Nav2.

## Checks

- Unit tests per input, invoke and output kind against in-process test
  servers.
- Leaving a state cancels its running action goal, and a second goal to the
  same server is sent only after the cancel is confirmed.
- No engine call from two threads (asserted in tests by instrumenting the
  worker).
- Deactivate cancels all invokes; activate restarts from the initial
  configuration.
- The turtlesim example runs in CI with `launch_testing`.

## Leaves out

Nav2, the viewer, child charts.
