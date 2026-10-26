# P3: Nav2 integration

## Goal

Drive Nav2 from a chart with no goal-building code for the common actions,
with outcomes and errors that read well in the chart.

## Delivers

- `statechart_ros_nav2` invoke kinds: `nav2/navigate_to_pose`,
  `nav2/navigate_through_poses`, `nav2/follow_waypoints`, `nav2/dock`,
  `nav2/undock`, `nav2/spin`, `nav2/back_up`, `nav2/wait`, `nav2/active`,
  each with typed attributes (poses from datamodel values or a YAML file of
  named poses, dock ids or poses, staging) and documented statuses.
- Error-code tables for each action, from `nav2_msgs` of the target
  distribution, as `error_name` in outcome data.
- Feedback summaries for the status and the viewer.
- Example: a simulated robot from Nav2's own simulation setup that patrols
  named poses, docks at the demo charging dock when a battery topic falls
  below a threshold, and pauses and resumes on a service; written as one
  chart with parallel regions (mode, safety, task) and history for resume.

## Checks

- Each kind tested against a fake server and once against real Nav2 in
  simulation (nightly CI job).
- The example's scenario test: patrol, low battery, dock, pause during
  navigation, resume continues the same goal, cancel ends the task.

## Leaves out

Any change to Nav2 itself.
