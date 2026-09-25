---
name: team-assemble
description: Analyze tasks and dynamically assemble expert agent teams using Claude Code's agent teams. Scouts your codebase, designs optimal agents, and executes with validation.
allowed-tools: [Agent, Bash, Read, Write, Edit, Glob, Grep, AskUserQuestion, TaskCreate, TaskUpdate, TaskList, TaskGet, SendMessage]
version: 1.0.0
---

# Team Assemble

Analyze a task, dynamically design the right expert agents, and orchestrate them as a team using Claude Code's agent teams feature.

## Prerequisites

Agent teams must be enabled via `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`. See
`references/enable-agent-teams.md`.

> **No setup step.** Since Claude Code **2.1.178** the session has **one implicit team** and the
> `TeamCreate` / `TeamDelete` tools are **removed**. Spawn teammates directly with the `Agent`
> tool's `name` parameter. (Verified 2026-08-17 on 2.1.233: `changelog.md` §2.1.178 +
> the live `Agent` schema — `team_name` is *"Deprecated; ignored"*.)

## When to Use

- Complex tasks that decompose into 2+ independent subtasks
- Work where role separation is clear (e.g., research + implementation + validation)
- Tasks that benefit from parallel execution

**Do NOT use for:** single-file edits, simple questions, purely sequential work

**SPEC/PLAN audits → `superpowers:spec-audit`.** It owns a fixed 3-auditor team. If invoked together
with `/spec-audit`, follow spec-audit's execution model (skip Phase 1–3 confirmations here, and do
not read this skill as "spawn an implementation team after the audit passes").

---

## Core Principles

- **Model 3-tier** — choose by role purpose (details: `references/agents.md`)
  - `opus` — strategy/judgment (scouts, complex execution)
  - `sonnet` — standard execution/validation (worker, qa, support)
  - `haiku` — exploration/writing (researcher, editor)
- **No fixed catalog** — agents are designed dynamically per task
- **Example bank** — `references/agents.md` provides reference examples (not mandatory)

---

## Workflow

```
Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6
Task       Codebase   Integrate  Execute   Validate   Complete
Analysis   Scouts     & Confirm                       & Cleanup
                                           ↕ FAIL → support fix (max 3x)
```

---

## Phase 1: Task Analysis

Analyze the user's request and identify relevant areas of the codebase:

1. Examine project structure, CLAUDE.md files, and README files
2. Identify which parts of the codebase are relevant to the task
3. Determine if codebase scouting (Phase 2) would help, or if the task is straightforward enough to skip to Phase 3

**Get user approval via AskUserQuestion:**

```
I've analyzed your task and identified the following areas of interest:

- [x] src/auth/ — Authentication module (needs refactoring)
- [x] tests/auth/ — Corresponding tests
- [ ] src/api/ — Not directly affected

I'll scout these areas to design an optimal team.
```

Options: "Looks good, proceed" / "I'd like to adjust the scope"

For straightforward tasks that don't need codebase exploration, skip Phase 2 and go directly to Phase 3 — design the team yourself using `references/agents.md` as a guide.

---

## Phase 2: Codebase Scouts (Parallel)

Launch **scout agents** in parallel to explore relevant areas of the codebase.

### Scout Configuration

- **Model**: opus
- **subagent_type**: `general-purpose` (constrained to read-only via prompt)
- **Parallel**: launch multiple scouts simultaneously when exploring different areas

### Scout Mission

Each scout reads the relevant codebase area and proposes agents for the task:

1. Read key files (CLAUDE.md, README.md, source code, configs)
2. Analyze the intersection between the task and the codebase area
3. Propose agents needed (name, role, tasks, reference files)
4. Reference `references/agents.md` for examples, but freely design new agents

> Prompt template: `references/project-templates.md` § Codebase Scout

### Scout Output Format

```
## Scout Report: {area}

### Current State
- {file structure summary}
- {relevance to the task}

### Proposed Agents
| Agent | Role | Tasks | Reference Files |
|-------|------|-------|-----------------|
| {name} | {role} | {task} | {files} |

### Notes
- {area-specific constraints or patterns to follow}
```

---

## Phase 3: Integrate & Confirm Team

Merge scout reports into a final team composition:

1. **Deduplicate** — merge similar agent proposals from different scouts
2. **Gap analysis** — check for missing roles
3. **Add qa + support** — validation/fix agents are always included
4. **Dependency graph** — design execution order between agents
5. **Define acceptance criteria** — measurable criteria for Phase 5 validation

### Team Proposal

**Get final approval via AskUserQuestion:**

```
Proposed team: {team-name}

| # | Agent | Role | Tasks | Dependencies |
|---|-------|------|-------|--------------|
| 1 | architect | System design | Design new auth flow | - |
| 2 | implementer | Code changes | Implement the design | #1 |
| 3 | test-writer | Test coverage | Write tests for changes | #2 |
| 4 | qa | Validation | PASS/FAIL against acceptance criteria | #2, #3 |

Acceptance criteria:
- [ ] AC-1: {measurable criterion}
- [ ] AC-2: {measurable criterion}
```

Options: "Looks good, execute" / "I'd like to adjust roles"

If the user selects "adjust roles", ask what specifically to change. After 2+ revision requests, switch to free-text input.

---

## Phase 4: Execution

### Distribute Tasks

No team creation step — the session already has one implicit team.

Create TaskCreate entries for each agent, then set dependencies with TaskUpdate.

> `TaskCreate`/`TaskUpdate`/`TaskList` need `CLAUDE_CODE_ENABLE_TODO_TOOLS=1` on Opus 4.8 /
> Sonnet 5 / Fable 5 / Mythos 5 and newer — they are not provided by default on those models
> (`changelog.md`). Without it, track the plan in your response text instead.

### Launch Teammates

- **name**: required to address the agent later via `SendMessage({to: name})`
- **Model**: apply 3-tier based on role (`references/agents.md`)
- **subagent_type**: `"general-purpose"`
- **Parallel**: launch agents without blockedBy dependencies in a single message
- **Sequential**: inject preceding agent results into the next agent's prompt

> Do **not** pass `mode:` or `team_name:` — both are accepted-but-ignored. Teammates inherit the
> parent session's permission mode.

### Teammate Prompt Requirements

1. **Context** — project background and how this task fits the whole
2. **Specific goal** — exactly what to achieve
3. **Reference files** — file paths identified by scouts
4. **Constraints** — what NOT to do, scope limits
5. **Output format** — expected deliverable format
6. **Team info** — the agent's own `name` (so it can be addressed) + task ID

> Detailed prompt structure: `references/project-templates.md`

---

## Phase 5: Validation

qa (sonnet) evaluates each **acceptance criterion** from Phase 3.

### Validation Process

```
Agent(name: "qa", model: "sonnet", prompt: """
## Acceptance Criteria
- [ ] AC-1: {criterion}

## Validation Target
{Phase 4 execution results}

Evaluate each criterion with evidence-based PASS/FAIL judgment.
No PASS without evidence.

## Output Format
| # | Criterion | Verdict | Evidence |
Overall: PASS / FAIL
Include fix suggestions for any FAIL items.
""")
```

### FAIL Handling

support (sonnet) fixes only FAIL items → qa re-validates:

- **Max 3 rounds** of verify/fix loop
- If the same error repeats 3 times, stop immediately
- After 3 rounds, halt the pipeline and report to user:

```
## Validation Failed — Manual Intervention Needed

### Repeated Failures
- AC-{N}: {criterion} — {failure reason}

### Attempted Fixes
1. {attempt 1}  2. {attempt 2}  3. {attempt 3}

### Recommended Action
{what needs to be done manually}
```

---

## Phase 6: Complete & Cleanup

### Result Report

```
## Team Results: {team-name}

### Acceptance Criteria
- [x] AC-1: {criterion} — PASS

### Per-Agent Results
- {agent}: {result summary}

### Deliverables
- {file paths or outputs}

### Validation History
- Validated {N} times, {M} fixes applied
```

### Team Cleanup

**Nothing to do.** There is no team object to delete, and the `SendMessage` contract says
*"Don't originate `shutdown_request` unless asked"* — agents finish on their own.

If you must reach a teammate again, address it **by name** (a send resumes it from its
transcript). Correct shape — `to` / `message`, not `recipient` / `content`:

```
SendMessage(to: "{name}", summary: "follow-up", message: "…")
```

---

## Common Mistakes

| Mistake | Correct Approach |
|---------|------------------|
| Creating team without user approval | Get AskUserQuestion approval in Phase 1 + Phase 3 |
| Executing without acceptance criteria | Always define criteria in Phase 3 |
| Running scouts for simple tasks | Skip Phase 2 for straightforward work |
| Skipping validation | Always run Phase 5 after execution |
| Ignoring model tiers | Use opus/sonnet/haiku based on role purpose |
| Only picking from fixed catalog | Scouts design freely; examples are reference only |
| Calling `TeamCreate` / `TeamDelete` | Removed in 2.1.178 — one implicit team, spawn with `Agent(name:)` |
| Originating `shutdown_request` | The tool forbids it unless asked; agents finish on their own |
| Spawning a teammate without `name` | Then you cannot `SendMessage` to it — always name teammates |
| Infinite FAIL loop | Max 3 verify/fix rounds, then report to user |

## Additional Resources

- **`references/agents.md`** — Agent example bank with model tier guide
- **`references/project-templates.md`** — Scout + execution + QA prompt templates
- **`references/examples.md`** — Worked examples: feature dev, refactoring, research
- **`references/enable-agent-teams.md`** — How to enable agent teams in Claude Code

