# Battle Buddy

Speak it once. It holds the line.

**No accounts.** No sign-up. No login. No email. No Steam key. No cloud. No Google.

External memory for veterans in long strategy and survival sessions. You speak or type a check. Battle Buddy holds the flame on your disk. When the clock hits, it FIREs. For the forgotten 99%. Active Stoicism. PHYRE.

## What it does

Four beats. No cloud. Nothing invented.

1. **Remind.** Voice or typed reminder that survives restart. State lives on disk under `%USERPROFILE%\.battlebuddy`. FIRE at due time. Local TTS if the box has it.
2. **SCAN.** Live-captures the running game from local processes (Steam/Epic folder or Unreal shipping). No Steam API.
3. **Wiki seed.** First sight of a new empty-folder game fetches the top 3 public wiki pages (DuckDuckGo HTML `{game} wiki`, public GET, no account).
4. **ASK.** Answers from those local pages. Compile a real how-to or miss. Nothing invented.

## The surface

High-contrast veteran UI: black, gold, cream, scarlet **SUBMIT** / **FIRE**. ADHD-friendly large targets. One primary action. Low noise.

## How to run

**Windows:** double-click `BattleBuddy-Setup.exe`. The UI opens. No login. pip is not required to run the exe.

**From a clone:**

```text
python -m battlebuddy ui
```

One reminder from the CLI (no account):

```text
python -m battlebuddy remind me in 1 minute to check food stores
```

Stay in that window. It confirms. It FIREs in one minute. Restart and `python -m battlebuddy list` still shows it.

## Yard

**Hackyard Yard #1.** Theme: no accounts. MIT.

We are not asking for a seat at their table. We built a revolution instead.

**Oorah.**

---

## Appendix

Clone path if you want source instead of the exe. Python 3.10+. No signup.

```text
git clone https://github.com/wyldephyre/battle-buddy.git
cd battle-buddy
python -m battlebuddy ui
```

Same on-disk memory for list / snooze / clear:

```text
python -m battlebuddy list
python -m battlebuddy snooze food stores 5 minutes
python -m battlebuddy clear reminder about mines
python -m battlebuddy clear all
```

macOS / Linux: same commands. Typed fallback always works. No cloud STT.

State: `%USERPROFILE%\.battlebuddy` on Windows, `~/.battlebuddy` on macOS/Linux. Not committed.

### Windows build

On a Windows box: `.\scripts\build-windows.ps1` (PyInstaller is build-only). Do not build the exe on Linux. pip is not required to run the shipped exe.

### Hermes (optional)

Same reminder loop as a [Hermes Desktop](https://hermes-agent.nousresearch.com/docs/getting-started/installation) skill. Local 2–3B. Empty API key.

```text
hermes skills install wyldephyre/battle-buddy/skills/battle-buddy
```

Jessica is not this app.

### Repo map

```text
skills/battle-buddy/SKILL.md   Hermes skill
battlebuddy/memory/            local JSON
battlebuddy/reminders/         schedule, fire, list, clear, snooze
battlebuddy/voice/             local TTS / STT, typed fallback
battlebuddy/game_detect/       local process SCAN. No Steam API.
battlebuddy/databank/          public wiki GET, local ASK
battlebuddy/ui/                high-contrast window
BattleBuddy.spec               PyInstaller onedir
installer/BattleBuddy.iss      per-user Inno Setup (no admin)
scripts/build-windows.ps1      Windows exe + setup
```

MIT. See `LICENSE`. Trademark check parked.
