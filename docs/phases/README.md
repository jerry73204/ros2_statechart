# Phases

Each phase ends with something usable and checked. A phase file states its
goal, what it delivers, the checks that close it, and what it leaves out.

| Phase | Delivers | Depends on |
|---|---|---|
| [P0](P0-foundations.md) | repository, CI, vendor package, engine probes as tests, SCXML tool compatibility | |
| [P1](P1-format.md) | loader and expansion of the `ros:` extension, validator, `validate` / `diagram` / `export` | P0 |
| [P2](P2-runtime.md) | `statechart_node`: queue, inputs, invokes, outputs, lifecycle, introspection messages | P1 |
| [P3](P3-nav2.md) | `statechart_ros_nav2` and an example robot in simulation | P2 |
| [P1 amendment](P1-format.md#amendment-expression-subset) | chart expressions: a validated Python subset; CI on Humble, Jazzy, Rolling | P3 |
| [P4](P4-testing.md) | `statechart_ros_testing`: fakes, scenarios, property tests, launch tests | P2 |
| [P5](P5-viewer.md) | web viewer, `show` / `echo` / `send` / `list` | P2 |
| [P6](P6-composition.md) | child charts, charts hosted as actions | P2 |
| [P7](P7-release.md) | documentation, tutorials, buildfarm release | P3 to P6 |
| [P8](P8-interfaces.md) | a chart's interface as a file, `interface` verb and `--check`, contract checks for other packages, a check on the robot | P7 |
| [P9](P9-slots.md) | slots: options registered by other packages, picked by the datamodel on entry; `data` for child charts | P6, P8 |

P3, P4, P5 and P6 can proceed in parallel once P2 is done.

## Rules for every phase

- Design changes go into [DESIGN.md](../DESIGN.md) or
  [FORMAT.md](../FORMAT.md) first, then the code.
- Every behaviour has a test; CI (GitHub Actions, ROS 2 Jazzy) runs build,
  lint (`ament_lint_auto`) and tests on every push.
- Examples use public robots and packages only (Nav2's simulated robots,
  the docking server's demo docks).
