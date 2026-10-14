#!/bin/bash
# Optional argument: exact adb device serial. Refuse ambiguous device selection.
set -euo pipefail
cd "$(dirname "$0")/.."
QA_ADB=$(command -v adb || true)
QA_ADB=${QA_ADB:-${ANDROID_HOME:-$HOME/Library/Android/sdk}/platform-tools/adb}
[[ -x "$QA_ADB" ]] || { echo 'adb missing. Run scripts/setup-mac.sh --brew.' >&2; exit 1; }
QA_VERSION=$(sed -nE "s/.*versionName '(.*)'.*/\1/p" android/app/build.gradle)
QA_APK="out/PlaytestDemon-$QA_VERSION.apk"
[[ -f "$QA_APK" ]] || { echo 'Build the APK first with ./build.sh.' >&2; exit 1; }
QA_SERIAL=${1:-}
if [[ -z "$QA_SERIAL" ]]; then
  QA_DEVICES=$("$QA_ADB" devices | awk '$2 == "device" {print $1}')
  QA_COUNT=$(printf '%s\n' "$QA_DEVICES" | awk 'NF {n++} END {print n+0}')
  [[ "$QA_COUNT" == 1 ]] || { echo 'Connect and authorize exactly one Android phone, or pass its serial.' >&2; "$QA_ADB" devices; exit 1; }
  QA_SERIAL=$QA_DEVICES
fi
"$QA_ADB" -s "$QA_SERIAL" install -r "$QA_APK"
"$QA_ADB" -s "$QA_SERIAL" shell am start -n com.infinitygames.qaclip/.MainActivity >/dev/null
printf 'Installed %s. On the phone: enable Playtest Demon volume buttons, then start a session.\n' "$QA_APK"
