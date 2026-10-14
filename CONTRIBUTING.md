# Contributing

QA Clip currently supports Android phones and macOS laptops. Keep the capture workflow simple and the data readable without the app.

1. Read AGENTS.md and docs/ARCHITECTURE.md.
2. Run `bash scripts/setup-mac.sh` to create the Python environment.
3. Work against a disposable `--inbox` directory and another `--port`; never test destructive transitions against your daily inbox.
4. Run `.venv/bin/python -m unittest discover -s tests -v` and `node scripts/check-ui.js`.
5. For browser changes, verify video playback, editing, approve/reject/undo, keyboard shortcuts, settings, incoming clips, and a narrow viewport.
6. Run `./build.sh` for Android changes. Verify on a real Android phone when capture behavior changes; a successful APK build does not prove screen capture works on every device.

Provider tests in CI use mocked CLI processes; live provider checks require your own login and consume usage. Use synthetic media. Describe what was tested and any remaining limitations in your pull request.
