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


"""The offline verbs: validate, diagram, export (P1)."""

import os
import subprocess

from lxml import etree
import pytest
from statechart_ros.loader import load_chart
import statechart_ros.validate

HERE = os.path.dirname(os.path.abspath(__file__))
README = os.path.join(HERE, 'charts', 'readme_example.scxml')
FIXTURES = os.path.join(HERE, 'fixtures')
W3C = os.path.join(os.path.dirname(statechart_ros.validate.__file__), 'schema', 'w3c',
                   'scxml.xsd')


def ros2(*args):
    return subprocess.run(['ros2', 'statechart', *args], capture_output=True, text=True,
                          check=False, timeout=60)


def test_readme_chart_is_in_step_with_the_readme():
    readme = os.path.join(HERE, '..', '..', 'README.md')
    if not os.path.exists(readme):
        pytest.skip('not in the source tree')
    with open(readme) as f:
        text = f.read()
    block = text.split('```xml\n', 1)[1].split('```', 1)[0]
    with open(README) as f:
        assert f.read() == block


def has_docking():
    try:
        from nav2_msgs.action import DockRobot  # noqa: F401
    except ImportError:
        return False
    return True


@pytest.mark.skipif(not has_docking(), reason='the README example docks (Nav2 Jazzy on)')
def test_validate_passes_the_readme_example():
    result = ros2('validate', README, '--model-path', FIXTURES)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'ok' in result.stdout


def test_validate_fails_with_file_line_and_rule(tmp_path):
    bad = tmp_path / 'bad.scxml'
    with open(README) as f:
        bad.write_text(f.read().replace('<ros:outcome status="*" target="IDLE"/>', ''))
    result = ros2('validate', str(bad), '--model-path', FIXTURES)
    assert result.returncode == 1
    assert f'{bad}:' in result.stdout
    assert '[rule 5]' in result.stdout


def test_validate_reports_a_missing_model():
    result = ros2('validate', README)
    assert result.returncode == 1
    assert '[rule 4]' in result.stdout


@pytest.mark.parametrize('fmt, marker', [
    ('mermaid', 'stateDiagram-v2'), ('dot', 'digraph statechart'), ('md', '| Source |')])
def test_diagram_text_formats(fmt, marker):
    result = ros2('diagram', README, '-f', fmt)
    assert result.returncode == 0, result.stderr
    assert marker in result.stdout
    assert 'dock_robot' in result.stdout


def test_diagram_svg(tmp_path):
    out = tmp_path / 'readme.svg'
    result = ros2('diagram', README, '-o', str(out))
    assert result.returncode == 0, result.stderr
    svg = etree.parse(str(out)).getroot()
    assert svg.tag.endswith('svg')
    assert b'DOCKING' in out.read_bytes()


def test_export_plain_loads_and_passes_the_w3c_schema(tmp_path):
    out = tmp_path / 'plain.scxml'
    result = ros2('export', '--plain', README, '-o', str(out))
    assert result.returncode == 0, result.stderr
    schema = etree.XMLSchema(etree.parse(W3C))
    doc = etree.parse(str(out))
    assert schema.validate(doc), schema.error_log
    assert b'ros:' not in out.read_bytes()
    from statemachine.io import load
    sm = load(str(out))()
    assert 'IDLE' in sm.configuration_values


def test_export_twice_gives_the_same_document(tmp_path):
    first = ros2('export', '--plain', README).stdout
    path = tmp_path / 'readme_example.scxml'
    path.write_text(first)
    second = ros2('export', '--plain', str(path)).stdout
    assert first == second
    assert load_chart(str(path)).plain_doc in second


def test_verbs_are_listed():
    out = ros2('--help').stdout
    for verb in ('validate', 'diagram', 'export'):
        assert verb in out
