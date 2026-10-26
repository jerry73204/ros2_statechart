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


"""``ros2 statechart show``."""

from statechart_ros_cli.online import fetch, format_tree
from statechart_ros_cli.ros_node import cli_node
from statechart_ros_cli.verb import VerbExtension


class ShowVerb(VerbExtension):
    """Show a chart's states as a tree, active ones marked, with running invokes."""

    def add_arguments(self, parser, cli_name):
        parser.add_argument('node', help='the node hosting the chart, e.g. /patrol')
        parser.add_argument('--timeout', type=float, default=3.0)

    def main(self, *, args):
        with cli_node() as node:
            structure, status = fetch(node, args.node.rstrip('/'), args.timeout)
        if structure is None:
            print(f'no chart structure on {args.node}/structure')
            return 1
        print(format_tree(structure, status))
        return 0
