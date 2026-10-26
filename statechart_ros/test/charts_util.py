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


"""Inline charts for the tests."""

import os

from statechart_ros.loader import load_chart, ROS_NS

HERE = os.path.dirname(os.path.abspath(__file__))
CHARTS = os.path.join(HERE, 'charts')
MODEL = '<ros:model class="my_robot.testmodel:TestModel"/>'


def doc(body, initial='a', model=True, datamodel='python'):
    """Return a chart document with the test model and the given body."""
    return (
        '<?xml version="1.0"?>\n'
        '<scxml xmlns="http://www.w3.org/2005/07/scxml"\n'
        f'       xmlns:ros="{ROS_NS}"\n'
        f'       version="1.0" datamodel="{datamodel}" initial="{initial}">\n'
        + (MODEL + '\n' if model else '') + body + '\n</scxml>\n')


def spec_of(body, **kwargs):
    """Load an inline chart."""
    params = kwargs.pop('params', None)
    return load_chart(None, text=doc(body, **kwargs), name='test', params=params)


def chart_path(name):
    return os.path.join(CHARTS, name)
