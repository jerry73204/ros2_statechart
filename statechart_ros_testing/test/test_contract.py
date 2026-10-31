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


"""Contract checks against a running graph (P8)."""

import uuid

from example_interfaces.action import Fibonacci
import pytest
import rclpy
from rclpy.action import ActionClient, ActionServer
from rclpy.qos import qos_profile_sensor_data, QoSProfile
from statechart_ros_testing import assert_provides, check_graph, load_interface
from std_msgs.msg import Bool, Float32, String
from std_srvs.srv import Trigger

INTERFACE = """\
statechart_interface: 1
chart: robot
subscribes:
- {name: battery, type: std_msgs/msg/Float32, qos: default}
- {name: e_stop, type: std_msgs/msg/Bool, qos: default}
- {name: odom, type: std_msgs/msg/Float32, qos: sensor}
publishes:
- {name: lamp, type: std_msgs/msg/String, qos: default}
services_served:
- {name: ~/command, type: statechart_ros_msgs/srv/SendEvent, commands: [start]}
services_called:
- {name: arm/hold, type: std_srvs/srv/Trigger}
actions_called:
- {name: drive, type: example_interfaces/action/Fibonacci}
parameters_set:
- {name: max_speed, node: /controller}
"""


@pytest.fixture
def graph(tmp_path):
    rclpy.init()
    path = tmp_path / 'robot.interface.yaml'
    path.write_text(INTERFACE)
    # a namespace per test: endpoints of a destroyed node can linger in the graph
    ns = '/robot_' + uuid.uuid4().hex[:8]
    probe = rclpy.create_node('probe', namespace=ns)
    nodes = [probe]
    yield probe, load_interface(str(path)), nodes, ns
    for n in nodes:
        n.destroy_node()
    rclpy.shutdown()


def test_the_matching_nodes_pass(graph):
    probe, iface, nodes, ns = graph
    party = rclpy.create_node('party', namespace=ns)
    nodes.append(party)
    party.create_publisher(Bool, 'e_stop', 10)
    party.create_publisher(Float32, 'odom', qos_profile_sensor_data)  # best effort offered
    party.create_service(Trigger, 'arm/hold', lambda req, res: res)
    ActionServer(party, Fibonacci, 'drive', lambda goal: Fibonacci.Result())
    names = ['e_stop', 'odom', 'arm/hold', 'drive']
    assert check_graph(probe, iface, names=names, namespace=ns) == []
    assert_provides(probe, iface, names, namespace=ns)


def test_missing_wrong_type_and_incompatible_qos_are_reported(graph):
    probe, iface, nodes, ns = graph
    party = rclpy.create_node('party', namespace=ns)
    nodes.append(party)
    party.create_publisher(String, 'e_stop', 10)                          # wrong type
    party.create_publisher(Float32, 'battery', qos_profile_sensor_data)   # best effort only
    problems = check_graph(probe, iface, sections=['subscribes', 'actions_called'],
                           namespace=ns, timeout=1.0)
    assert problems == [
        f'subscribes battery ({ns}/battery): no publisher with QoS compatible with "default"',
        f'subscribes e_stop ({ns}/e_stop): publishers have type std_msgs/msg/String, '
        'not std_msgs/msg/Bool',
        f'subscribes odom ({ns}/odom): no publisher',
        f'actions_called drive ({ns}/drive): no action server',
    ]
    with pytest.raises(AssertionError, match='no publisher'):
        assert_provides(probe, iface, ['odom'], namespace=ns, timeout=0.5)


def test_served_and_published_endpoints_need_their_users(graph):
    probe, iface, nodes, ns = graph
    user = rclpy.create_node('user', namespace=ns)
    nodes.append(user)
    user.create_subscription(String, 'lamp', lambda m: None, QoSProfile(depth=1))
    from statechart_ros_msgs.srv import SendEvent
    user.create_client(SendEvent, 'mission/command')
    ActionClient(user, Fibonacci, 'other')
    problems = check_graph(probe, iface, sections=['publishes', 'services_served'],
                           namespace=ns, node_name='mission', timeout=1.0)
    assert problems == []
    problems = check_graph(probe, iface, sections=['parameters_set'], timeout=0.5)
    assert problems == ['parameters_set /controller max_speed: no node /controller']
