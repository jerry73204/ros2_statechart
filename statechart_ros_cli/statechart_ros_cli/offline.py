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


"""The work of the offline verbs, callable without the ros2 command."""

import sys

from statechart_ros.diagram import render
from statechart_ros.loader import ChartError, load_chart
from statechart_ros.validate import errors, validate


def add_model_path(paths):
    """Make extra directories importable, for models of charts not yet installed."""
    for path in reversed(paths or []):
        if path not in sys.path:
            sys.path.insert(0, path)


def validate_charts(charts, check_types=True, check_model=True, out=None):
    """Validate charts and print the findings; return the number of errors."""
    out = out or sys.stdout
    count = 0
    for chart in charts:
        try:
            spec = load_chart(chart)
        except ChartError as exc:
            for finding in exc.findings:
                print(finding, file=out)
            count += len(exc.findings)
            continue
        except OSError as exc:
            print(f'{chart}: cannot read: {exc}', file=out)
            count += 1
            continue
        findings = validate(spec, check_types=check_types, check_model=check_model)
        for finding in findings:
            print(finding, file=out)
        n = len(errors(findings))
        count += n
        warnings = len(findings) - n
        print(f'{chart}: {"ok" if n == 0 else f"{n} error(s)"}'
              + (f', {warnings} warning(s)' if warnings else ''), file=out)
    return count


FORMATS = {'.svg': 'svg', '.png': 'png', '.pdf': 'pdf', '.dot': 'dot', '.gv': 'dot',
           '.mmd': 'mermaid', '.md': 'md'}


def diagram(chart, fmt=None, output=None):
    """Return the diagram of a chart (bytes for images, str for text formats)."""
    if fmt is None:
        fmt = 'mermaid'
        if output:
            for ext, name in FORMATS.items():
                if output.endswith(ext):
                    fmt = name
    spec = load_chart(chart)
    return render(spec.structure(), fmt)


def export_plain(chart):
    """Return the expanded, extension-free SCXML of a chart."""
    spec = load_chart(chart)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + spec.plain_doc + '\n'


def interface_text(chart, out=None):
    """Return a chart's interface file text; print its warnings to ``out``."""
    from statechart_ros.interface import chart_interface, dump
    out = out or sys.stderr
    iface = chart_interface(chart)
    for w in iface['warnings']:
        print(f'warning: {w}', file=out)
    return dump(iface, chart)


def check_interface(chart, path, out=None):
    """Compare a chart with an interface file; print the changes; return their number."""
    from statechart_ros.interface import chart_interface, compare, load
    out = out or sys.stdout
    changes = compare(load(path), chart_interface(chart))
    for severity, message in changes:
        print(f'{severity}: {message}', file=out)
    if changes:
        print(f'{path} does not match {chart}: regenerate it with `ros2 statechart '
              f'interface {chart} -o {path}`', file=out)
    return len(changes)
