#!/usr/bin/env bash
# Copyright 2026 The ros2_statechart Authors
# SPDX-License-Identifier: Apache-2.0
#
# Apache Commons SCXML 2.0-SNAPSHOT and 0.9 on every chart variant.
# Needs a JDK (javac, java) 11 or newer and curl.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
WORK="$REPO/tmp/compat/commons"; DL="$WORK/dl"; VAR="$REPO/tmp/compat/variants"
"$HERE/fetch_jars.sh" >/dev/null
"$HERE/../make_variants.sh" >/dev/null
CP2="$(ls "$DL"/commons-scxml2-*.jar "$DL"/commons-logging-*.jar "$DL"/commons-io-*.jar "$DL"/commons-jexl3-*.jar "$DL"/jackson-*.jar | tr '\n' :)"
CP09="$DL/commons-scxml-0.9.jar:$DL/commons-digester-1.8.jar:$DL/commons-beanutils-1.7.0.jar:$DL/commons-jexl-1.1.jar:$DL/commons-logging-1.4.0.jar:$DL/xalan-2.7.3.jar:$DL/serializer-2.7.3.jar:"
mkdir -p "$WORK/classes2" "$WORK/classes09" "$WORK/out"
javac -nowarn -d "$WORK/classes2" -cp "$CP2" "$HERE/CommonsScxml2Load.java"
javac -nowarn -d "$WORK/classes09" -cp "$CP09" "$HERE/CommonsScxml09Load.java" 2>&1 | grep -v '^Note:'
java -version 2>&1 | head -1
# One line per log record; the location block of each SCXMLReader warning is dropped.
LOG=(-Djava.util.logging.SimpleFormatter.format='  log %4$s: %5$s%n')
location='^(Column number|System Id|Public Id|Location Uri|CharacterOffset|$)'
declare -A EVENTS=([minimal]="go" [nested_history]="pause resume" [readme_example]="go e_stop resume")
for c in minimal nested_history readme_example; do
  for v in python null ecmascript null.plain ecmascript.plain; do
    echo "=== commons-scxml2 2.0-SNAPSHOT: $c.$v (events: ${EVENTS[$c]})"
    java "${LOG[@]}" -cp "$CP2$WORK/classes2" CommonsScxml2Load "$VAR/$c.$v.scxml" "$WORK/out/$c.$v.scxml2.scxml" ${EVENTS[$c]} 2>&1 | grep -Ev "$location"
  done
  for v in python nodm nodm.plain; do
    echo "=== commons-scxml 0.9: $c.$v (events: ${EVENTS[$c]})"
    java "${LOG[@]}" -cp "$CP09$WORK/classes09" CommonsScxml09Load "$VAR/$c.$v.scxml" "$WORK/out/$c.$v.scxml09.scxml" ${EVENTS[$c]} 2>&1 | grep -Ev "$location|^\s+at |^java.lang.IllegalArgumentException"
  done
done
