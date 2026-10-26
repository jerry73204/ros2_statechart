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


"""The node's side of a running chart: ROS time, timers, outputs, server gates."""

import threading

from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.qos import (DurabilityPolicy, HistoryPolicy, qos_profile_sensor_data, QoSProfile,
                       ReliabilityPolicy)
from statechart_ros.runtime import Host
import yaml

POLL = 0.02


def qos_profile(name):
    """Return the QoS profile of a ``qos`` attribute: default, sensor or latched."""
    if name == 'sensor':
        return qos_profile_sensor_data
    if name == 'latched':
        return QoSProfile(depth=1, history=HistoryPolicy.KEEP_LAST,
                          reliability=ReliabilityPolicy.RELIABLE,
                          durability=DurabilityPolicy.TRANSIENT_LOCAL)
    return QoSProfile(depth=10)


def literal(text):
    """Read an attribute value as YAML (numbers, booleans, strings, mappings)."""
    return yaml.safe_load(text) if text is not None else None


def fill_message(msg, value):
    """Fill a message from a literal: a mapping sets fields, anything else sets ``data``."""
    from rosidl_runtime_py.set_message import set_message_fields
    if isinstance(value, dict):
        set_message_fields(msg, value)
    else:
        if not hasattr(msg, 'data'):
            raise ValueError(f'{type(msg).__name__} has no field "data"; give the value as '
                             'a mapping of fields')
        field_type = type(getattr(msg, 'data'))
        msg.data = field_type(value) if field_type in (bool, int, float, str) else value
    return msg


def destroy_waitable(node, waitable, delay=1.0):
    """
    Destroy an action client or server without racing the executor.

    The executor may be inside a wait that includes the waitable; removing it
    from the node first and destroying it a little later keeps the executor
    from taking data from a destroyed handle.
    """
    try:
        node.remove_waitable(waitable)
    except Exception:  # noqa: B902 - already removed
        pass

    def destroy():
        try:
            waitable.destroy()
        except Exception:  # noqa: B902 - the node may be gone
            pass

    timer = threading.Timer(delay, destroy)
    timer.daemon = True
    timer.start()


class Gate:
    """One goal at a time per action server, released when its cancel is confirmed."""

    def __init__(self):
        self._lock = threading.Lock()

    def acquire(self, cancelled):
        while not self._lock.acquire(timeout=POLL):
            if cancelled.is_set():
                return False
        return True

    def release(self):
        self._lock.release()

    def locked(self):
        return self._lock.locked()


class _OneShot:
    """A one-shot ROS timer that can be cancelled from any thread."""

    def __init__(self, node, delay, callback):
        self._node = node
        self._callback = callback
        self._lock = threading.Lock()
        self._done = False
        self._timer = node.create_timer(max(delay, 1e-6), self._fire, clock=node.get_clock())

    def _fire(self):
        with self._lock:
            if self._done:
                return
            self._done = True
            self._timer.cancel()
        self._callback()
        self._destroy()

    def cancel(self):
        with self._lock:
            if self._done:
                return
            self._done = True
            self._timer.cancel()
        self._destroy()

    def _destroy(self):
        try:
            self._node.destroy_timer(self._timer)
        except Exception:  # noqa: B902 - the node may be shutting down
            pass


class RosHost(Host):
    """Host of a chart in a ROS node."""

    def __init__(self, node, spec):
        self.node = node
        self.spec = spec
        self.callback_group = ReentrantCallbackGroup()
        self._gates = {}
        self._gates_lock = threading.Lock()
        self._publishers = {}
        self._clients = {}
        self._latched = {out.attrs['publish'] for outs in spec.outputs.values() for out in outs
                         if out.action == 'publish' and out.attrs.get('qos') == 'latched'}

    def logger(self):
        return self.node.get_logger()

    def now(self):
        return self.node.get_clock().now().nanoseconds * 1e-9

    def schedule(self, delay, callback):
        return _OneShot(self.node, delay, callback)

    def wait(self, event, seconds):
        deadline = self.now() + seconds
        while not event.wait(POLL):
            if self.now() >= deadline:
                return event.is_set()
        return True

    def resolve(self, name):
        """Return a name as the chart wrote it; rclpy resolves relative and ~/ names."""
        return name

    def qos(self, name):
        return qos_profile(name)

    def gate(self, server):
        with self._gates_lock:
            return self._gates.setdefault(server, Gate())

    def interface(self, kind, type_name):
        from statechart_ros.validate import import_interface
        return import_interface(kind, type_name)

    # --- outputs ----------------------------------------------------------------

    def setup_outputs(self):
        """Create one publisher per topic and one client per service the outputs use."""
        for outs in self.spec.outputs.values():
            for out in outs:
                if out.action == 'publish':
                    topic = out.attrs['publish']
                    if topic not in self._publishers:
                        msg_type = self.interface('msg', out.attrs['type'])
                        qos = qos_profile('latched' if topic in self._latched else 'default')
                        self._publishers[topic] = (msg_type, self.node.create_publisher(
                            msg_type, topic, qos))
                elif out.action == 'call':
                    service = out.attrs['call']
                    if service not in self._clients:
                        srv_type = self.interface('srv', out.attrs['type'])
                        self._clients[service] = (srv_type, self.node.create_client(
                            srv_type, service, callback_group=self.callback_group))
                elif out.action == 'set_param' and out.attrs.get('node'):
                    key = ('set_param', out.attrs['node'])
                    if key not in self._clients:
                        from rcl_interfaces.srv import SetParameters
                        name = out.attrs['node'].rstrip('/') + '/set_parameters'
                        self._clients[key] = (SetParameters, self.node.create_client(
                            SetParameters, name, callback_group=self.callback_group))

    def teardown_outputs(self):
        for _, pub in self._publishers.values():
            self.node.destroy_publisher(pub)
        for _, client in self._clients.values():
            self.node.destroy_client(client)
        self._publishers.clear()
        self._clients.clear()

    def output(self, out, model):
        runner = self.runner
        if out.action == 'publish':
            msg_type, pub = self._publishers[out.attrs['publish']]
            msg = msg_type()
            if out.attrs.get('value') is not None:
                fill_message(msg, literal(out.attrs['value']))
            if out.attrs.get('message'):
                built = runner.call_model(out.attrs['message'], msg=msg)
                if built is not None:
                    msg = built
            pub.publish(msg)
        elif out.action == 'call':
            srv_type, client = self._clients[out.attrs['call']]
            request = srv_type.Request()
            if out.attrs.get('request'):
                built = runner.call_model(out.attrs['request'], request=request)
                if built is not None:
                    request = built
            if not client.service_is_ready():
                self.logger().warning(f'service {out.attrs["call"]} is not available; the '
                                      f'call of state {out.state} is skipped')
                return
            client.call_async(request)
        elif out.action == 'set_param':
            from rclpy.parameter import Parameter
            param = Parameter(out.attrs['set_param'], value=literal(out.attrs['value']))
            if not out.attrs.get('node'):
                results = self.node.set_parameters([param])
                if results and not results[0].successful:
                    raise ValueError(f'setting {out.attrs["set_param"]}: {results[0].reason}')
                return
            srv_type, client = self._clients[('set_param', out.attrs['node'])]
            if not client.service_is_ready():
                self.logger().warning(f'node {out.attrs["node"]} has no parameter service; '
                                      f'set_param of state {out.state} is skipped')
                return
            request = srv_type.Request()
            request.parameters = [param.to_parameter_msg()]
            client.call_async(request)
