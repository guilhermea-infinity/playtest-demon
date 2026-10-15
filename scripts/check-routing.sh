#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
QA_ROUTE_TMP=$(mktemp -d)
trap 'rm -rf "$QA_ROUTE_TMP"' EXIT
javac -d "$QA_ROUTE_TMP" android/app/src/main/java/com/infinitygames/qaclip/MacRoute.java tests/java/MacRouteTest.java
java -cp "$QA_ROUTE_TMP" com.infinitygames.qaclip.MacRouteTest
