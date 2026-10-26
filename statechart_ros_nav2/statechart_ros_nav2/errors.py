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
Names of Nav2 error codes, read from the installed nav2_msgs.

Each Nav2 action declares its error codes as constants of its Result
(``FAILED_TO_DETECT_DOCK = 904``); the codes of different actions are in
different ranges, and a navigator reports the code of the action that failed
inside its behavior tree. ``error_name(code)`` returns the lowercase constant
name and ``error_source(code)`` the action that declares it.
"""

import re

ACTIONS = (
    'AssistedTeleop', 'BackUp', 'ComputeAndTrackRoute', 'ComputePathThroughPoses',
    'ComputePathToPose', 'ComputeRoute', 'DockRobot', 'DriveOnHeading', 'DummyBehavior',
    'FollowGPSWaypoints', 'FollowObject', 'FollowPath', 'FollowWaypoints',
    'NavigateThroughPoses', 'NavigateToPose', 'SmoothPath', 'Spin', 'UndockRobot', 'Wait',
)

_tables = {}
_all = None


def snake(name):
    return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()


def result_constants(action):
    """Return {constant name: value} of an action's Result, from nav2_msgs."""
    if action not in _tables:
        import nav2_msgs.action as actions
        cls = getattr(actions, action, None)
        if cls is None:
            _tables[action] = {}
        else:
            meta = type(cls.Result)
            constants = getattr(meta, f'_Metaclass_{action}_Result__constants', {})
            _tables[action] = {k: v for k, v in constants.items() if k != 'NONE'}
    return _tables[action]


def table():
    """Return {code: (name, source action)} over every Nav2 action."""
    global _all
    if _all is None:
        codes = {}
        for action in ACTIONS:
            for name, value in result_constants(action).items():
                codes.setdefault(value, (name.lower(), snake(action)))
        _all = codes
    return _all


def error_name(code, action=None):
    """Return the name of a Nav2 error code ('' for 0 or an unknown code)."""
    if not code:
        return ''
    if action:
        for name, value in result_constants(action).items():
            if value == code:
                return name.lower()
    return table().get(code, ('', ''))[0]


def error_source(code, action=None):
    """Return the action (snake case) that declares a code."""
    if not code:
        return ''
    if action and code in result_constants(action).values():
        return snake(action)
    return table().get(code, ('', ''))[1]
