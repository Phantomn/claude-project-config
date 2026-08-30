---
name: using-superpowers
description: Use when starting any conversation - establishes how to find and use skills, requiring skill invocation before ANY response including clarifying questions
---

<SUBAGENT-STOP>
If you were dispatched as a subagent to execute a specific task, ignore this skill.
</SUBAGENT-STOP>

## The Rule

Check for a relevant skill before acting on a task, and invoke it when one applies.
If it turns out wrong for the situation, you don't have to use it.

Process skills set the approach, then implementation skills carry it out:

- "Let's build X" → `superpowers:brainstorming`, then implementation skills.
- "Fix this bug" → `superpowers:systematic-debugging`, then domain skills.

Announce "Using [skill] to [purpose]" and follow it. If it has a checklist, make a todo per item.

## Rationalizations

These thoughts mean you're talking yourself out of a skill that applies:
"just a simple question" · "need more context first" · "let me explore/check
files first" · "overkill here" · "I remember this skill" (skills evolve — re-read).

Questions and small actions are tasks too.

## Precedence

User instructions (CLAUDE.md, AGENTS.md, direct requests) > skills > default behavior.
Where a user rule and a skill conflict, the user rule wins — including rules about
scope, minimalism, and when to ask before acting.

## Platform Adaptation

If your harness appears here, read its reference file: Codex `references/codex-tools.md` ·
Pi `references/pi-tools.md` · Antigravity `references/antigravity-tools.md` ·
Hermes `references/hermes-tools.md`.
