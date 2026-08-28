# Development loop — Grok + Grok Bot + Cursor

Captain runs three surfaces. They do not all write code. They do not all set scope.

## Surfaces

### 1. Project Grok (this thread / SuperGrok Heavy)

**Job:** Command intent, theme police, language, demo plan, “are we offsides.”

**Does:** PRD, kickoff orders, cut scope, write the pitch line, check the Sunday ship list.

**Does not:** Dump 400 lines of Python unasked. Does not replace Cursor.

Talk to this Grok when the question is *what* or *whether*. Not when the question is *paste this file*.

### 2. Grok Bot

**Job:** Implementation officer. Tight orders. Checklists. “Do this next.”

Yard #1 runs on Grok Bot as the working implementer beside Cursor — not as an X Chat API project bot, not as `@WyldeJessica`.

**How to use it at 13:00**

1. Open Grok Bot.
2. Paste the block in `docs/KICKOFF-COMMANDS.md` (Grok Bot card).
3. Give **one** objective. Wait for a file list or a patch.
4. You (or Cursor) apply it in the local clone and `git push`.

If Grok Bot can write the GitHub repo directly, still review the diff before you treat it as shipped. Captain owns the push.

### 3. Cursor

**Job:** Hands on the files. This is where the repo lives on disk.

**Setup (do this before 13:00)**

```text
git clone https://github.com/wyldephyre/battle-buddy.git
cd battle-buddy
```

Open that folder as the Cursor workspace.  
`.cursor/rules/00-battle-buddy.mdc` and `AGENTS.md` load as project rules. Do not add a second competing ruleset.

**At 13:00** paste the Cursor card from `docs/KICKOFF-COMMANDS.md` into Composer / Agent.

## Traffic pattern

```text
Captain
  ├─ Grok (this thread)  →  decide / cut / bless
  ├─ Grok Bot            →  next concrete slice
  └─ Cursor              →  write / run / commit
```

Never give all three the same “build everything” prompt at once. That is how ADHD sessions die.

## Commit rhythm

Small commits. Present tense.

```text
git add -A
git commit -m "Add local JSON reminder store"
git push origin main
```

Do not commit model weights, `.venv`, or `memory.json`.

## Credit / cognitive load

Routine work stays on SuperGrok Heavy / Grok Bot / Cursor. Do not burn reserved xAI API credits. One question to Captain at a time.
