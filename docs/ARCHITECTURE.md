# How QA Demon works

## Capture and transfer

The Android MediaProjection foreground service buffers encoded screen frames. A Volume Up press retains the configured 0–30 seconds (default 10) and begins the marked recording; the next press finishes it. Accessibility listens for the hardware buttons. Microphone audio accompanies the screen; internal game audio is not captured.

The uploader retries local clips through the last endpoint, Bonjour (`_qaclip._tcp`), and USB reverse forwarding to port 8799. Each request has a device key and clip metadata. Unknown Wi-Fi keys require an owner-approved pairing dialog; loopback connections through USB are trusted. The receiver writes a `.part` file, checks its length, renames it, writes metadata, and appends to `inbox.jsonl` before acknowledging. Only completed arrivals enter the analysis queue.

For nonzero lookback, the ring starts at the newest keyframe at or before the requested boundary. At zero, no pre-roll is retained: the muxer waits for a newly requested sync frame and sets the press offset to zero. Changing lookback/voice requires stopping the session. Game selection is snapshotted when the clip starts; changing it later cannot relabel a clip in progress.

`desk_games.py` merges game names in `games.json` under an OS file lock plus a thread lock. Both desktop and receiver use it. Names are case-insensitively deduplicated and are separate from filesystem-safe clip folders. Authenticated receiver `/games` GET/POST syncs the phone’s cached/offline additions; unapproved phones cannot read or change the list. An explicit `game` metadata field takes precedence over automatic app labels.

## Queue and analysis

The inbox watcher scans the arrival log every second independently of the single analysis worker. `Store` persists transitions to `Tickets/clips.json` with atomic replacement, guarded by an RLock. On startup, interrupted working clips return to queued. The desktop process holds a lock per inbox to prevent two desks from editing the same queue.

States: queued → working → done or failed. Retry moves failed/skipped/done clips to queued; already queued/working clips cannot be retried. Redo with a hint rejects only that clip's unapproved drafts. Provider auth errors put a clip back in the queue until sign-in succeeds.

The worker snapshots provider/model/effort settings at the start of each clip, extracts frames at 2 fps, creates a labelled contact sheet, and optionally transcribes audio with whisper.cpp. It sends the prompt and evidence to Claude Code (`-p`, Read/Glob tools) or Codex (`exec`, read-only sandbox, JSON schema and image attachment). Both CLI results are validated against the ticket schema. ffmpeg exports selected screenshots, Pillow adds evidence boxes, and Store writes reviewable drafts.

`desk_models.py` discovers capabilities with Codex app-server `model/list` or Claude’s stream-JSON initialize control response. No inference prompt is sent. Only model metadata is retained; account details are discarded. Discovery is time-bounded, cached per provider, and runs outside the queue lock. Effort options come from capabilities and are validated server-side, then passed as Claude `--effort` or Codex `model_reasoning_effort`. A failed model never silently falls back.

There is intentionally no worker pool. This keeps model usage bounded, draft IDs sequential, and duplicate detection aware of previous clips. A long analysis never blocks receiving or reviewing other work.

## Review and handoff

The loopback HTTP server exposes state, settings, ticket transitions, handoffs and byte-range media playback. The browser polls state every 1.5 seconds and preserves the active form instead of rebuilding it on each update. Settings and queue pause persist per inbox.

Ticket states: draft → approved/rejected; either can return to draft. An exported handoff moves its approved tickets to sent; Undo restores them. Handoff filenames include a unique ID, avoiding collisions for repeated exports in the same minute. Handoffs are local Markdown, not remote messages or GitHub issues.

## Boundaries

The receiver is reachable on the local network; the review server is loopback-only and checks Host/Origin. Media paths must stay inside the inbox. Pairing uses device keys, but Wi-Fi transport is not encrypted; use a trusted network or USB. The selected provider receives extracted images/transcript/context. Local logs and inbox files may contain private content and are excluded from Git.
