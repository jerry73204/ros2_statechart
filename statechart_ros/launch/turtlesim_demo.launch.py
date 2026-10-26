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

"""Turtlesim and the example chart that drives it."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def default_chart():
    """Turtlesim's interfaces moved to turtlesim_msgs after Jazzy."""
    from ament_index_python.packages import get_package_share_directory, PackageNotFoundError
    try:
        get_package_share_directory('turtlesim_msgs')
        return 'package://statechart_ros/examples/turtlesim_demo_msgs.scxml'
    except PackageNotFoundError:
        return 'package://statechart_ros/examples/turtlesim_demo.scxml'


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('chart', default_value=default_chart()),
        Node(package='turtlesim', executable='turtlesim_node', name='turtlesim'),
        Node(package='statechart_ros', executable='statechart_node', name='turtle_demo',
             output='screen',
             parameters=[{'chart': LaunchConfiguration('chart'),
                          'datamodel_publish': ['laps']}]),
    ])
