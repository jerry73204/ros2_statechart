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


"""``ros2 statechart slots``."""

from statechart_ros_cli.offline import slots_text
from statechart_ros_cli.verb import VerbExtension


class SlotsVerb(VerbExtension):
    """List the options installed packages register for slots (ros:slot)."""

    def add_arguments(self, parser, cli_name):
        parser.add_argument('slot', nargs='?', help='only this slot')

    def main(self, *, args):
        text, problems = slots_text(args.slot)
        print(text, end='')
        return 1 if problems else 0
