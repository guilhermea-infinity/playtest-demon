# How QA Clip works

## Capture and transfer

The Android MediaProjection foreground service buffers encoded screen frames. A Volume Up press retains the preceding 15 seconds and begins the marked recording; the next press finishes it. Accessibility listens for the hardware buttons. Microphone audio accompanies the screen; internal game audio is not captured.

The uploader retries local clips through the last endpoint, Bonjour (`_qaclip._tcp`), and USB reverse forwarding to port 8799. Each request has a device key and clip metadata. Unknown Wi-Fi keys require an owner-approved pairing dialog; loopback connections through USB are trusted. The receiver writes a `.part` file, checks its length, renames it, writes metadata, and appends to `inbox.jsonl` before acknowledging. Only completed arrivals enter the analysis queue.

## Queue and analysis

The inbox watcher scans the arrival log every second independently of the single analysis worker. `Store` persists transitions to `Tickets/clips.json` with atomic replacement, guarded by an RLock. On startup, interrupted working clips return to queued. The desktop process holds a lock per inbox to prevent two desks from editing the same queue.

States: queued → working → done or failed. Retry moves failed/skipped/done clips to queued; already queued/working clips cannot be retried. Redo with a hint rejects only that clip's unapproved drafts. Provider auth errors put a clip back in the queue until sign-in succeeds.

The worker snapshots provider/model settings at the start of each clip, extracts frames at 2 fps, creates a labelled contact sheet, and optionally transcribes audio with whisper.cpp. It sends the prompt and evidence to Claude Code (`-p`, Read/Glob tools) or Codex (`exec`, read-only sandbox, JSON schema and image attachment). Both CLI results are validated against the ticket schema. ffmpeg exports selected screenshots, Pillow adds evidence boxes, and Store writes reviewable drafts.

There is intentionally no worker pool. This keeps model usage bounded, draft IDs sequential, and duplicate detection aware of previous clips. A long analysis never blocks receiving or reviewing other work.

## Review and handoff

The loopback HTTP server exposes state, settings, ticket transitions, handoffs and byte-range media playback. The browser polls state every 1.5 seconds and preserves the active form instead of rebuilding it on each update. Settings and queue pause persist per inbox.

Ticket states: draft → approved/rejected; either can return to draft. An exported handoff moves its approved tickets to sent; Undo restores them. Handoff filenames include a unique ID, avoiding collisions for repeated exports in the same minute. Handoffs are local Markdown, not remote messages or GitHub issues.

## Boundaries

The receiver is reachable on the local network; the review server is loopback-only and checks Host/Origin. Media paths must stay inside the inbox. Pairing uses device keys, but Wi-Fi transport is not encrypted; use a trusted network or USB. The selected provider receives extracted images/transcript/context. Local logs and inbox files may contain private content and are excluded from Git.
