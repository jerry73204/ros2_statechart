#!/usr/bin/env bash
# Use the installed Debian packages the way a user does: validate a chart,
# run it in statechart_node, send it an event and see the new state.
#
#   smoke_debs.sh <distro>
set -eo pipefail

distro=$1
source "/opt/ros/$distro/setup.bash"
set -u

python3 -c "import statemachine; print('python-statemachine', statemachine.__version__)"

work=$(mktemp -d)
chart=$work/smoke.scxml
cat > "$chart" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<scxml xmlns="http://www.w3.org/2005/07/scxml"
       xmlns:ros="https://github.com/jerry73204/ros2_statechart/ns/1"
       version="1.0" datamodel="python" initial="IDLE">
  <state id="IDLE">
    <transition event="go" target="RUNNING"/>
  </state>
  <state id="RUNNING">
    <transition event="stop" target="IDLE"/>
  </state>
</scxml>
EOF

ros2 statechart validate "$chart"
if [ "$distro" != humble ]; then
  # Humble's Nav2 has no docking actions, which the example uses.
  ros2 statechart validate \
    "$(ros2 pkg prefix statechart_ros_nav2)/share/statechart_ros_nav2/examples/patrol.scxml"
fi

ros2 run statechart_ros statechart_node --ros-args -r __node:=smoke \
  -p chart:="$chart" -p debug_events:=true > "$work/node.log" 2>&1 &
node=$!
trap 'kill $node 2> /dev/null || true; cat "$work/node.log"' EXIT

for _ in $(seq 30); do
  ros2 statechart show /smoke 2> /dev/null | grep -q IDLE && break
  sleep 1
done
ros2 statechart send /smoke go --timeout 10
ros2 statechart show /smoke | tee "$work/show.txt"
grep -q RUNNING "$work/show.txt"
echo "smoke test passed"
