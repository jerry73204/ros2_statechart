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


"""``ros2 statechart interface``."""

import sys

from statechart_ros_cli.offline import check_interface, interface_text
from statechart_ros_cli.verb import VerbExtension


class InterfaceVerb(VerbExtension):
    """Print a chart's interface (topics, services, actions) as YAML, or check a file."""

    def add_arguments(self, parser, cli_name):
        parser.add_argument('chart', help='chart file or package:// URL')
        parser.add_argument('-o', '--output', help='output file (default: standard output)')
        parser.add_argument('--check', metavar='FILE',
                            help='compare with an interface file; exit 1 if they differ')

    def main(self, *, args):
        if args.check:
            return 1 if check_interface(args.chart, args.check) else 0
        text = interface_text(args.chart)
        if args.output:
            with open(args.output, 'w') as f:
                f.write(text)
        else:
            sys.stdout.write(text)
        return 0
