#!/bin/bash
# Installs QA Clip on the phone plugged in by USB (USB debugging on) and opens it.
set -e
cd "$(dirname "$0")/.."
APK=$(ls -t out/QAClip-*.apk | head -1)
ADB=$(command -v adb || echo ~/Library/Android/sdk/platform-tools/adb)
"$ADB" install -r "$APK"
"$ADB" shell am start -n com.infinitygames.qaclip/.MainActivity >/dev/null
echo "Installed $APK. On the phone: tap 'Volume buttons: Turn on' and switch QA Clip on."
