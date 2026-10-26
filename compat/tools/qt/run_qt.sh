#!/usr/bin/env bash
# Copyright 2026 The ros2_statechart Authors
# SPDX-License-Identifier: Apache-2.0
#
# Qt SCXML: qscxmlc and QScxmlStateMachine::fromFile on every chart variant.
# Run inside Ubuntu 24.04 with qt6-scxml-dev libqt6scxml6-bin qt6-base-dev cmake g++.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
WORK="$REPO/tmp/compat/qt"
VAR="$REPO/tmp/compat/variants"
QSCXMLC="${QSCXMLC:-/usr/lib/qt6/libexec/qscxmlc}"
"$HERE/../make_variants.sh" >/dev/null
cmake -S "$HERE" -B "$WORK/build" -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build "$WORK/build" >/dev/null
"$QSCXMLC" --version
declare -A EVENTS=([minimal]="go" [nested_history]="pause resume" [readme_example]="go e_stop resume")
mkdir -p "$WORK/qscxmlc"
for c in minimal nested_history readme_example; do
  for v in python null ecmascript null.plain ecmascript.plain; do
    f="$VAR/$c.$v.scxml"
    echo "=== $c.$v"
    echo "-- qscxmlc"
    (cd "$WORK/qscxmlc" && "$QSCXMLC" -o "$c.$v" "$f"; echo "  rc=$?")
    echo "-- fromFile (events: ${EVENTS[$c]})"
    QT_QPA_PLATFORM=offscreen "$WORK/build/qt_load" "$f" ${EVENTS[$c]}
    echo "  rc=$?"
  done
done
