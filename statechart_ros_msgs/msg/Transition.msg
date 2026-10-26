# One processed event and what it did: published on ~/transitions.

builtin_interfaces/Time stamp
string name
uint64 sequence
string event
# Event data as JSON (ROS messages converted to dictionaries).
string data
string[] source_configuration
string[] target_configuration
# The transitions taken, as "source -> target" (target empty when targetless).
string[] taken
bool handled
string refusal
# The reason, when a ros:ignore matched (handled stays true; "ignored" if none given).
string ignored
# Processing time of the macrostep, in seconds.
float64 duration
