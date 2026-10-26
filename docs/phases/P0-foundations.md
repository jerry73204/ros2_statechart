# P0: Foundations

## Goal

A repository that builds and tests in CI, with the engine's behaviour pinned
by tests, so later phases build on verified facts.

## Delivers

- Workspace layout: one directory per package (`statechart_ros_msgs`,
  `statechart_ros`, `statechart_ros_nav2`, `statechart_ros_cli`,
  `statechart_ros_viewer`, `statechart_ros_testing`,
  `python_statemachine_vendor`), empty but buildable.
- `python_statemachine_vendor`: installs python-statemachine 3.2.2 with the
  `io` extra into the package's install space; `package.xml` declares its
  own dependencies (PyYAML, jsonschema) as rosdep keys.
- GitHub Actions: build and test on ROS 2 Jazzy (`ros-tooling/setup-ros`,
  `ros-tooling/action-ros-ci`, pinned to release tags), lint.
- **Engine probes as tests** (`statechart_ros/test/engine/`): every row of
  [ENGINE.md](../ENGINE.md) (E1 to E12) as a pytest case, plus the open
  questions answered and turned into tests:
  - order of `done.invoke` against events sent from the handler;
  - deep history entering a state with an invoke;
  - parallel exit order and invoke cancellation when a whole parallel state
    is left;
  - thread use under many short invokes.
- **SCXML tool compatibility**: three sample charts (minimal, nested with
  history, the README example) run through the W3C schema (xmllint), Qt
  SCXML (`qscxmlc` and Qt Creator's editor), Apache Commons SCXML, scxmlgui
  and AS2FM. For each tool: loads, ignores `ros:` elements, rejects, keeps
  them on save. The table goes into [FORMAT.md](../FORMAT.md) section 7.

## Checks

- CI green on Jazzy.
- All engine probe tests pass on 3.2.2; ENGINE.md has no open question left
  without a test.
- Compatibility table filled for every listed tool.

## Leaves out

Any loader or node code.
