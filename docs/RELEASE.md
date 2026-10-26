# Releasing

## Versions

All seven packages share one version (`package.xml` and, for the Python
packages, `setup.py`), released together from one tag `vX.Y.Z`. The `ros:`
namespace URI carries the format's major version (`.../ns/1`) and changes
only with an incompatible format. Each package has a `CHANGELOG.rst` in the
format `catkin_generate_changelog` writes and bloom reads.

| Package | Build type | Released for |
|---|---|---|
| `python_statemachine_vendor` | ament_cmake | Humble, Jazzy, Rolling |
| `statechart_ros_msgs` | ament_cmake (rosidl) | Humble, Jazzy, Rolling |
| `statechart_ros` | ament_python | Humble, Jazzy, Rolling |
| `statechart_ros_cli` | ament_python | Humble, Jazzy, Rolling |
| `statechart_ros_viewer` | ament_python | Humble, Jazzy, Rolling |
| `statechart_ros_testing` | ament_python | Humble, Jazzy, Rolling |
| `statechart_ros_nav2` | ament_python | Humble, Jazzy (Rolling has no Nav2 binaries yet) |

## Dependencies and rosdep

Every dependency is a ROS package or an existing rosdep key
(`python3-lxml`, `python3-yaml`, `python3-jsonschema`,
`python3-hypothesis`, `python3-pytest`); no new rosdep key is needed.

python-statemachine is not packaged by Ubuntu or Debian, and the buildfarm
does not install pip packages, so `python_statemachine_vendor` installs the
released wheel: CMake downloads it from PyPI at build time and checks its
SHA-256. For builds without network access, pass the wheel with
`-DPYTHON_STATEMACHINE_WHEEL=/path/to/python_statemachine-3.2.2-py3-none-any.whl`.
Whether the buildfarm's binary jobs may download during the build is the
maintainer's to confirm with the first release; if not, the release
repository can carry the wheel and a bloom patch can set that option.

The browser test (Playwright) and the nightly simulation (`nav2_bringup`,
`nav2_loopback_sim`) are CI-only and not declared as dependencies.

## Before tagging

1. CI green on Humble, Jazzy, Rolling and the browser job; the nightly
   simulation green (run it with *workflow_dispatch* if needed).
2. Versions raised in every `package.xml` and `setup.py`
   (`catkin_prepare_release` does both and commits).
3. `CHANGELOG.rst` updated in every package (`catkin_generate_changelog`,
   then edit), dated the day of the tag.
4. Annotated tag `vX.Y.Z` pushed.

## Debian packages on GitHub

Pushing a tag `vX.Y.Z` runs `.github/workflows/debs.yml`: for Humble and
Jazzy, in a stock `ros:<distro>-ros-base` container on amd64 and on arm64 (GitHub's arm runners), it checks that the tag
is the version in every `package.xml`, builds each package with
`bloom-generate rosdebian` and `debian/rules binary` in dependency order
(`.github/scripts/build_debs.sh`), installs them, runs a chart from the
installed packages (`.github/scripts/smoke_debs.sh`), and attaches the
`.deb` files to the tag's GitHub release, creating it if needed. Tests are
not run in this build; CI runs them. To build the packages of an existing
tag again, run the workflow by hand with that tag. Rolling is left out: its
base image changes often and has no Nav2.

## Steps for the maintainer (not done by this repository's CI)

1. Create a release repository, for example
   `github.com/<owner>/ros2_statechart-release`, empty.
2. For each distribution (`humble`, `jazzy`, `rolling`):
   `bloom-release --new-track --rosdistro <distro> --track <distro> ros2_statechart`,
   answering: repository URL of this project, version from the tag,
   upstream devel branch `main`, and for Rolling ignore
   `statechart_ros_nav2` (`ignored` packages in the track, or a
   `<distro>.ignored` file in the release repository).
3. bloom opens a pull request against `ros/rosdistro` adding the release
   (and, on request, `doc` and `source` entries for the documentation
   and the source CI jobs). Review it, answer the reviewers, wait for the
   merge.
4. Watch the buildfarm jobs (`build.ros2.org`) for each package and
   distribution; fix and re-release with a new patch version if one fails.
5. Packages reach `ros2-testing` after the merge, and the main apt
   repository at the next sync of each distribution.
6. Check the first tutorial on a fresh Jazzy machine with the apt packages:
   `sudo apt install ros-jazzy-statechart-ros ros-jazzy-statechart-ros-cli ros-jazzy-turtlesim`,
   then the commands of [tutorial 1](tutorials/01-first-chart.md) unchanged.
   Until then CI runs it on a fresh Ubuntu 24.04 container built from source
   (the job "tutorials").
