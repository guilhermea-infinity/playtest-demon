# QA Clip

Play any game on an Android phone. When something breaks, press **Vol +**. The last 15 seconds, plus everything
until you press **Vol +** again, land on your Mac as a video named after the game. Talk while you play: your voice
is in the clip.

On the Mac, **QA Desk** has Claude watch each clip as it arrives and draft tickets. You approve them one by one, and
the approved ones become a single prompt for your programmer agent, ready to copy or drag.

| Button | While playing |
|---|---|
| **Vol +** | Start a clip. It already holds the 15 s before the press, and keeps recording. |
| **Vol +** again | Stop. The clip goes to the Mac. |
| **Vol −** while recording | Throw that clip away. |

Outside a session, and Vol − when no clip is recording, the buttons change the volume as normal.
A small pill in the top-left shows `● REC 0:23`, then `Saved` or `Thrown away`. The phone also buzzes:
one tick = recording, two ticks = saved, one long buzz = thrown away.

## Setup (once)

1. **Mac:** double-click `QA Desk.command`. Leave that window open while you play. The review page opens in your
   browser at http://127.0.0.1:8800.
   The first time, also run `claude auth login` in Terminal, so the desk can use Claude Code. Until you do, clips
   wait in the queue.
2. **Phone:** plug it in with USB debugging on, then run `bash ~/Desktop/qa-clip/mac/install-phone.sh`.
   You can also copy `out/QAClip-0.1.0.apk` to the phone and open it there.
3. In QA Clip, tap **Volume buttons → Turn on**, and switch on **QA Clip volume buttons**.
   If that switch is greyed out, go to Settings → Apps → QA Clip → ⋮ → **Allow restricted settings**, then try again.
4. The first time the phone finds the Mac over Wi-Fi, the Mac asks **Allow?** Click Allow. Phones on USB are trusted
   without asking.

## Each session

Open QA Clip → **Start session** → **Share screen**. The app gets out of the way. Open the game and play.
When you're done, tap **Stop session**, either in the app or in the notification.

## How clips reach the Mac

The phone tries three routes, in this order, with no setup:
1. The Mac it reached last time.
2. Bonjour on the Wi-Fi: the Mac announces itself, and the phone finds it by name.
3. A USB cable: the inbox runs `adb reverse` on any plugged-in phone. Use this on office Wi-Fi that blocks
   phone-to-Mac traffic.

If the Mac can't be reached (it's asleep, you're on the train, the inbox is closed), clips wait on the phone
("2 waiting") and send by themselves once the Mac is back. The phone deletes nothing until the Mac confirms it got
every byte, and keeps the last 20 sent clips as a backup.

## Where clips land

```
~/Desktop/QA-Inbox/
  Club Empire/
    2026-10-14 15.59.24.mp4    the clip
    2026-10-14 15.59.24.json   game, version, device, pressedAtSecond, clipSeconds, voice
  inbox.jsonl                  one line per clip, oldest first
  Tickets/
    CE-001/                    ticket.json, shot-1.png (red box), shot-1-clean.png
    clips.json                 which clips were analysed, and any errors
    .work/                     Claude's frames, sheet, transcript and raw answer, per clip
  Handoffs/                    every prompt you copied, as .md
```

`pressedAtSecond` is where in the video you pressed Vol +. The thing you saw happened just before that point.

## Tickets: from clip to programmer

1. **Claude drafts.** For each new clip, the desk:
   - pulls a frame every 0.5 s, plus an overview sheet;
   - transcribes your voice with whisper;
   - runs Claude Code headless (`claude -p`, Opus by default), once per clip.

   Claude looks at the frames, matches them against what you said, and writes 1 to 3 tickets. Each ticket has
   where, now, want, steps, done when, your quote, and up to 3 screenshots with a red box on the element.
   A 30 s clip takes about a minute.
2. **You review**, one ticket at a time, with the clip playing at the right moment. You can edit any field and
   drop a screenshot. The orange "Check before approving" box lists anything Claude wasn't sure about, for example
   you said "left" when the buttons are on the right.
   - **A** approves.
   - **R** rejects (there's an Undo).
   - **L** leaves it for later.
   - **⌘↵** approves even while you're typing.
   - If Claude misread the clip, use *Redo this clip with a hint* to re-draft it with your correction.
3. **Hand off.** Approved tickets collect on the right, one prompt per game.
   - **Copy prompt** copies the prompt. **⠿ Drag** lets you drop it into your agent's chat, or onto Finder as a
     `.md` file.
   - The prompt has every ticket plus the full paths to its screenshots and clip, so an agent running on this Mac
     can open them itself. An agent in the cloud can't see your files.
   - Each hand-off is saved in `QA-Inbox/Handoffs/`. **Sent → Copy again** copies an old one.

To change what Claude is told, edit `mac/prompts/analyst.md` (how it drafts) or `mac/prompts/handoff.md` (the
intro your programmer agent gets). Both take effect on the next clip or copy.

## Prototype limits

- Android only, sideloaded. It needs Android 10 or later.
- Android asks "Share screen?" once per session. On Android 15 and later, locking the phone ends the session.
  A clip that is recording when that happens is saved.
- The capture size is fixed when the session starts (720 px wide, in portrait). If you rotate to landscape
  mid-session, the clip is letterboxed. Start the session in the game's orientation.
- One clip is capped at 3 minutes. At the cap it saves by itself.
- Your voice comes from the phone mic; game sound is not captured.
- The volume buttons were tested on an OPPO A16 (Android 11). Other phone makers' software could still grab them
  first.
- QA Desk only drafts while its window is open. Clips that arrive while it's closed are drafted the next time you
  start it.
- Each clip is one Claude Code run on your plan, so it counts toward your usage. A 30 s clip reads about 10 frames.

## Files

- `android/`: the phone app. Plain Java, no libraries. Rebuild with `./build.sh`.
- `mac/qa-desk.py`: QA Desk. It starts the inbox, the analyst and the review page. Options:
  - `--model sonnet`: use a different Claude model.
  - `--from-now`: skip the clips already in the inbox.
  - `--port N`: serve the review page on another port.
  - `--no-inbox`: don't start the inbox.
  - `--no-open`: don't open the review page.
- `mac/desk_*.py`, `mac/desk-ui/index.html`, `mac/prompts/`: the analyst, the review page and the two prompts.
- `mac/qa-inbox.py`: the inbox on its own. Python standard library only. Options: `--inbox DIR`, `--port N`,
  `--no-usb`.
- Approved phones are stored in `~/.config/qa-clip/devices.json`. Delete a line there to un-pair a phone.

## What lives outside this folder

All the code is here. These are tools on the Mac that it uses, and what you'd install on a new Mac:

- Claude Code, signed in (`claude auth login`).
- `brew install ffmpeg whisper-cpp`, plus a whisper model at `~/.cache/whisper/ggml-medium.bin`. Without
  whisper-cli the desk still works, but Claude can't hear you.
- Pillow for Python 3 (`python3 -m pip install --user pillow`), for the contact sheet and the red boxes.
- To rebuild the phone app or install it over USB: `brew install openjdk@21` and the Android SDK
  (`~/Library/Android/sdk`, which Android Studio sets up). `android/local.properties` points at it.
- Your data is in `~/Desktop/QA-Inbox`, not here: clips, `Tickets/` and `Handoffs/`.
