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


"""``ros2 statechart send``."""

import json

from statechart_ros_cli.online import send
from statechart_ros_cli.ros_node import cli_node
from statechart_ros_cli.verb import VerbExtension


class SendVerb(VerbExtension):
    """Send a debug event (the chart node needs debug_events:=true)."""

    def add_arguments(self, parser, cli_name):
        parser.add_argument('node', help='the node hosting the chart, e.g. /patrol')
        parser.add_argument('event', help='event name')
        parser.add_argument('data', nargs='?', default='', help='event data as a JSON object')
        parser.add_argument('--timeout', type=float, default=5.0)

    def main(self, *, args):
        with cli_node() as node:
            try:
                answer = send(node, args.node.rstrip('/'), args.event, args.data, args.timeout)
            except (RuntimeError, json.JSONDecodeError) as exc:
                print(f'error: {exc}')
                return 1
        if answer.refusal:
            print(f'refused: {answer.refusal}')
        else:
            print('handled' if answer.handled else 'not handled')
        print('configuration: ' + ', '.join(answer.configuration))
        return 0 if answer.handled else 2
