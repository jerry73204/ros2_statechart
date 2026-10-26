# One transition of a chart, as written or as expanded from ros: elements.

string source
# Event descriptors, space-separated; empty for an eventless transition.
string event
# Guard expression or name; generated outcome conditions are "sc_ros_outcome_...".
string cond
string[] targets
# "external" or "internal".
string type
# Where it comes from: "scxml", "outcome", "refuse" or "ignore".
string origin
# For outcomes, the statuses (and guard); for refusals, the reason.
string label
uint32 line
