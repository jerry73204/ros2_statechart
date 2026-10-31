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
Nav2 invoke kinds: ``<ros:invoke kind="nav2/..."/>``.

Each kind fills its Nav2 goal from typed attributes (poses by name, dock ids,
distances), so most charts need no goal builder; a ``goal`` builder still
runs afterwards for anything else. Outcomes carry ``error_name`` and
``error_source`` (statechart_ros_nav2.errors) next to ``error_code``, and the
feedback is summarised for the status and the viewer.
"""

from statechart_ros.builtin_invokes import ActionKind, wait_ready
from statechart_ros.kinds import (Attr, BOOL, BUILDER, EVENT, FLOAT, HANDLER, INT, InvokeKind,
                                  NAME, Outcome, STRING)
from statechart_ros_nav2 import errors, poses

ACTION_STATUSES = ('succeeded', 'aborted', 'canceled', 'rejected', 'unavailable')


def _duration(seconds):
    from builtin_interfaces.msg import Duration
    d = Duration()
    d.sec = int(seconds)
    d.nanosec = int(round((seconds - int(seconds)) * 1e9)) % 1000000000
    return d


def _seconds(duration):
    return duration.sec + duration.nanosec * 1e-9


def common(server):
    """Attributes every Nav2 action kind accepts."""
    return {
        'server': Attr(NAME, default=server, doc=f'action server (default {server})'),
        'goal': Attr(BUILDER, doc='model method completing the goal after the kind filled it'),
        'feedback': Attr(HANDLER, doc='model method receiving each feedback message'),
        'feedback_event': Attr(EVENT, doc='event sent with each feedback message'),
        'server_timeout': Attr(FLOAT, default=5.0, doc='seconds to wait for the server'),
        'cancel_timeout': Attr(FLOAT, default=5.0,
                               doc='seconds to wait for a cancel to be confirmed'),
    }


class Nav2ActionKind(ActionKind):
    """Base of the Nav2 action kinds: a fixed action type and server name."""

    action = ''
    server = ''
    attributes = common('')
    statuses = ACTION_STATUSES

    @classmethod
    def interfaces(cls, attrs):
        return [('action', f'nav2_msgs/action/{cls.action}')]

    @classmethod
    def endpoints(cls, attrs):
        return [{'kind': 'action', 'name': attrs.get('server', cls.server),
                 'type': f'nav2_msgs/action/{cls.action}'}]

    @classmethod
    def summary(cls, attrs):
        what = attrs.get('pose') or attrs.get('poses') or attrs.get('dock_id') or \
            attrs.get('dock_pose')
        server = attrs.get('server', cls.server)
        return {'target': f'{server} {what}' if what else server,
                'type': f'nav2_msgs/action/{cls.action}'}

    def __init__(self, host, state_id, attrs):
        attrs = dict(attrs)
        attrs.setdefault('server', self.server)
        attrs['type'] = f'nav2_msgs/action/{self.action}'
        super().__init__(host, state_id, attrs)

    def setup(self):
        super().setup()
        node = self.host.node
        if not node.has_parameter(poses.NAMED_POSES_PARAM):
            node.declare_parameter(poses.NAMED_POSES_PARAM, '')
        path = node.get_parameter(poses.NAMED_POSES_PARAM).value
        self.named = poses.NamedPoses(path or None)

    def make_goal(self, invocation):
        goal = self.action_type.Goal()
        runner = self.host.runner
        runner.run_in_worker(self.fill, goal, runner.model, cancelled=invocation.cancelled)
        if self.attrs.get('goal'):
            built = runner.call_model(self.attrs['goal'], cancelled=invocation.cancelled,
                                      goal=goal)
            if built is not None:
                goal = built
        return goal

    def fill(self, goal, datamodel):
        """Fill the goal from the attributes (runs on the worker)."""

    def pose(self, name, datamodel):
        return poses.resolve(name, datamodel, self.named, self.host.node.get_clock().now()
                             .to_msg())

    def error_name(self, code):
        return errors.error_name(code, self.action)

    def outcome(self, status, result):
        out = super().outcome(status, result)
        out.data['error_source'] = errors.error_source(out.error_code, self.action)
        return out


class NavigateToPose(Nav2ActionKind):
    """Navigate to one pose with bt_navigator."""

    name = 'nav2/navigate_to_pose'
    action = 'NavigateToPose'
    server = 'navigate_to_pose'
    attributes = dict(common('navigate_to_pose'), **{
        'pose': Attr(STRING, required=True, doc='name of the goal pose'),
        'behavior_tree': Attr(STRING, doc="behavior tree file (default: the navigator's)"),
    })

    def fill(self, goal, datamodel):
        goal.pose = self.pose(self.attrs['pose'], datamodel)
        goal.behavior_tree = self.attrs.get('behavior_tree', '')

    def feedback_summary(self, feedback):
        return {'distance_remaining': round(float(feedback.distance_remaining), 2),
                'number_of_recoveries': int(feedback.number_of_recoveries),
                'estimated_time_remaining': round(_seconds(feedback.estimated_time_remaining),
                                                  1)}


def _pose_list(kind, datamodel):
    names = kind.attrs['poses'].split()
    if len(names) == 1:
        value = getattr(datamodel, names[0], None)
        is_list = isinstance(value, (list, tuple)) and value
        if is_list and not isinstance(value[0], (int, float)):
            return [poses.to_pose_stamped(v, kind.named.frame_id) for v in value]
    return [kind.pose(name, datamodel) for name in names]


class NavigateThroughPoses(Nav2ActionKind):
    """Navigate through several poses with bt_navigator."""

    name = 'nav2/navigate_through_poses'
    action = 'NavigateThroughPoses'
    server = 'navigate_through_poses'
    attributes = dict(common('navigate_through_poses'), **{
        'poses': Attr(STRING, required=True,
                      doc='names of the poses, space-separated, or one datamodel list'),
        'behavior_tree': Attr(STRING, doc='behavior tree file'),
    })

    def fill(self, goal, datamodel):
        goal.poses = _pose_list(self, datamodel)
        goal.behavior_tree = self.attrs.get('behavior_tree', '')

    def feedback_summary(self, feedback):
        return {'distance_remaining': round(float(feedback.distance_remaining), 2),
                'number_of_poses_remaining': int(feedback.number_of_poses_remaining),
                'number_of_recoveries': int(feedback.number_of_recoveries)}


class FollowWaypoints(Nav2ActionKind):
    """Visit waypoints with the waypoint follower."""

    name = 'nav2/follow_waypoints'
    action = 'FollowWaypoints'
    server = 'follow_waypoints'
    attributes = dict(common('follow_waypoints'), **{
        'poses': Attr(STRING, required=True,
                      doc='names of the waypoints, space-separated, or one datamodel list'),
        'loops': Attr(INT, default=0, doc='number of extra loops'),
    })

    def fill(self, goal, datamodel):
        goal.poses = _pose_list(self, datamodel)
        goal.number_of_loops = self.attr('loops')

    def feedback_summary(self, feedback):
        return {'current_waypoint': int(feedback.current_waypoint)}


DOCK_STATES = {0: 'none', 1: 'nav_to_staging_pose', 2: 'initial_perception',
               3: 'controlling', 4: 'wait_for_charge', 5: 'retry'}


class Dock(Nav2ActionKind):
    """Dock with the docking server, at a dock of its database or at a pose."""

    name = 'nav2/dock'
    action = 'DockRobot'
    server = 'dock_robot'
    attributes = dict(common('dock_robot'), **{
        'dock_id': Attr(STRING, doc="dock in the docking server's database"),
        'dock_pose': Attr(STRING, doc='name of the dock pose (instead of dock_id)'),
        'dock_type': Attr(STRING, doc='dock plugin, with dock_pose'),
        'staging': Attr(BOOL, default=True, doc='navigate to the staging pose first'),
        'max_staging_time': Attr(FLOAT, default=1000.0, doc='seconds to reach staging'),
    })

    @classmethod
    def check(cls, attrs):
        if bool(attrs.get('dock_id')) == bool(attrs.get('dock_pose')):
            return ['give exactly one of dock_id and dock_pose']
        return []

    def fill(self, goal, datamodel):
        if self.attrs.get('dock_id'):
            goal.use_dock_id = True
            goal.dock_id = self.attrs['dock_id']
        else:
            goal.use_dock_id = False
            goal.dock_pose = self.pose(self.attrs['dock_pose'], datamodel)
        goal.dock_type = self.attrs.get('dock_type', '')
        goal.navigate_to_staging_pose = self.attr('staging')
        goal.max_staging_time = self.attr('max_staging_time')

    def outcome(self, status, result):
        if status == 'succeeded' and result is not None and not result.success:
            status = 'aborted'
        out = super().outcome(status, result)
        if result is not None:
            out.data['num_retries'] = int(result.num_retries)
        return out

    def feedback_summary(self, feedback):
        return {'state': DOCK_STATES.get(int(feedback.state), str(feedback.state)),
                'num_retries': int(feedback.num_retries),
                'docking_time': round(_seconds(feedback.docking_time), 1)}


class Undock(Nav2ActionKind):
    """Undock with the docking server."""

    name = 'nav2/undock'
    action = 'UndockRobot'
    server = 'undock_robot'
    attributes = dict(common('undock_robot'), **{
        'dock_type': Attr(STRING, doc='dock plugin (needed when the server has several)'),
        'max_undocking_time': Attr(FLOAT, default=30.0, doc='seconds to undock'),
    })

    def fill(self, goal, datamodel):
        goal.dock_type = self.attrs.get('dock_type', '')
        goal.max_undocking_time = self.attr('max_undocking_time')

    def outcome(self, status, result):
        if status == 'succeeded' and result is not None and not result.success:
            status = 'aborted'
        return super().outcome(status, result)


class Spin(Nav2ActionKind):
    """Turn in place with the behavior server."""

    name = 'nav2/spin'
    action = 'Spin'
    server = 'spin'
    attributes = dict(common('spin'), **{
        'angle': Attr(FLOAT, required=True, doc='angle to turn, in radians'),
        'time_allowance': Attr(FLOAT, default=10.0, doc='seconds allowed'),
    })

    def fill(self, goal, datamodel):
        goal.target_yaw = float(self.attrs['angle'])
        goal.time_allowance = _duration(self.attr('time_allowance'))

    def feedback_summary(self, feedback):
        return {'angular_distance_traveled': round(float(feedback.angular_distance_traveled),
                                                   2)}


class BackUp(Nav2ActionKind):
    """Drive backwards in a straight line with the behavior server."""

    name = 'nav2/back_up'
    action = 'BackUp'
    server = 'backup'
    attributes = dict(common('backup'), **{
        'distance': Attr(FLOAT, required=True, doc='metres to back up'),
        'speed': Attr(FLOAT, default=0.1, doc='metres per second'),
        'time_allowance': Attr(FLOAT, default=10.0, doc='seconds allowed'),
    })

    def fill(self, goal, datamodel):
        goal.target.x = abs(float(self.attrs['distance']))
        goal.speed = abs(self.attr('speed'))
        goal.time_allowance = _duration(self.attr('time_allowance'))

    def feedback_summary(self, feedback):
        return {'distance_traveled': round(float(feedback.distance_traveled), 2)}


class Wait(Nav2ActionKind):
    """Wait with the behavior server."""

    name = 'nav2/wait'
    action = 'Wait'
    server = 'wait'
    attributes = dict(common('wait'), **{
        'duration': Attr(FLOAT, required=True, doc='seconds to wait'),
    })

    def fill(self, goal, datamodel):
        goal.time = _duration(float(self.attrs['duration']))

    def feedback_summary(self, feedback):
        return {'time_left': round(_seconds(feedback.time_left), 1)}


class Active(InvokeKind):
    """Succeed once the named Nav2 lifecycle managers report their nodes active."""

    name = 'nav2/active'
    attributes = {
        'managers': Attr(STRING, default='lifecycle_manager_navigation',
                         doc='lifecycle manager node names, space-separated'),
        'timeout': Attr(FLOAT, default=60.0, doc='seconds to wait'),
        'period': Attr(FLOAT, default=0.5, doc='seconds between checks'),
    }
    statuses = ('succeeded', 'timeout')

    @classmethod
    def interfaces(cls, attrs):
        return [('srv', 'std_srvs/srv/Trigger')]

    @classmethod
    def endpoints(cls, attrs):
        managers = attrs.get('managers', cls.attributes['managers'].default).split()
        return [{'kind': 'service', 'name': m.rstrip('/') + '/is_active',
                 'type': 'std_srvs/srv/Trigger'} for m in managers]

    @classmethod
    def summary(cls, attrs):
        return {'target': attrs.get('managers', 'lifecycle_manager_navigation'),
                'type': 'nav2 lifecycle'}

    def setup(self):
        from std_srvs.srv import Trigger
        self.clients = {}
        for manager in self.attr('managers').split():
            name = manager.rstrip('/') + '/is_active'
            self.clients[manager] = self.host.node.create_client(
                Trigger, name, callback_group=self.host.callback_group)

    def teardown(self):
        for client in getattr(self, 'clients', {}).values():
            self.host.node.destroy_client(client)
        self.clients = {}

    def run(self, invocation):
        from std_srvs.srv import Trigger
        from statechart_ros.builtin_invokes import wait_future
        host = self.host
        deadline = host.now() + self.attr('timeout')
        pending = set(self.clients)
        while pending:
            for manager in sorted(pending):
                client = self.clients[manager]
                remaining = max(0.0, deadline - host.now())
                if wait_ready(host, client.service_is_ready, invocation,
                              min(remaining, self.attr('period'))) != 'done':
                    continue
                future = client.call_async(Trigger.Request())
                if wait_future(host, future, invocation, self.attr('period') * 4) == 'done':
                    if future.result().success:
                        pending.discard(manager)
                else:
                    client.remove_pending_request(future)
            if invocation.cancelled.is_set():
                return None
            invocation.feedback({'waiting_for': ' '.join(sorted(pending))})
            if not pending:
                break
            if host.now() >= deadline:
                return Outcome('timeout', error_msg='not active: ' + ', '.join(sorted(pending)))
            if invocation.cancelled.wait(min(self.attr('period'),
                                             max(0.0, deadline - host.now()))):
                return None
        return Outcome('succeeded')


KINDS = [NavigateToPose, NavigateThroughPoses, FollowWaypoints, Dock, Undock, Spin, BackUp,
         Wait, Active]
