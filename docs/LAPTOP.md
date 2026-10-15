# Playtest a game on your laptop

The Mac desk can record a browser game or another game window without a phone. Each tester needs Playtest Demon running on their own Mac, ffmpeg, local whisper/model for spoken requests, and their chosen signed-in AI CLI. Use `bash scripts/setup-mac.sh --brew --laptop` for a source setup without Java/Android tools. The prebuilt Mac app embeds its Python runtime. Windows/Linux desks and hosted team collection are not shipped.

## Capture an observation

1. Open **Playtest Demon → Live feed → Start playtest session**. The recorder opens in your default browser. Chrome is the tested browser; available capture/codec/floating features are detected at runtime.
2. Choose a game or type a new name. Paste its URL and click **Open game**. There is no iframe: games that block embedding can still be captured. Game names sync through the existing catalog after the first clip arrives; the selected name labels that clip.
3. Keep **Record my voice** checked to narrate. Choose 0–30 seconds of lookback, with 10 suggested. Ten seconds gives you time to notice a one-off bug before reacting. Zero starts at the clip marker. Settings and the last game link are remembered in this browser.
4. Click **Start playtest session**. In the browser's sharing prompt, select the game tab or game window. Approve microphone access when prompted. The owner must choose and approve the shared screen; an agent must not bypass these prompts. Share just the game to exclude unrelated windows. On macOS, the browser may also need Screen Recording permission in System Settings.
5. Wait for the lookback to fill, then play. Click **Float controls** where available to keep controls above the game. Without floating controls, put the recorder window next to the game. Keep this tab open throughout.
6. When something happens, click **Start clip**, describe what you saw and what should happen, then **Finish & send**. The clip includes available lookback. **Discard clip** throws away only the current observation. The session keeps buffering for the next one. A clip finishes after three minutes even if you forget.
7. Watch the received status below the recorder or return to **Live feed**. The same local transcription, selected AI/model, editable review tickets, approvals and fixing batches apply. The queue may be paused; receiving still works.
8. **End session** releases screen sharing and the microphone. If a clip is active, confirm to finish/send it first. Stopping sharing with the browser's own control also ends the session and sends any active clip. Unmarked buffer footage is discarded.

The recorder URL can prefill a session, e.g. `http://127.0.0.1:8800/playtest?game=Example&url=https%3A%2F%2Fexample.com%2Fgame`. It opens the receiver on the tester's own laptop. It does not send clips to another person's Mac; sharing a game link is not a hosted upload service.

## Controls and recovery

- **Start clip / Finish & send** is also **Option + Shift + C** while this recorder page or its floating window has focus. This shortcut is not global and does not intercept keys inside another game tab.
- Floating controls use Document Picture-in-Picture when the browser exposes it. Closing them returns controls to the recorder; recording continues. Keep the recorder page open.
- Failed sends keep the clip in this tab with **Retry send**, **Download backup** and **Remove**. Retrying the identical game, buffer and trim creates one queue item even after an acknowledgement is lost.
- Backups are the original WebM/MP4 buffer, including footage before the selected trim. They can contain up to about a minute before the marked clip; the MP4 received by the desk is trimmed to the selected lookback. Review a backup before sharing it.
- Unsent recordings live in browser memory, not permanent storage. Download a backup before closing the tab if the desk is unavailable. The browser warns when leaving with a session or unsent clip. A browser crash can still lose unsent clips.
- If the game freezes or sharing stops, check the browser capture indicator, macOS Screen Recording permission and that the chosen tab/window still exists. Permission cancellation releases any opened tracks; restart the session after granting access.
- No system/game audio is requested. Voice uses the microphone. A microphone disconnected during capture ends the session and sends the current clip with audio captured so far.

## Privacy and implementation

The browser captures only after explicit permission. Unmarked lookback stays in local memory. Sent clips transfer to the local loopback API and are converted to MP4; selected frames/transcript later go to the owner's chosen AI provider, just as Android clips do. The app does not expose its review API on the LAN or change provider automatically.

A rolling buffer starts a complete MediaRecorder container every 30 seconds, retaining overlapping containers for up to roughly 60 seconds plus any pinned observation. This avoids concatenating partial WebM chunks without their headers. A marked observation pins the appropriate container; ffmpeg trims the selected lookback and observation, preserving microphone audio. Rotation and sends continue independently. Encoding two overlapping buffers costs more CPU than a single recorder; capture requests 1280×720 around 20 fps and browser codecs are selected from supported WebM/MP4 options. Exact browser dimensions/frame rates can differ. There is a 100 MB per-buffer safety cap; slow/backgrounded pages can provide a shorter lookback after resuming.

## Verification for an installing agent

Use a harmless game or synthetic demo with the owner's consent. Verify a **real browser sharing prompt and real microphone recording** separately from synthetic tests:

1. Open a game URL; select its tab/window, allow the microphone and let 10 seconds accumulate.
2. Trigger an obvious visual change, start the clip just afterward, speak a short request and finish/send.
3. Confirm the received MP4 includes the pre-marker change, audible narration, platform `Browser` and correct press/lookback offsets. Verify a draft ticket in Review with the chosen CLI/model; approve only the owner's test request.
4. Send a second clip without restarting the session. Discard another. Exercise floating controls when available, including returning them to the recorder.
5. Interrupt a transfer only in a disposable inbox; confirm retry keeps one recording. End sharing and confirm the browser capture indicator/microphone are released.

Development checks: Python regression tests, `node scripts/check-ui.js`, `node --test tests/test_capture.js`, and a browser session against a **paused disposable inbox**. Automated browser checks use a canvas and generated audio; they verify actual MediaRecorder containers, MP4 conversion, lookback timing, repeat/discard/send/retry and floating controls without recording private owner screens or submitting clips to a provider. A synthetic capture check does not verify OS consent, a real microphone or a real AI ticket.

Browser API references: [screen capture](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getDisplayMedia), [MediaRecorder container/chunk behavior](https://developer.mozilla.org/en-US/docs/Web/API/MediaStream_Recording_API).
