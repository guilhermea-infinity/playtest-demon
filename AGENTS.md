# QA Clip agent instructions

QA Clip is an Android-only screen recorder plus a macOS receiver and QA review desk.

## If asked to install

Read `docs/INSTALL-AGENT.md` and follow its verification sequence. Preserve existing clips, drafts, handoffs, provider preferences and pairing keys. The owner chooses the provider/model and completes account sign-in and Android consent. Use the `.venv` runtime. Report real verification separately from inferred behavior.

## If asked to develop

- `android/`: plain Java app, minimum Android API 29, compile SDK 36. Keep `com.infinitygames.qaclip` for compatibility with installed phones.
- `mac/qa-inbox.py`: USB/Bonjour receiver, complete-file acknowledgement.
- `mac/desk_store.py`: durable queue, ticket state and handoffs; disk mutations use its lock.
- `mac/desk_analyst.py`: one worker, media extraction, transcription and provider adapters. Keep arrivals observable while this worker blocks.
- `mac/desk_server.py`: loopback-only HTTP API, same-origin writes and bounded media paths.
- `mac/desk-ui/`: dependency-free browser UI. Preserve in-progress edits and playback across polling.
- `mac/prompts/`: hot-loaded instructions, shared by both providers.

Do not weaken sandbox/tool restrictions to get a provider run working. Do not silently fall back to another provider or model. Never submit real user clips to a different service during tests; use synthetic fixtures. Keep data and auth outside the repository.

Validate meaningful changes with `.venv/bin/python -m unittest discover -s tests -v`. Check frontend syntax (`scripts/check-ui.js`) and visually exercise changed flows against a disposable inbox. Build Android changes with `./build.sh`. No iOS implementation is in scope.

Publish only source, documentation, synthetic screenshots and explicitly intended release APKs/checksums. Never commit `android/local.properties`, `.venv`, `.gradle`, build outputs, inboxes, device keys or signing keys. Do not uninstall an existing phone app without owner approval; its unsent clips may be lost.
