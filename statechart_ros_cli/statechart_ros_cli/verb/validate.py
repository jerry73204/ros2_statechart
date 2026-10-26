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


"""``ros2 statechart validate``."""

from statechart_ros_cli.offline import add_model_path, validate_charts
from statechart_ros_cli.verb import VerbExtension


class ValidateVerb(VerbExtension):
    """Check charts: schema, structure, ROS types, model names, inputs (exit 1 on errors)."""

    def add_arguments(self, parser, cli_name):
        parser.add_argument('charts', nargs='+', help='chart files or package:// URLs')
        parser.add_argument('--model-path', action='append', default=[],
                            help='a directory to import model classes from (repeatable)')
        parser.add_argument('--no-types', action='store_true',
                            help='skip the check that ROS interface types exist')
        parser.add_argument('--no-model', action='store_true',
                            help='skip importing the model class')

    def main(self, *, args):
        add_model_path(args.model_path)
        count = validate_charts(args.charts, check_types=not args.no_types,
                                check_model=not args.no_model)
        return 1 if count else 0
