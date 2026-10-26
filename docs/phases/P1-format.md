# P1: Format, loader and validator

## Goal

Read a chart with the `ros:` extension, check it completely, and produce the
engine class plus the description of what each state does in ROS, without
starting ROS.

## Delivers

- `statechart_ros.loader`:
  - parse with ElementTree (DTDs refused), collect `ros:` elements with
    their positions, reject misplaced ones;
  - expand sugar into standard SCXML: `ros:outcome` into `done.invoke`
    transitions with generated conditions, `ros:refuse` and `ros:ignore`
    into internal transitions with an `<assign>`;
  - remove the remaining `ros:` elements and load the expanded document with
    `statemachine.io.load(..., trusted=False)`;
  - return a `ChartSpec`: the engine class, the inputs, per-state invokes and
    outputs, model class, parameters, and a structure description (the
    future `StatechartStructure`).
- `statechart_ros.validate`: the checks of [FORMAT.md](../FORMAT.md)
  section 6. Type existence is checked through `rosidl_runtime_py`
  utilities; model names by importing the class. Each finding has a file,
  line, rule number and message.
- `statechart_ros_cli` verbs `validate`, `diagram` (Mermaid, Graphviz,
  Markdown table, with `ros:` annotations) and `export --plain`.
- An XSD for the `ros:` namespace, so editors with the W3C SCXML schema plus
  ours complete and check both.

## Checks

- Unit tests for every element and every validation rule, with one passing
  and at least one failing fixture per rule.
- The README example validates, diagrams and exports; the exported plain
  document loads in python-statemachine and passes the W3C schema.
- Round trip: expanding then exporting is stable (exporting twice gives the
  same document).

## Leaves out

The node, ROS communication, introspection topics.
