# Model checking: notes on AS2FM

Status: notes, not a feature. Read 2026-10-26 from the AS2FM documentation
(<https://convince-project.github.io/AS2FM/>); re-check before relying on
them.

## What AS2FM reads

AS2FM converts a robotic system description into a model checker's input:

- input: ROS nodes as SCXML, an environment model as SCXML, a behavior tree
  (BehaviorTree.CPP XML) with SCXML plugins for its leaves, and the property
  to check (given in JANI, inside a high-level XML system description);
- output: JANI, checked with `smc_storm` (statistical model checking), or
  plain SCXML for SCAN.

Its SCXML has its own ROS elements: `ros_time_rate` with
`ros_rate_callback`; `ros_topic_publisher`, `ros_topic_subscriber`,
`ros_topic_callback`, `ros_topic_publish` with `field`; the service
elements `ros_service_server`, `ros_service_client`,
`ros_service_send_request`, `ros_service_handle_request`,
`ros_service_send_response`, `ros_service_handle_response`; and `bt_*`
elements for behavior tree ticks and ports. Its how-to page marks ROS
actions as to be written while its conversion page lists them as supported.
The documentation does not say which core SCXML features (compound states,
parallel states, history, `<invoke>`, delayed `<send>`) the conversion to
JANI supports; events become shared variables, since JANI has none.

## What an exporter would have to do

`ros2 statechart export --plain` already writes the chart as plain SCXML
(the `ros:` elements expanded into states, transitions and generated
conditions, [FORMAT.md](FORMAT.md) section 7). An AS2FM exporter would
additionally:

1. map inputs to AS2FM elements: `ros:subscribe` to `ros_topic_subscriber`
   and `ros_topic_callback`, `ros:timer` to `ros_time_rate`,
   `ros:service_server` to `ros_service_server` with handle/send response;
2. map outputs: `ros:on_entry publish` to `ros_topic_publisher` and
   `ros_topic_publish` in `<onentry>`;
3. replace invokes by request/response pairs (`ros_service_client`, action
   elements if supported) plus states waiting for the response, and model
   cancellation on exit explicitly;
4. replace model methods (guards and builders in Python) by expressions over
   message fields, or by an environment model: AS2FM cannot run Python;
5. flatten hierarchy, parallel regions and history if AS2FM's conversion
   does not support them;
6. write the environment (Nav2 servers, battery) as SCXML models, which is
   most of the work and specific to each robot.

## Assessment

Steps 1 and 2 are mechanical. Steps 3 to 6 change the chart's meaning in
ways that need checking themselves, and step 6 is per robot. Worth building
when a project needs guarantees beyond tests and property tests (for
example a safety argument for a certification), starting with a probe: export
the tutorial square chart by hand, run it through AS2FM, and record which
SCXML features survive. Until then the property tests of
`statechart_ros_testing` (random event sequences against invariants) are the
cheaper check.
