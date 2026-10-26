# Tutorials

On turtlesim and Nav2's own simulation, in order:

1. [A first chart](01-first-chart.md): states, events, transitions, data,
   outputs, timeouts, refusals; validate and run.
2. [Nesting and history](02-nesting-and-history.md): compound states,
   shared answers, pause and resume.
3. [A Nav2 patrol with docking](03-nav2-patrol.md): parallel regions, Nav2
   goals as invokes, outcomes, named poses, docking.
4. [Testing a chart](04-testing.md): scenarios, properties, simulation.
5. [Composing charts](05-composing.md): child charts in the same node and
   charts hosted as actions.

Every command and file in them is checked in CI: `check_tutorial.py` runs
the blocks marked with `<!-- check: ... -->` and compares the listed files
with the repository (tutorials 1, 2, 4 and 5 on every push, tutorial 3
nightly with Nav2's simulation).
