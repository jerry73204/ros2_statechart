# The engine: python-statemachine

ros2_statechart runs charts with python-statemachine **as released, without
patches**. This file records what the design relies on and how each point was
established. Facts marked *probed* were checked on 2026-10-26 against
python-statemachine 3.2.2 (`pip install "python-statemachine[io]==3.2.2"`);
the probe scripts become the regression tests of phase P0, so a new release
that changes any of them fails CI before it reaches users.

## Model

python-statemachine implements statecharts with SCXML semantics:

- `StateChart` classes, or documents loaded with `statemachine.io.load()` from
  SCXML, YAML or JSON, which return a `StateChart` subclass;
- atomic, compound (`State.Compound`), parallel (`State.Parallel`), final and
  history (shallow and deep) states;
- the current state is a set, `sm.configuration`;
- transitions with `event`, `cond`/`unless`, eventless transitions, internal
  transitions, `In(state)` across parallel regions;
- an external queue (`sm.send`) and an internal queue (raised, `done.*`,
  `error.*` events); one external event is processed to completion
  (macrostep) before the next;
- on a transition: exit the active states below the least common ancestor
  innermost first, run the transition's actions, enter the targets
  outermost first;
- `done.state.<id>` when a compound state reaches a final child (a parallel
  state when all regions have);
- exceptions in callbacks become `error.execution` events
  (`catch_errors_as_events`, default on for `StateChart`);
- invoke: a state starts work on entry and the work is cancelled on exit;
- listeners: objects whose methods are called by naming convention
  (`on_enter_<state>`, `on_exit_<state>`, `after_transition`...), arguments
  injected by name;
- diagrams: Graphviz and Mermaid renderers, a Markdown transition table;
- class-level checks: unreachable states, trap states (non-final states with
  no way out).

## Probed behaviour the design relies on

| # | Behaviour | Result |
|---|---|---|
| E1 | Elements from another namespace directly under `<scxml>` or `<state>` | ignored by the SCXML reader; the document loads |
| E2 | Elements from another namespace inside `<onentry>`, `<onexit>`, `<transition>` | refused at load: `ValueError: Unknown tag: ...` |
| E3 | `<invoke type="...">` with any type other than `scxml`; `<send type="...">` with a custom type | load, then fail at run time with `error.execution` |
| E4 | A listener method `on_invoke_<state>(ctx)` on a loaded SCXML chart | called on entry with an `InvokeContext`: `ctx.send(event, **data)`, `ctx.cancelled` (a `threading.Event`), `ctx.state_id` |
| E5 | Leaving the state while the invoke runs | `ctx.cancelled` is set; the handler's return is then discarded |
| E6 | The invoke returns a value | event `done.invoke.<state>.<suffix>` (matches `done.invoke.<state>` by SCXML prefix matching); in the datamodel `_event.data` is a wrapper whose `data` holds the returned value |
| E7 | The invoke raises | `error.execution` |
| E8 | Re-entering the state (for example after leaving to a pause state and coming back) | the invoke runs again |
| E9 | An event no active state handles | silently ignored (`allow_event_without_transition = True` on `StateChart`, as SCXML specifies) |
| E10 | `cond="name"` (a bare name) with `model=obj` | resolved as a callback on the model, arguments injected |
| E11 | `cond="name(arg)"` (a call) in the default restricted datamodel | refused at load: `Unsupported function` |
| E12 | `cond="name(arg)"` with `trusted=True` | loads, but the name did not resolve to the model; not used |

## Consequences for the design

- **Where `ros:` elements may go (E1, E2, E3).** Only directly under
  `<scxml>`, `<state>`, `<parallel>` and `<final>`; never in executable content.
  Standard `<invoke>` and `<send>` with ROS types cannot be used without a
  patch.
- **How ROS work is attached (E4, E5, E8).** The loader reads the `ros:`
  elements and installs one listener with an `on_invoke_<state>` handler per
  state that has an invoke. Cancellation on exit and re-invocation on
  re-entry come from the engine.
- **How outcomes reach transitions (E6, E7).** The wrapper around invoke
  data is an engine detail. Users write `<ros:outcome status="aborted"
  target="..."/>`; the loader expands it into a standard `<transition
  event="done.invoke.<state>" cond="...">` whose condition is a generated
  model callback (E10). Errors inside our handlers are caught and reported as
  an outcome, so `error.execution` is left for genuine faults.
- **Guards and builders (E10, E11, E12).** Charts are loaded in the
  restricted datamodel. A guard is a bare name resolved on the model object;
  a goal builder is a name the loader calls itself. No document needs
  `trusted=True`.
- **Unhandled events (E9).** Silently ignoring a command is a defect for a
  robot. The validator requires every declared input event to be handled or
  explicitly refused in every reachable configuration, and the node reports
  an unhandled event on the transition log and in the service reply.

## Open questions for P0

- Whether `done.invoke` arrives before or after events the handler sent with
  `ctx.send` just before returning (ordering of the internal and external
  queues for invoke results).
- The exact wrapper type of `_event.data` across 3.x releases; the generated
  outcome conditions isolate users from it either way.
- Behaviour of deep history when the remembered leaf had an invoke (E8
  suggests it re-invokes; to confirm with history).
- Thread model of invokes (one thread per invocation) under many short
  states; whether the async engine fits rclpy better.
