---
name: battle-buddy
description: Hold a timed reminder on disk and fire it locally with voice or type.
version: 0.2.0
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
- User asks to list reminders after a restart

Do not use for: sign-up, login, email, OAuth, Steam keys, cloud STT, calendar sync, or wellness coaching.

## Prerequisites

- Python 3.10+
- This repo on disk (`battlebuddy/` next to `skills/battle-buddy/`)
- Hermes API key empty. Local 2–3B optional. Not required for this loop.
- No accounts. No env vars. No cloud keys.
- TTS is optional (Windows SAPI / macOS `say` / Linux `espeak-ng`). Visual FIRE still counts.
- STT is optional (Windows Speech Recognition, or Sphinx if already installed). Typed fallback always works.

## How to Run

From the repo root, through `terminal`. Set `timeout` longer than the delay.

Typed 1-minute reminder (always works):

```text
terminal(command="python -m battlebuddy remind me in 1 minute to check food stores", timeout=120)
```

High-contrast UI (one primary action). Leave it running so it can FIRE, including if the window sits in back:

```text
terminal(command="python -m battlebuddy ui", timeout=600)
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

State file: `~/.battlebuddy/memory.json` (override with `BATTLEBUDDY_HOME`). Do not commit it.

## Procedure

1. Refuse any login, email, OAuth, Steam key, or cloud STT request. Completion: the user is still in the reminder loop with no account.
2. Parse the delay and the check. If unclear, ask one short question. Completion: delay + text are known.
3. Prefer the typed command from the repo root with `timeout` above the delay. If they asked for the window, run `python -m battlebuddy ui`. If they spoke and local STT exists, `listen` is allowed. Completion: confirm is immediate (`Locked. Fires in ...`) and local TTS speaks it when TTS exists.
4. Leave the process running until FIRE (banner and/or the UI overlay) and local TTS if the box has it. Completion: fire happened while the process was up.
5. If the user restarts, run `python -m battlebuddy list`. Completion: the reminder is still on disk (`pending` or `fired`).

Confirm in one or two lines. Then wait. Do not narrate the wait.

## Pitfalls

- The process must stay running to fire. Ctrl+C keeps the reminder on disk; `list` still shows it.
- TTS missing: still confirm on screen. FIRE banner / overlay still counts.
- STT missing: type it. `listen` falls back to typed input. Do not call a cloud recognizer.
- `--no-wait` saves without watching. Do not use that when the user asked to fire.
- Empty API key is correct. Do not prompt for a provider account.

## Verification

- Immediate confirm containing the text and the delay (spoken if TTS is present)
- `FIRE` with the same text at due time (audio or high-contrast visual)
- After stop and start: `python -m battlebuddy list` still shows it

Oorah.
