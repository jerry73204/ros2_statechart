# The engine: python-statemachine

ros2_statechart runs charts with python-statemachine **as released, without
patches**. This file records what the design relies on and how each point was
established. Every row of the table below is a test in
`statechart_ros/test/engine/` (`test_engine_facts.py`,
`test_engine_questions.py`), run against python-statemachine 3.2.2 on Python
3.12 (ROS 2 Jazzy) in CI, so a new release that changes any of them fails CI
before it reaches users. The first exploration (2026-10-26, Python 3.10) is in
[probes/](../probes/).

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
| E1 | Elements from another namespace directly under `<scxml>` or `<state>` | ignored by the SCXML reader; the document loads. Caveat: the reader strips namespaces first, so a foreign element whose local name is an SCXML element (`ros:invoke`, `ros:transition`) is read as that SCXML element |
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
| E13 | `<send delay="...">` | the caller of `send` is held, polling, until the delayed event is due (the sync engine waits for due events in its processing loop) |
| E14 | `send` from another thread while no macrostep runs | the macrostep runs on that thread; in particular `done.invoke` is processed on the invoke's own thread when the machine is idle |
| E15 | A bare name starting with `_` in a guard | never resolved on the model (`error.execution`, `NameError`) |
| E16 | A chart loaded from SCXML with unreachable or trap states | loads: the SCXML reader turns the engine's class-level checks off |
| E17 | A targetless `<transition type="internal">` | refused at load (`InvalidDefinition: Not a valid internal transition`); a targetless transition without `type` handles the event in place, running its content |
| E18 | `<data id="state">` | overwritten: the engine keeps the configuration in the model attribute `state` |

## Answered in P0

| # | Question | Answer (test) |
|---|---|---|
| Q1 | Does `done.invoke` arrive before or after events the handler sent with `ctx.send` just before returning? | after: both go to the external queue in order (`test_q1_...`) |
| Q2 | Deep history entering a state with an invoke | the remembered leaf is entered and invoked again with a fresh context (`test_q2_...`) |
| Q3 | Leaving a whole parallel state | every region's invoke is cancelled; exit order is descendants before ancestors, later document order first among states of one depth: `y, x, r2, r1, P` (`test_q3_...`) |
| Q4 | Threads under many short invokes | one new daemon thread per invocation (200 cycles, 200 threads), all ended afterwards; a chart with only synchronous callbacks runs on the sync engine (`test_q4_...`) |
| Q5 | The wrapper type of `_event.data` | an engine object whose `data` attribute holds the returned value (not a dict); the outcome conditions never read it (`test_e6_...`) |

The async engine is not used: the node runs the sync engine on its own
worker thread, which needs no event loop next to rclpy's executor.

## Consequences for the design

- **Where `ros:` elements may go (E1, E2, E3).** Only directly under
  `<scxml>`, `<state>`, `<parallel>` and `<final>`; never in executable content.
  Standard `<invoke>` and `<send>` with ROS types cannot be used without a
  patch.
- **How ROS work is attached (E4, E5, E8).** The loader reads the `ros:`
  elements and installs one listener with an `on_invoke_<state>` handler per
  state that has an invoke. Cancellation on exit and re-invocation on
  re-entry come from the engine. The loader removes every `ros:` element
  before the engine reads the document (E1 caveat).
- **One thread enters the engine (E14).** Our handlers never return their
  outcome to the engine and never call `ctx.send`: either would let the
  engine process the event on the invoke thread. A handler puts its outcome
  on the node's queue and then waits for `ctx.cancelled`; the node's worker
  sends `done.invoke.<state>` itself, after checking that the invocation is
  still the current one of its state.
- **No delayed sends (E13).** A pending delayed event would hold the worker.
  The validator refuses `<send delay>` and `delayexpr`; a state that needs a
  timeout declares `ros:after` (FORMAT.md section 4), which runs on a ROS
  timer, in ROS time.
- **How outcomes reach transitions (E6, E7).** The wrapper around invoke
  data is an engine detail. Users write `<ros:outcome status="aborted"
  target="..."/>`; the loader expands it into a standard `<transition
  event="done.invoke.<state>" cond="...">` whose condition is a generated
  model callback (E10) named `sc_ros_outcome_<state>_<n>`, without a leading
  underscore (E15). Errors inside our handlers are caught and reported as
  an outcome, so `error.execution` is left for genuine faults.
- **Guards and builders (E10, E11, E12).** Charts are loaded in the
  restricted datamodel. A guard is a bare name resolved on the engine's
  model object, never on listeners (E10), so the node gives the engine one
  model object that holds the datamodel values, answers the generated
  outcome conditions and forwards every other public name to the user's
  `ros:model` instance. A goal builder is a name the loader calls itself.
  No document needs `trusted=True`.
- **Engine checks (E16).** The validator runs reachability and trap-state
  checks itself on the loaded class.
- **Refusals (E17, E18).** `ros:refuse` expands into a targetless transition
  without `type`. Data ids `state` and names starting `sc_ros_` are reserved.
- **Unhandled events (E9).** Silently ignoring a command is a defect for a
  robot. The validator requires every declared input event to be handled or
  explicitly refused in every reachable configuration, and the node reports
  an unhandled event on the transition log and in the service reply.
