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
Helpers for launch_testing: watch a chart node's status and send it events.

    watcher = ChartWatcher(test_node, '/patrol')
    watcher.wait_for_configuration({'IDLE'}, timeout=60.0)
    result = watcher.send('start')                  # needs ~/send_event or ~/command
"""

import json
import threading
import time

from rclpy.qos import DurabilityPolicy, QoSProfile
from statechart_ros_msgs.msg import StatechartStatus, Transition
from statechart_ros_msgs.srv import SendEvent


class ChartWatcher:
    """Follow ``<chart>/status`` and ``<chart>/transitions`` from a test node."""

    def __init__(self, node, chart, service='send_event'):
        self.node = node
        self.chart = chart.rstrip('/')
        self.status = None
        self.statuses = []
        self.transitions = []
        self._lock = threading.Lock()
        latched = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        node.create_subscription(StatechartStatus, f'{self.chart}/status', self._on_status,
                                 latched)
        node.create_subscription(Transition, f'{self.chart}/transitions', self._on_transition,
                                 100)
        self.client = node.create_client(SendEvent, f'{self.chart}/{service}')

    def _on_status(self, msg):
        with self._lock:
            self.status = msg
            self.statuses.append(msg)

    def _on_transition(self, msg):
        with self._lock:
            self.transitions.append(msg)

    def active(self):
        with self._lock:
            return set(self.status.active) if self.status is not None else set()

    def wait_for(self, predicate, timeout=30.0, period=0.05):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(period)
        return bool(predicate())

    def wait_for_configuration(self, states, timeout=30.0):
        """Wait until all the given states are active; return whether they are."""
        states = set(states)
        return self.wait_for(lambda: states <= self.active(), timeout)

    def outcomes(self, state):
        """Return the statuses of the ``done.invoke`` events of a state so far."""
        with self._lock:
            found = list(self.transitions)
        return [json.loads(t.data).get('status') for t in found
                if t.event == f'done.invoke.{state}' and t.data]

    def send(self, event, data=None, timeout=30.0):
        """Send an event through the chart's SendEvent service; return the response."""
        if not self.client.wait_for_service(timeout_sec=timeout):
            raise TimeoutError(f'{self.client.srv_name} is not available')
        request = SendEvent.Request()
        request.event = event
        request.data = json.dumps(data) if data else ''
        future = self.client.call_async(request)
        if not self.wait_for(future.done, timeout, 0.01):
            raise TimeoutError(f'no answer to {event}')
        return future.result()
