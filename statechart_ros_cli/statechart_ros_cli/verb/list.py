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


"""``ros2 statechart list``."""

from statechart_ros_cli.online import chart_nodes
from statechart_ros_cli.ros_node import cli_node
from statechart_ros_cli.verb import VerbExtension


class ListVerb(VerbExtension):
    """List the running charts (nodes publishing ~/structure)."""

    def add_arguments(self, parser, cli_name):
        parser.add_argument('--wait', type=float, default=1.0,
                            help='seconds to wait for discovery (default 1)')

    def main(self, *, args):
        with cli_node() as node:
            for chart in chart_nodes(node, args.wait):
                print(chart)
        return 0
