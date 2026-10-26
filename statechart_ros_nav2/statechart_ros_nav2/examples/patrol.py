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


"""The model of the patrol example (examples/patrol.scxml)."""


class Patrol:
    """Guards and builders of the patrol chart."""

    def __init__(self, node=None):
        self.node = node

    def battery_data(self, msg):
        return {'percentage': float(msg.percentage)}

    def is_low(self, percentage, datamodel):
        return percentage < datamodel.battery_low

    def is_charged(self, percentage, datamodel):
        return percentage >= datamodel.battery_full

    def pressed(self, msg):
        return bool(msg.data)

    def released(self, msg):
        return not msg.data
