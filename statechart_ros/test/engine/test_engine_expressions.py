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


"""Engine facts behind chart expressions (ENGINE.md E19 to E22)."""

from engine_util import config
import pytest
from statemachine.exceptions import InvalidDefinition


def chart_with(cond, datamodel='python'):
    from statemachine.io import load
    return load(
        '<scxml xmlns="http://www.w3.org/2005/07/scxml" version="1.0" '
        f'datamodel="{datamodel}" initial="a"><datamodel><data id="x" expr="1"/>'
        '<data id="p" expr="{\'k\': 2}"/><data id="f" expr="True"/></datamodel>'
        f'<state id="a"><transition event="go" cond="{cond}" target="b"/>'
        '<transition event="error.execution" target="err"/></state>'
        '<state id="b"/><state id="err"/></scxml>', format='scxml')


def outcome(cond, datamodel='python'):
    sm = chart_with(cond, datamodel)()
    sm.send('go')
    return config(sm)


@pytest.mark.parametrize('datamodel', ['ecmascript', 'null', 'anything'])
def test_e19_the_datamodel_attribute_is_ignored(datamodel):
    assert outcome('x == 1', datamodel) == {'b'}


@pytest.mark.parametrize('cond', ['x == 1 &amp;&amp; f', 'x === 1', 'x !== 2', 'f == true',
                                  'x == 2 || f'])
def test_e20_javascript_tokens_are_normalised(cond):
    assert outcome(cond) == {'b'}


def test_e20_bang_is_refused_at_load():
    with pytest.raises(InvalidDefinition):
        chart_with('!f')


def test_e21_member_access_on_a_dict_fails_at_run_time():
    assert outcome('p.k == 2') == {'err'}
    assert outcome("p['k'] == 2") == {'b'}


@pytest.mark.parametrize('cond', ['x in [1]', 'x is 1'])
def test_e22_in_and_is_are_refused_at_load_with_a_key_error(cond):
    with pytest.raises(KeyError):
        chart_with(cond)
