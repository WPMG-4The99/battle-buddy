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

- Python 3.12. Stdlib only. `requirements.txt` has no packages. Do not pip-install for the reminder loop.
- Linux UI needs `python3-tk`. Linux TTS needs `espeak-ng`. Visual FIRE still works if TTS is missing.
- Tests: `python3 -m unittest discover -s tests`. A full-suite process can abort on exit with `Tcl_AsyncDelete` after Tk tests. Per-file runs exit clean: `python3 -m unittest tests.test_list_snooze_clear`.
- `tests.test_xai.SourceLawTest.test_hosts_stay_out_of_reason_and_tts` fails today because `battlebuddy/ui/app.py` reads `XAI_API_KEY`. That is product code, not a missing package.
- UI: `python3 -m battlebuddy ui` (needs a display). CLI: `python3 -m battlebuddy remind me in 1 minute to check food stores`.
- State is `~/.battlebuddy` or `BATTLEBUDDY_HOME`. Leave `XAI_API_KEY` and `STEAM_WEB_API_KEY` unset.
