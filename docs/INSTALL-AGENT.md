# Install QA Clip for your owner

You are installing an Android capture app and its macOS review desk. Complete the checks you can perform, guide the owner through Android permission prompts, and report what you actually verified. Do not claim an end-to-end phone test unless a real clip arrived and produced a ticket.

## 1. Inspect and choose

- Confirm this is macOS and the phone is Android 10+. Other laptop operating systems and iOS are not supported.
- Inspect `python3`, `brew`, `node`, `ffmpeg`, `ffprobe`, `whisper-cli`, `claude`, `codex`, Java, `adb`, and the Android SDK. Reuse working installations.
- Ask the owner to choose **Codex CLI or Claude Code**, a model or CLI default, the installation directory, and the inbox location if their preferences are not already known. Do not switch providers because one lacks credentials.
- Check for an existing QA Clip installation and `~/Desktop/QA-Inbox`. Preserve data, settings and pairing keys. Back up the existing inbox before migration. Never put it inside the Git repository.
- Inspect `adb devices`. If several devices are connected, select the owner's intended serial explicitly. An `unauthorized` device needs the owner's approval on the phone.

## 2. Install the laptop tools

Clone the repository into an owner-approved directory. From that directory:

```bash
bash scripts/setup-mac.sh --brew
```

The script installs Homebrew packages and Python dependencies in `.venv`. If Homebrew is missing, guide the owner through its official installation at https://brew.sh; do not assume administrator access. For existing dependencies, omit `--brew` to set up only Python.

If Node.js is missing, install it (`brew install node`). Install only the selected CLI:

```bash
npm install -g @openai/codex
codex login
# OR
npm install -g @anthropic-ai/claude-code
claude auth login
```

The owner completes browser/account sign-in. Never collect passwords, copy credentials, or print token files. Confirm `codex login status` or `claude auth status`.

For voice, reuse an existing whisper.cpp model. Otherwise download the multilingual small model (roughly 466 MB):

```bash
mkdir -p "$HOME/.cache/whisper"
curl -fL --retry 3 https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin \
  -o "$HOME/.cache/whisper/ggml-small.bin"
```

An alternate model path can be supplied with `QA_WHISPER_MODEL`. This environment variable must be present when starting QA Desk; a Terminal-only export is not inherited by a later Finder launch. The default cache location works for both.

Run `.venv/bin/python scripts/doctor.py --provider codex` (or `claude`). Resolve required missing tools; explicitly report if voice transcription is unavailable.

## 3. Build and install Android

Use Android Studio's SDK Manager to install Android SDK Platform 36 and Build Tools 35.0.0. Its usual macOS SDK location is `~/Library/Android/sdk`. Set `ANDROID_HOME` if different. With command-line SDK tools already available, the equivalent is:

```bash
sdkmanager 'platform-tools' 'platforms;android-36' 'build-tools;35.0.0'
```

The owner must accept Android SDK licenses. Do not blindly pipe “yes” into license prompts.

```bash
./build.sh
./mac/install-phone.sh DEVICE_SERIAL
```

Alternatively, download the versioned APK and checksum file from this repository's GitHub Release, verify it using `shasum -a 256`, place it in `out/`, and use `install-phone.sh`. An APK alone does not require Java or the full SDK; only adb is needed for USB installation.

If Android reports `INSTALL_FAILED_UPDATE_INCOMPATIBLE`, the installed app uses a different signing key. Stop before uninstalling: that would erase unsent clips. Ask the owner to export/send the clips first or use an APK built with the original signing key. Keep the same local debug key for future local upgrades.

## 4. Guide the owner through phone permissions

These are owner actions, not permissions an agent should silently grant:

1. Enable Developer options and USB debugging; approve the Mac's debugging fingerprint.
2. In QA Clip, enable “QA Clip volume buttons” in Accessibility settings.
3. If Android blocks Accessibility for a sideloaded app, open Settings → Apps → QA Clip → ⋮ → Allow restricted settings, then retry.
4. Grant microphone and notification permissions when prompted.
5. Tap Start session and approve screen capture. Choose the whole screen when offered so the game is included.

Do not disable platform protections or change unrelated accessibility services.

## 5. Start and verify the full loop

```bash
./QA\ Desk.command --provider codex
# OR: ./QA\ Desk.command --provider claude --model sonnet
```

Use `--inbox /absolute/path` for a custom inbox. Open http://127.0.0.1:8800. If the port is occupied, identify the existing process before changing it. Only one desk may manage a given inbox.

- Confirm Videos loads and the intended provider/model appears in settings.
- Ask the owner to record a harmless 5–10 second clip: Volume Up, describe one visible change request, then Volume Up again.
- Confirm the phone finishes sending and a card appears in Videos. New cards should continue appearing while another clip is analysed.
- Confirm the card moves through extraction, transcription and provider analysis to Ready to review, or shows a specific actionable error.
- Open Review. Confirm video playback, the spoken quote if audio is enabled, screenshots and editable fields.
- With the owner's test ticket, verify edit → approve → Handoffs → preview/copy. Do not post a ticket to an external issue tracker.
- If Wi-Fi is desired, disconnect USB, approve the new phone pairing dialog on the Mac, and repeat. Some office Wi-Fi blocks local discovery; USB remains a valid fallback.
- Stop the test session on the phone. Explain how to start the next one.

## 6. Leave a clear handover

Give the owner the repository path, inbox path, chosen CLI/model, exact launch command and any unverified items. Double-clicking QA Desk.command works after setup and remembers provider/model settings. Keep Terminal open; Ctrl+C stops the desk. The browser's Pause queue control is persistent and does not stop the receiver.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Missing CLI / sign-in banner | Run the selected CLI's login command in Terminal; make sure it is on PATH. Queue checks again automatically. |
| Model failure or usage limit | Read the card's error; choose a valid vision model or wait for account quota, then Retry. |
| No spoken quote | Check mic permission, `whisper-cli`, its model, and `QA_WHISPER_MODEL`. |
| No USB arrival | `adb devices`, cable/authorization, receiver port 8799, `adb -s SERIAL reverse tcp:8799 tcp:8799`. |
| No Wi-Fi arrival | Same trusted network, Mac firewall approval, pairing dialog, Bonjour allowed. Try USB. |
| Clip waits on phone | Keep QA Desk running and the Mac awake. The phone retries automatically. |
| Empty review | Videos may still be processing or the queue may be paused. Review has only unapproved drafts. |
| Interrupted analysis | Restart QA Desk; working clips become queued. Check `.work/` logs if it repeatedly fails. |
| Python import error | Rerun `bash scripts/setup-mac.sh` and launch through QA Desk.command, which uses `.venv`. |

Data lives outside Git. Back up the inbox separately. Delete neither the inbox nor `~/.config/qa-clip/devices.json` as a troubleshooting shortcut.
