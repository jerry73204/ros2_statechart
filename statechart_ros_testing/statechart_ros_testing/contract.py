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
Contract checks for packages that work with a chart they do not own.

A package that publishes a chart's inputs, or serves the actions it calls,
tests its own nodes against the chart's interface file, without the chart:

    iface = load_interface('mission.interface.yaml')
    problems = check_graph(test_node, iface, names=['health', 'e_stop'])
    assert problems == [], problems
"""

from statechart_ros import interface as _interface


def load_interface(path):
    """Read an interface file written by ``ros2 statechart interface``."""
    return _interface.load(path)


def check_graph(node, interface, sections=None, names=None, namespace='/',
                node_name='statechart', timeout=5.0):
    """
    Return what the running graph lacks for an interface, as strings (empty: all there).

    ``node`` is any node of the test, used to read the graph. Each endpoint of
    ``sections`` (default: all) whose name is in ``names`` (default: all)
    needs its counterpart: a publisher of a topic the chart subscribes to,
    with the type and a compatible QoS; a subscriber of a topic it publishes;
    a server of a service or action it calls; a client of one it serves.
    Relative names resolve against ``namespace`` and the chart node's name.
    """
    return _interface.check_graph(node, interface, sections=sections, names=names,
                                  namespace=namespace, node_name=node_name, timeout=timeout)


def assert_provides(node, interface, names, sections=None, **kwargs):
    """Fail with the list of problems unless the graph provides these endpoints."""
    problems = check_graph(node, interface, sections=sections, names=names, **kwargs)
    assert not problems, 'the graph does not match the interface:\n  ' + '\n  '.join(problems)
