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


"""A model with every method the test charts name."""


class TestModel:
    """Guards, builders and handlers for the loader and validator tests."""

    def __init__(self, node=None):
        self.node = node

    def ok(self, **kwargs):
        return True

    def msg_true(self, msg):
        return msg.data

    def goal(self, goal):
        return goal

    def on_feedback(self, feedback):
        pass

    def request(self, request):
        return request

    def response(self, response):
        pass

    def message(self, msg):
        return msg

    def reply(self, response):
        return response

    def retries_left(self, **kwargs):
        return True

    not_callable = 3
