# MVP PRD — Battle Buddy

**Authority:** Business Grok master prompt 20 Aug 2026 + Yard #1 official card 28 Aug 2026  
**Repo:** https://github.com/wyldephyre/battle-buddy  
**Owner:** Captain Phyre — solo  
**Status:** Pre-kickoff briefing. Product code starts 2026-08-28 18:00 UTC.

## Purpose

Voice-activated cognitive prosthetic for veterans with ADHD, PTSD, and TBI in long strategy and survival sessions. External memory so a critical check is not lost mid-session.

Pitch: Speak it once. It holds the line. No account. No cloud. No one else in your session.

## Two clocks, one product

| Layer | What | Constraint |
|---|---|---|
| Product v1 | Hermes Desktop, local-first, 2–3B class OK | Locked 20 Aug |
| Yard Release 0 | Same modules, zero accounts, written in 48 hours | Official Yard card |
| Later premium | Game packages, optional Zo heavy tier | Parked. Do not block. |

Hermes is the product runtime. SuperGrok OAuth is allowed on Captain’s daily box and forbidden as a required path for the Yard demo. Standalone launch is the judge safety net.

## Locked decisions

1. No sign-up, no login, no email to use it.
2. All product code written during the 48-hour window. Do not copy `veteran-gaming-assistant` source.
3. State lives on disk (JSON or SQLite).
4. Voice: local TTS. Local STT if the box can carry it. Typed fallback always present.
5. Game detect, if any: local process scan. No Steam Web API.
6. ADHD surface: large targets, low noise, high contrast, one primary action.
7. Jessica stays XO. This app is a specialist rifle.
8. No moralizing.

## Must ship by Sunday 18:00 UTC

- Clone and run with no signup
- “Remind me in 15 minutes to check food stores” by voice or type
- Immediate confirmation
- Fires on time with audio or visual while minimized
- List, cancel, snooze
- Survives restart
- Hermes `SKILL.md` for the same loop
- README run steps above the fold
- Demo video 60–90s + screenshot

## Must not ship

Zo / Gmail / Calendar triage. Required OAuth. Steam keys. Cloud sync. Game knowledge packs. Wake-word / overlay / mobile. Jessica identity in the UI.

## Commands

| Said or typed | System does |
|---|---|
| Remind me in 15 minutes to check food stores | Confirm. Schedule. Persist. |
| In 20 minutes remind me to scout north | Same |
| List my reminders | Speak count. Show list. |
| Snooze food stores 5 minutes | Shift due. Confirm. |
| Clear reminder about mines | Delete match. Confirm. |
| Clear all | Confirm once. Wipe. |

Resource / event lines may be stored as notes that do not auto-fire.

## Acceptance

A stranger clones the repo, runs it, sets a 1-minute reminder with no login, sees or hears it fire, restarts, and the reminder is still there. README says “no accounts” above the fold. No Steam key field. No required cloud model.

## Battle rhythm

- Fri 13:00–18:00 CDT — memory + time reminders + skill stub
- Fri night–Sat 13:00 — TTS / STT or typed fallback + high-contrast UI
- Sat 13:00–20:00 — list / snooze / clear + README
- Sun 08:00–13:00 CDT — demo, screenshot, submit. Feature freeze 11:00 CDT

## Language

Always: Fire, PHYRE, flame, ash, wildfire, Phoenix, the forgotten 99%, Active Stoicism, Oorah.  
Never in product: Prometheus, Satan/Satanic, worship / obedience / submission, Hooah, wellness copy.

## Phase 2 slice 1 — War Room (Scribe)

Standing state for the **home roster only** (Star Citizen, Bellwright, Corsair Cove, ASKA, Clanfolk). Lives in `catalog.sqlite` under `BATTLEBUDDY_HOME`. Reminders stay in `memory.json`. No accounts. Not Jessica. Not Coach. Not Intel. Walk-in titles are refused; this slice does not add titles to the roster.

Commands: `remember for <Game>:`, `where was I`, `war room`, `correct`. Typed / CLI, offline.

## Phase 2 slice 2 — War Room on the existing UI

Same window. Left strip under the reminder list: roster chips, HOLD / WHERE, Hold this. Calls `run_line`. No Correct button. No walk-in game box. Reminder SUBMIT stays reminders.

## Phase 2 slice 3 — Coach (one move)

Deterministic next brick from the selected War Room row only (trap, else place, else decision, else patch). No wiki. No model. No account. CLI: `next` / `coach` / `what now`. UI: gold NEXT beside WHERE. HOLD stays primary.

## Phase 2 prove-out — session help (Step 1)

`BATTLEBUDDY_HOME/session.json` holds `{ "tier": "gentle" }`. Default Gentle. Mid-session `tier handhold` / `tier gentle` / `tier socratic` (and spoken aliases) changes the next NEXT line. Template Coach only. Empty key is correct. Harvest, Grok, vision, and Steam API wait.

## Phase 2 prove-out — harvest locate (Step 2)

Local Steam files plus `%LOCALAPPDATA%\CorsairCove\Saved` for AppID `1368140`. CLI: `harvest` / `locate corsair`. Snapshot: `harvest.json`. Paths only. No Web API. No inject. No save-editor. Wiki and Grok wait.

## Phase 2 prove-out — wiki seed (Step 3)

Corsair Cove hub `https://wiki.hoodedhorse.com/Corsair_Cove/`. Same-origin child pages only (cap 3). No DuckDuckGo happy path. No paste happy path. SCAN / `seed corsair` public GET. Grok waits.

## Phase 2 prove-out — Coach vs Grok (Step 4)

`coach(game, tier, harvest, war_room)` wraps the template. Empty `XAI_API_KEY`: template plus `Grok is dark. Scribe still holds.` (empty row stays `Hold a place first.`). Key set: grok-4.6 via existing loop, caps, fields only. Template still works if the call fails. Vision waits.
