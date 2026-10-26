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
The patrol example on Nav2's own simulation, without Gazebo.

Nav2's TurtleBot3 loopback simulation (nav2_bringup tb3_loopback_simulation:
map server, Nav2, docking server and nav2_loopback_sim, which integrates
cmd_vel and fakes the laser from the map), with one dock added to the docking
server's parameters, the initial pose published once, a fake battery, and the
patrol chart.
"""

import os
import tempfile

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription,
                            OpaqueFunction, TimerAction)
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import yaml

DOCK_POSE = [-2.2, 0.55, 3.1416]
INITIAL_POSE = ('{header: {frame_id: map}, pose: {pose: {position: {x: -2.0, y: -0.5}, '
                'orientation: {w: 1.0}}}}')


def nav2_params_with_dock():
    """Nav2's default parameters plus one dock, written to a temporary file."""
    bringup = get_package_share_directory('nav2_bringup')
    with open(os.path.join(bringup, 'params', 'nav2_params.yaml')) as f:
        params = yaml.safe_load(f)
    docking = params['docking_server']['ros__parameters']
    docking['docks'] = ['home_dock']
    docking['home_dock'] = {'type': 'simple_charging_dock', 'frame': 'map',
                            'pose': DOCK_POSE}
    docking['simple_charging_dock']['use_external_detection_pose'] = False
    out = tempfile.NamedTemporaryFile('w', prefix='patrol_nav2_', suffix='.yaml',
                                      delete=False)
    with out:
        yaml.safe_dump(params, out)
    return out.name


def launch_setup(context):
    bringup = get_package_share_directory('nav2_bringup')
    share = get_package_share_directory('statechart_ros_nav2')
    params_file = nav2_params_with_dock()
    return [
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(os.path.join(bringup, 'launch',
                                                       'tb3_loopback_simulation.launch.py')),
            launch_arguments={'params_file': params_file, 'use_rviz':
                              LaunchConfiguration('use_rviz')}.items()),
        TimerAction(period=5.0, actions=[ExecuteProcess(
            cmd=['ros2', 'topic', 'pub', '--once', '-w', '1', '/initialpose',
                 'geometry_msgs/msg/PoseWithCovarianceStamped', INITIAL_POSE],
            output='screen')]),
        Node(package='statechart_ros_nav2', executable='fake_battery', name='fake_battery',
             condition=IfCondition(LaunchConfiguration('fake_battery')),
             parameters=[{'use_sim_time': True}]),
        Node(package='statechart_ros', executable='statechart_node', name='patrol',
             output='screen',
             parameters=[{'use_sim_time': True,
                          'chart': LaunchConfiguration('chart'),
                          'named_poses': os.path.join(share, 'examples', 'sandbox_poses.yaml'),
                          'datamodel_publish': ['laps']}]),
    ]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('chart', default_value='package://statechart_ros_nav2/'
                                                     'examples/patrol.scxml'),
        DeclareLaunchArgument('use_rviz', default_value='False'),
        DeclareLaunchArgument('fake_battery', default_value='True',
                              description='start the fake battery (tests publish their own)'),
        OpaqueFunction(function=launch_setup),
    ])
