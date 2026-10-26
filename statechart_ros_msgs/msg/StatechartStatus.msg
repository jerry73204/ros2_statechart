# The state of a running chart: published, latched, on ~/status after every change.

builtin_interfaces/Time stamp
string name
# Number of the macrostep this status follows.
uint64 sequence
# Active states, in document order (child chart states qualified).
string[] active
string last_event
# Whether the last event was handled (a transition other than a refusal was taken).
bool handled
# The reason, when the last event was refused.
string refusal
# The reason, when a ros:ignore matched the last event (handled stays true).
string ignored
# Selected datamodel values (parameter datamodel_publish).
DataValue[] data
InvokeStatus[] invokes
# False before activation and after deactivation.
bool running
