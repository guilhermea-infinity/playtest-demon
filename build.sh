#!/bin/bash
# Builds the phone app into out/QAClip-<version>.apk (needs JDK 21 and the Android SDK).
set -e
cd "$(dirname "$0")/android"
export JAVA_HOME=${JAVA_HOME:-/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home}
./gradlew assembleDebug -q
V=$(grep versionName app/build.gradle | sed -E "s/.*'(.*)'.*/\1/")
cp app/build/outputs/apk/debug/app-debug.apk ../out/QAClip-$V.apk
echo "out/QAClip-$V.apk"
