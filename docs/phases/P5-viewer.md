# P5: Web viewer and terminal tools

## Goal

See a chart's structure and its live state from a browser, and inspect it
from a terminal, on a robot or from a bag.

## Delivers

- `statechart_ros_viewer` node: discovers charts by their `~/structure`
  topics; serves static files and a server-sent-events stream of status and
  transitions; port and bind address as parameters.
- The page: hierarchical layout of nested and parallel states, `ros:`
  annotations on states, active states highlighted, running invoke with
  elapsed time and feedback, transition log with time travel to any past
  configuration, datamodel values, event sending when the chart allows it,
  works with `ros2 bag play`.
- `ros2 statechart list`, `show`, `echo`, `send`.

## Checks

- Viewer tested headless (page loads, receives a structure and a status,
  highlights the right states) in CI: Playwright with Chromium, in its own
  CI job (`statechart_ros_viewer/test_browser/`); the HTTP API and event
  stream are also tested without a browser in every distribution's job.
- A recorded bag of the P3 example replays in the viewer with correct
  highlighting.
- The page works offline on the robot's network (no external assets).

## Leaves out

Editing charts in the browser; a Foxglove panel (later).
