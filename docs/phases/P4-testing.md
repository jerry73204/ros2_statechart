# P4: Testing kit

## Goal

Let users test their charts the way they test code: fast, without
simulation, and with random exploration that finds unhandled paths.

## Delivers

- `statechart_ros_testing`:
  - `chart_under_test(path, outcomes={...})`: loads a chart with fake invoke
    kinds whose outcomes are scripted per state and per attempt;
  - a scenario runner: events in, expected configurations and outputs out,
    written as YAML or pytest;
  - Hypothesis stateful testing: random sequences of the chart's input
    events and invoke outcomes, user invariants checked after every
    macrostep, shrinking to a minimal failing sequence;
  - `launch_testing` helpers that wait for a configuration on `~/status`.
- A guide: what to assert at each level (unit, scenario, property,
  simulation).

## Checks

- The P3 example's chart is covered by scenarios and by a property test
  with at least three invariants; a deliberately broken copy of the chart is
  caught.

## Leaves out

Model checking (see P7's notes on AS2FM).
