# Battle Buddy

Speak it once. It holds the line.

**No accounts.** No sign-up. No login. No email. No Steam key. No cloud.

External memory for veterans in long game sessions. For the forgotten 99%, we rise.

## Run it — Windows (PowerShell or cmd)

Python 3.10+. No signup. Clone, run, done.

```text
git clone https://github.com/wyldephyre/battle-buddy.git
cd battle-buddy
python -m battlebuddy remind me in 1 minute to check food stores
```

Stay in that window. It confirms immediately, then fires in 1 minute (visual banner; local TTS if the box has it).

High-contrast UI (same folder, no account):

```text
python -m battlebuddy ui
```

List, snooze, and clear (same on-disk memory):

```text
python -m battlebuddy list
python -m battlebuddy snooze food stores 5 minutes
python -m battlebuddy clear reminder about mines
python -m battlebuddy clear all
```

macOS / Linux: same commands. venv optional. Typed fallback always works even if the mic does not. No cloud STT.

State file: `%USERPROFILE%\.battlebuddy\memory.json` on Windows, `~/.battlebuddy/memory.json` on macOS/Linux. Not committed. Restart and `list` still shows it.

---

## What this is

A voice-first cognitive prosthetic for veterans with ADHD, PTSD, and TBI who play complex strategy and survival games. You say “remind me in 15 minutes to check food stores.” It confirms. It fires. It survives a restart. State lives on your disk.

This is a **Hermes Desktop skill pack** plus a standalone launch of the same modules so a stranger can run the loop without installing Hermes.

Jessica is not this app. Jessica stays the XO. Battle Buddy is a specialist tool.

**Hackyard Yard #1 — Escape Velocity.** Theme: no accounts.

## What this is not

- No sign-up. No login. No email.
- No Google account. No Steam API key. No SuperGrok OAuth required to use it.
- No Zo email-triage product. That is a different tool.
- No wellness coach. No moralizing.

## Hermes skill (product runtime)

1. Install [Hermes Desktop](https://hermes-agent.nousresearch.com/docs/getting-started/installation) (official installer).
2. Point Hermes at a **local** 2–3B (Ollama / LM Studio / llama.cpp). Empty API key. No provider signup.
3. Clone this repo. Install the skill:

```text
hermes skills install wyldephyre/battle-buddy/skills/battle-buddy
```

4. From the repo root, say or type: `Remind me in 1 minute to check food stores.`

Same modules as the standalone commands above. UI: `python -m battlebuddy ui`. One primary action: SUBMIT. SPEAK appears only if local STT exists. TTS is optional — if the box has no voice, FIRE still fills the window.

## System requirements

**Floor (reminder loop, typed + local TTS):** Windows 10/11, Python 3.10+, mic optional, 8 GB RAM.

**Recommended (Hermes + local 2–3B):** NVIDIA 8 GB VRAM (12 GB happier), 16 GB RAM. If the box is below that, skip the local LLM. The reminder loop must still work.

## Repo map (this slice)

```text
skills/battle-buddy/SKILL.md   Hermes skill: remind, list, snooze, clear
battlebuddy/memory/            local JSON store
battlebuddy/reminders/         schedule, fire, list, clear, snooze
battlebuddy/voice/             local TTS / STT, typed fallback
battlebuddy/game_detect/       local process scan. No Steam.
battlebuddy/ui/                high-contrast window
battlebuddy/__main__.py        typed CLI
docs/                          PRD, agent loop, kickoff commands
.cursor/rules/                 Cursor project rules
AGENTS.md                      Standing orders for every agent
```

## Agent loop

Captain Phyre runs three surfaces. Read `docs/DEV-LOOP.md` and `docs/KICKOFF-COMMANDS.md` before writing a line.

| Surface | Job |
|---|---|
| This Grok (project / Business) | Scope, theme police, language, demo plan |
| Grok Bot | Implementation orders, tight loops, ship checklist |
| Cursor | Files on disk. Apply diffs. Run the app |

One objective at a time.

## License

MIT. See `LICENSE`.

## Name

Working product name: Battle Buddy. Trademark check is parked until after the Yard.

---

We are not asking for a seat at their table. We built a revolution instead.

**Oorah.**
