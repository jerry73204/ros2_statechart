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
The viewer's ROS side: find charts by their ``~/structure`` topics and follow them.

A chart is identified by the node that hosts it (``/patrol``). For each, the
viewer keeps the structure, the latest status and the recent transitions,
and hands every change to listeners (the server-sent-events stream).
"""

import collections
import json
import threading

from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from statechart_ros.introspection import structure_dict
from statechart_ros_msgs.msg import StatechartStatus, StatechartStructure, Transition
from statechart_ros_msgs.srv import SendEvent

STRUCTURE_TYPE = 'statechart_ros_msgs/msg/StatechartStructure'


def seconds(stamp):
    return stamp.sec + stamp.nanosec * 1e-9


def status_dict(msg):
    return {
        'stamp': seconds(msg.stamp), 'name': msg.name, 'sequence': msg.sequence,
        'active': list(msg.active), 'last_event': msg.last_event, 'handled': msg.handled,
        'refusal': msg.refusal, 'running': msg.running,
        'data': {d.key: d.json for d in msg.data},
        'invokes': [{'state': i.state, 'kind': i.kind, 'target': i.target,
                     'since': seconds(i.since),
                     'feedback': json.loads(i.feedback) if i.feedback else {}}
                    for i in msg.invokes],
    }


def transition_dict(msg):
    return {
        'stamp': seconds(msg.stamp), 'name': msg.name, 'sequence': msg.sequence,
        'event': msg.event, 'data': msg.data, 'source': list(msg.source_configuration),
        'target': list(msg.target_configuration), 'taken': list(msg.taken),
        'handled': msg.handled, 'refusal': msg.refusal, 'duration': msg.duration,
    }


class Chart:
    """What the viewer knows about one chart."""

    def __init__(self, node_name, history):
        self.node = node_name
        self.structure = None
        self.status = None
        self.transitions = collections.deque(maxlen=history)
        self.subscriptions = []
        self.client = None

    def summary(self):
        s = self.structure or {}
        return {'node': self.node, 'name': s.get('name', ''), 'source': s.get('source', ''),
                'debug_events': bool(s.get('debug_events')),
                'running': bool(self.status and self.status['running'])}


class ChartTracker:
    """Discover charts and follow their structure, status and transitions."""

    def __init__(self, node: Node, history=1000):
        self.node = node
        self.history = history
        self.charts = {}
        self.lock = threading.Lock()
        self.listeners = []

    def listen(self, callback):
        with self.lock:
            self.listeners.append(callback)

    def unlisten(self, callback):
        with self.lock:
            if callback in self.listeners:
                self.listeners.remove(callback)

    def _emit(self, kind, chart, payload):
        with self.lock:
            listeners = list(self.listeners)
        for callback in listeners:
            callback(kind, chart, payload)

    def discover(self):
        """Subscribe to every chart whose structure topic exists."""
        for topic, types in self.node.get_topic_names_and_types():
            if STRUCTURE_TYPE not in types or not topic.endswith('/structure'):
                continue
            chart_node = topic[:-len('/structure')] or '/'
            with self.lock:
                known = chart_node in self.charts
                if not known:
                    self.charts[chart_node] = Chart(chart_node, self.history)
            if not known:
                self._follow(chart_node)

    def _follow(self, chart_node):
        chart = self.charts[chart_node]
        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)

        def on_structure(msg):
            chart.structure = structure_dict(msg)
            self._emit('structure', chart_node, chart.structure)
            self._emit('charts', chart_node, self.summaries())

        def on_status(msg):
            chart.status = status_dict(msg)
            self._emit('status', chart_node, chart.status)

        def on_transition(msg):
            record = transition_dict(msg)
            chart.transitions.append(record)
            self._emit('transition', chart_node, record)

        chart.subscriptions = [
            self.node.create_subscription(StatechartStructure, f'{chart_node}/structure',
                                          on_structure, latched),
            self.node.create_subscription(StatechartStatus, f'{chart_node}/status',
                                          on_status, latched),
            self.node.create_subscription(Transition, f'{chart_node}/transitions',
                                          on_transition, 100),
        ]
        chart.client = self.node.create_client(SendEvent, f'{chart_node}/send_event')

    def summaries(self):
        with self.lock:
            return [c.summary() for c in sorted(self.charts.values(), key=lambda c: c.node)]

    def snapshot(self, chart_node):
        with self.lock:
            chart = self.charts.get(chart_node)
        if chart is None:
            return None
        return {'node': chart_node, 'structure': chart.structure, 'status': chart.status,
                'transitions': list(chart.transitions)}

    def send(self, chart_node, event, data, timeout=10.0):
        """Send an event through the chart's ~/send_event; return the answer as a dict."""
        with self.lock:
            chart = self.charts.get(chart_node)
        if chart is None:
            return {'error': f'no chart {chart_node}'}
        if not (chart.structure and chart.structure.get('debug_events')):
            return {'error': f'{chart_node} does not accept debug events (debug_events is off)'}
        if not chart.client.wait_for_service(timeout_sec=2.0):
            return {'error': f'{chart_node}/send_event is not available'}
        request = SendEvent.Request()
        request.event = event
        request.data = json.dumps(data) if data else ''
        future = chart.client.call_async(request)
        done = threading.Event()
        future.add_done_callback(lambda _f: done.set())
        if not done.wait(timeout):
            return {'error': 'no answer'}
        response = future.result()
        return {'handled': response.handled, 'refusal': response.refusal,
                'configuration': list(response.configuration)}
