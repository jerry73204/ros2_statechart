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


"""The work of the verbs that look at running charts: list, show, echo, send."""

import json
import sys
import threading
import time

from rclpy.qos import DurabilityPolicy, QoSProfile

STRUCTURE_TYPE = 'statechart_ros_msgs/msg/StatechartStructure'


def chart_nodes(node, wait=1.0):
    """Return the nodes publishing a chart structure, after waiting for discovery."""
    deadline = time.monotonic() + wait
    found = set()
    while True:
        for topic, types in node.get_topic_names_and_types():
            if STRUCTURE_TYPE in types and topic.endswith('/structure'):
                found.add(topic[:-len('/structure')] or '/')
        if time.monotonic() >= deadline:
            return sorted(found)
        time.sleep(0.1)


def _latched():
    return QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)


def _spin_until(node, predicate, timeout):
    import rclpy
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.05)
    return predicate()


def fetch(node, chart, timeout=3.0):
    """Return (structure message, status message) of a chart, or None for missing ones."""
    from statechart_ros_msgs.msg import StatechartStatus, StatechartStructure
    got = {}
    node.create_subscription(StatechartStructure, f'{chart}/structure',
                             lambda m: got.__setitem__('structure', m), _latched())
    node.create_subscription(StatechartStatus, f'{chart}/status',
                             lambda m: got.__setitem__('status', m), _latched())
    _spin_until(node, lambda: len(got) == 2, timeout)
    return got.get('structure'), got.get('status')


def format_tree(structure, status, now=None):
    """Return the chart as an indented tree, active states marked with '*'."""
    active = set(status.active) if status is not None else set()
    invokes = {i.state: i for i in status.invokes} if status is not None else {}
    stamp = (status.stamp.sec + status.stamp.nanosec * 1e-9) if status is not None else 0.0
    children = {}
    for s in structure.states:
        children.setdefault(s.parent, []).append(s)
    lines = [f'{structure.name} ({structure.node or "?"})'
             + ('' if status is None or status.running else ' [not running]')]

    def walk(parent, depth):
        for s in children.get(parent, []):
            mark = '*' if s.id in active else ' '
            kind = {2: ' (parallel)', 3: ' (final)', 4: f' (history {s.history})'}.get(s.kind, '')
            lines.append(f'{"  " * depth}{mark} {s.id}{kind}')
            inv = invokes.get(s.id)
            if inv is not None:
                since = inv.since.sec + inv.since.nanosec * 1e-9
                text = f'{inv.kind} {inv.target}, {max(0.0, stamp - since):.1f} s'
                if inv.feedback:
                    text += f', {inv.feedback}'
                lines.append(f'{"  " * depth}    > {text}')
            walk(s.id, depth + 1)

    walk('', 0)
    if status is not None:
        lines.append(f'last event: {status.last_event or "-"}'
                     + (f' (refused: {status.refusal})' if status.refusal else ''))
        for d in status.data:
            lines.append(f'  {d.key} = {d.json}')
    return '\n'.join(lines)


def format_transition(msg):
    stamp = msg.stamp.sec + msg.stamp.nanosec * 1e-9
    clock = time.strftime('%H:%M:%S', time.gmtime(stamp)) + f'.{int(stamp % 1 * 1000):03d}'
    if msg.refusal:
        what = f'refused: {msg.refusal}'
    elif not msg.handled:
        what = 'not handled'
    else:
        what = '; '.join(msg.taken) or 'handled'
    data = f' {msg.data}' if msg.data else ''
    return f'{clock} {msg.event}{data}: {what}'


def echo(node, chart, count=None, out=None, timeout=None):
    """Print transitions as they happen; return how many were printed."""
    from statechart_ros_msgs.msg import Transition
    out = out or sys.stdout
    printed = [0]
    done = threading.Event()

    def on_transition(msg):
        print(format_transition(msg), file=out, flush=True)
        printed[0] += 1
        if count is not None and printed[0] >= count:
            done.set()

    node.create_subscription(Transition, f'{chart}/transitions', on_transition, 100)
    deadline = None if timeout is None else time.monotonic() + timeout
    import rclpy
    while not done.is_set() and (deadline is None or time.monotonic() < deadline):
        rclpy.spin_once(node, timeout_sec=0.1)
    return printed[0]


def send(node, chart, event, data_text='', timeout=5.0):
    """Send an event through ``<chart>/send_event``; return the response or raise."""
    from statechart_ros_msgs.srv import SendEvent
    if data_text:
        json.loads(data_text)
    client = node.create_client(SendEvent, f'{chart}/send_event')
    if not client.wait_for_service(timeout_sec=timeout):
        raise RuntimeError(f'{chart}/send_event is not available: is the chart running '
                           'with debug_events:=true?')
    request = SendEvent.Request()
    request.event = event
    request.data = data_text or ''
    future = client.call_async(request)
    import rclpy
    rclpy.spin_until_future_complete(node, future, timeout_sec=timeout)
    if not future.done():
        raise RuntimeError(f'no answer from {chart}/send_event')
    return future.result()
