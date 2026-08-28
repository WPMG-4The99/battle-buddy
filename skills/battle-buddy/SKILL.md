---
name: battle-buddy
description: Hold a timed reminder on disk and fire it locally.
version: 0.1.0
author: Captain Phyre (wyldephyre)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [reminders, memory, local, veterans]
    related_skills: []
    requires_toolsets: [terminal]
---

# Battle Buddy Skill

Voice-first external memory for a timed check in a long session. Same modules as the standalone CLI. No account. No cloud. No API key. Jessica is not this app.

## When to Use

- User says or types a timed reminder: "remind me in 15 minutes to check food stores"
- User wants confirmation now and a fire later
- User asks to list reminders after a restart

Do not use for: sign-up, login, email, OAuth, Steam keys, cloud STT, calendar sync, or wellness coaching.

## Prerequisites

- Python 3.10+
- This repo on disk (`battlebuddy/` next to `skills/battle-buddy/`)
- Hermes API key empty. Local 2–3B optional. Not required for this loop.
- No accounts. No env vars. No cloud keys.

## How to Run

From the repo root, through `terminal`. Set `timeout` longer than the delay.

```text
terminal(command="python -m battlebuddy remind me in 1 minute to check food stores", timeout=120)
```

Typed fallback is the required path. If the user spoke, transcribe locally if the box can, then run that same command. Never send audio to a cloud.

## Quick Reference

| Said or typed | Command |
|---|---|
| Remind me in 1 minute to check food stores | `python -m battlebuddy remind me in 1 minute to check food stores` |
| In 20 minutes remind me to scout north | `python -m battlebuddy in 20 minutes remind me to scout north` |
| List my reminders | `python -m battlebuddy list` |

State file: `~/.battlebuddy/memory.json` (override with `BATTLEBUDDY_HOME`). Do not commit it.

## Procedure

1. Refuse any login, email, OAuth, Steam key, or cloud STT request. Completion: the user is still in the reminder loop with no account.
2. Parse the delay and the check. If unclear, ask one short question. Completion: delay + text are known.
3. Run `python -m battlebuddy <the line>` from the repo root with `timeout` above the delay. Completion: stdout shows `Locked. Fires in ...` immediately.
4. Leave the process running until stdout shows the `FIRE` banner (visual) and local TTS if the box has it. Completion: fire happened while the process was up.
5. If the user restarts, run `python -m battlebuddy list`. Completion: the reminder is still on disk (`pending` or `fired`).

Confirm in one or two lines. Then wait. Do not narrate the wait.

## Pitfalls

- The process must stay running to fire. Ctrl+C keeps the reminder on disk; `list` still shows it.
- Linux may have no TTS. The `FIRE` banner still counts.
- `--no-wait` saves without watching. Do not use that when the user asked to fire.
- Empty API key is correct. Do not prompt for a provider account.

## Verification

- Immediate confirm containing the text and the delay
- `FIRE` line with the same text at due time
- After stop and start: `python -m battlebuddy list` still shows it

Oorah.
