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
Scenario tests: events in, expected configurations, data and outputs out.

A scenario is YAML (or the same structure as a dict)::

    chart: ../examples/patrol.scxml     # relative to the scenario file
    params: {battery_low: 0.3}
    outcomes: {WAIT_NAV2: succeeded}    # scripted invokes; others are pending
    steps:
      - expect: [IDLE, AUTO]
      - send: start
        handled: true
        expect: [TO_A]
      - send: battery
        data: {percentage: 0.2}
        expect: [DOCKING]
        expect_not: [TO_A]
      - complete: DOCKING               # end a pending invoke
        status: succeeded
        expect: [CHARGING]
        outputs: [[publish, charging, true]]   # outputs of this step
      - send: start
        refused: a patrol is running
      - advance: 5.0                    # seconds, fires ros:after timeouts
      - datamodel: {laps: 1}

Each step may combine one action (``send`` with optional event ``data``,
``complete`` with optional ``status``, ``advance``) with any of the checks
(``expect``, ``expect_not``, ``configuration``, ``handled``, ``refused``,
``datamodel``, ``outputs``). ``run_scenario`` raises ``ChartTestError`` naming the step.
"""

import os

from statechart_ros_testing.chart_test import chart_under_test, ChartTestError
import yaml

ACTIONS = ('send', 'complete', 'advance')
CHECKS = ('expect', 'expect_not', 'configuration', 'handled', 'refused', 'ignored', 'datamodel',
          'outputs')
ARGUMENTS = ('data', 'status', 'note')


def load_scenario(source):
    """Return the scenario dict and the directory relative paths start from."""
    if isinstance(source, dict):
        return source, os.getcwd()
    with open(source) as f:
        return yaml.safe_load(f), os.path.dirname(os.path.abspath(source))


def run_scenario(source, model=None, chart=None):
    """Run a scenario; return the ChartTest (closed) for further checks."""
    scenario, base = load_scenario(source)
    path = chart or scenario['chart']
    if not os.path.isabs(path) and not path.startswith('package://'):
        path = os.path.join(base, path)
    test = chart_under_test(path, outcomes=scenario.get('outcomes'), model=model,
                            params=scenario.get('params'))
    try:
        for index, step in enumerate(scenario.get('steps', []), start=1):
            unknown = set(step) - set(ACTIONS) - set(CHECKS) - set(ARGUMENTS)
            if unknown:
                raise ChartTestError(f'step {index}: unknown keys {sorted(unknown)}')
            try:
                _run_step(test, step)
            except AssertionError as exc:
                raise ChartTestError(f'step {index} ({_describe(step)}): {exc}') from None
    finally:
        test.close()
    return test


def _describe(step):
    for key in ACTIONS:
        if key in step:
            return f'{key} {step[key]}'
    return 'check'


def _run_step(test, step):
    before = len(test.outputs)
    result = None
    if 'send' in step:
        result = test.send(step['send'], step.get('data'))
    elif 'complete' in step:
        test.complete(step['complete'], step.get('status', 'succeeded'))
    elif 'advance' in step:
        test.advance(float(step['advance']))
    config = set(test.configuration())
    for state in step.get('expect', []):
        assert state in config, f'{state} is not active; active: {sorted(config)}'
    for state in step.get('expect_not', []):
        assert state not in config, f'{state} is active'
    if 'configuration' in step:
        assert config == set(step['configuration']), f'configuration {sorted(config)}'
    if 'handled' in step:
        assert result is not None, 'handled needs a send'
        assert result.handled == step['handled'], f'handled is {result.handled}'
    if 'refused' in step:
        assert result is not None, 'refused needs a send'
        assert result.refusal == step['refused'], f'refusal is {result.refusal!r}'
    if 'ignored' in step:
        assert result is not None, 'ignored needs a send'
        assert result.ignored == step['ignored'], f'ignored is {result.ignored!r}'
    for key, value in step.get('datamodel', {}).items():
        got = getattr(test.data, key)
        assert got == value, f'datamodel {key} is {got!r}, expected {value!r}'
    if 'outputs' in step:
        got = [(o.action, o.target, o.value) for o in test.outputs[before:]]
        want = [tuple(o) for o in step['outputs']]
        assert got == want, f'outputs {got}'
