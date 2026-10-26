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


"""
Property tests: random event sequences against invariants (Hypothesis).

``chart_machine`` builds a Hypothesis ``RuleBasedStateMachine`` from a chart:
its rules send the chart's input events (with data drawn from strategies the
test gives), end pending invokes with any status of their kind, and advance
time; after every step each invariant is checked. A failure shrinks to a
minimal sequence of steps.

    def never_moves_while_paused(config):
        return not ({'PAUSED'} <= config and {'TO_A', 'TO_B'} & config)

    Machine = chart_machine('patrol.scxml', [never_moves_while_paused],
                            event_data={'battery': battery_strategy})
    TestPatrol = Machine.TestCase
"""

from hypothesis import strategies as st
from hypothesis.stateful import invariant, precondition, rule, RuleBasedStateMachine
from statechart_ros.loader import load_chart
from statechart_ros.runtime import call_with
from statechart_ros.validate import import_model, receivers
from statechart_ros_testing.chart_test import ChartTest


class InvariantViolated(AssertionError):
    """An invariant was false after a step."""


def chart_machine(path, invariants, event_data=None, events=None, params=None,
                  model_factory=None, outcomes=None, max_advance=30.0, text=None):
    """
    Return a RuleBasedStateMachine class exploring a chart.

    ``invariants`` are functions taking any of ``config`` (a frozenset of
    active states), ``datamodel``, ``outputs`` and ``test``. ``event_data``
    maps event names to strategies of event data dicts (default: no data).
    ``events`` defaults to the chart's input events. ``outcomes`` scripts
    invokes as in ``chart_under_test`` (the default leaves them pending, for
    the machine to end).
    """
    spec = load_chart(path, params=params, text=text)
    names = sorted(events if events is not None else receivers(spec))
    data_for = dict(event_data or {})
    model_class = import_model(spec.model_class) if spec.model_class else None
    script = dict(outcomes or {})

    def make_model():
        if model_factory is not None:
            return model_factory()
        if model_class is None:
            return None
        try:
            return model_class(None)
        except TypeError:
            return model_class()

    class ChartMachine(RuleBasedStateMachine):

        def __init__(self):
            super().__init__()
            self.test = ChartTest(spec, make_model(),
                                  {k: (list(v) if isinstance(v, list) else v)
                                   for k, v in script.items()})

        @rule(event=st.sampled_from(names) if names else st.nothing(), draw=st.data())
        def send(self, event, draw):
            strategy = data_for.get(event)
            data = draw.draw(strategy, label=f'{event} data') if strategy is not None else {}
            self.test.send(event, data)

        @precondition(lambda self: bool(self.test.pending()))
        @rule(draw=st.data())
        def complete(self, draw):
            state = draw.draw(st.sampled_from(self.test.pending()), label='invoke of')
            kind = self.test.runner.kinds[state]
            status = draw.draw(st.sampled_from(list(kind.statuses)), label='status')
            self.test.complete(state, status)

        @rule(seconds=st.floats(min_value=0.1, max_value=max_advance))
        def advance(self, seconds):
            self.test.advance(seconds)

        @invariant()
        def invariants_hold(self):
            available = {'config': frozenset(self.test.configuration()),
                         'datamodel': self.test.data, 'outputs': list(self.test.outputs),
                         'test': self.test}
            for check in invariants:
                if not call_with(check, available):
                    raise InvariantViolated(
                        f'{check.__name__} is false in {sorted(available["config"])}')

        def teardown(self):
            self.test.close()

    ChartMachine.__name__ = f'{spec.name}_machine'
    return ChartMachine
