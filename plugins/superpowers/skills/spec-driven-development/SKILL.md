---
name: spec-driven-development
description: "구조화 spec을 먼저 쓰고 gated 워크플로우로 구현하는 단일 정본. SPECIFY→PLAN→TASKS→IMPLEMENT. PLAN·구현은 superpowers 스킬에 위임하고 spec 생명주기(delta 병합·validate)를 흡수한다. spec 기반 개발, 다파일 변경, 아키텍처 결정, 30분+ 작업 시 사용."
---

# Spec-Driven Development

> **이 스킬이 spec/plan 워크플로우의 단일 정본이다.** spec 작성·생명주기는 여기서 소유하고,
> plan 작성과 구현은 superpowers 스킬에 위임한다. (이전 분산됐던 spec 워크플로우 3계보를
> 2026-09-20 여기로 수렴 — 설계·근거는 `CONSOLIDATION-DESIGN.md`.)

## Overview

Write a structured specification before writing any code. The spec is the shared source of truth between you and the human engineer — it defines what we're building, why, and how we'll know it's done. Code without a spec is guessing.

## When to Use

- Starting a new project or feature
- Requirements are ambiguous or incomplete
- The change touches multiple files or modules
- You're about to make an architectural decision
- The task would take more than 30 minutes to implement

**When NOT to use:** Single-line fixes, typo corrections, or changes where requirements are unambiguous and self-contained.

## 라우팅 & 한계 (진입점 규율)

이 스킬이 상위 진입점이고 `superpowers:writing-plans`·`subagent-driven-development` 등은 하위 실행엔진이다. 다만 superpowers 스킬도 model-invoked 자동발견되므로 **직접진입을 완전히 막을 수는 없다(알려진 한계)**. 그럴 때 규율:

- spec 없이 `writing-plans`부터 진입했다면 → **SPECIFY로 회귀**해 최소 spec(수용조건+경계)을 먼저 세운다.
- superpowers는 재작성/복제하지 않고 **호출로 위임**한다(marketplace fork divergence 회피).

## The Gated Workflow

Spec-driven development has four phases. Do not advance to the next phase until the current one is validated.

```
SPECIFY ──→ PLAN ──→ TASKS ──→ IMPLEMENT
   │          │        │          │
   ▼          ▼        ▼          ▼
 Human      Human    Human      Human
 reviews    reviews  reviews    reviews
```

### Phase 1: Specify

Start with a high-level vision. Ask the human clarifying questions until requirements are concrete.

**Surface assumptions immediately.** Before writing any spec content, list what you're assuming:

```
ASSUMPTIONS I'M MAKING:
1. This is a web application (not native mobile)
2. Authentication uses session-based cookies (not JWT)
3. The database is PostgreSQL (based on existing Prisma schema)
4. We're targeting modern browsers only (no IE11)
→ Correct me now or I'll proceed with these.
```

Don't silently fill in ambiguous requirements. The spec's entire purpose is to surface misunderstandings *before* code gets written — assumptions are the most dangerous form of misunderstanding.

**Write a spec document covering these six core areas:**

1. **Objective** — What are we building and why? Who is the user? What does success look like?
2. **Commands** — Full executable commands with flags, not just tool names (`npm test -- --coverage`, not "run tests").
3. **Project Structure** — Where source code lives, where tests go, where docs belong.
4. **Code Style** — One real code snippet showing your style beats three paragraphs describing it.
5. **Testing Strategy** — Framework, where tests live, coverage expectations, which test levels for which concerns.
6. **Boundaries** — Three-tier: **Always do** (run tests before commits, validate inputs) / **Ask first** (schema changes, new dependencies, CI config) / **Never do** (commit secrets, edit vendor dirs, remove failing tests without approval).

**Spec template:**

```markdown
# Spec: [Project/Feature Name]

## Objective
[What we're building and why. User stories or acceptance criteria.]

## Tech Stack
[Framework, language, key dependencies with versions]

## Commands
[Build, test, lint, dev — full commands]

## Project Structure
[Directory layout with descriptions]

## Code Style
[Example snippet + key conventions]

## Testing Strategy
[Framework, test locations, coverage requirements, test levels]

## Boundaries
- Always: [...]
- Ask first: [...]
- Never: [...]

## Success Criteria
[How we'll know this is done — specific, testable conditions]

## Open Questions
[Anything unresolved that needs human input]
```

**Reframe instructions as success criteria.** When receiving vague requirements, translate them into concrete, testable conditions:

```
REQUIREMENT: "Make the dashboard faster"

REFRAMED SUCCESS CRITERIA:
- Dashboard LCP < 2.5s on 4G connection
- Initial data load completes in < 500ms
- No layout shift during load (CLS < 0.1)
→ Are these the right targets?
```

This lets you loop, retry, and problem-solve toward a clear goal rather than guessing what "faster" means.

**A spec is a change unit.** Each spec (or spec revision) is the unit of work that flows through PLAN→IMPLEMENT and back into the living spec set — treat it as one reviewable, mergeable change, not a throwaway note.

### Phase 2: Plan

With the validated spec, produce a technical implementation plan by **delegating to `superpowers:writing-plans`** — do not hand-roll a plan format here. That skill turns the spec into bite-sized, testable tasks with exact files, interfaces, and TDD steps. The spec travels with the plan (writing-plans reads both).

**Revising an existing spec set (양방향 재조정).** When a change touches specs that already exist, don't just append. Reconcile in both directions:

- **Spec → plan:** every changed requirement maps to a task; list any requirement with no task as a gap.
- **Plan → spec:** every task traces back to a requirement; a task with no home means the spec is missing something — add it to the spec first.
- Re-check the *whole* affected spec set, not only the section you touched: a new requirement can contradict or duplicate an existing one. Removed requirements must be reflected, not left dangling.

### Phase 3: Tasks

Task decomposition is part of `superpowers:writing-plans` (bite-sized steps, acceptance criteria, verification per task, dependency ordering, ≤~5 files per task). Review the generated tasks against the spec before implementing.

### Phase 4: Implement

Execute the plan by **delegating to `superpowers:subagent-driven-development`** (recommended — fresh subagent per task + review) or `superpowers:executing-plans` (inline batch). Cross-cutting skills apply throughout: `test-driven-development`, `using-git-worktrees`, and `requesting-code-review`/`receiving-code-review` for the reviews.

## Keeping the Spec Alive (생명주기)

The spec is a living document, not a one-time artifact. This section owns the spec lifecycle that used to live in an external CLI — no external tool required.

- **Update when decisions change** — discover the data model must change? Update the spec first, then implement.
- **Update when scope changes** — features added or cut are reflected in the spec.
- **Commit the spec** — it belongs in version control alongside the code.
- **Reference the spec in PRs** — link the spec section each PR implements.

**Merging a spec revision into the canonical spec set (agent-driven).** Read the revision (its ADDED/MODIFIED/REMOVED/RENAMED requirements) and directly edit the main spec files to apply the changes — intelligent merging (e.g. add a scenario without recopying the whole requirement), not a mechanical overwrite. Archiving a completed revision is a plain file move (`mkdir` the archive path, `mv` the change dir).

**Validate before merging (결정론 가드).** After editing main specs, run the bundled validator to catch a revision that drops a scenario the main spec still has, or a malformed requirement block:

```bash
python scripts/validate_spec.py <change-delta.md> --main <main-spec.md>
```

It exits non-zero on ERROR-level violations (missing scenario, dropped scenario, unpaired RENAME, cross-section conflict, …). It is a thin, dependency-free port; the delta-spec rules and their upstream source are documented in `references/validator-port-spec.md`.

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "This is simple, I don't need a spec" | Simple tasks don't need *long* specs, but still need acceptance criteria. A two-line spec is fine. |
| "I'll write the spec after I code it" | That's documentation, not specification. The spec's value is forcing clarity *before* code. |
| "The spec will slow us down" | A 15-minute spec prevents hours of rework. |
| "Requirements will change anyway" | That's why the spec is a living document. An outdated spec still beats no spec. |
| "The user knows what they want" | Even clear requests have implicit assumptions. The spec surfaces them. |

## Red Flags

- Starting to write code without any written requirements
- Asking "should I just start building?" before clarifying what "done" means
- Implementing features not mentioned in any spec or task list
- Making architectural decisions without documenting them
- Skipping the spec because "it's obvious what to build"

## Verification

Before proceeding to implementation, confirm:

- [ ] The spec covers all six core areas
- [ ] The human has reviewed and approved the spec
- [ ] Success criteria are specific and testable
- [ ] Boundaries (Always/Ask First/Never) are defined
- [ ] The spec is saved to a file in the repository
