# AGENTS.md — Battle Buddy

Load this file at the start of every Cursor, Grok Bot, or Grok session on this repo.

**Repo:** https://github.com/wyldephyre/battle-buddy  
**Owner:** Captain Phyre (solo). Marlando is not on this project.  
**Event:** Hackyard Yard #1. Kickoff 2026-08-28 18:00 UTC. Ship 2026-08-30 18:00 UTC.

## Who you are talking to

Captain Phyre. Owner's personal medical details are private and kept out of the repo. One task at a time. No walls of text. Micro-steps. Kind not nice.

## Mission filter

Voice-first external memory for veterans in long strategy / survival sessions. Local. No accounts. If a suggestion needs a login, a cloud key, or a Steam API field, refuse it.

## Locked rules

1. No sign-up, no login, no email to use the product.
2. Product code starts at kickoff. Do not copy `wyldephyre/veteran-gaming-assistant` source into this repo.
3. Hermes Desktop is the product runtime. Local 2–3B. Empty API key.
4. Standalone launch of the same modules is required so a judge without Hermes can still run the reminder loop.
5. Jessica is not this app. Do not put XO identity in the UI.
6. No moralizing. No wellness copy. No Prometheus. No Hooah. Oorah only.
7. Scope is a weapon. First green loop beats a cathedral.

## Module map (write these after kickoff)

- `skills/battle-buddy/` — Hermes skill
- `battlebuddy/voice/` — STT / TTS / confirm
- `battlebuddy/memory/` — local JSON or SQLite
- `battlebuddy/reminders/` — schedule, fire, list, cancel, snooze
- `battlebuddy/game_detect/` — local process scan only
- `battlebuddy/ui/` — large targets, low noise, high contrast
- `battlebuddy/config/` — no account fields

## First objective after kickoff

Persist a time reminder and fire it with no account. Then the Hermes `SKILL.md`. Then UI. Then README run commands. Demo video last.

## Language

Always: Fire, PHYRE, flame, ash, wildfire, Phoenix, the forgotten 99%, Active Stoicism, Oorah.  
Never in product or README: Satan/Satanic, worship/obedience/submission, Hooah, corporate wellness.

## North star

We are not asking for a seat at their table. We built a revolution instead. 
For the forgotten 99%, we rise.

## Cursor Cloud specific instructions

Stdlib only. Python 3.10+. No pip. No venv. No account and no API key.

Linux UI and Tk tests need `python3-tk`. Local TTS needs `espeak-ng`. The Cloud Agent install command installs both. The typed CLI works without them.

```text
python3 -m battlebuddy --no-wait remind me in 1 minute to check food stores
python3 -m battlebuddy list
python3 -m battlebuddy ui
python3 -m unittest discover -s tests
```

State is `~/.battlebuddy` or `BATTLEBUDDY_HOME`. Do not commit it.

`python3 -m unittest discover -s tests` can abort the interpreter at the end on Linux (`Tcl_AsyncDelete`) after Tk windows from UI tests. Run the modules if that happens. `test_xai.SourceLawTest.test_hosts_stay_out_of_reason_and_tts` fails because `battlebuddy/ui/app.py` reads `XAI_API_KEY`. That is product code, not a missing package.
