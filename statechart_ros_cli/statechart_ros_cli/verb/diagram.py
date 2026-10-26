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


"""``ros2 statechart diagram``."""

import sys

from statechart_ros_cli.offline import add_model_path, diagram
from statechart_ros_cli.verb import VerbExtension


class DiagramVerb(VerbExtension):
    """Draw a chart with its ros: annotations: Mermaid, Graphviz, Markdown or an image."""

    def add_arguments(self, parser, cli_name):
        parser.add_argument('chart', help='chart file or package:// URL')
        parser.add_argument('-o', '--output', help='output file; the format follows the '
                            'extension (.svg .png .pdf need Graphviz; .dot .mmd .md)')
        parser.add_argument('-f', '--format', choices=['mermaid', 'dot', 'md', 'svg', 'png',
                                                       'pdf'],
                            help='format (default: from the output file, else mermaid)')
        parser.add_argument('--model-path', action='append', default=[])

    def main(self, *, args):
        add_model_path(args.model_path)
        result = diagram(args.chart, args.format, args.output)
        if args.output:
            mode = 'wb' if isinstance(result, bytes) else 'w'
            with open(args.output, mode) as f:
                f.write(result)
        elif isinstance(result, bytes):
            sys.stdout.buffer.write(result)
        else:
            sys.stdout.write(result)
        return 0
