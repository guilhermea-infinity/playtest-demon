#!/bin/bash
# Build an installable debug APK with a local signing key. Never commit that key.
set -euo pipefail
cd "$(dirname "$0")"
if [[ -z "${JAVA_HOME:-}" ]]; then
  if command -v brew >/dev/null && [[ -d "$(brew --prefix openjdk@21 2>/dev/null)/libexec/openjdk.jdk/Contents/Home" ]]; then
    export JAVA_HOME="$(brew --prefix openjdk@21)/libexec/openjdk.jdk/Contents/Home"
  elif [[ -x /usr/libexec/java_home ]]; then
    export JAVA_HOME="$(/usr/libexec/java_home -v 21)"
  fi
fi
export ANDROID_HOME="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Library/Android/sdk}}"
if [[ ! -d "$ANDROID_HOME" ]]; then
  echo 'Android SDK not found. Set ANDROID_HOME; see docs/INSTALL-AGENT.md.' >&2; exit 1
fi
mkdir -p out
(cd android && ./gradlew assembleDebug -q)
QA_VERSION=$(sed -nE "s/.*versionName '(.*)'.*/\1/p" android/app/build.gradle)
cp android/app/build/outputs/apk/debug/app-debug.apk "out/QAClip-$QA_VERSION.apk"
printf 'Built out/QAClip-%s.apk\n' "$QA_VERSION"
