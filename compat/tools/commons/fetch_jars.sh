#!/usr/bin/env bash
# Copyright 2026 The ros2_statechart Authors
# SPDX-License-Identifier: Apache-2.0
#
# Downloads the Apache Commons SCXML jars and their runtime dependencies.
# commons-scxml2 (2.0) has never been released; the only build is the
# 2.0-SNAPSHOT in the Apache snapshots repository. 0.9 is the last release.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DL="${DL:-$(cd "$HERE/../../.." && pwd)/tmp/compat/commons/dl}"
mkdir -p "$DL"; cd "$DL"
C=https://repo1.maven.org/maven2
S=https://repository.apache.org/content/repositories/snapshots/org/apache/commons/commons-scxml2/2.0-SNAPSHOT
SNAP="${SNAP:-2.0-20260701.010636-103}"
get() { [ -f "$(basename "$1")" ] || curl -sfO "$1"; }
get "$S/commons-scxml2-$SNAP.jar"
get "$S/commons-scxml2-$SNAP.pom"
get $C/commons-logging/commons-logging/1.4.0/commons-logging-1.4.0.jar
get $C/commons-io/commons-io/2.22.0/commons-io-2.22.0.jar
get $C/org/apache/commons/commons-jexl3/3.6.4/commons-jexl3-3.6.4.jar
get $C/com/fasterxml/jackson/core/jackson-core/2.20.0/jackson-core-2.20.0.jar
get $C/com/fasterxml/jackson/core/jackson-databind/2.20.0/jackson-databind-2.20.0.jar
get $C/com/fasterxml/jackson/core/jackson-annotations/2.20/jackson-annotations-2.20.jar
get $C/commons-scxml/commons-scxml/0.9/commons-scxml-0.9.jar
get $C/commons-digester/commons-digester/1.8/commons-digester-1.8.jar
get $C/commons-beanutils/commons-beanutils/1.7.0/commons-beanutils-1.7.0.jar
get $C/commons-jexl/commons-jexl/1.1/commons-jexl-1.1.jar
get $C/xalan/xalan/2.7.3/xalan-2.7.3.jar
get $C/xalan/serializer/2.7.3/serializer-2.7.3.jar
sha256sum *.jar
