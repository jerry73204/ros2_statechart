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
Spin an executor without dying when an entity is destroyed while it waits.

rclpy on Humble raises ``InvalidHandle`` from the executor when a
subscription, timer or client is destroyed between the executor's wait and
its take, which a lifecycle cleanup does by design. Later rclpy releases
handle it inside the executor. ``spin`` retries in that case; the node's own
``main`` uses it, and so should a program that adds the node to its own
executor on Humble.
"""

from rclpy.executors import ExternalShutdownException, ShutdownException

try:
    from rclpy._rclpy_pybind11 import InvalidHandle
except ImportError:  # pragma: no cover - other rclpy layouts
    InvalidHandle = RuntimeError


def spin(executor, timeout_sec=0.1):
    """Spin until the context or the executor shuts down."""
    while executor.context.ok():
        try:
            executor.spin_once(timeout_sec=timeout_sec)
        except (ShutdownException, ExternalShutdownException):
            return
        except InvalidHandle:
            continue
        except Exception:  # noqa: B902 - errors from a context shut down meanwhile
            if not executor.context.ok():
                return
            raise
