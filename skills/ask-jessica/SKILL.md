---
name: ask-jessica
description: Cap-only Ask Jessica via Hermes SuperGrok OAuth (xai-oauth). Not Zo. Cap owns soul.
version: 0.1.0
author: Captain Phyre (wyldephyre)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [jessica, hermes, supergrok, oauth, captain]
    related_skills: [battle-buddy]
    requires_toolsets: [terminal]
---

# Ask Jessica (Hermes SuperGrok OAuth)

Thin Cap path. Hermes already holds SuperGrok OAuth (`xai-oauth`). Cap owns Jessica soul outside this repo. Not Zo. Consumer Battle Buddy offline / local ASK stays untouched.

## When to Use

- Captain says or types **Ask Jessica** / `ask jessica <question>`
- Hermes on this box is signed into SuperGrok OAuth (`hermes auth add xai-oauth` or Desktop SuperGrok card)
- Cap wants XO answers through Hermes, not through Zo and not through a committed API key

Do not use for: Yard demo consumers, required OAuth in Battle Buddy UI, Zo routes, Steam keys, or inventing Jessica soul text.

## Prerequisites

- Hermes Desktop or CLI on PATH (Windows/PC Cap box)
- SuperGrok OAuth ready: `hermes auth add xai-oauth` (or Desktop OAuth card)
- Cap's Jessica soul / persona already configured in Hermes by Cap — not shipped here
- If the OAuth client or Desktop SuperGrok card is missing from your Hermes build: **ask Cap**. Do not invent client secrets.

## How to Run

Prefer the Battle Buddy thin hook (same modules, no Zo):

```text
terminal(command="python -m battlebuddy ask jessica what holds the line tonight", timeout=180)
```

Or one-shot Hermes on Cap's OAuth provider (soul stays Cap's Hermes profile):

```text
terminal(command="hermes chat --provider xai-oauth -q \"what holds the line tonight\"", timeout=180)
```

Windows/PC notes: Hermes data under `%LOCALAPPDATA%\hermes\` (`auth.json` holds OAuth — never commit it). Battle Buddy consumer state stays under `%USERPROFILE%\.battlebuddy`.

## Procedure

1. Confirm this is Cap Ask Jessica, not the consumer reminder loop. Completion: offline remind / local ASK still work with no Hermes.
2. If Hermes or `xai-oauth` is missing, stop and tell Cap to install Hermes Desktop and run `hermes auth add xai-oauth` (or use the Desktop card). If the OAuth client is absent from the build, ask Cap. Completion: no invented secrets, no Zo fallback.
3. Run the thin hook or `hermes chat --provider xai-oauth -q "..."`. Completion: answer returned through Hermes SuperGrok OAuth.
4. Do not paste soul doctrine into Battle Buddy UI. Cap owns soul in Hermes. Completion: UI still has no Jessica identity chrome.

## Pitfalls

- Empty `XAI_API_KEY` remains correct for Yard / offline Battle Buddy.
- Do not route Ask Jessica to Zo.
- Do not commit `auth.json`, tokens, or client secrets.
- Consumer ASK (saved wiki pages) is a different path. Leave it alone.

Oorah.
