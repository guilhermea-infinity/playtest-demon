#!/bin/bash
# Double-click to start QA Desk: it receives clips from the phone, has Claude draft tickets, and opens the review page.
# Leave this window open while you play; close it to stop.
cd "$(dirname "$0")" && exec python3 mac/qa-desk.py "$@"
