# Testing charts (`statechart_ros_testing`)

A chart is code: test it the way you test code, at four levels, from the
fastest to the slowest. Each level answers a different question; most charts
need the first three, and one simulation test per behaviour that depends on
the real servers.

| Level | Question | Tool | Speed |
|---|---|---|---|
| Validation | Is the chart well formed, are names and types right, is every command answered in every configuration? | `ros2 statechart validate` (FORMAT.md section 6) | instant, in CI with no ROS graph |
| Scenario | Does this sequence of events and outcomes lead where I expect, with the outputs I expect? | `chart_under_test`, `run_scenario` | milliseconds, no ROS |
| Property | Does any sequence break a rule that must always hold? | `chart_machine` (Hypothesis) | seconds, no ROS |
| Simulation | Do the real servers do what the chart assumes? | `launch_testing` with `ChartWatcher` | minutes, nightly |

## Validation

Run `ros2 statechart validate path/to/chart.scxml` in CI (`--model-path` for
models not installed yet). It catches what a test would only find by
accident: an outcome status nobody handles, a command refused nowhere, a
misspelled guard.

## Scenarios: `chart_under_test`

The chart runs in the same runner as on the robot (one worker, the engine,
the generated outcome conditions), but its invokes are fakes with the real
kinds' statuses, time moves only when the test advances it, and outputs are
recorded instead of published.

```python
from statechart_ros_testing import chart_under_test

def test_dock_retries_once():
    with chart_under_test('charts/mission.scxml',
                          outcomes={'DOCKING': ['aborted', 'succeeded']}) as t:
        t.send('dock')
        assert t.active('DOCKED')
        assert t.finished == [('DOCKING', 'aborted'), ('DOCKING', 'succeeded')]
        assert ('publish', 'dock/hold', True) in t.outputs
```

- `outcomes` per state: a status for every attempt, a list (one per attempt),
  a dict with `status` and outcome data (`error_code`, `error_name`,
  `result`...), a function `(attempt, attrs)`, or `'pending'` (the default).
- `t.complete(state, status, **data)` ends a pending invoke; `t.pending()`
  lists them.
- `t.send(event, data)` returns the answer a service caller would get:
  `handled`, `refusal`, `configuration`.
- `t.advance(seconds)` fires `ros:after` timeouts that fall due, in order.
- `t.data` is the datamodel; `t.outputs` the recorded `ros:on_entry` and
  `ros:on_exit` outputs; `t.cancelled` the states whose invoke was cancelled.

A child chart (`ros:chart`) is one invoke here, like any other: its
statuses are the child's top-level `<final>` ids, and the test ends it with
`t.complete('DOCKING', 'docked', tries=1)`. Test the child chart with its own
`chart_under_test`.

Every call returns once the chart has settled (all queued events and invoke
outcomes processed), so tests need no sleeps.

The same steps can be written as YAML and run with `run_scenario`
(`statechart_ros_testing/scenario.py` documents the keys); the patrol
example's scenario is `statechart_ros_testing/test/scenarios/patrol.yaml`.

**What to assert:** the configuration after each step (`expect`), refusals
with their reasons, outcome routing (each status goes where it should),
history (pause, resume returns to the same state), outputs at entry and exit,
timeouts just before and just after they are due.

## Properties: `chart_machine`

Scenarios check the paths you thought of. A property test sends random
sequences of the chart's input events, ends pending invokes with random
statuses of their kinds, advances time, and checks invariants after every
step; Hypothesis shrinks a failure to the shortest sequence that breaks it.

```python
from hypothesis import settings, strategies as st
from hypothesis.stateful import run_state_machine_as_test
from statechart_ros_testing.properties import chart_machine

def still_while_paused(config):
    return not ('PAUSED' in config and {'TO_A', 'TO_B', 'DOCKING'} & config)

def test_properties():
    machine = chart_machine('patrol.scxml', [still_while_paused],
                            event_data={'battery': st.fixed_dictionaries(
                                {'percentage': st.floats(0, 1)})})
    run_state_machine_as_test(machine, settings=settings(deadline=None))
```

Invariants take any of `config` (frozenset of active states), `datamodel`,
`outputs` and `test`. Good invariants are safety rules (never move while
stopped), resource rules (never navigate on a low battery), consistency of
outputs with states (the last value on `charging` matches `CHARGING`), and
structure (one task state at a time). `event_data` gives the data events need
for their guards. `statechart_ros_testing/test/test_patrol_coverage.py` runs
four invariants on the patrol example and shows that removing one transition
from the chart is caught.

## Simulation: `ChartWatcher`

```python
from statechart_ros_testing.launch import ChartWatcher

watcher = ChartWatcher(test_node, '/patrol', service='command')
assert watcher.wait_for_configuration({'IDLE'}, timeout=120.0)
assert watcher.send('start').handled
assert watcher.wait_for(lambda: 'succeeded' in watcher.outcomes('TO_B'), 180.0)
```

It follows the chart's `~/status` and `~/transitions` and calls its
`SendEvent` service (`~/send_event` with `debug_events`, or the chart's own
`ros:service_server`). Keep simulation tests for what only the real servers
show (does Nav2 reach the pose, does the dock succeed); run them nightly
(`.github/workflows/nightly.yml` and `statechart_ros_nav2/test_sim/`).
