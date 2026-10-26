# P6: Composition

## Goal

Split large behaviour into charts without losing statechart guarantees.

## Delivers

- `ros:chart src=...`: a child chart invoked by a state in the same node;
  stopped with all its invokes when the state is left; its final state's
  `donedata` becomes the outcome.
- Hosting a chart as an action server (`statechart_ros_msgs/action/RunStatechart`):
  goal starts it, feedback is its status, cancel exits it, result is its
  final state; a parent chart invokes it with `ros:action`.
- Introspection of child charts nested in the parent's structure and status,
  so the viewer shows them inside their state.
- Guidance: when a child chart in the same node, when a chart in another
  node (another owner, computer or lifecycle), and why parallel regions that
  share guards stay in one chart.

## Checks

- Leaving the parent state stops a child chart and cancels its invokes, in
  the same node and across nodes.
- The viewer shows a child chart's live state inside its parent.

## Leaves out

Distributed parallel regions (deliberately not supported).
