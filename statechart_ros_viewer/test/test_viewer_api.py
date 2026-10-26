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


"""The viewer's HTTP API and event stream, without a browser (P5)."""

import http.client
import json
import threading
import urllib.error
import urllib.request

import pytest
from viewer_util import CHART, Setup, wait_for


@pytest.fixture(scope='module')
def setup(tmp_path_factory):
    path = tmp_path_factory.mktemp('viewer') / 'demo.scxml'
    path.write_text(CHART)
    s = Setup(path)
    yield s
    s.close()


def get(setup, path):
    with urllib.request.urlopen(setup.url + path, timeout=10) as r:
        return r.status, r.headers.get('Content-Type'), r.read()


def get_json(setup, path):
    return json.loads(get(setup, path)[2])


def post(setup, path, body):
    req = urllib.request.Request(setup.url + path, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_charts_are_discovered(setup):
    # Only /demo: other tests' chart nodes may share the ROS domain.
    charts = wait_for(lambda: [c for c in get_json(setup, '/api/charts')
                               if c['name'] and c['node'] == '/demo' and c['running']])
    assert charts == [{'node': '/demo', 'name': 'demo', 'source': charts[0]['source'],
                       'debug_events': True, 'running': True}]


def test_one_chart_snapshot(setup):
    snap = wait_for(lambda: (lambda s: s if s['status'] and s['structure'] else None)(
        get_json(setup, '/api/chart?node=/demo')))
    states = {s['id']: s for s in snap['structure']['states']}
    assert states['run']['kind'] == 'parallel'
    assert states['BUSY']['after'] == ['timeout after 30 s']
    assert set(snap['status']['active']) == {'run', 'mode', 'AUTO', 'task', 'IDLE'}
    assert snap['status']['data'] == {'count': '0'}


def test_static_files_and_errors(setup):
    status, ctype, body = get(setup, '/')
    assert status == 200 and ctype.startswith('text/html') and b'app.js' in body
    for path in ('/static/app.js', '/static/style.css', '/static/vendor/dagre.min.js',
                 '/static/vendor/LICENSE.dagre'):
        assert get(setup, path)[0] == 200
    for path in ('/static/../server.py', '/static/%2e%2e/server.py', '/nothing',
                 '/api/chart?node=/nobody'):
        with pytest.raises(urllib.error.HTTPError) as exc:
            get(setup, path)
        assert exc.value.code == 404


def test_events_stream_and_send(setup):
    wait_for(lambda: get_json(setup, '/api/chart?node=/demo')['status'])
    conn = http.client.HTTPConnection('127.0.0.1', setup.viewer.port, timeout=10)
    conn.request('GET', '/api/events')
    response = conn.getresponse()
    assert response.getheader('Content-Type') == 'text/event-stream'
    events = []

    def read():
        kind = None
        while True:
            line = response.fp.readline().decode()
            if not line:
                return
            if line.startswith('event: '):
                kind = line[7:].strip()
            elif line.startswith('data: '):
                events.append((kind, json.loads(line[6:])))

    threading.Thread(target=read, daemon=True).start()
    assert wait_for(lambda: any(k == 'charts' for k, _ in events))
    status, answer = post(setup, '/api/send', {'node': '/demo', 'event': 'go'})
    assert status == 200
    assert answer['handled'] and 'BUSY' in answer['configuration']
    assert wait_for(lambda: any(k == 'status' and 'BUSY' in m['payload']['active']
                                for k, m in events))
    assert wait_for(lambda: any(k == 'transition' and m['payload']['event'] == 'go'
                                for k, m in events))
    status, answer = post(setup, '/api/send', {'node': '/demo', 'event': 'pause'})
    status, answer = post(setup, '/api/send', {'node': '/demo', 'event': 'pause'})
    assert answer == {'handled': False, 'refusal': 'already paused', 'ignored': '',
                      'configuration': answer['configuration']}
    conn.close()


def test_send_errors(setup):
    assert post(setup, '/api/send', {'node': '/nobody', 'event': 'go'})[0] == 400
    assert post(setup, '/api/send', {'event': 'go'})[0] == 400
    assert post(setup, '/api/send', {'node': '/demo', 'event': 'go', 'data': [1]})[0] == 400
