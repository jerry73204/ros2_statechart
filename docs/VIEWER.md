# Viewer and terminal tools

## The web viewer (`statechart_ros_viewer`)

```bash
ros2 run statechart_ros_viewer viewer          # http://<robot>:8095/
ros2 run statechart_ros_viewer viewer --ros-args -p port:=8096 -p address:=127.0.0.1
```

The viewer node finds every chart by its `~/structure` topic (every
`discovery_period` seconds) and follows its `~/status` and `~/transitions`.
It serves one page and its files itself (the layout library, dagre, is
vendored with its licences), so the page works on a robot's network with
no internet access; nothing else runs on the robot: no rosbridge, no build
tools.

The page shows, for the chart chosen at the top (or named in the URL,
`http://robot:8095/#/patrol`):

- **the diagram**: nested states as boxes in boxes, parallel states with a
  dashed border and `∥`, history states as `H`/`H*`, a child chart
  (`ros:chart`) inside the state that runs it, with a dotted border and its
  states' ids qualified (`DOCKING/APPROACH`), the `ros:` annotations
  under each state's name (its invoke, outputs, timeouts, refusals),
  transitions labelled with their event and guard, outcomes with their
  statuses. Drag to pan, scroll to zoom, *Fit* to see it all again;
- **large charts**: double-click a compound or parallel state to fold it into
  one box (it stays lit while it is active, and its arrows go to the box),
  and again to open it; *Expand all* opens every folded state. *Notes*
  shows or hides the annotations under each name; a chart with more than 25
  states opens without them. Folded states and the notes switch are
  remembered per chart in the browser;
- **live state**: active states are lit; the transitions an event took
  flash;
- **running work**: each invoke with its elapsed time and its last feedback
  summary (distance remaining, docking phase...);
- **data**: the datamodel values the chart node publishes
  (`datamodel_publish`);
- **transitions**: every event with what it did, refusals in red, ignored
  events in grey with their reason; click an
  entry to see the configuration after it ("time travel"), and *Back to
  live* to return;
- **send an event**: when the chart node runs with `debug_events:=true`, a
  form sends any of its input events with JSON data.

Parameters: `port` (8095), `address` (`0.0.0.0`: every interface; set
`127.0.0.1` to keep it on the machine), `history` (transitions kept per
chart, 1000), `discovery_period` (1 s).

HTTP interface, for other tools: `GET /api/charts`,
`GET /api/chart?node=/patrol` (structure, status, recent transitions),
`GET /api/events` (server-sent events `charts`, `structure`, `status`,
`transition`), `POST /api/send` (`{"node", "event", "data"}`; only for charts
with `debug_events`).

### Replaying a run

The introspection topics are ordinary topics, so a bag of them is the whole
history of a chart:

```bash
ros2 bag record /patrol/structure /patrol/status /patrol/transitions
ros2 run statechart_ros_viewer viewer &
ros2 bag play --delay 3 my_run          # the delay lets the viewer subscribe first
```

The page then shows the run as it happened, and keeps the last status when
the bag ends. Playing the bag again starts a new transition log, as does a
chart node that restarts: the viewer notices that the chart counts its
events from the start again.

## Terminal: `ros2 statechart`

| Verb | Does |
|---|---|
| `list` | the running charts (nodes with `~/structure`) |
| `show /patrol` | the states as a tree, active ones marked `*`, running invokes with elapsed time and feedback, the last event, published data |
| `echo /patrol [-n N] [--timeout S]` | transitions as they happen: time, event, data, what was taken, or why it was refused or ignored |
| `send /patrol start '{"key": 1}'` | a debug event (needs `debug_events:=true`); prints handled, refused or ignored with the reason, or not handled, and the configuration; exit code 0, 1 (error) or 2 (not handled) |
| `validate`, `diagram`, `export --plain`, `interface` | the offline verbs (FORMAT.md section 6, DESIGN.md section 7, INTERFACES.md) |
