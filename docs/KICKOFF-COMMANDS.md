# Kickoff command cards — paste at 13:00 CDT / 18:00 UTC

Do not paste these before kickoff. Briefing is done. Product code starts on the clock.

---

## Card A — Grok Bot (paste first)

```text
Battle Buddy Yard #1. Repo: https://github.com/wyldephyre/battle-buddy
Read AGENTS.md, docs/PRD.md, docs/DEV-LOOP.md in that repo.

Theme lock: no sign-up, no login, no email to use it.
Runtime: Hermes skill + standalone modules. Local 2–3B optional. Empty API key.
Do not copy wyldephyre/veteran-gaming-assistant.

First objective only:
1. Create skills/battle-buddy/SKILL.md for a voice-first reminder prosthetic.
2. Create battlebuddy/memory and battlebuddy/reminders so a time reminder persists on disk and can fire.
3. Create a typed CLI or minimal UI entry point so I can run: remind me in 1 minute to check food stores.
4. Do not add Steam keys, OAuth, cloud STT, or accounts.

Return the file tree and the exact run command. Then stop.
```

---

## Card B — Cursor Agent / Composer (paste second, in the cloned folder)

```text
Read AGENTS.md and docs/PRD.md.

Kickoff is live. Implement the first loop only.

Create:
- skills/battle-buddy/SKILL.md
- battlebuddy/memory/store.py (or equivalent) — local JSON
- battlebuddy/reminders/engine.py — schedule, list, cancel, snooze, fire
- battlebuddy/__main__.py — typed entry so I can add a 1-minute reminder
- requirements.txt — no cloud STT as default

Acceptance: I can add a 1-minute reminder with no account, see it persist after restart, and have it fire.

Do not copy the old veteran-gaming-assistant monolith.
After the files exist, give me the exact commands to run on Windows.
```

---

## Card C — This Grok (only if the loop stalls)

```text
First loop is stalling. Stay on the single objective: persist and fire a 1-minute reminder with no account. Cut anything else. Tell me the one next file to write.
```

---

## Sunday ship card (do not use Friday)

```text
Feature freeze. Do not add features.
Check: clone → run → 1-minute reminder → fire → restart still has it.
Write the demo script: 60–90 seconds, say “no accounts” out loud.
List the screenshot target and the Hackyard submit fields.
```
