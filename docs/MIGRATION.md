# Coming from SMACH-style libraries

SMACH, and the libraries that followed its model in ROS 2 (YASMIN, and in
part FlexBE), build a state machine in Python from state classes that return
an outcome string, with containers wiring outcomes to next states. Most of
that model carries over; what changes is where things are written and what
the runtime guarantees.

## Mapping

| SMACH-style | Here |
|---|---|
| a state class whose `execute()` returns an outcome | a state with an invoke (`ros:action`, `ros:service_call`, `ros:wait_for`, a Nav2 kind) and `ros:outcome` per status; or plain transitions on events |
| `StateMachine` container, `transitions={'succeeded': 'NEXT'}` | a compound state; `<ros:outcome status="succeeded" target="NEXT"/>` |
| `Concurrence` with outcome maps | a `<parallel>` state; regions read each other with `In(...)` |
| `SimpleActionState` | `<ros:action server=... type=... goal="builder"/>` |
| `ServiceState` | `<ros:service_call service=... type=... request="builder"/>` |
| `MonitorState` | `<ros:wait_for topic=... type=... when="guard"/>` |
| userdata / blackboard | the datamodel; Python objects live in the model class |
| preemption (`request_preempt`, `service_preempt`) | leaving the state: its invoke is cancelled by the runtime |
| nested state machine as a state | a compound state, or a child chart (`ros:chart`) |
| introspection server and viewer | `~/structure`, `~/status`, `~/transitions` topics; the web viewer; `ros2 statechart show` |

## What changes

- **Events, not only outcomes.** A SMACH state runs until it returns; it
  cannot react to a command meanwhile unless it polls. Here every state
  reacts to events (commands, topics, timers) while its work runs, and the
  work is cancelled by leaving.
- **Hierarchy with shared answers.** A transition on a compound state
  applies to all its children; with history, the machine returns where it
  was. SMACH-style containers pass outcomes up instead.
- **Declarative file, checked before running.** The chart is SCXML; the
  validator checks reachability, traps, types, model names and that every
  command is answered in every state.
- **One queue.** Callbacks never run in parallel with transitions.
- **Code moves to the model.** Goal builders, guards on messages and result
  handlers are methods of one Python class named in the chart
  (`ros:model`); simple conditions are chart expressions.

## Porting a machine

1. List the states and, for each, the work it does (an action, a service, a
   wait) and its outcomes.
2. Write one `<state>` per state with its invoke and one `ros:outcome` per
   outcome; group states that share reactions (stop, pause, errors) into
   compound states.
3. Move goal construction and result checks into the model class.
4. Add the commands the old machine handled by polling or preemption as
   events, with `ros:refuse` where they do not apply.
5. Run `ros2 statechart validate`, then write a scenario per old behaviour
   ([tutorial 4](tutorials/04-testing.md)).
