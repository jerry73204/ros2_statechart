# The structure of a running chart: published once, latched, on ~/structure.

builtin_interfaces/Time stamp
# Chart name and source document.
string name
string source
# The node hosting the chart.
string node
string[] initial
# States in document order; child charts' states follow the state that invokes them.
StateInfo[] states
TransitionInfo[] transitions
# Events ROS inputs can send (topics, timers, servers) and command events.
string[] input_events
# Whether ~/send_event is available.
bool debug_events
