#!/usr/bin/env bash
# Copyright 2026 The ros2_statechart Authors
# SPDX-License-Identifier: Apache-2.0
#
# Writes variants of compat/charts/*.scxml into $OUT (default tmp/compat/variants):
#   <chart>.python.scxml      the chart as is (datamodel="python")
#   <chart>.null.scxml        datamodel="null", ros: elements kept
#   <chart>.ecmascript.scxml  datamodel="ecmascript", ros: elements kept
#   <chart>.ecmascript.plain.scxml  datamodel="ecmascript", ros: elements removed (control)
#   <chart>.null.plain.scxml  datamodel="null", ros: elements removed (control)
#   <chart>.nodm.scxml        no datamodel attribute (for Commons SCXML 0.9,
#                             which predates the attribute), ros: elements kept
#   <chart>.nodm.plain.scxml  no datamodel attribute, ros: elements removed
# The ros: elements in the sample charts are one self-closing element per line,
# so removing them is a line filter.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
OUT="${OUT:-$REPO/tmp/compat/variants}"
mkdir -p "$OUT"
for f in "$REPO"/compat/charts/*.scxml; do
  c="$(basename "$f" .scxml)"
  cp "$f" "$OUT/$c.python.scxml"
  for dm in null ecmascript; do
    sed "s/datamodel=\"python\"/datamodel=\"$dm\"/" "$f" > "$OUT/$c.$dm.scxml"
    grep -v '^[[:space:]]*<ros:' "$OUT/$c.$dm.scxml" > "$OUT/$c.$dm.plain.scxml"
  done
  sed 's/ datamodel="python"//' "$f" > "$OUT/$c.nodm.scxml"
  grep -v '^[[:space:]]*<ros:' "$OUT/$c.nodm.scxml" > "$OUT/$c.nodm.plain.scxml"
done
ls "$OUT"
