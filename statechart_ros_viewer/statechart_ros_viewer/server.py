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
The viewer's HTTP side: static files, a JSON API and a server-sent-events stream.

    GET  /                       the page
    GET  /static/<file>          its files (no external assets)
    GET  /api/charts             the charts found
    GET  /api/chart?node=/x      structure, status and recent transitions of one chart
    GET  /api/events             server-sent events: charts, structure, status, transition
    POST /api/send               {"node": "/x", "event": "go", "data": {...}}
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
import queue
import threading
from urllib.parse import parse_qs, urlparse

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')
KEEPALIVE = 15.0


class ViewerServer(ThreadingHTTPServer):
    """An HTTP server bound to a tracker."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, port, tracker, logger=None):
        self.tracker = tracker
        self.logger = logger
        self.closing = threading.Event()
        super().__init__((address, port), Handler)

    def start(self):
        thread = threading.Thread(target=self.serve_forever, daemon=True,
                                  name='statechart-viewer-http')
        thread.start()
        return thread

    def stop(self):
        self.closing.set()
        self.shutdown()
        self.server_close()


class Handler(BaseHTTPRequestHandler):
    """Requests of one connection."""

    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        logger = self.server.logger
        if logger is not None:
            logger.debug('http: ' + fmt % args)

    def _send(self, code, body, content_type='application/json'):
        data = body if isinstance(body, bytes) else body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, value):
        self._send(code, json.dumps(value))

    def do_GET(self):  # noqa: N802 - http.server API
        url = urlparse(self.path)
        if url.path in ('/', '/index.html'):
            return self._file('index.html')
        if url.path.startswith('/static/'):
            return self._file(url.path[len('/static/'):])
        if url.path == '/api/charts':
            return self._json(200, self.server.tracker.summaries())
        if url.path == '/api/chart':
            node = parse_qs(url.query).get('node', [''])[0]
            snapshot = self.server.tracker.snapshot(node)
            if snapshot is None:
                return self._json(404, {'error': f'no chart {node}'})
            return self._json(200, snapshot)
        if url.path == '/api/events':
            return self._events()
        return self._json(404, {'error': 'not found'})

    def do_POST(self):  # noqa: N802 - http.server API
        if urlparse(self.path).path != '/api/send':
            return self._json(404, {'error': 'not found'})
        length = int(self.headers.get('Content-Length', '0'))
        try:
            body = json.loads(self.rfile.read(length) or b'{}')
            node, event = body['node'], body['event']
            data = body.get('data') or {}
            if not isinstance(data, dict):
                raise ValueError('data must be an object')
        except (ValueError, KeyError) as exc:
            return self._json(400, {'error': f'bad request: {exc}'})
        answer = self.server.tracker.send(node, event, data)
        return self._json(400 if 'error' in answer else 200, answer)

    def _file(self, rel):
        path = os.path.normpath(os.path.join(WEB, rel))
        if not path.startswith(WEB + os.sep) or not os.path.isfile(path):
            return self._json(404, {'error': 'not found'})
        content_type = mimetypes.guess_type(path)[0] or 'application/octet-stream'
        if content_type.startswith('text/') or content_type.endswith('javascript'):
            content_type += '; charset=utf-8'
        with open(path, 'rb') as f:
            return self._send(200, f.read(), content_type)

    def _events(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Connection', 'keep-alive')
        self.end_headers()
        events = queue.Queue(maxsize=10000)
        tracker = self.server.tracker

        def listener(kind, chart, payload):
            try:
                events.put_nowait((kind, chart, payload))
            except queue.Full:
                pass

        tracker.listen(listener)
        try:
            self._write_event('charts', None, tracker.summaries())
            while not self.server.closing.is_set():
                try:
                    kind, chart, payload = events.get(timeout=KEEPALIVE)
                except queue.Empty:
                    self.wfile.write(b': keepalive\n\n')
                    self.wfile.flush()
                    continue
                self._write_event(kind, chart, payload)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            tracker.unlisten(listener)

    def _write_event(self, kind, chart, payload):
        data = json.dumps({'node': chart, 'payload': payload})
        self.wfile.write(f'event: {kind}\ndata: {data}\n\n'.encode('utf-8'))
        self.wfile.flush()
