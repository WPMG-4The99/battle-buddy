# Battle Buddy

External memory for veterans in long game sessions.

Speak it once. It holds the line. No account. No cloud. No one else in your session.

**Hackyard Yard #1 — Escape Velocity.** Theme: no accounts.  
Repo opened 28 Aug 2026. Product code starts at kickoff (28 Aug 18:00 UTC).

For the forgotten 99%, we rise.

---

## What this is

A voice-first cognitive prosthetic for veterans with ADHD, PTSD, and TBI who play complex strategy and survival games. You say “remind me in 15 minutes to check food stores.” It confirms. It fires. It survives a restart. State lives on your disk.

This is a **Hermes Desktop skill pack** plus a standalone launch of the same modules so a stranger can run the loop without installing Hermes.

Jessica is not this app. Jessica stays the XO. Battle Buddy is a specialist tool.

## What this is not

- No sign-up. No login. No email.
- No Google account. No Steam API key. No SuperGrok OAuth required to use it.
- No Zo email-triage product. That is a different tool.
- No wellness coach. No moralizing.

## Yard rules we are honoring

- Theme: no sign-up, no login, no email **to use it**
- Any local model (target: 2–3B)
- Solo
- All **product code** written during the 48-hour window
- Public repo
- Demo video

No accounts. Product code is the reminder loop in this repo.

## How you run it

Two paths. Same reminder logic. Same on-disk memory. Python 3.10+. No signup.

### Path A — Hermes skill (product shape)

1. Install [Hermes Desktop](https://hermes-agent.nousresearch.com/docs/getting-started/installation) (official installer).
2. Point Hermes at a **local** 2–3B (Ollama / LM Studio / llama.cpp). Empty API key. No provider signup.
3. Clone this repo. Install the skill:

```text
hermes skills install wyldephyre/battle-buddy/skills/battle-buddy
```

4. From the repo root, say or type: `Remind me in 1 minute to check food stores.`

### Path B — Standalone (judge / no-Hermes proof)

```text
git clone https://github.com/wyldephyre/battle-buddy.git
cd battle-buddy
python -m battlebuddy remind me in 1 minute to check food stores
```

Stay in that window. It confirms immediately, then fires in 1 minute (visual banner; local TTS if the box has it).

High-contrast UI (Windows, from the clone folder):

```text
python -m battlebuddy ui
```

One primary action: HOLD THE LINE. Typed entry is prefilled. SPEAK appears only if local STT exists. TTS is optional — if the box has no voice, FIRE still fills the window.

After restart:

```text
python -m battlebuddy list
```

Windows (PowerShell or cmd), from the clone folder:

```text
python -m battlebuddy remind me in 1 minute to check food stores
```

venv is optional. `requirements.txt` is empty on purpose: stdlib only. No cloud STT. Typed fallback always works even if the mic does not.

State file: `%USERPROFILE%\.battlebuddy\memory.json` on Windows, `~/.battlebuddy/memory.json` on macOS/Linux. Not committed.

## System requirements

**Floor (reminder loop, typed + local TTS):** Windows 10/11, Python 3.10+, mic optional, 8 GB RAM.

**Recommended (Hermes + local 2–3B):** NVIDIA 8 GB VRAM (12 GB happier), 16 GB RAM. If the box is below that, skip the local LLM. The reminder loop must still work.

## Repo map (this slice)

```text
skills/battle-buddy/SKILL.md   Hermes skill for the same loop
battlebuddy/memory/            local JSON store
battlebuddy/reminders/         schedule, fire, list, cancel, snooze
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

One objective at a time. First objective after kickoff: persist a reminder and fire it with no account.

## License

MIT. See `LICENSE`.

## Name

Working product name: Battle Buddy. Trademark check is parked until after the Yard.

---

We are not asking for a seat at their table. We built a revolution instead.

**Oorah.**
