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


"""The model of the turtlesim example chart (examples/turtlesim_demo.scxml)."""


class TurtleDemo:
    """Goal builders and guards of the turtlesim demo."""

    def __init__(self, node=None):
        self.node = node

    def face_east(self, goal):
        goal.theta = 0.0
        return goal

    def far_enough(self, msg):
        return msg.x > 7.0

    def home(self, request):
        request.x = 5.5
        request.y = 5.5
        request.theta = 0.0
        return request
