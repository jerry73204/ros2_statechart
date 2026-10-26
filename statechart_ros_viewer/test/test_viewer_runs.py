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

"""A chart that counts its macrosteps from the start again gets a new log."""

import json
import urllib.error
import urllib.request

from rclpy.lifecycle import TransitionCallbackReturn
from viewer_util import CHART, Setup, wait_for


def snapshot(setup):
    try:
        with urllib.request.urlopen(setup.url + '/api/chart?node=/demo', timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError:      # not discovered yet
        return {}


def chart_log(setup):
    return [t['event'] for t in snapshot(setup).get('transitions', [])]


def test_a_restarted_chart_starts_a_new_log(tmp_path):
    path = tmp_path / 'demo.scxml'
    path.write_text(CHART)
    setup = Setup(path)
    try:
        # Transitions are not latched: follow the chart before it moves.
        assert wait_for(lambda: snapshot(setup).get('status'))
        setup.chart.runner.send('go')
        setup.chart.runner.send('pause')
        assert wait_for(lambda: chart_log(setup)[-2:] == ['go', 'pause']), chart_log(setup)
        # Restart: the new runner counts from the start, as a bag played again does.
        assert setup.chart.trigger_deactivate() == TransitionCallbackReturn.SUCCESS
        assert setup.chart.trigger_cleanup() == TransitionCallbackReturn.SUCCESS
        assert setup.chart.trigger_configure() == TransitionCallbackReturn.SUCCESS
        assert setup.chart.trigger_activate() == TransitionCallbackReturn.SUCCESS
        setup.chart.runner.send('go')
        assert wait_for(lambda: 'pause' not in chart_log(setup) and 'go' in chart_log(setup)), \
            chart_log(setup)
    finally:
        setup.close()
