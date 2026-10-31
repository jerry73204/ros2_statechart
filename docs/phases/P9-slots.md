# P9: Slots

## Goal

Let other packages add behaviour to a chart without editing it. A state
declares a slot; installed packages register child charts for that slot; on
entry the state runs the one chart its datamodel selects. The parent chart
stays the same when a package adds an option, and every option is still
loaded and validated with the parent, so adding behaviour does not weaken
the checks.

The use that motivates it: a robot's mission runs a job step by step, and a
customer asks for a new kind of step (pass an automatic door, wait at a
crossing). The step's states belong in a chart of their own, shipped in the
customer's package; the mission chart keeps its executor, holds, retries
and refusals for every step, old or new.

## Delivers

- **`ros:slot`**, an invoke like `ros:chart` whose child is picked on entry:

  ```xml
  <state id="RUN_STEP">
    <ros:slot name="step" select="step_kind" data="step_data"
              outcomes="succeeded failed cancelled"/>
    <ros:outcome status="succeeded" target="STEP_DONE"/>
    <ros:outcome status="*" target="STEP_FAILED"/>
  </state>
  ```

  - `name`: the slot. Its options are the charts registered for it.
  - `select`: a datamodel value; its value on entry names the option.
  - `outcomes`: the statuses of the slot. Every option's top-level
    `<final>` ids must be among them.
  - `data` (optional): a builder returning a dict. Its entries become the
    option's initial datamodel values.
  - `autoforward`: as for `ros:chart`.

  No option registered under the selected name ends the invoke at once, with
  an empty status and the reason in `error_msg`.
- **Registration through the ament resource index.** A package installs
  `share/ament_index/resource_index/statechart_slots/<package>`, a YAML
  mapping from slot to option name to chart path. The path is relative to
  the package's share directory, or a `package://` URL:

  ```yaml
  step:
    PASS_DOOR: charts/pass_door.scxml
  ```

  The index is language-neutral: a CMake package registers with
  `ament_index_register_resource`, a Python package installs the file with
  `data_files`. Two packages registering the same option for a slot is an
  error that names both.
- **`data` on `ros:chart`** too: a builder whose dict sets the child's
  initial datamodel values, as the `data` of a `RunStatechart` goal already
  does. Keys that are not `<data>` ids of the child end the invoke with an
  error.
- **Validation.** The loader resolves the options when it loads the parent.
  The validator checks each option as a child chart (rule 7: no inputs of
  its own) and checks that its finals are among the slot's `outcomes` (rule
  5). A slot with no options is a warning, since the packages may not be
  installed where the chart is checked.
- **Introspection.** Each option's states appear in the parent's structure
  under `STATE/OPTION` (`RUN_STEP/PASS_DOOR/WAIT_OPEN`). Status and
  transitions use the same ids, so `show`, `echo` and the viewer show the
  running option inside its state.
- **`ros2 statechart slots [SLOT]`** lists the registered options and the
  packages that provide them.

## Checks

- Unit tests:
  - a slot runs the selected option, passes `data`, and ends with its final;
  - an unknown option ends with an error;
  - leaving the state stops the option;
  - duplicate registrations and finals outside `outcomes` are reported;
  - `ros:chart data` sets the child's datamodel, and an undeclared key is
    reported.
- The structure contains each option under its state with qualified ids.
- The test resources are installed into a temporary prefix on
  `AMENT_PREFIX_PATH`, the way a real package registers.

## Leaves out

- Options chosen by anything but a datamodel value (no expressions in
  `select`).
- A slot's options in the parent's interface file. Each option chart ships
  its own interface file with its package, since the set of options depends
  on what is installed.
- Loading options while the node runs: the set is fixed when the chart is
  loaded.
