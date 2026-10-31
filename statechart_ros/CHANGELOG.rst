^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Changelog for package statechart_ros
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

0.1.7 (2026-10-31)
------------------
* The interface of a chart (``statechart_ros.interface``): the topics it subscribes to and publishes, the services and actions it serves and calls, the parameters it sets on other nodes, child charts and user kinds included; written as YAML (``statechart_interface: 1``) and compared, each difference breaking, additive or doc (docs/INTERFACES.md).
* ``InvokeKind.endpoints``: what a use of a kind touches, for the interface; the default pairs the kind's first name and type attributes.
* Every ``ros:`` element accepts an optional ``doc`` attribute.
* Node parameter ``check_interface`` (s, default 5, 0 off): once after activation, a warning for each input topic without a publisher, each called service or action without a server and each node set parameters on that is not running.

0.1.6 (2026-10-28)
------------------
* A refusal again follows the events an event raises, as before 0.1.5: a router that forwards a service request by raising answers with the refusal of what it raised (0.1.5 answered "accepted"). An ignore still counts only for the event that took it.

0.1.5 (2026-10-27)
------------------
* An event's refusal and ignore reasons are its own: an event raised later in the same macrostep and refused or ignored there no longer marks the sent event refused or ignored (``done.invoke`` events that moved the chart on were logged as ignored, and a refused raised event could report the sent one refused).

0.1.4 (2026-10-27)
------------------
* No changes; released with statechart_ros_viewer 0.1.4.

0.1.3 (2026-10-27)
------------------
* No changes; released with statechart_ros_testing 0.1.3.

0.1.2 (2026-10-27)
------------------
* An event a ``ros:ignore`` matched reports its reason as ``ignored`` (``EventResult``, the transition log, the status, ``SendEvent`` replies and reply builders); ``handled`` stays true.
* Diagrams of charts whose transitions cross compound states' borders: the Mermaid output is a flowchart with one subgraph per compound or parallel state (a ``stateDiagram-v2`` moved states out of their parents, and notes inside nested states stopped Mermaid 10); Graphviz no longer fails with "trouble in init_rank" (an edge is clipped at a cluster only when its other end is outside it, and initial-state edges come after the cluster's states).

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
