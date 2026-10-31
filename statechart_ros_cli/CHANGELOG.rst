^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Changelog for package statechart_ros_cli
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

0.1.8 (2026-11-01)
------------------
* ``ros2 statechart slots [SLOT]``: the options installed packages register for slots, and conflicting registrations (exit 1).

0.1.7 (2026-10-31)
------------------
* ``ros2 statechart interface CHART [-o FILE] [--check FILE]``: print a chart's interface, or exit 1 when a committed interface file no longer matches the chart.

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
* No changes; released with statechart_ros_testing 0.1.3.

0.1.2 (2026-10-27)
------------------
* ``send`` and ``echo`` print ``ignored: <reason>`` for an ignored event (``send`` printed ``handled``, ``echo`` an empty target); ``show`` adds it to the last event.

0.1.1 (2026-10-26)
------------------
* No changes; released with statechart_ros 0.1.1.

0.1.0 (2026-10-26)
------------------
* First release.
* ``ros2 statechart`` verbs: validate, diagram, export, list, show, echo, send.
