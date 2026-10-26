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

package_name = 'statechart_ros'

setup(
    name=package_name,
    version='0.1.1',
    packages=find_packages(exclude=['test']),
    package_data={package_name: ['schema/*.xsd', 'schema/*.md', 'schema/w3c/*.xsd',
                                 'schema/w3c/*.md']},
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/examples', glob('examples/*.scxml')),
        ('share/' + package_name + '/examples/tutorial', glob('examples/tutorial/*.scxml')),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=False,
    maintainer='jerry73204',
    maintainer_email='jerry73204@gmail.com',
    description=(
        'The node that hosts a statechart: loader for the ros: extension of '
        'SCXML, one event queue, invokes, outputs, introspection, lifecycle.'
    ),
    license='Apache-2.0',
    tests_require=['pytest'],
    extras_require={'test': ['pytest']},
    entry_points={
        'console_scripts': [
            'statechart_node = statechart_ros.node:main',
        ],
    },
)
