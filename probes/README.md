# Engine probes

The scripts behind [docs/ENGINE.md](../docs/ENGINE.md), as run on 2026-10-26
against python-statemachine 3.2.2 (`pip install "python-statemachine[io]==3.2.2"`,
Python 3.10). They print what the engine did. Phase P0 turned each into
asserting tests under `statechart_ros/test/engine/`, which are now the
reference; the scripts stay as the record of the first exploration.

| Script | Rows |
|---|---|
| `e1_e4_e5_e9_foreign_and_invoke.py` | foreign elements under states, listener invoke, cancel on exit, unhandled events |
| `e2_foreign_in_executable_content.py` | foreign elements in `<onentry>` and `<transition>` (fails to load, by design of the probe) |
| `e3_custom_invoke_send_types.py` | `<invoke type>` and `<send type>` with custom types |
| `e6_e10_invoke_data_and_guards.py` | what `done.invoke` carries; bare-name guards on the model |
| `e7_e8_e11_outcomes_reentry_restricted.py` | errors, re-invoke on re-entry, restricted versus trusted expressions (exploratory; timing-dependent rows are not relied on) |
