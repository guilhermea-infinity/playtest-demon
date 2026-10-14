# How Playtest Demon works

## Capture and transfer

The Android MediaProjection foreground service buffers encoded screen frames. A Volume Up press retains the configured 0–30 seconds (default 10) and begins the marked recording; the next press finishes it. Accessibility listens for the hardware buttons. Microphone audio accompanies the screen; internal game audio is not captured.

The uploader retries local clips through the last endpoint, Bonjour (`_qaclip._tcp`), and USB reverse forwarding to port 8799. Each request has a device key and clip metadata. Unknown Wi-Fi keys require an owner-approved pairing dialog; loopback connections through USB are trusted. The receiver writes a `.part` file, checks its length, renames it, writes metadata, and appends to `inbox.jsonl` before acknowledging. Only completed arrivals enter the analysis queue. Streaming transfer hashes and the fsynced arrival log deduplicate Android retries after an acknowledgement loss, including concurrent transfers; temporary filenames are unique.

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

## iOS / desktop import

`POST /api/import` streams bounded raw MOV/MP4/M4V bytes into a temporary folder. Host/Origin checks apply before reading. SHA-256 detects identical imports, including concurrent submissions. ffprobe requires a video track and a duration below 10 minutes; ffmpeg converts to H.264/AAC MP4 with faststart while retaining audio. Under the Store lock, the completed file, sidecar and fsynced arrival log are written before queue discovery. No interrupted upload is queued. A hash of an item in recoverable trash does not prevent the owner importing it again.

Imported metadata identifies iOS/Imported and a zero press offset. The analyst prompt explicitly excludes Android trigger/lookback/REC-overlay assumptions. The system recorder is the shipped iOS capture mechanism; there is no native iOS executable in this repository.

## Fix batches

`desk_runs.Runs` owns a separate single worker and durable `Tickets/runs.json`. `POST /api/run` reserves approved requests under Store’s lock and persists their immutable snapshot; states proceed queued → preparing → fixing → testing → publishing → pr_ready → merge_queued → merged. Failures/interruption stay reserved for explicit recovery or cancellation. An open PR/active or unresolved failed run blocks new runs for that repository. Startup reconciles reservations and marks interrupted work, without rerunning an agent.

Each run clones the remote base into `AgentRuns/<ID>/repo`, copies selected evidence, invokes its configured CLI and requires every request to be accounted for. The desk reruns the configured checks and verifies the agent did not switch branches/commits. It removes evidence/helpers, creates a commit, pushes only the new branch and creates/reuses the PR by head branch. Saved verified commits can recover publication without another inference.

PR refresh records GitHub state; merge requires the original commit and required status checks and delegates to GitHub auto-merge without admin bypass. Merged requests become fixed; only human playtest confirmation makes them verified. Closed PRs return requests to approved. Reopening a fix retains its previous run ID.

## Review recovery

Trash is a durable soft deletion of a clip and its requests. Restoring returns their prior states; originals remain on disk. Active/submitted evidence cannot be trashed. Duplicate suggestions compare titles and provider hints; linking is human-controlled, scoped to a game, and reversible. A duplicate retains its own ticket/evidence and links to a canonical request. Copying a prompt is a pure export and no longer marks requests sent; older handoff state remains readable/reversible.

Receiver contact contains only device display name, transport and timestamp, separate from pairing keys. Desk process health, receiver availability and recent authenticated phone contact are separate UI signals. Estimates use the median duration of the last ten completed clips after at least three samples; the UI shows a range with an uncertainty explanation.
