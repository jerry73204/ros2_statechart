^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Changelog for package statechart_ros
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

0.1.0 (2026-10-26)
------------------
* First release.
* The ``ros:`` extension of SCXML (namespace ``.../ns/1``): inputs, invokes, outcomes, outputs, timeouts, refusals, child charts; chart expressions.
* Loader and validator (schema, engine checks, types, model names, outcome coverage, every input answered in every configuration).
* Lifecycle node ``statechart_node``: one event queue and worker, invokes on actions, services, topics and child charts, introspection topics, ``run_as_action``.
* Turtlesim example and the tutorial charts.
