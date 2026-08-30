---
name: battle-buddy
description: Hold a timed reminder on disk, fire it locally, then list, snooze, or clear it.
version: 1.0.0
author: Captain Phyre (wyldephyre)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [reminders, memory, local, veterans, voice]
    related_skills: []
    requires_toolsets: [terminal]
---

# Battle Buddy Skill

Voice-first external memory for a timed check in a long session. Same modules as the standalone CLI and UI. No account. No cloud. No API key. Jessica is not this app.

## When to Use

- User says or types a timed reminder: "remind me in 15 minutes to check food stores"
- User wants confirmation now and a fire later (visual + local TTS if the box has it)
- User wants the high-contrast window
- User asks to list, snooze, or clear reminders (including after a restart)

Do not use for: sign-up, login, email, OAuth, Steam keys, cloud STT, calendar sync, or wellness coaching.

## Prerequisites

- Python 3.10+
- This repo on disk (`battlebuddy/` next to `skills/battle-buddy/`)
- Hermes API key empty. Local 2–3B optional. Not required for this loop.
- No accounts. No env vars. No cloud keys.
- TTS is optional (Windows SAPI / macOS `say` / Linux `espeak-ng`). Visual FIRE still counts.
- STT is optional (Windows Speech Recognition, or Sphinx if already installed). Typed fallback always works.

## How to Run

From the repo root, through `terminal`. Set `timeout` longer than the delay when waiting for fire.

Typed 1-minute reminder (always works):

```text
terminal(command="python -m battlebuddy remind me in 1 minute to check food stores", timeout=120)
```

High-contrast UI (one primary action). Leave it running so it can FIRE, including if the window sits in back. List, snooze, and clear are large targets in that window.

```text
terminal(command="python -m battlebuddy ui", timeout=600)
```

List / snooze / clear (return immediately, same memory file):

```text
terminal(command="python -m battlebuddy list")
terminal(command="python -m battlebuddy snooze food stores 5 minutes")
terminal(command="python -m battlebuddy clear reminder about mines")
terminal(command="python -m battlebuddy clear all")
```

Local listen if STT exists, otherwise it asks for type:

```text
terminal(command="python -m battlebuddy listen", timeout=120)
```

Never send audio to a cloud. Never ask for an API key.

## Quick Reference

| Said or typed | Command |
|---|---|
| Open the window | `python -m battlebuddy ui` |
| Remind me in 1 minute to check food stores | `python -m battlebuddy remind me in 1 minute to check food stores` |
| In 20 minutes remind me to scout north | `python -m battlebuddy in 20 minutes remind me to scout north` |
| Speak a reminder (local STT) | `python -m battlebuddy listen` |
| List my reminders | `python -m battlebuddy list` |
| Snooze food stores 5 minutes | `python -m battlebuddy snooze food stores 5 minutes` |
| Clear reminder about mines | `python -m battlebuddy clear reminder about mines` |
| Clear all | `python -m battlebuddy clear all` |

State file: `~/.battlebuddy/memory.json` (override with `BATTLEBUDDY_HOME`). Do not commit it.

## Procedure

1. Refuse any login, email, OAuth, Steam key, or cloud STT request. Completion: the user is still in the reminder loop with no account.
2. Parse the delay and the check, or the list / snooze / clear line. If unclear, ask one short question. Completion: the command is known.
3. Prefer the typed command from the repo root. If they asked for the window, run `python -m battlebuddy ui`. If they spoke and local STT exists, `listen` is allowed. For a new reminder, set `timeout` above the delay. Completion: confirm is immediate (`Locked. Fires in ...`, `Snoozed...`, or `Cleared...`) and local TTS speaks it when TTS exists.
4. For a new reminder, leave the process running until FIRE (banner and/or the due card, plus the topmost splash if the window is hidden) and local TTS if the box has it. Completion: fire happened while the process was up. List / snooze / clear do not wait to fire.
5. If the user restarts, run `python -m battlebuddy list`. Completion: the reminder is still on disk (`pending` or `fired`) unless they cleared it.

Confirm in one or two lines. Then wait. Do not narrate the wait.

## Pitfalls

- The process must stay running to fire. Ctrl+C keeps the reminder on disk; `list` still shows it.
- TTS missing: still confirm on screen. FIRE banner / due card / splash still counts.
- STT missing: type it. `listen` falls back to typed input. Do not call a cloud recognizer.
- `--no-wait` saves without watching. Do not use that when the user asked to fire.
- `clear all` wipes the store. Do it when they said clear all. Confirm the wipe in one line.
- Empty API key is correct. Do not prompt for a provider account.

## Verification

- Immediate confirm containing the text and the delay (spoken if TTS is present)
- `FIRE` with the same text at due time (audio or high-contrast visual)
- After stop and start: `python -m battlebuddy list` still shows it
- `snooze food stores 5 minutes` shifts due and confirms
- `clear reminder about mines` deletes the match and confirms
- `clear all` wipes and confirms

Oorah.
