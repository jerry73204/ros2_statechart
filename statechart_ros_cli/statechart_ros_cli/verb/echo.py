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


"""``ros2 statechart echo``."""

from statechart_ros_cli.online import echo
from statechart_ros_cli.ros_node import cli_node
from statechart_ros_cli.verb import VerbExtension


class EchoVerb(VerbExtension):
    """Print a chart's transitions as they happen."""

    def add_arguments(self, parser, cli_name):
        parser.add_argument('node', help='the node hosting the chart, e.g. /patrol')
        parser.add_argument('-n', '--count', type=int, help='stop after this many')
        parser.add_argument('--timeout', type=float, help='stop after this many seconds')

    def main(self, *, args):
        with cli_node() as node:
            try:
                echo(node, args.node.rstrip('/'), args.count, timeout=args.timeout)
            except KeyboardInterrupt:
                pass
        return 0
