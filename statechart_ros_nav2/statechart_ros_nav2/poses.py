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
Poses for Nav2 goals: from the datamodel or from a file of named poses.

A ``pose`` attribute names a pose. The name is looked up first in the
datamodel (a ``geometry_msgs/PoseStamped``, a ``Pose``, a mapping with ``x``,
``y``, ``yaw`` and optionally ``frame_id``, or a list ``[x, y, yaw]``), then
in the YAML file given by the node parameter ``named_poses``::

    poses:
      kitchen: {x: 1.0, y: 2.0, yaw: 1.57}
      dock_area: [0.5, -1.0, 0.0]
    frame_id: map          # optional, default map
"""

import math

import yaml

NAMED_POSES_PARAM = 'named_poses'


def quaternion(yaw):
    return (0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0))


def to_pose_stamped(value, frame_id='map', stamp=None):
    """Convert a pose value into a geometry_msgs/PoseStamped."""
    from geometry_msgs.msg import Pose, PoseStamped
    if isinstance(value, PoseStamped):
        return value
    msg = PoseStamped()
    msg.header.frame_id = frame_id
    if stamp is not None:
        msg.header.stamp = stamp
    if isinstance(value, Pose):
        msg.pose = value
        return msg
    if isinstance(value, dict):
        msg.header.frame_id = value.get('frame_id', frame_id)
        x, y, yaw = float(value.get('x', 0.0)), float(value.get('y', 0.0)), \
            float(value.get('yaw', 0.0))
    elif isinstance(value, (list, tuple)) and len(value) in (2, 3):
        x, y = float(value[0]), float(value[1])
        yaw = float(value[2]) if len(value) == 3 else 0.0
    else:
        raise ValueError(f'cannot read a pose from {value!r}')
    msg.pose.position.x = x
    msg.pose.position.y = y
    qx, qy, qz, qw = quaternion(yaw)
    msg.pose.orientation.x = qx
    msg.pose.orientation.y = qy
    msg.pose.orientation.z = qz
    msg.pose.orientation.w = qw
    return msg


class NamedPoses:
    """The poses of a YAML file, loaded once."""

    def __init__(self, path=None):
        self.path = path
        self.poses = {}
        self.frame_id = 'map'
        if path:
            from statechart_ros.loader import resolve_path
            with open(resolve_path(path)) as f:
                data = yaml.safe_load(f) or {}
            self.poses = dict(data.get('poses', {}))
            self.frame_id = data.get('frame_id', 'map')

    def __contains__(self, name):
        return name in self.poses

    def get(self, name):
        return self.poses[name]


def resolve(name, datamodel, named, stamp=None):
    """Return the PoseStamped a name stands for."""
    value = getattr(datamodel, name, None) if datamodel is not None else None
    if value is not None and not callable(value):
        return to_pose_stamped(value, named.frame_id if named else 'map', stamp)
    if named is not None and name in named:
        return to_pose_stamped(named.get(name), named.frame_id, stamp)
    where = f' or in {named.path}' if named is not None and named.path else ''
    raise KeyError(f'pose "{name}" is neither a datamodel value{where}')
