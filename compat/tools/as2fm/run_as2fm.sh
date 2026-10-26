#!/usr/bin/env bash
# Copyright 2026 The ros2_statechart Authors
# SPDX-License-Identifier: Apache-2.0
#
# AS2FM (not on PyPI; installed from its git repository into a venv) on every
# chart variant. Each variant is loaded as is and "adapted" to what AS2FM
# requires of plain SCXML (a name attribute on <scxml>, a type on <data>);
# the "rootonly" form of the adapted chart also drops the ros: elements inside
# states (indented four spaces or more) and keeps the ones under <scxml>.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
WORK="$REPO/tmp/compat/as2fm"; VAR="$REPO/tmp/compat/variants"
AS2FM_REV="${AS2FM_REV:-3252344093c2fb2a56d65449bb2000d167b99b85}"
SRC="$REPO/tmp/compat/as2fm-src"; VENV="$REPO/tmp/compat/venv-as2fm"
[ -d "$SRC" ] || git clone -q https://github.com/convince-project/AS2FM.git "$SRC"
git -C "$SRC" checkout -q "$AS2FM_REV"
[ -x "$VENV/bin/python" ] || { python3 -m venv "$VENV" && "$VENV/bin/pip" install -q "$SRC"; }
"$HERE/../make_variants.sh" >/dev/null
echo "AS2FM $(git -C "$SRC" describe --tags --always) ($AS2FM_REV)"
mkdir -p "$WORK/in" "$WORK/out"
for c in minimal nested_history readme_example; do
  for v in python ecmascript ecmascript.plain; do
    f="$VAR/$c.$v.scxml"
    named="$WORK/in/$c.$v.adapted.scxml"
    sed -e "0,/<scxml /s//<scxml name=\"$c\" /" -e 's/<data id="laps"/<data id="laps" type="int32"/' "$f" > "$named"
    rootonly="$WORK/in/$c.$v.adapted.rootonly.scxml"
    grep -v '^    \+<ros:' "$named" > "$rootonly"
    for in in "$f" "$named" "$rootonly"; do
      echo "=== $(basename "$in")"
      (cd "$WORK" && "$VENV/bin/python" -I "$HERE/as2fm_load.py" "$in" "$WORK/out/$(basename "$in")" 2>&1 | grep -v '^xml_file=')
    done
  done
done
