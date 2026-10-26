#!/usr/bin/env bash
# Build a Debian package of every package for one ROS distribution, the way
# the buildfarm does (bloom-generate rosdebian, then debian/rules binary), in
# dependency order, installing each one before the next is built.
#
#   build_debs.sh <distro> <output directory> [source directory]
#
# Runs as root in a ros:<distro>-ros-base container (the ROS apt repository
# and rosdep already set up). Tests are not run here (nocheck), so their
# dependencies are not installed; CI runs them.
set -euo pipefail

distro=$1
out=$(realpath -m "$2")
src=$(realpath "${3:-$(dirname "$0")/../..}")

packages=(
  python_statemachine_vendor
  statechart_ros_msgs
  statechart_ros
  statechart_ros_nav2
  statechart_ros_cli
  statechart_ros_viewer
  statechart_ros_testing
)
if [ "$distro" = rolling ]; then
  # No Nav2 binaries on Rolling (docs/RELEASE.md).
  packages=("${packages[@]/statechart_ros_nav2}")
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  python3-bloom python3-rosdep fakeroot debhelper dpkg-dev \
  dh-python python3-all python3-setuptools

# rosdep has to resolve this repository's packages to the Debian packages
# built here, so bloom can write them as dependencies.
work=$(mktemp -d)
keys=$work/rosdep.yaml
for p in "${packages[@]}"; do
  [ -n "$p" ] || continue
  echo "$p: {ubuntu: [ros-$distro-${p//_/-}]}" >> "$keys"
done
echo "yaml file://$keys" > /etc/ros/rosdep/sources.list.d/50-ros2-statechart.list
rosdep update --rosdistro "$distro"

mkdir -p "$out"
for p in "${packages[@]}"; do
  [ -n "$p" ] || continue
  echo "::group::$p"
  cp -r "$src/$p" "$work/$p"
  cd "$work/$p"
  rosdep install --from-paths . --ignore-src -y --rosdistro "$distro" \
    -t buildtool -t buildtool_export -t build -t build_export
  bloom-generate rosdebian --ros-distro "$distro"
  DEB_BUILD_OPTIONS=nocheck fakeroot debian/rules binary
  deb=$(ls "$work"/ros-"$distro"-"${p//_/-}"_*.deb)
  apt-get install -y "$deb"
  mv "$deb" "$out/"
  echo "::endgroup::"
done

ls -l "$out"
