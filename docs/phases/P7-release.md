# P7: Release

## Goal

Make the packages installable and learnable by people who were not involved.

## Delivers

- Documentation site: concepts (statecharts in ROS terms), the format
  reference, Nav2 guide, testing guide, viewer guide, migration notes from
  SMACH-style libraries.
- Tutorials on public simulations: a first chart, nesting and history,
  Nav2 patrol and docking, testing a chart, composing charts.
- Release through bloom to the ROS buildfarm for Humble, Jazzy and Rolling;
  rosdep keys for the vendor package's dependencies.
- Notes on model checking: what AS2FM needs to read our charts, and whether
  an exporter is worth building.

## Checks

- A user on a fresh Jazzy machine installs with apt and runs the first
  tutorial unchanged.
- Every tutorial runs in CI.

## Leaves out

New features; they start from a design change in DESIGN.md or FORMAT.md.
