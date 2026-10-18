# Battle Buddy

Speak it once. It holds the line.

**No accounts.** No sign-up. No login. No email. No Steam key. No cloud. No Google.

External memory for veterans in long strategy and survival sessions. You speak or type a check. Battle Buddy holds the flame on your disk. When the clock hits, it FIREs. For the forgotten 99%. Active Stoicism. PHYRE.

## What it does

Four beats plus a hygiene loop. No cloud. Nothing invented.

1. **Remind.** Voice or typed reminder that survives restart. State lives on disk under `%USERPROFILE%\.battlebuddy`. FIRE at due time. Local TTS if the box has it.
2. **SCAN.** Live-captures the running game from local processes (Steam/Epic folder or Unreal shipping). No Steam API.
3. **Wiki seed.** First sight of a new empty-folder game fetches the top 3 public wiki pages (DuckDuckGo HTML `{game} wiki`, public GET, no account).
4. **ASK.** Answers from those local pages. Compile a real how-to or miss. Nothing invented.
5. **Hygiene.** 15 minutes work / 5 minutes break. Break FIRE rotates stand/move, eyes, breath. Gold **HYGIENE** button starts and stops it. Survives restart.

## The surface

High-contrast veteran UI: black, gold, cream, scarlet **SUBMIT** / **FIRE**. Gold **HYGIENE** starts and stops the 15/5 loop. ADHD-friendly large targets. One primary action. Low noise.

## How to run

**Windows:** double-click `BattleBuddy-Setup.exe`. The UI opens. No login. pip is not required to run the exe.

**From a clone:**

```text
python -m battlebuddy ui
```

One reminder from the CLI (no account):

```text
python -m battlebuddy remind me in 1 minute to check food stores
```

Stay in that window. It confirms. It FIREs in one minute. Restart and `python -m battlebuddy list` still shows it.

## Read This

**Ctrl+Alt+R** dims every connected monitor. Drag a box over on-screen text on any screen, including across a boundary (a Stellaris event, a quest, a tooltip). Release. Battle Buddy reads it with the same local TTS. No cloud. No account.

Esc cancels the box on all monitors at once. The same hotkey, or Esc while it is speaking, stops the voice. **READ THIS** sits next to **SCAN**. **READ AGAIN** (next to ASK) grabs that same box again, even when it lives on a side monitor. **REPEAT LAST** speaks the last text again.

Change the hotkey with `BATTLEBUDDY_READ_HOTKEY=ctrl+shift+r`, or add `"read_hotkey": "ctrl+shift+r"` in `session.json` under the Battle Buddy home folder. Other session keys stay put.

Capture and OCR are optional extras. The rest of the app runs without them.

```text
pip install -r requirements-readthis.txt
```

Windows OCR is the default. `winsdk` is used when that package imports. When it does not (no wheel for this Python), Battle Buddy calls the same Windows.Media.Ocr engine through Windows PowerShell. No compiler. Tesseract is the fallback (`pytesseract` plus the Tesseract binary on PATH). The grab prefers `mss` and falls back to Pillow. Each read is saved as a note so ASK can search it. Set `BATTLEBUDDY_SAVE_READS=0` to skip the note.

## Snap & Ask

**Ctrl+Shift+F10** grabs the monitor under the pointer (Stellaris eats Alt). Local OCR, same path as Read This, then a spoken answer from that text plus this game's notes and databank. **SNAP** does the full monitor under the pointer. **SNAP BOX** dims every connected monitor and drags a region first, including across a boundary. Esc stops speech. A follow-up box takes a typed question, or the mic when the box is empty.

Shots stay in `snaps` under the Battle Buddy home and drop off after 7 days. The snap is stored as a fact sourced `snap` for that game only. Change the hotkey with `BATTLEBUDDY_SNAP_HOTKEY` or `"snap_hotkey"` in `session.json`.

Brain local uses the sidecar when it is up, and the on-screen text when it is not. Brain Grok sends the text only. The image stays on the box unless `BATTLEBUDDY_SNAP_SEND_IMAGE=1`.

## Demo

PHYRE on a reel, no login: [watch the share page](https://reporeel-marlandoj.zocomputer.io/v/orZ8RaBQ). Reel by Marlando ([RepoReel](https://github.com/marlandoj/reporeel)). For the forgotten 99%. Oorah.

## Yard

**Hackyard Yard #1.** Theme: no accounts. MIT.

We are not asking for a seat at their table. We built a revolution instead.

**Oorah.**

---

## Appendix

Clone path if you want source instead of the exe. Python 3.10+. No signup.

```text
git clone https://github.com/wyldephyre/battle-buddy.git
cd battle-buddy
python -m battlebuddy ui
```

Same on-disk memory for list / snooze / clear:

```text
python -m battlebuddy list
python -m battlebuddy snooze food stores 5 minutes
python -m battlebuddy clear reminder about mines
python -m battlebuddy clear all
python -m battlebuddy hygiene start
python -m battlebuddy hygiene stop
```

macOS / Linux: same commands. Typed fallback always works. No cloud STT.

State: `%USERPROFILE%\.battlebuddy` on Windows, `~/.battlebuddy` on macOS/Linux. Reminders stay in `memory.json`. Games seen by SCAN and optional notes live in `catalog.sqlite`. Wiki pages stay under `databanks/`. Read This keeps its hotkey, last box, and last text in `session.json`. Not committed.

```text
python -m battlebuddy note granary is low
python -m battlebuddy games
python -m battlebuddy notes
```

Notes do not FIRE. ASK can read them and the saved wiki pages. Nothing invented. No key.

### Windows build

On a Windows box: `.\scripts\build-windows.ps1` (PyInstaller is build-only). Do not build the exe on Linux. pip is not required to run the shipped exe.

### Optional xAI (not required)

Yard 1 needs no key. Offline remind / FIRE / hygiene stay on disk with local TTS.

`XAI_API_KEY` in the environment maps messy remind / list / snooze / clear / hygiene lines onto the existing engine. Asks compile from saved wiki pages. Grok does not invent when those pages miss. Confirm and FIRE stay OS-local TTS. No UI field. No account. Never commit the key. Absent key is today's path.

Optional `STEAM_WEB_API_KEY` can add Corsair Cove news, achievement count, and owned status to `harvest`. Unset skips. No UI field. Never a Steam password. Never commit the key. Local library parse still works without it.

### Hermes (optional)

Same reminder loop as a [Hermes Desktop](https://hermes-agent.nousresearch.com/docs/getting-started/installation) skill. Local 2–3B. Empty API key.

```text
hermes skills install wyldephyre/battle-buddy/skills/battle-buddy
```

Jessica is not this app.

### Repo map

```text
skills/battle-buddy/SKILL.md   Hermes skill
battlebuddy/memory/            local JSON reminders + SQLite catalog
battlebuddy/reminders/         schedule, fire, list, clear, snooze
battlebuddy/voice/             local TTS / STT, typed fallback
battlebuddy/readthis/          region grab, local OCR, read aloud
battlebuddy/snap/              Snap & Ask. Monitor grab, sourced snap fact
battlebuddy/game_detect/       local process SCAN. No Steam API.
battlebuddy/databank/          public wiki GET, local ASK
battlebuddy/xai/               optional Grok map/compile (env key only)
battlebuddy/ui/                high-contrast window
BattleBuddy.spec               PyInstaller onedir
installer/BattleBuddy.iss      per-user Inno Setup (no admin)
scripts/build-windows.ps1      Windows exe + setup
```

MIT. See `LICENSE`. Trademark check parked.
