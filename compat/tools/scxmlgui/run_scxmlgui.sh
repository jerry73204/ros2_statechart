#!/usr/bin/env bash
# Copyright 2026 The ros2_statechart Authors
# SPDX-License-Identifier: Apache-2.0
#
# scxmlgui: read and save every chart variant with the prebuilt editor jar
# (extra/fsm-editor.jar in its git repository), headless. Needs a JDK 11.
# The saved documents are checked against the W3C schema when xmllint and the
# XSDs (XSD_DIR, default the W3C schema in statechart_ros) are present.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
WORK="$REPO/tmp/compat/scxmlgui"; VAR="$REPO/tmp/compat/variants"
SRC="$REPO/tmp/compat/scxmlgui-src"; XSD_DIR="${XSD_DIR:-$REPO/statechart_ros/statechart_ros/schema/w3c}"
SCXMLGUI_REV="${SCXMLGUI_REV:-1e092023635b21e1d5e22820075d736b46c537fb}"
[ -d "$SRC" ] || git clone -q https://github.com/fmorbini/scxmlgui.git "$SRC"
git -C "$SRC" checkout -q "$SCXMLGUI_REV"
"$HERE/../make_variants.sh" >/dev/null
# jaxb-api is needed to compile against the jar on Java 11; the jar carries
# its own .java sources, so implicit compilation is turned off.
CP="$SRC/extra/fsm-editor.jar:$SRC/lib/jaxb-api-2.3.0.jar"
mkdir -p "$WORK/classes" "$WORK/out"
javac -nowarn -implicit:none -sourcepath "" -d "$WORK/classes" -cp "$CP" "$HERE/ScxmlguiRoundTrip.java"
echo "scxmlgui $SCXMLGUI_REV, extra/fsm-editor.jar ($(unzip -p "$SRC/extra/fsm-editor.jar" svn.version)), sha256 $(sha256sum "$SRC/extra/fsm-editor.jar" | cut -c1-16)"
java -version 2>&1 | head -1
for c in minimal nested_history readme_example; do
  for v in python ecmascript ecmascript.plain; do
    out="$WORK/out/$c.$v.scxml"
    echo "=== $c.$v"
    (cd "$WORK" && timeout 120 java -Djava.awt.headless=true -cp "$CP:$WORK/classes" ScxmlguiRoundTrip "$VAR/$c.$v.scxml" "$out" 2>&1 \
      | grep -E '^  (read|write|error)|^    [A-Za-z_]|Exception' )
    if [ -f "$out" ] && command -v xmllint >/dev/null && [ -f "$XSD_DIR/scxml.xsd" ]; then
      xmllint --noout --schema "$XSD_DIR/scxml.xsd" "$out" 2>&1 | grep -v 'Skipping import' | sed 's/^/  xsd: /'
    fi
  done
done
