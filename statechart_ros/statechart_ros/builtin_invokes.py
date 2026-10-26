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
Built-in invoke kinds: ``ros:action``, ``ros:service_call``, ``ros:wait_for``.

This module declares what each kind accepts and which statuses it ends with;
the node runs them (``statechart_ros.invokes``).
"""

from statechart_ros.kinds import (
    ACTION_TYPE, Attr, BUILDER, ENUM, EVENT, FLOAT, GUARD, HANDLER, InvokeKind, MSG_TYPE,
    NAME, PATH, SRV_TYPE)

QOS_CHOICES = ('default', 'sensor', 'latched')


class ActionKind(InvokeKind):
    """Send a goal to an action server; the goal is cancelled when the state is left."""

    name = 'ros/action'
    attributes = {
        'server': Attr(NAME, required=True, doc='action server name'),
        'type': Attr(ACTION_TYPE, required=True, doc='action type'),
        'goal': Attr(BUILDER, doc='model method filling the goal'),
        'feedback': Attr(HANDLER, doc='model method receiving each feedback message'),
        'feedback_event': Attr(EVENT, doc='event sent with each feedback message'),
        'server_timeout': Attr(FLOAT, default=5.0, doc='seconds to wait for the server'),
        'cancel_timeout': Attr(FLOAT, default=5.0,
                               doc='seconds to wait for a cancel to be confirmed'),
    }
    statuses = ('succeeded', 'aborted', 'canceled', 'rejected', 'unavailable')


class ServiceCallKind(InvokeKind):
    """Call a service; the call is abandoned when the state is left."""

    name = 'ros/service_call'
    attributes = {
        'service': Attr(NAME, required=True, doc='service name'),
        'type': Attr(SRV_TYPE, required=True, doc='service type'),
        'request': Attr(BUILDER, doc='model method filling the request'),
        'response': Attr(HANDLER, doc='model method receiving the response'),
        'success': Attr(GUARD, doc='model method deciding from the response whether the '
                                   'call succeeded (default: every response succeeds)'),
        'timeout': Attr(FLOAT, default=10.0, doc='seconds to wait for the response'),
        'server_timeout': Attr(FLOAT, default=5.0, doc='seconds to wait for the service'),
    }
    statuses = ('succeeded', 'failed', 'timeout', 'unavailable')


class WaitForKind(InvokeKind):
    """Wait for a message on a topic, optionally one that passes a guard."""

    name = 'ros/wait_for'
    attributes = {
        'topic': Attr(NAME, required=True, doc='topic name'),
        'type': Attr(MSG_TYPE, required=True, doc='message type'),
        'when': Attr(GUARD, doc='model method accepting the message'),
        'timeout': Attr(FLOAT, doc='seconds to wait (default: no limit)'),
        'qos': Attr(ENUM, default='default', choices=QOS_CHOICES, doc='QoS profile'),
    }
    statuses = ('succeeded', 'timeout')


class ChartKind(InvokeKind):
    """Run a child chart in the same node; it is stopped when the state is left."""

    name = 'ros/chart'
    attributes = {
        'src': Attr(PATH, required=True, doc='the child chart: a path or package:// URL'),
    }
    statuses = ('succeeded', 'failed')

    @classmethod
    def summary(cls, attrs):
        return {'target': attrs.get('src', ''), 'type': 'chart'}


KINDS = [ActionKind, ServiceCallKind, WaitForKind, ChartKind]
