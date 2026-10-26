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


def test_resuming_into_turn_does_not_count_the_side_again():
    with chart_under_test(SQUARE) as t:
        t.send('go')
        t.advance(11.0)                 # in the fourth TURN
        assert t.active('TURN') and t.data.sides == 4
        t.send('pause')
        t.send('resume')                # back into TURN through history
        assert t.active('TURN') and t.data.sides == 4
        t.advance(1.5)
        assert t.active('IDLE')


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
