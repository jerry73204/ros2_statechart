# One state of a chart, with what it does in ROS.

uint8 ATOMIC = 0
uint8 COMPOUND = 1
uint8 PARALLEL = 2
uint8 FINAL = 3
uint8 HISTORY = 4

# State id. States of a child chart (ros:chart) are qualified by the id of the
# state that invokes it: "DOCK_PROCEDURE/APPROACH".
string id
# Parent state id; empty for a top-level state of the root chart.
string parent
uint8 kind
# Initial child states (compound states).
string[] initial
# "shallow" or "deep" for history states, else empty.
string history
string[] children
# The chart this state belongs to: empty for the root chart, otherwise the
# qualified id of the state invoking the child chart.
string chart

# The state's invoke, if any: kind ("ros/action", "nav2/dock", ...), target
# (server, service or topic name) and interface type.
string invoke_kind
string invoke_target
string invoke_type
# ros:on_entry and ros:on_exit outputs, as short labels.
string[] outputs
# ros:after timeouts, as "event after N s".
string[] timeouts
# ros:refuse and ros:ignore, as "event: reason".
string[] refuses
string[] ignores
# Source line in the chart document.
uint32 line
