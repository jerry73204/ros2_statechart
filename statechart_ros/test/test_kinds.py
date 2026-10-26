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


"""Invoke kinds from the entry point group statechart_ros.invokes (P2)."""

from statechart_ros import kinds
from statechart_ros.kinds import InvokeKind


class FromEntryPoint(InvokeKind):
    name = 'example/from_entry_point'
    statuses = ('succeeded',)


class FakeEntryPoint:
    name = 'example/from_entry_point'

    def load(self):
        return FromEntryPoint


def test_kinds_are_found_through_entry_points(monkeypatch):
    def fake_entry_points(group):
        assert group == 'statechart_ros.invokes'
        return [FakeEntryPoint()]

    monkeypatch.setattr(kinds, 'entry_points', fake_entry_points)
    try:
        kinds.registry(reload=True)
        assert kinds.get_kind('example/from_entry_point') is FromEntryPoint
        assert kinds.get_kind('ros/action').name == 'ros/action'
        assert kinds.get_kind('example/missing') is None
    finally:
        monkeypatch.undo()
        kinds.registry(reload=True)
