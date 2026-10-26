^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Changelog for package statechart_ros
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

0.1.1 (2026-10-26)
------------------
* ``ros:on_entry`` / ``ros:on_exit`` ``run="method"``: a model method inside the macrostep, with the state, the event and its data.
* ``ros:refuse`` takes ``cond``; a refusal naming several events refuses each of them (it was reported as handled).
* ``ros:after`` ``delay`` may name a ``<data>`` value (a ``ros:param``).
* ``ros:action_server``: ``result_status`` (succeeded, aborted or canceled, chosen by the model) and ``cancel_waits`` (the chart ends a cancelled goal).
* ``ros:service_server`` event templates with fixed parts, such as ``command.{command}``.

0.1.0 (2026-10-26)
------------------
* First release.
* The ``ros:`` extension of SCXML (namespace ``.../ns/1``): inputs, invokes, outcomes, outputs, timeouts, refusals, child charts; chart expressions.
* Loader and validator (schema, engine checks, types, model names, outcome coverage, every input answered in every configuration).
* Lifecycle node ``statechart_node``: one event queue and worker, invokes on actions, services, topics and child charts, introspection topics, ``run_as_action``.
* Turtlesim example and the tutorial charts.
