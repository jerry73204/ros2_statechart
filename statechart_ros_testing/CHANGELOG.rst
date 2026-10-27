^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Changelog for package statechart_ros_testing
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

0.1.6 (2026-10-28)
------------------
* No changes; released with statechart_ros 0.1.6.

0.1.5 (2026-10-27)
------------------
* No changes; released with statechart_ros 0.1.5.

0.1.4 (2026-10-27)
------------------
* No changes; released with statechart_ros_viewer 0.1.4.

0.1.3 (2026-10-27)
------------------
* A ``message=`` or ``request=`` builder of an output gets a message of the declared type, filled from ``value=``, as on the robot (it got ``None``, so the output failed and was not recorded); the recorded value takes ``value=``'s form.

0.1.2 (2026-10-27)
------------------
* Scenario steps take ``ignored: <reason>``.

0.1.1 (2026-10-26)
------------------
* No changes; released with statechart_ros 0.1.1.

0.1.0 (2026-10-26)
------------------
* First release.
* ``chart_under_test`` with fake invokes and a manual clock, YAML scenarios, Hypothesis property tests, ``ChartWatcher`` for launch tests.
