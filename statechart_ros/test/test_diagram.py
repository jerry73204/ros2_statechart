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

"""Diagrams of a chart whose transitions cross compound states' borders."""

import re
import shutil
import subprocess

from charts_util import spec_of
import pytest
from statechart_ros.diagram import _mermaid_ids, graphviz, mermaid

# Parallel regions; a compound state with a history state; transitions into
# a compound state, out of one, to its own descendant, from a descendant to
# outside its parents, and into a history state.
CHART = """
<parallel id="run">
  <state id="mode" initial="START">
    <state id="START">
      <transition event="go" target="AUTO"/>
    </state>
    <state id="AUTO" initial="EXEC">
      <transition event="manual" target="MANUAL"/>
      <state id="EXEC" initial="IDLE">
        <history id="EXEC_H" type="shallow"><transition target="IDLE"/></history>
        <transition event="reset" target="IDLE"/>
        <transition event="hold" target="HELD"/>
        <state id="IDLE"><transition event="job" target="DOCK"/></state>
        <state id="DOCK" initial="APPROACH">
          <state id="APPROACH"><transition event="near" target="STOPPING"/></state>
          <state id="STOPPING"><transition event="stopped" target="DONE"/></state>
        </state>
        <state id="DONE"><transition event="next" target="IDLE"/></state>
      </state>
      <state id="HELD"><transition event="resume" target="EXEC_H"/></state>
    </state>
    <state id="MANUAL"><transition event="auto" target="AUTO"/></state>
  </state>
  <state id="end" initial="OK">
    <state id="OK"><transition event="stop" target="end.STOP"/></state>
    <state id="end.STOP"><transition event="release" target="OK"/></state>
  </state>
</parallel>
"""


def structure():
    return spec_of(CHART, initial='run', model=False).structure()


def mermaid_parents(text):
    """Return the subgraph each node is declared in, from the flowchart's nesting."""
    parents, stack = {}, ['']
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('subgraph '):
            nid = line.split()[1].split('[')[0]
            parents[nid] = stack[-1]
            stack.append(nid)
        elif line == 'end':
            stack.pop()
        else:
            m = re.match(r'(\w+)\(', line)
            if m and not m.group(1).endswith('_init') and m.group(1) != 'init':
                parents[m.group(1)] = stack[-1]
    assert stack == ['']
    return parents


def test_mermaid_keeps_every_state_in_its_parent():
    s = structure()
    text = mermaid(s)
    assert text.startswith('flowchart TB\n')
    ids = _mermaid_ids({state['id']: state for state in s['states']})
    assert ids['end'] != 'end' and ids['end.STOP'] == 'end_STOP'     # a reserved word, a dot
    parents = mermaid_parents(text)
    for state in s['states']:
        assert parents[ids[state['id']]] == (ids[state['parent']] if state['parent'] else '')


def test_mermaid_draws_every_transition():
    s = structure()
    edges = [line for line in mermaid(s).splitlines()
             if re.match(r'\s+\w+ (-->|==>)', line) and '_init ' not in line
             and not line.strip().startswith('init ')]
    expected = sum(len(t['targets']) for t in s['transitions'] if t['targets'])
    assert len(edges) == expected


@pytest.mark.skipif(shutil.which('dot') is None, reason='Graphviz is not installed')
def test_graphviz_lays_out_without_warnings():
    result = subprocess.run(['dot', '-Tsvg'], input=graphviz(structure()).encode(),
                            capture_output=True, check=False)
    assert result.returncode == 0, result.stderr.decode()
    assert result.stderr.decode() == ''
