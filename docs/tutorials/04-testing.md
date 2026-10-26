# Tutorial 4: testing a chart

A chart is a specification of behaviour, so it can be tested like one, in
three layers that go from fast to real:

| Layer | Runs | Checks |
|---|---|---|
| validation | `ros2 statechart validate`, in CI and when the node starts | structure, types, model names, every command answered |
| scenarios and properties | `pytest`, without ROS, in milliseconds | the paths you thought of, and random paths against rules |
| simulation | `launch_testing` with the real servers, nightly | what only the real servers show |

This tutorial tests the chart of [tutorial 2](02-nesting-and-history.md)
with the first two layers; the patrol of tutorial 3 has all three
(`statechart_ros_testing/test/test_patrol_coverage.py`,
`statechart_ros_nav2/test_sim/`).

## Install

```bash
sudo apt install ros-jazzy-statechart-ros-testing
```

## A test with `chart_under_test`

The chart runs in the same runner as on the robot, but without ROS: outputs
are recorded instead of published, invokes are fakes whose outcomes the test
scripts, and time moves only when the test advances it. Every call returns
once the chart has settled, so tests need no sleeps.

From `statechart_ros_testing/test/test_tutorial_square.py` (the whole file
is below):

```python
def test_a_whole_square():
    with chart_under_test(SQUARE) as t:
        t.send('go')
        for _ in range(8):           # four sides and four turns, 1.5 s each
            t.advance(1.5)
        assert t.active('IDLE')
        assert t.data.sides == 4
        assert [o.value for o in t.outputs].count({'angular': {'z': 1.5708}}) == 4
```

`t.advance(1.5)` fires the `ros:after` timeouts that fall due; `t.outputs`
lists every `ros:on_entry` and `ros:on_exit` output with its value.

## A scenario in YAML

The same steps as data, for paths worth writing down: each step sends an
event, ends an invoke or advances time, then checks the configuration,
refusals, data and outputs.

<!-- check: file statechart_ros_testing/test/scenarios/square_pause.yaml -->
```yaml
# Tutorial 4: the chart of tutorial 2, step by step, without ROS.
chart: ../../../statechart_ros/examples/tutorial/square_pause.scxml
steps:
  - expect: [IDLE]
  - send: resume              # ignored: answered, nothing changes
    handled: true
    expect: [IDLE]
  - send: go
    expect: [DRAWING, FORWARD]
    outputs: [[publish, turtle1/cmd_vel, {linear: {x: 2.0}}]]
  - advance: 1.4              # the timeout is 1.5 s: not yet
    expect: [FORWARD]
  - advance: 0.1
    expect: [TURN]
    datamodel: {sides: 1}
  - send: pause
    expect: [PAUSED]
    expect_not: [DRAWING]
    outputs: [[publish, turtle1/cmd_vel, {}]]
  - advance: 10.0             # the turn's timeout went with the state
    expect: [PAUSED]
  - send: go
    refused: 'paused: resume or stop first'
  - send: resume              # back to TURN through the history state
    expect: [DRAWING, TURN]
    datamodel: {sides: 2}     # TURN is entered again: its entry runs again
  - advance: 1.5
    expect: [FORWARD]
  - send: stop
    expect: [IDLE]
```

What it pins down: the timeout is exactly 1.5 s, a pause stops the turtle
and cancels the pending timeout, `go` is refused while paused with its
reason, and history returns to `TURN`, whose entry runs again (so a resumed
turn counts a side again: a scenario is where such details become visible
and get decided).

## Properties

Scenarios check the paths you thought of. `chart_machine` sends random
sequences of the chart's input events, ends pending invokes with random
statuses, advances time by random amounts, and checks invariants after every
step; Hypothesis shrinks a failure to the shortest sequence that breaks it:

```python
def still_while_paused(config, outputs):
    """Entering PAUSED stops the turtle: its last command is zero."""
    return 'PAUSED' not in config or outputs[-1].value == {}


def four_sides_at_most(datamodel):
    return 0 <= datamodel.sides <= 4


def test_properties():
    machine = chart_machine(SQUARE, [still_while_paused, four_sides_at_most])
    run_state_machine_as_test(machine, settings=settings(max_examples=50, deadline=None))
```

Good invariants are safety rules (never move while stopped), consistency of
outputs with states, and bounds on data.

## A parent chart with a child

A child chart (`ros:chart`, [tutorial 5](05-composing.md)) is one invoke for
its parent's tests, whose statuses are the child's final states; the child
is tested with its own `chart_under_test`.

## The test file

<!-- check: file statechart_ros_testing/test/test_tutorial_square.py -->
```python
# Copyright 2026 The ros2_statechart Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tutorial 4: tests of the tutorial charts, without ROS."""

import os

from hypothesis import settings
from hypothesis.stateful import run_state_machine_as_test
from statechart_ros_testing import chart_under_test, run_scenario
from statechart_ros_testing.properties import chart_machine

HERE = os.path.dirname(os.path.abspath(__file__))
TUTORIAL = os.path.join(HERE, '..', '..', 'statechart_ros', 'examples', 'tutorial')
SQUARE = os.path.join(TUTORIAL, 'square_pause.scxml')


def test_a_whole_square():
    with chart_under_test(SQUARE) as t:
        t.send('go')
        for _ in range(8):           # four sides and four turns, 1.5 s each
            t.advance(1.5)
        assert t.active('IDLE')
        assert t.data.sides == 4
        assert [o.value for o in t.outputs].count({'angular': {'z': 1.5708}}) == 4


def test_pause_and_resume_scenario():
    run_scenario(os.path.join(HERE, 'scenarios', 'square_pause.yaml'))


def still_while_paused(config, outputs):
    """Entering PAUSED stops the turtle: its last command is zero."""
    return 'PAUSED' not in config or outputs[-1].value == {}


def four_sides_at_most(datamodel):
    return 0 <= datamodel.sides <= 4


def test_properties():
    machine = chart_machine(SQUARE, [still_while_paused, four_sides_at_most])
    run_state_machine_as_test(machine, settings=settings(max_examples=50, deadline=None))


def test_the_parent_of_tutorial_5_with_its_child_as_one_invoke():
    with chart_under_test(os.path.join(TUTORIAL, 'shapes.scxml'),
                          outcomes={'CLEAR': 'succeeded'}) as t:
        t.send('go')
        assert t.pending() == ['DRAW']
        t.complete('DRAW', 'drawn', sides=4)
        assert t.active('DRAW') and t.data.squares == 1    # cleared, second square
        t.complete('DRAW', 'drawn', sides=4)
        assert t.active('IDLE') and t.data.squares == 2
```

Run it:

<!-- check: run -->
```bash
python3 -m pytest -q statechart_ros_testing/test/test_tutorial_square.py
```

In your own package, put such tests in `test/` with `python3-pytest` and
`statechart_ros_testing` as `test_depend`s; `colcon test` runs them, and
`ros2 statechart validate` belongs in the same CI job.

## What to remember

- Validate on every change; test behaviour without ROS, where it is fast
  and exact; keep simulation for what needs the real servers.
- Write scenarios for the paths that matter, invariants for the rules that
  must always hold.

Next: [composing charts](05-composing.md).
