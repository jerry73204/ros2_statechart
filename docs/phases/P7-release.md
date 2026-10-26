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

## Done (2026-10-26)

- Documentation: [docs/README.md](../README.md) indexes concepts, the five
  tutorials, the format reference and the guides, migration notes and the
  model checking notes.
- Tutorials: every listed file is compared with the repository and every
  marked command is run by `docs/tutorials/check_tutorial.py`, in the CI
  job "tutorials" (1, 2, 4, 5 on a fresh Ubuntu 24.04 container) and in
  the nightly job (3, with Nav2's loopback simulation).
- Release files: one version, `CHANGELOG.rst` per package, rosdep notes
  and the maintainer's steps in [RELEASE.md](../RELEASE.md); tag `v0.1.0`.
- Not done here, by design: bloom, rosdistro, the buildfarm. The first
  check ("installs with apt on a fresh Jazzy machine") can only run after
  the release; until then the "tutorials" job runs tutorial 1 unchanged on
  a fresh container built from source.
