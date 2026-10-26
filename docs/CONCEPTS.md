# Concepts: statecharts in ROS terms

A **statechart** describes what a system does as a set of situations
(states) and the events that move it between them. It adds three things to a
plain state machine, each of which removes a way flat machines grow out of
hand: nesting, parallel regions and history. W3C standardised statecharts as
SCXML, which this project uses as its file format.

| Statechart term | Meaning | In ROS terms here |
|---|---|---|
| state | a situation the robot is in | while active, its work runs: a goal, a service call, a wait for a topic, a child chart |
| event | something that happened | a message, a service request, a timer, an action result, a command |
| transition | on an event (and a condition), go from one state to another | runs to completion before the next event is taken |
| compound state | a state made of states | shared answers: `stop` on `RUN` applies in every child |
| parallel state | regions active at the same time | independent concerns (mode, safety, power, task) in one chart |
| history state | return to the child that was active | resume a patrol at the leg it left |
| final state | the chart, or a compound state, is done | its donedata is the result, for a parent or an action client |
| datamodel | the chart's data | counters, thresholds; values set by parameters |
| guard (`cond`) | a condition on a transition | a chart expression (`laps < 3`, `In('AUTO')`) or a model method |

## Run to completion, one queue

All events of a chart go through one queue, taken one at a time. An event is
processed completely (exit actions, transition actions, entry actions, and
any eventless transitions that follow) before the next one is looked at.
Nothing in a chart is ever half-way between two states, so charts and their
Python models need no locks ([DESIGN.md](DESIGN.md) section 4).

## Work belongs to states

Work that takes time is an **invoke**: it starts when its state is entered
and is cancelled when the state is left, whatever the reason. A Nav2 goal,
a service call, a wait for a message and a child chart are invokes; their
result arrives as an event, routed by `ros:outcome`. One-shot outputs
(`ros:on_entry`, `ros:on_exit`) publish or call once. Timeouts
(`ros:after`) belong to their state the same way. This is why a chart
cannot "forget" to cancel a goal on pause: leaving the state is the cancel.

## Every command is answered

Commands are events. In every state, each command is handled, refused with a
reason (`ros:refuse`) or ignored (`ros:ignore`), and the validator checks
this for every configuration the chart can be in. A caller of the command
service always gets an answer: handled, or refused and why.

## The chart is the specification

The SCXML file is read by the node, drawn by `ros2 statechart diagram` and
the viewer, checked by `ros2 statechart validate`, and exercised by tests
without ROS ([TESTING.md](TESTING.md)). What the robot does is in one place,
and code (the model, the invoke kinds) only does what a chart cannot say.

## Where to go next

[The tutorials](tutorials/README.md), then [FORMAT.md](FORMAT.md) for the
reference.
