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

This README and the docs under `docs/` are pre-kickoff briefing. Implementation files land after 18:00 UTC 28 Aug 2026.

## After kickoff — how you run it

Two paths. Same reminder logic. Same on-disk memory.

### Path A — Hermes skill (product shape)

1. Install [Hermes Desktop](https://hermes-agent.nousresearch.com/docs/getting-started/installation) (official installer).
2. Point Hermes at a **local** 2–3B (Ollama / LM Studio / llama.cpp). Empty API key. No provider signup.
3. Install this skill from the repo after the first product commit exists:

```text
hermes skills install wyldephyre/battle-buddy/skills/battle-buddy
```

4. New Hermes session. Say or type: `Remind me in 15 minutes to check food stores.`

### Path B — Standalone (judge / no-Hermes proof)

Commands will live here after the first product commit. Planned shape:

```text
git clone https://github.com/wyldephyre/battle-buddy.git
cd battle-buddy
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m battlebuddy
```

Typed fallback always works even if the mic does not.

## System requirements

**Floor (reminder loop, typed + local TTS):** Windows 10/11, Python 3.10+, mic optional, 8 GB RAM.

**Recommended (Hermes + local 2–3B):** NVIDIA 8 GB VRAM (12 GB happier), 16 GB RAM. If the box is below that, skip the local LLM. The reminder loop must still work.

## Repo map (target after kickoff)

```text
skills/battle-buddy/     Hermes skill (SKILL.md + scripts)
battlebuddy/             Shared modules: voice, memory, reminders, ui, config
docs/                    PRD, agent loop, kickoff commands
.cursor/rules/           Cursor project rules
AGENTS.md                Standing orders for every agent
```

Nothing in `battlebuddy/` or `skills/` is product code until kickoff.

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
