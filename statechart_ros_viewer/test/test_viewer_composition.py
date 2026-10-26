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


"""A child chart in the viewer's API: its states inside the invoking state (P6)."""

import json
import urllib.error
import urllib.request

from viewer_util import Setup, wait_for, write_composed


def get_json(setup, path):
    try:
        with urllib.request.urlopen(setup.url + path, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError:
        return None              # not discovered yet


def post(setup, path, body):
    req = urllib.request.Request(setup.url + path, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def test_child_chart_inside_its_state(tmp_path):
    s = Setup(write_composed(tmp_path))
    try:
        snap = wait_for(lambda: (lambda x: x if x and x['status'] and x['structure'] else None)(
            get_json(s, '/api/chart?node=/demo')))
        states = {st['id']: st for st in snap['structure']['states']}
        assert states['PROC/STEP1']['parent'] == 'PROC'
        assert states['PROC']['invoke']['type'] == 'chart'
        post(s, '/api/send', {'node': '/demo', 'event': 'go'})
        post(s, '/api/send', {'node': '/demo', 'event': 'next'})
        assert wait_for(lambda: set(get_json(s, '/api/chart?node=/demo')['status']['active'])
                        == {'PROC', 'PROC/STEP2'})
    finally:
        s.close()
