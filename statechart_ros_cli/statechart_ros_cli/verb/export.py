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


"""``ros2 statechart export``."""

import sys

from statechart_ros_cli.offline import export_plain
from statechart_ros_cli.verb import VerbExtension


class ExportVerb(VerbExtension):
    """Write the expanded chart as plain SCXML, without ros: elements, for other tools."""

    def add_arguments(self, parser, cli_name):
        parser.add_argument('chart', help='chart file or package:// URL')
        parser.add_argument('--plain', action='store_true', default=True,
                            help='write plain SCXML (the only export format of version 1)')
        parser.add_argument('-o', '--output', help='output file (default: standard output)')

    def main(self, *, args):
        text = export_plain(args.chart)
        if args.output:
            with open(args.output, 'w') as f:
                f.write(text)
        else:
            sys.stdout.write(text)
        return 0
