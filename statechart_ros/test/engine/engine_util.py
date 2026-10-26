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


"""Helpers for the engine tests: inline charts and waiting for a condition."""

import time

from statemachine.io import load

ROS_NS = 'https://github.com/jerry73204/ros2_statechart/ns/1'


def chart(body, initial='a', extra_ns=''):
    """Return an SCXML document with the given body and initial state."""
    return (
        '<scxml xmlns="http://www.w3.org/2005/07/scxml" '
        f'xmlns:ros="{ROS_NS}" {extra_ns} version="1.0" datamodel="python" '
        f'initial="{initial}">{body}</scxml>'
    )


def load_chart(body, initial='a', **kwargs):
    """Load an inline chart and return its class."""
    return load(chart(body, initial), format='scxml', **kwargs)


def config(sm):
    """Return the active state ids as a set."""
    return set(sm.configuration_values)


def wait_until(predicate, timeout=2.0, period=0.01):
    """Poll predicate until it is true or the timeout expires; return its last value."""
    deadline = time.monotonic() + timeout
    while True:
        value = predicate()
        if value or time.monotonic() >= deadline:
            return value
        time.sleep(period)
