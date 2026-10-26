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
``statechart_node``: a lifecycle node hosting one chart.

configure loads and validates the chart and creates its ROS interfaces,
activate enters the initial configuration, deactivate exits every state
(cancelling every invoke), cleanup drops the chart.
"""

import ast
import json
import re
import threading
import time

from rcl_interfaces.msg import ParameterDescriptor
import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.clock import Clock, ClockType
from rclpy.exceptions import ParameterUninitializedException
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.lifecycle import Node as LifecycleNode
from rclpy.lifecycle import TransitionCallbackReturn
from rclpy.parameter import Parameter
from statechart_ros import introspection
from statechart_ros.host import destroy_waitable, qos_profile, RosHost
from statechart_ros.loader import ChartError, load_chart
from statechart_ros.runtime import call_with, ChartRunner, to_json
from statechart_ros.spin import spin
from statechart_ros.validate import errors, import_interface, import_model, matches, validate
from statechart_ros_msgs.srv import GetStructure, SendEvent

REPLY_TIMEOUT = 30.0


def make_user_model(class_path, node):
    """Instantiate the ros:model class with the node, if its constructor takes one."""
    cls = import_model(class_path)
    try:
        return cls(node)
    except TypeError:
        return cls()


class StatechartNode(LifecycleNode):
    """Host a chart: inputs to events, invokes, outputs, introspection."""

    def __init__(self, node_name='statechart', **kwargs):
        super().__init__(node_name, **kwargs)
        self.declare_parameter('chart', '')
        self.declare_parameter('debug_events', False)
        self.declare_parameter('status_rate_max', 20.0)
        self.declare_parameter('datamodel_publish', Parameter.Type.STRING_ARRAY)
        self.declare_parameter('autostart', True)
        self.declare_parameter('run_as_action', '')
        self.spec = None
        self.runner = None
        self.host = None
        self._entities = []
        self._group = ReentrantCallbackGroup()
        self._status_lock = threading.Lock()
        self._status_dirty = False
        self._last_status = 0.0
        self._data_json = {}
        self._goal = None
        self.structure = None
        self._run_server = None
        self._accepting = False

    # --- lifecycle ------------------------------------------------------------------

    def on_configure(self, state):
        chart = self.get_parameter('chart').value
        if not chart:
            self.get_logger().error('parameter "chart" is empty')
            return TransitionCallbackReturn.FAILURE
        try:
            spec = load_chart(chart, load_engine=False)
            params = self._declare_chart_params(spec)
            spec = load_chart(chart, params=params)
        except (ChartError, OSError) as exc:
            self.get_logger().error(f'cannot read chart {chart}: {exc}')
            return TransitionCallbackReturn.FAILURE
        findings = validate(spec)
        for f in findings:
            (self.get_logger().error if f.severity == 'error'
             else self.get_logger().warning)(str(f))
        if errors(findings):
            self.get_logger().error(f'chart {chart} has {len(errors(findings))} error(s); '
                                    'not configured')
            return TransitionCallbackReturn.FAILURE
        self.spec = spec
        try:
            user = make_user_model(spec.model_class, self) if spec.model_class else None
            self.host = RosHost(self, spec)
            self.runner = ChartRunner(spec, user, self.host)
            self.runner.observers.append(self._on_record)
            self.runner.status_observers.append(self._on_status_change)
            self.host.setup_outputs()
            for kind in self.runner.kinds.values():
                kind.setup()
            self._create_introspection()
            self._create_inputs()
            self._create_run_server()
        except Exception as exc:  # noqa: B902 - any setup failure fails the transition
            self.get_logger().error(f'configuring chart {chart} failed: {exc!r}')
            self._teardown()
            return TransitionCallbackReturn.FAILURE
        self.runner.start_worker()
        self.get_logger().info(f'chart {spec.name} configured from {spec.path}')
        return TransitionCallbackReturn.SUCCESS

    def on_activate(self, state):
        if self._run_server is not None:
            self._accepting = True
            self._publish_status(force=True)
            self.get_logger().info(f'chart {self.spec.name} waits for RunStatechart goals on '
                                   f'{self.get_parameter("run_as_action").value}')
            return super().on_activate(state)
        try:
            self.runner.start()
        except Exception as exc:  # noqa: B902
            self.get_logger().error(f'starting the chart failed: {exc!r}')
            return TransitionCallbackReturn.FAILURE
        self._publish_status(force=True)
        self.get_logger().info(f'chart {self.spec.name} active: '
                               + ', '.join(self.runner.configuration()))
        return super().on_activate(state)

    def on_deactivate(self, state):
        self._accepting = False
        if self.runner is not None:
            self.runner.stop()
            self._publish_status(force=True)
        return super().on_deactivate(state)

    def on_cleanup(self, state):
        self._teardown()
        return TransitionCallbackReturn.SUCCESS

    def on_shutdown(self, state):
        self._teardown()
        return TransitionCallbackReturn.SUCCESS

    def _teardown(self):
        if self.runner is not None:
            try:
                self.runner.shutdown()
            except Exception as exc:  # noqa: B902
                self.get_logger().warning(f'stopping the chart: {exc!r}')
            for kind in self.runner.kinds.values():
                try:
                    kind.teardown()
                except Exception:  # noqa: B902
                    pass
        if self.host is not None:
            self.host.teardown_outputs()
        for destroy, entity in reversed(self._entities):
            try:
                destroy(entity)
            except Exception:  # noqa: B902
                pass
        self._entities.clear()
        self.runner = None
        self.host = None
        self.spec = None

    def _keep(self, destroy, entity):
        self._entities.append((destroy, entity))
        return entity

    def _declare_chart_params(self, spec):
        values = {}
        for name in spec.params:
            default = spec.data.get(name)
            try:
                value = ast.literal_eval(default) if default is not None else None
            except (ValueError, SyntaxError):
                value = None
            if not self.has_parameter(name):
                if value is None:
                    # No typed default (None): any type, e.g. an array of numbers.
                    self.declare_parameter(name, None,
                                           ParameterDescriptor(dynamic_typing=True))
                else:
                    self.declare_parameter(name, value)
            current = self.get_parameter(name).value
            if current is not None:
                values[name] = current
        return values

    # --- introspection ----------------------------------------------------------------

    def _create_introspection(self):
        latched = qos_profile('latched')
        self._structure_pub = self._keep(self.destroy_publisher, self.create_publisher(
            introspection.StatechartStructure, '~/structure', latched))
        self._status_pub = self._keep(self.destroy_publisher, self.create_publisher(
            introspection.StatechartStatus, '~/status', latched))
        self._transitions_pub = self._keep(self.destroy_publisher, self.create_publisher(
            introspection.Transition, '~/transitions', 100))
        debug = bool(self.get_parameter('debug_events').value)
        self.structure = introspection.structure_msg(
            self.spec.structure(), self.get_fully_qualified_name(), self.host.now(), debug)
        self._structure_pub.publish(self.structure)
        self._keep(self.destroy_service, self.create_service(
            GetStructure, '~/get_structure', self._get_structure,
            callback_group=self._group))
        if debug:
            self._keep(self.destroy_service, self.create_service(
                SendEvent, '~/send_event', self._send_event, callback_group=self._group))
        rate = float(self.get_parameter('status_rate_max').value or 20.0)
        self._status_period = 1.0 / rate if rate > 0 else 0.0
        if self._status_period > 0:
            self._keep(self.destroy_timer, self.create_timer(
                self._status_period, self._status_timer, callback_group=self._group,
                clock=Clock(clock_type=ClockType.STEADY_TIME)))
        try:
            names = self.get_parameter('datamodel_publish').value or []
        except ParameterUninitializedException:
            names = []
        self._publish_names = set(names)

    def _get_structure(self, request, response):
        response.structure = self.structure
        return response

    def _on_record(self, record):
        """On the worker, after every processed event."""
        if self._publish_names:
            values = self.runner.model.values(self._publish_names)
            self._data_json = {k: to_json(v) for k, v in values.items()}
        self._transitions_pub.publish(introspection.transition_msg(self.spec.name, record))
        self._action_server_progress(record)

    def _on_status_change(self):
        with self._status_lock:
            self._status_dirty = True
        self._publish_status()

    def _status_timer(self):
        if self._status_dirty:
            self._publish_status()

    def _publish_status(self, force=False):
        if self.runner is None:
            return
        with self._status_lock:
            now = time.monotonic()
            if not force and now - self._last_status < self._status_period:
                return
            self._last_status = now
            self._status_dirty = False
        msg = introspection.status_msg(self.spec.name, self.runner.snapshot(),
                                       dict(self._data_json), self.host.now())
        self._status_pub.publish(msg)

    # --- inputs -------------------------------------------------------------------------

    def _create_inputs(self):
        for el in self.spec.inputs:
            getattr(self, f'_input_{el.tag}')(el)

    def _call_user(self, name, available):
        """Call a model method on the worker (we are on the worker in prepare functions)."""
        fn = getattr(self.runner.user_model, name)
        return call_with(fn, dict(available, datamodel=self.runner.model))

    def _input_subscribe(self, el):
        msg_type = import_interface('msg', el.get('type'))
        event = el.get('event')
        when = el.get('when')
        build = el.get('data')

        def callback(msg):
            if self.runner is None or not self.runner.running:
                return

            def prepare():
                if when and not self._call_user(when, {'msg': msg}):
                    return None
                data = {'msg': msg}
                if build:
                    extra = self._call_user(build, {'msg': msg})
                    if isinstance(extra, dict):
                        data.update(extra)
                return event, data

            self.runner.post(event, None, prepare)

        self._keep(self.destroy_subscription, self.create_subscription(
            msg_type, el.get('topic'), callback, qos_profile(el.get('qos', 'default')),
            callback_group=self._group))

    def _input_timer(self, el):
        event = el.get('event')

        def callback():
            if self.runner is not None and self.runner.running:
                self.runner.post(event)

        self._keep(self.destroy_timer, self.create_timer(
            float(el.get('period')), callback, callback_group=self._group))

    def _wait(self, future):
        try:
            return future.result(timeout=REPLY_TIMEOUT)
        except Exception as exc:  # noqa: B902 - timeouts and worker errors alike
            self.get_logger().error(f'event processing failed: {exc!r}')
            return None

    def _send_event(self, request, response):
        """Answer the generic SendEvent service (~/send_event and ros:service_server)."""
        return self._answer_send_event(request.event, request.data, response)

    def _answer_send_event(self, event, data_text, response):
        try:
            data = json.loads(data_text) if data_text else {}
            if not isinstance(data, dict):
                raise ValueError('data must be a JSON object')
        except ValueError as exc:
            response.handled = False
            response.refusal = f'invalid data: {exc}'
            response.configuration = self.runner.configuration() if self.runner else []
            return response
        if self.runner is None:
            response.handled = False
            response.refusal = 'the chart is not configured'
            return response
        result = self._wait(self.runner.post(event, data))
        if result is None:
            response.handled = False
            response.refusal = 'the event was not processed'
            return response
        response.handled = result.handled
        response.refusal = result.refusal
        response.ignored = result.ignored
        response.configuration = list(result.configuration)
        return response

    def _input_service_server(self, el):
        srv_type = import_interface('srv', el.get('type'))
        fixed = el.get('event')
        reply = el.get('reply')
        generic = srv_type is SendEvent

        def callback(request, response):
            if generic and not fixed:
                return self._answer_send_event(request.event, request.data, response)
            if fixed and '{' in fixed:
                # a template: each {field} is replaced by the request's field
                event = re.sub(r'\{(\w+)\}', lambda m: str(getattr(request, m.group(1))), fixed)
            else:
                event = fixed or getattr(request, 'event', '')
            if self.runner is None:
                return response
            result = self._wait(self.runner.post(event, {'request': request}))
            if result is None:
                return response
            if reply:
                built = self.runner.run_in_worker(self._call_user, reply, {
                    'response': response, 'request': request, 'handled': result.handled,
                    'refusal': result.refusal, 'ignored': result.ignored,
                    'configuration': result.configuration})
                return built if built is not None else response
            for key, value in (('handled', result.handled), ('refusal', result.refusal),
                               ('ignored', result.ignored),
                               ('configuration', list(result.configuration))):
                if hasattr(response, key):
                    setattr(response, key, value)
            return response

        self._keep(self.destroy_service, self.create_service(
            srv_type, el.get('name'), callback, callback_group=self._group))

    def _input_action_server(self, el):
        from rclpy.action import ActionServer, CancelResponse, GoalResponse
        action_type = import_interface('action', el.get('type'))
        node = self

        def goal_callback(goal_request):
            if node.runner is None or not node.runner.running or node._goal is not None:
                return GoalResponse.REJECT
            if el.get('accept'):
                ok = node.runner.run_in_worker(node._call_user, el.get('accept'),
                                               {'goal': goal_request}, timeout=REPLY_TIMEOUT)
                if not ok:
                    return GoalResponse.REJECT
            return GoalResponse.ACCEPT

        def cancel_callback(goal_handle):
            if not el.get('cancel_event'):
                return CancelResponse.REJECT
            return CancelResponse.ACCEPT

        def execute_callback(goal_handle):
            done = threading.Event()
            node._goal = {'handle': goal_handle, 'done': done, 'el': el, 'type': action_type,
                          'outcome': None}
            try:
                result = node._wait(node.runner.post(el.get('event'),
                                                     {'goal': goal_handle.request}))
                if result is None or not result.handled:
                    goal_handle.abort()
                    return action_type.Result()
                cancel_sent = False
                waits = str(el.get('cancel_waits', 'false')).lower() in ('true', '1', 'yes')
                while not done.wait(0.05):
                    if goal_handle.is_cancel_requested and not cancel_sent:
                        cancel_sent = True
                        node._goal['cancel_requested'] = True
                        node._wait(node.runner.post(el.get('cancel_event')))
                        if not waits:
                            node._goal['outcome'] = 'canceled'
                            done.set()
                    if node.runner is None or not node.runner.running:
                        node._goal['outcome'] = node._goal['outcome'] or 'aborted'
                        done.set()
                outcome = node._goal['outcome']
                response = node._goal.get('result') or action_type.Result()
                if outcome == 'succeeded':
                    goal_handle.succeed()
                elif outcome == 'canceled':
                    goal_handle.canceled()
                else:
                    goal_handle.abort()
                return response
            finally:
                node._goal = None

        server = ActionServer(self, action_type, el.get('name'),
                              execute_callback=execute_callback, goal_callback=goal_callback,
                              cancel_callback=cancel_callback, callback_group=self._group)
        self._keep(lambda s: destroy_waitable(self, s), server)

    # --- the chart as an action (run_as_action) -----------------------------------------

    def _create_run_server(self):
        name = self.get_parameter('run_as_action').value
        if not name:
            return
        from rclpy.action import ActionServer, CancelResponse, GoalResponse
        from statechart_ros.loader import load_engine_class, load_chart
        from statechart_ros_msgs.action import RunStatechart
        node = self
        busy = threading.Lock()

        def goal_callback(goal):
            if not node._accepting or node.runner is None or node.runner.running:
                return GoalResponse.REJECT
            if goal.chart and goal.chart not in (node.get_parameter('chart').value,
                                                 node.spec.path):
                node.get_logger().warning(f'RunStatechart goal for {goal.chart} rejected: '
                                          f'this node hosts {node.spec.path}')
                return GoalResponse.REJECT
            if goal.data:
                try:
                    data = json.loads(goal.data)
                    if not isinstance(data, dict):
                        raise ValueError('data is not an object')
                except ValueError as exc:
                    node.get_logger().warning(f'RunStatechart goal rejected: {exc}')
                    return GoalResponse.REJECT
            return GoalResponse.ACCEPT

        def execute(goal_handle):
            with busy:
                return node._run_goal(goal_handle, load_chart, load_engine_class, RunStatechart)

        server = ActionServer(self, RunStatechart, name, execute_callback=execute,
                              goal_callback=goal_callback,
                              cancel_callback=lambda _h: CancelResponse.ACCEPT,
                              callback_group=self._group)
        self._run_server = server
        self._keep(lambda s: destroy_waitable(self, s), server)

    def _run_goal(self, goal_handle, load_chart, load_engine_class, action):
        data = json.loads(goal_handle.request.data) if goal_handle.request.data else {}
        engine_class = None
        if data:
            params = {name: self.get_parameter(name).value for name in self.spec.params
                      if self.has_parameter(name)}
            variant = load_chart(self.spec.path, params=dict(params, **data), load_engine=False)
            engine_class = load_engine_class(variant)
        changed = threading.Event()

        def on_change():
            changed.set()

        self.runner.status_observers.append(on_change)
        result = action.Result()
        try:
            self.runner.start(engine_class=engine_class)
            self._publish_status(force=True)
            while True:
                if changed.wait(0.05):
                    changed.clear()
                    feedback = action.Feedback()
                    feedback.status = introspection.status_msg(
                        self.spec.name, self.runner.snapshot(), dict(self._data_json),
                        self.host.now())
                    goal_handle.publish_feedback(feedback)
                if goal_handle.is_cancel_requested:
                    self.runner.stop()
                    self._publish_status(force=True)
                    goal_handle.canceled()
                    return result
                if not self.runner.running:
                    final, donedata = self.runner.final or ('', {})
                    result.final_state = final
                    result.donedata = to_json(donedata) if donedata else ''
                    self._publish_status(force=True)
                    if final:
                        goal_handle.succeed()
                    else:
                        goal_handle.abort()
                    return result
        finally:
            if on_change in self.runner.status_observers:
                self.runner.status_observers.remove(on_change)

    def _action_server_progress(self, record):
        """On the worker: feedback for the active goal, and its result on ``result_on``."""
        goal = self._goal
        if goal is None or goal['outcome'] is not None:
            return
        el = goal['el']
        if el.get('feedback'):
            feedback = goal['type'].Feedback()
            built = self._call_user(el.get('feedback'), {'feedback': feedback,
                                                         'configuration': record.target})
            goal['handle'].publish_feedback(built if built is not None else feedback)
        result_on = el.get('result_on')
        if result_on and any(matches(result_on, ev) for ev in record.events):
            response = goal['type'].Result()
            available = {'result': response, 'configuration': record.target,
                         'cancel_requested': bool(goal.get('cancel_requested'))}
            if el.get('result'):
                built = self._call_user(el.get('result'), available)
                response = built if built is not None else response
            outcome = 'succeeded'
            if el.get('result_status'):
                outcome = self._call_user(el.get('result_status'),
                                          dict(available, result=response))
                if outcome not in ('succeeded', 'aborted', 'canceled'):
                    self.get_logger().error(f'result_status {el.get("result_status")} returned '
                                            f'{outcome!r}; the goal is aborted')
                    outcome = 'aborted'
            goal['result'] = response
            goal['outcome'] = outcome
            goal['done'].set()


def main(args=None):
    rclpy.init(args=args)
    node = StatechartNode()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        if node.get_parameter('autostart').value:
            def bring_up():
                if node.trigger_configure() == TransitionCallbackReturn.SUCCESS:
                    node.trigger_activate()
            threading.Thread(target=bring_up, daemon=True).start()
        spin(executor)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        try:
            if node.runner is not None:
                if not node.context.ok():
                    node.runner.observers.clear()
                    node.runner.status_observers.clear()
                node.runner.shutdown(timeout=2.0)
        except Exception:  # noqa: B902
            pass
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
