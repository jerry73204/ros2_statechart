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


"""Chart expressions (FORMAT.md section 8): one passing and one failing case per construct."""

from charts_util import spec_of
import pytest
from statechart_ros.validate import errors, validate

DATA = ('<datamodel><data id="n" expr="3"/><data id="limit" expr="5.0"/>'
        '<data id="flag" expr="True"/><data id="name" expr="\'home\'"/>'
        '<data id="nothing" expr="None"/></datamodel>')
SUB = '<ros:subscribe topic="t" type="std_msgs/msg/Bool" event="go"/>'


def cond_errors(cond, rule=10):
    body = (DATA + SUB + f'<state id="a"><transition event="go" cond="{cond}" target="b"/>'
            '</state><state id="b"><transition event="go" target="a"/></state>')
    return [f.message for f in errors(validate(spec_of(body))) if f.rule == rule]


def value_errors(expr, location='n'):
    body = (DATA + f'<state id="a"><onentry><assign location="{location}" expr="{expr}"/>'
            '</onentry><transition event="go" target="a"/></state>')
    return [f.message for f in errors(validate(spec_of(body))) if f.rule == 10]


# Allowed: each passes -------------------------------------------------------------

@pytest.mark.parametrize('cond', [
    'n &lt; 4',                         # comparison of a datamodel value and an int
    'limit &gt;= 2.5',                  # float literal
    "name == 'home'",                   # str literal
    'nothing == None',                  # None
    'flag',                             # a boolean datamodel value
    'flag == True',                     # True
    'ok',                               # a guard name (model method)
    "In('a')",                          # In with an existing state
    "n != 1 and In('b') or not flag",   # and, or, not
    '(n + 1) * 2 / 4 - 1 &gt; -1',      # arithmetic, parentheses, unary minus
    'msg.data == True',                 # event data attribute chain
    'n &lt;= 3', 'n &gt; 2', 'n == 3',
])
def test_allowed_conditions(cond):
    assert cond_errors(cond) == []


@pytest.mark.parametrize('expr', ['n + 1', '7', "'text'", 'limit * 2', '-n', 'None',
                                  'msg.data', 'False'])
def test_allowed_values(expr):
    assert value_errors(expr) == []


# Refused: each fails with a message ----------------------------------------------

@pytest.mark.parametrize('cond, message', [
    ('len(name) == 4', 'calls are not allowed'),
    ('ok()', 'calls are not allowed'),
    ("In('nowhere')", 'no state "nowhere"'),
    ('In(name)', 'one literal state id'),
    ("name[0] == 'h'", 'indexing and slicing'),
    ('[x for x in name] == []', 'comprehensions'),
    ('(lambda: True)()', 'calls are not allowed'),
    ("f'{n}' == '3'", 'f-strings'),
    ('(m := 3) == 3', ':='),
    ('(1 if flag else 2) == 1', 'conditional expressions'),
    ('n ** 2 == 9', '"**" is not allowed'),
    ('n // 2 == 1', '"//" is not allowed'),
    ('n % 2 == 1', '"%" is not allowed'),
    ('(n &amp; 1) == 1', 'bitwise operators'),
    ('~n == 1', 'Invert'),
    ('1 &lt; n &lt; 5', 'chained comparisons'),
    ('nothing is None', '"is" is not allowed'),
    ('n in (1, 3)', '"in" is not allowed'),
    ('n == 3 &amp;&amp; flag', '"&&" is JavaScript'),
    ('n == 3 || flag', '"||" is JavaScript'),
    ('n === 3', '"===" is JavaScript'),
    ('n !== 3', '"!==" is JavaScript'),
    ('!flag', '"!" is JavaScript'),
    ('flag == true', '"true" is JavaScript'),
    ('flag == false', '"false" is JavaScript'),
    ('nothing == null', '"null" is JavaScript'),
    ('n', 'must be boolean'),
    ('n + 1', 'must be boolean'),
    ("'yes'", 'must be boolean'),
    ('msg.data', 'must be boolean'),
    ('_event.data', 'reserved name'),
    ('sc_ros_refusal == 1', 'reserved name'),
    ('msg._x == 1', 'reserved'),
    ("'a' + 1 == 2", 'numbers only'),
    ('[1] == [1]', 'list displays'),
    ("b'x' == 1", 'literal'),
])
def test_refused_conditions(cond, message):
    found = cond_errors(cond)
    assert found, cond
    assert any(message in m for m in found), found


@pytest.mark.parametrize('expr, location, message', [
    ('[1, 2]', 'n', 'list displays'),
    ("{'k': 1}", 'n', 'dict displays'),
    ('n', 'n.x', 'datamodel name only'),
    ('n', 'missing', 'not a datamodel value'),
    ('n', '_hidden', 'reserved name'),
    ('max(n, 1)', 'n', 'calls are not allowed'),
])
def test_refused_values_and_locations(expr, location, message):
    found = value_errors(expr, location)
    assert any(message in m for m in found), found


def test_data_expressions_and_if_conditions_are_checked():
    body = ('<datamodel><data id="xs" expr="[1, 2]"/></datamodel>'
            '<state id="a"><onentry><if cond="1"><log expr="1"/></if></onentry>'
            '<transition event="go" target="a"/></state>')
    found = [f.message for f in errors(validate(spec_of(body))) if f.rule == 10]
    assert any('list displays' in m for m in found)
    assert any('must be boolean' in m for m in found)


def test_reserved_and_keyword_data_names():
    body = ('<datamodel><data id="lambda" expr="1"/><data id="_x" expr="1"/></datamodel>'
            '<state id="a"><transition event="go" target="a"/></state>')
    found = [f.message for f in errors(validate(spec_of(body))) if f.rule == 9]
    assert len(found) == 2


def test_unknown_names_are_rule_4():
    found = cond_errors('mystery == 1', rule=4)
    assert any('"mystery"' in m for m in found)


def test_findings_have_the_line_of_the_expression():
    body = DATA + '<state id="a">\n<transition event="go" cond="n === 1" target="a"/></state>'
    found = [f for f in errors(validate(spec_of(body))) if f.rule == 10]
    assert found[0].line == 7
