# Ask Jessica via Hermes (Cap PC) — DO NOT MERGE guide

Thin Cap path on branch `jessica-hermes`. Hermes SuperGrok OAuth. **Not Zo.** Cap owns Jessica soul. Consumer offline / local Battle Buddy stays green without this.

## Survey (entrypoints)

| Surface | Path | Role |
|---|---|---|
| Local ASK | `battlebuddy/databank/search.py` + UI query box | Consumer offline wiki ASK |
| Optional env Grok | `battlebuddy/xai/loop.py` + `XAI_API_KEY` | Map/compile only; absent key is Yard |
| **Ask Jessica (this slice)** | `battlebuddy/jessica/ask.py` → `hermes chat --provider xai-oauth -q ...` | Cap-only Hermes SuperGrok OAuth |
| Hermes skill | `skills/ask-jessica/SKILL.md` | Cap installs beside battle-buddy |
| UI | unchanged | No Jessica chrome |

Smallest hook: parse `ask jessica …`, require Hermes + `xai-oauth` in Hermes `auth.json`, one-shot `hermes chat --provider xai-oauth -q`. No Zo. No secrets in repo.

## Windows / PC (Cap)

1. Install [Hermes Desktop](https://hermes-agent.nousresearch.com/docs/getting-started/installation) on the Windows box (App Installer / MSIX, or `iex (irm https://hermes-agent.nousresearch.com/install.ps1)`).
2. Sign in SuperGrok OAuth — Desktop SuperGrok card, or:

```text
hermes auth add xai-oauth
```

3. Confirm provider (no token dump):

```text
hermes doctor
```

Look for `xai-oauth` under Auth Providers. Auth file lives at `%LOCALAPPDATA%\hermes\auth.json` (or `%HERMES_HOME%\auth.json`). **Never commit it.**

4. Cap owns Jessica soul in Hermes (persona / profile). Not in this repo. Not Zo.

5. From the battle-buddy clone:

```text
python -m battlebuddy ask jessica what holds the line tonight
```

Or install the thin skill:

```text
hermes skills install wyldephyre/battle-buddy/skills/ask-jessica
```

6. If the OAuth client or Desktop SuperGrok card is missing from your Hermes build: **ask Cap**. Do not invent client IDs or paste secrets into git.

## Preserve consumer paths

- Remind / FIRE / hygiene / War Room / local ASK: unchanged with no Hermes and no key.
- UI still has no Jessica identity.
- Optional `XAI_API_KEY` path stays optional and separate.
- Yard acceptance still: no account, no required cloud.

## Refuse

Zo URLs, committed tokens, required OAuth for consumers, Jessica soul dumps into Battle Buddy UI.
