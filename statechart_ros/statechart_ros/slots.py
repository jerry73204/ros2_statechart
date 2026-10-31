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


"""
The options of slots, registered by installed packages (FORMAT.md section 5).

A package registers child charts for a slot by installing
``share/ament_index/resource_index/statechart_slots/<package>``, a YAML
mapping from slot to option to chart; a chart is a path relative to the
package's share directory or a ``package://`` URL::

    step:
      PASS_DOOR: charts/pass_door.scxml
"""
import os

import yaml

RESOURCE_TYPE = 'statechart_slots'


class Option:
    """One registered option: its slot, name, chart file and package."""

    def __init__(self, slot, name, path, package):
        self.slot = slot
        self.name = name
        self.path = path
        self.package = package

    def __repr__(self):
        return f'Option({self.slot!r}, {self.name!r}, {self.path!r}, {self.package!r})'


def registered():
    """
    Return every registration as ``(options, problems)``.

    ``options`` maps slot to option name to a list of Options (more than one
    when packages disagree); ``problems`` lists registrations that cannot be
    read.
    """
    from ament_index_python.resources import get_resource, get_resources
    from statechart_ros.loader import resolve_path
    options = {}
    problems = []
    for package in sorted(get_resources(RESOURCE_TYPE)):
        content, prefix = get_resource(RESOURCE_TYPE, package)
        where = os.path.join(prefix, 'share', 'ament_index', 'resource_index', RESOURCE_TYPE,
                             package)
        try:
            table = yaml.safe_load(content) or {}
        except yaml.YAMLError as exc:
            problems.append(f'{where}: not YAML: {exc}')
            continue
        if not isinstance(table, dict):
            problems.append(f'{where}: must map slots to options')
            continue
        share = os.path.join(prefix, 'share', package)
        for slot, entries in table.items():
            if not isinstance(entries, dict):
                problems.append(f'{where}: slot "{slot}" must map options to charts')
                continue
            for name, chart in entries.items():
                chart = str(chart)
                try:
                    path = resolve_path(chart) if chart.startswith('package://') \
                        else os.path.normpath(os.path.join(share, chart))
                except LookupError as exc:
                    problems.append(f'{where}: {slot}/{name}: {exc}')
                    continue
                options.setdefault(str(slot), {}).setdefault(str(name), []).append(
                    Option(str(slot), str(name), path, package))
    return options, problems


def options_for(slot):
    """Return ``(options, problems)`` of one slot: option name to Option, and messages."""
    every, problems = registered()
    found = {}
    for name, candidates in sorted(every.get(slot, {}).items()):
        if len(candidates) > 1:
            packages = ', '.join(c.package for c in candidates)
            problems.append(f'slot "{slot}": option "{name}" is registered by more than one '
                            f'package ({packages})')
            continue
        found[name] = candidates[0]
    return found, problems
