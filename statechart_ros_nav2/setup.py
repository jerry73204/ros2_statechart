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

from glob import glob

from setuptools import find_packages, setup

package_name = 'statechart_ros_nav2'

setup(
    name=package_name,
    version='0.1.3',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/examples',
         glob('examples/*.scxml') + glob('examples/*.yaml')),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='jerry73204',
    maintainer_email='jerry73204@gmail.com',
    description=(
        'Nav2 invoke kinds for statechart_ros: navigation, docking and behavior'
        ' actions, error-code names, waiting for Nav2 to be active.'
    ),
    license='Apache-2.0',
    tests_require=['pytest'],
    extras_require={'test': ['pytest']},
    entry_points={
        'console_scripts': [
            'fake_battery = statechart_ros_nav2.examples.fake_battery:main',
        ],
        'statechart_ros.invokes': [
            'nav2/navigate_to_pose = statechart_ros_nav2.kinds:NavigateToPose',
            'nav2/navigate_through_poses = statechart_ros_nav2.kinds:NavigateThroughPoses',
            'nav2/follow_waypoints = statechart_ros_nav2.kinds:FollowWaypoints',
            'nav2/dock = statechart_ros_nav2.kinds:Dock',
            'nav2/undock = statechart_ros_nav2.kinds:Undock',
            'nav2/spin = statechart_ros_nav2.kinds:Spin',
            'nav2/back_up = statechart_ros_nav2.kinds:BackUp',
            'nav2/wait = statechart_ros_nav2.kinds:Wait',
            'nav2/active = statechart_ros_nav2.kinds:Active',
        ],
    },
)
