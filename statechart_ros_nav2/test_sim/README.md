# Tests against Nav2 in simulation

Run nightly in CI (`.github/workflows/nightly.yml`), not on every push: each
launches Nav2's TurtleBot3 loopback simulation (`nav2_bringup`,
`nav2_loopback_sim`) through `launch/patrol_sim.launch.py`.

| File | What it checks |
|---|---|
| `sim_all_kinds.py` with `all_kinds.scxml` | every Nav2 kind (`navigate_to_pose`, `navigate_through_poses`, `follow_waypoints`, `spin`, `back_up`, `wait`, `dock`, `undock`, `active`) succeeds once against the real servers |
| `sim_patrol.py` | the patrol example: legs reached by Nav2, low battery, docking and undocking, pause and resume, cancel |

```bash
sudo apt install ros-jazzy-nav2-bringup ros-jazzy-nav2-loopback-sim
launch_test statechart_ros_nav2/test_sim/sim_all_kinds.py
launch_test statechart_ros_nav2/test_sim/sim_patrol.py
```

The file names do not start with `test_`, so the per-push `colcon test`
does not collect them.
