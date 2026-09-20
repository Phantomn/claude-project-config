# OpenSpec Validator — Thin Python Port (B2) Execution Spec

Self-contained. Sources: `@fission-ai/openspec@dist` (`v24.16.0` node_modules) —
`core/validation/validator.js` (923 LOC), `core/parsers/{requirement-blocks,requirement-text,code-fence,spec-structure,markdown-parser}.js`,
`core/schemas/{spec,change,base}.schema.js`, `core/validation/constants.js`;
delta syntax from `bounty/.claude/commands/opsx/sync.md` L189-255.

## 0. Scope decision (what "thin" means)

The load-bearing command is **`validate <change>` over delta spec files** =
`Validator.validateChangeDeltaSpecs()`. That is the gate authors hit. Port that.

**Port (load-bearing):** delta markdown parsing + the ERROR-producing rules below +
main-spec scenario-loss check + verdict.
**Skip (gold-plating, all either INFO-only or a separate concern):**
- `.openspec.yaml` `skip_specs` marker handling (only matters if a repo uses it).
- Task-file checkbox/numbering lint (`collectTaskFileIssues`) — WARNING, unrelated to spec correctness.
- `findArchiveBlockers` / `buildUpdatedSpec` archive dry-run — **INFO only, never changes verdict** (validator.js:797 "INFO leaves the verdict unchanged").
- Windows path canonicalization, symlink 8.3 alias handling, nested multi-area discovery.
- Full `ChangeSchema`/Zod object validation of proposal.md (`validateChange`) — the delta-spec path is the real content gate; proposal-level checks are cosmetic (Why length, What Changes present).
- Main-spec `validateSpec` (Purpose/Requirements sections, too-long INFO, purpose placeholder WARNING) — port only if you also need `validate <spec>`; adds ~60 LOC (§5).

---

## 1. Load-bearing validation rules  (input condition → violation)

Levels: **ERROR** fails the report; **WARNING** fails only in `--strict`; **INFO** never fails.
Verdict: `valid = (errors==0)` else `--strict`: `valid = (errors==0 and warnings==0)`. (validator.js:849)

### Delta-spec rules (validateChangeDeltaSpecs — the core)

1. **[ERROR] No deltas at all.** `totalDeltas==0` across every discovered `spec.md` (and no root-level spec / unread file already reported) → `"Change must have at least one delta"` (+ GUIDE_NO_DELTAS). Counts ADDED+MODIFIED+REMOVED+RENAMED entries. (validator.js:443-449)
2. **[ERROR] ADDED requirement missing body text.** ADDED block whose body (lines after header, fence/blank/metadata-aware) is empty → `ADDED "<name>" is missing requirement text` (or the "move SHALL/MUST to body" variant if the *header* itself contains SHALL/MUST). (validator.js:238-247)
3. **[WARNING] ADDED/MODIFIED body lacks SHALL/MUST.** Body text present but no `\b(SHALL|MUST)\b` → guidance warning `... should contain SHALL or MUST (RFC 2119 ...)`. **Guidance only, not ERROR** (unless strict). (validator.js:248-254)
4. **[ERROR] ADDED requirement has no scenario.** `countScenarios(block) < 1` → `ADDED "<name>" must include at least one scenario` (+ empty-scenario hint if a bare `####` header with no body exists). (validator.js:255-258)
5. **[ERROR] MODIFIED missing body text** — same as rule 2 for MODIFIED. (validator.js:270-279)
6. **[WARNING] MODIFIED body lacks SHALL/MUST** — same as rule 3. (validator.js:280-286)
7. **[ERROR] MODIFIED has no scenario** — same as rule 4 for MODIFIED. (validator.js:287-290)
8. **[ERROR] MODIFIED drops a scenario the main spec still has.** (needs `mainSpecsDir`) For each MODIFIED block, parse the current main `spec.md`'s matching requirement; scenario names present in current but not in incoming (multiplicity-aware: N in current, M in incoming → max(0,N−M) missing) → `MODIFIED "<name>" omits scenario(s) the current spec still has: "<s>". Copy them into the MODIFIED block ...`. **This is the sync.md:253 rule.** Silent if main spec / requirement absent (a sister change may add it). (validator.js:578-654, requirement-blocks.js:392-414)
9. **[ERROR] REMOVED** — names only; **no body/scenario required**. Only duplicate-name check applies. (validator.js:300-309)
10. **[ERROR] RENAMED unpaired FROM/TO.** A `FROM:` with no immediately following `TO:` (or a `TO:` with no pending `FROM:`, or interleaved FROM/FROM) → `RENAMED FROM: "<n>" has no matching TO: line ...`. Never guess-pair interleaved lines. (validator.js:181-189, requirement-blocks.js:346-382)
11. **[ERROR] Duplicate name within a section.** normalizeRequirementName-keyed dup in ADDED / MODIFIED / REMOVED / RENAMED-FROM / RENAMED-TO → `Duplicate requirement in <SECTION>: "<name>"`. (validator.js:232,264,303,315,321)
12. **[ERROR] Cross-section conflicts** (same spec file):
    - name in both MODIFIED & REMOVED / MODIFIED & ADDED / ADDED & REMOVED. (validator.js:329-341)
    - RENAMED-FROM also in MODIFIED → `MODIFIED references old name from RENAMED`.
    - RENAMED-TO also in ADDED → `RENAMED TO collides with ADDED`.
    - RENAMED-FROM also in REMOVED (case/whitespace-folded) → `present in both RENAMED and REMOVED`. (validator.js:342-362)
13. **[ERROR] Empty delta section.** A `## ADDED/MODIFIED/... Requirements` header present but zero requirement entries parsed → `Delta sections <...> were found, but no requirement entries parsed ...`. (validator.js:401-407)
14. **[ERROR] No delta sections / missing headers.** A discovered spec.md with no delta section headers at all → `No delta sections found. Add headers such as "## ADDED Requirements" ...`. (validator.js:408-414)
15. **[ERROR] Delta at `specs/spec.md` root** (no capability folder) → merge path drops it. Also **[ERROR] unread delta files** (`specs/<cap>.md`, notes beside spec.md). (validator.js:144-150, 393-400)
16. **[WARNING] Orphaned requirement** — a well-formed `### Requirement:` outside all four delta sections (or above first `## `) → ignored, warn to move it. (validator.js:195-205)
17. **[INFO] Skipped `###` header** — a level-3 header inside a delta section that is not `### Requirement:` → ignored, INFO note. Nameless `### Requirement` (no name) also INFO. (validator.js:167-177)

**"Minor" (safe to drop in thin port):** rules 16 (WARNING orphan), 17 (INFO), 13/14/15 file-layout errors are only reachable when authors misfile specs — port 13/14 (cheap, part of the section loop) but 15 (root/unread discovery) can be deferred if your caller always passes a single well-formed `spec.md`. `applyChangeRules` (delta description too brief WARNING, delta missing requirements WARNING) and the proposal Zod checks are cosmetic.

---

## 2. Delta / spec markdown syntax (what the parser consumes)

**Normalization:** strip UTF-8 BOM `﻿`; `\r\n?` → `\n`. (requirement-blocks.js:94-98)

**Fence mask (load-bearing everywhere):** a line opening with `^\s*(`{3,}|~{3,})` starts a fence; it closes on `^\s*(same-marker){>=len}\s*$`. Every line inside (incl. both fences) is masked; masked lines are invisible to *all* header/section/scenario matching. (code-fence.js)

**Section headers** (`## `, non-fenced): `^(##)\s+(.+)$`, title trimmed. The four delta sections match **case-insensitively but title-exactly** on `title.lower()` ∈ {`added requirements`, `modified requirements`, `removed requirements`, `renamed requirements`}. Note: `## ADDED  Requirements` (double space) does NOT match — reader is strict on interior whitespace. **Repeated headers merge** (both bodies apply); do not keep only the last. (requirement-blocks.js:155,198-246)

**Requirement header** (`### `, non-fenced): `^###\s*Requirement:\s*(.+)\s*$` (case-insensitive). Name = capture group, then `normalizeRequirementName`: strip a trailing ATX close run `/[ \t]+#+[ \t]*$/` then `.strip()` (so `### Requirement: Foo ###` → `Foo`, but `C#` keeps its `#`). Body = every line after the header up to the next `### Requirement:` or `## ` header. (requirement-blocks.js:2-8, 247-292)

**Scenario header** (`#### `, non-fenced): `^####\s+` — **ANY level-4 header counts as a scenario, not only `#### Scenario:`**. A scenario counts only if its body (lines to next non-fenced `^#{1,4}\s` header) is **non-empty** (`body.trim()` length > 0). Scenario name = header text with `^####\s+` removed, optional ATX close run stripped, optional `^Scenario:\s*` prefix stripped, trimmed. (requirement-text.js:27-39,101-125; requirement-blocks.js:419-474)

**Requirement body extraction** (for SHALL/MUST + "missing text"): from body lines, skip fenced/blank lines, break at first non-fenced `^#{1,6}\s` header; `**Key**: ...` metadata lines are held aside and used as the body *only if no other body text exists*. Result trimmed, `\n`-joined. Empty → "missing requirement text". (requirement-text.js:62-84)

**SHALL/MUST:** `/\b(SHALL|MUST)\b/` (case-sensitive, whole word). (requirement-text.js:45-47)

**REMOVED entries:** either a `### Requirement: <name>` header **or** a bullet `^\s*[-*+]\s*`?###\s*Requirement:\s*(.+?)`?\s*$` (any CommonMark marker `-`/`*`/`+`, optional backticks). (requirement-blocks.js:300-324)

**RENAMED entries:** lines `^\s*[-*+]?\s*FROM:\s*`?###\s*Requirement:\s*(.+?)`?\s*$` and same with `TO:`. A pair = FROM immediately followed by TO (no intervening second FROM). (requirement-blocks.js:346-382)

**Delta section order in a file** (canonical, from sync.md): `## ADDED Requirements`, `## MODIFIED Requirements`, `## REMOVED Requirements`, `## RENAMED Requirements`. RENAMED uses the `- FROM:` / `- TO:` bullet pair form. Optional leading `## Purpose` seeds a brand-new capability (only read at capability creation; not validated here).

**Main spec format** (target of merge, for rule 8): single `## Requirements` section, each `### Requirement: <name>` + body (SHALL/MUST) + `#### Scenario: <name>` blocks; **no delta operation headers allowed** in a main spec.

---

## 3. Contrast fixtures (5 pairs — become the port's test corpus)

### (a) PASS — valid ADDED delta
```markdown
## ADDED Requirements

### Requirement: User Login
The system SHALL authenticate users by email and password.

#### Scenario: Valid credentials
- **WHEN** a user submits a correct email and password
- **THEN** the system grants a session
```
→ 0 errors. valid=true.

### (b) FAIL — MODIFIED drops a scenario the main spec still has (rule 8, sync.md:253)
main `specs/auth/spec.md`:
```markdown
## Requirements

### Requirement: User Login
The system SHALL authenticate users.

#### Scenario: Valid credentials
- **WHEN** correct creds
- **THEN** grant session

#### Scenario: Locked account
- **WHEN** account is locked
- **THEN** deny with 423
```
delta MODIFIED (drops "Locked account"):
```markdown
## MODIFIED Requirements

### Requirement: User Login
The system SHALL authenticate users, now with rate limiting.

#### Scenario: Valid credentials
- **WHEN** correct creds
- **THEN** grant session
```
→ ERROR: `MODIFIED "User Login" omits scenario(s) the current spec still has: "Locked account"`. valid=false.

### (c) FAIL — no delta sections / no ADDED at all (rule 1 + rule 14)
```markdown
## Notes

### Requirement: Something
The system SHALL do a thing.

#### Scenario: x
- **WHEN** a
- **THEN** b
```
→ WARNING orphan `Requirement "Something" is under "## Notes" ... ignored`; ERROR `No delta sections found ...`; ERROR `Change must have at least one delta`. valid=false.

### (d) FAIL — ADDED requirement with no scenario (rule 4)
```markdown
## ADDED Requirements

### Requirement: Password Reset
The system SHALL allow a user to reset a password via email.
```
→ ERROR `ADDED "Password Reset" must include at least one scenario`. valid=false.

### (e) FAIL — RENAMED unpaired + cross-section conflict (rules 10, 12)
```markdown
## RENAMED Requirements

- FROM: `### Requirement: Old Login`
- FROM: `### Requirement: Old Signup`
- TO: `### Requirement: New Signup`

## REMOVED Requirements

### Requirement: Old Login
```
→ ERROR unpaired `RENAMED FROM: "Old Login" has no matching TO:` (displaced by second FROM); ERROR `present in both RENAMED and REMOVED: "Old Login"`. valid=false.

### (bonus) WARNING-only — body without SHALL/MUST (rule 3, PASS in non-strict)
```markdown
## ADDED Requirements

### Requirement: Export Data
The system exports the user's data as JSON.

#### Scenario: Basic export
- **WHEN** user clicks export
- **THEN** a JSON file downloads
```
→ WARNING `ADDED "Export Data" should contain SHALL or MUST`. valid=true (non-strict), false (--strict). Proves the ERROR/WARNING boundary.

---

## 4. Thin-port sizing

**Rule count:** 17 numbered; ~11 are ERROR-producing and load-bearing; port rules 1–15 (drop 16 WARNING/17 INFO unless you want parity).

**Parser complexity:** single-pass, line-based, fence-mask driven. No AST/CommonMark lib needed — plain regex + a fence-state boolean. The only non-trivial piece is the fence mask (must run before every header scan) and the multiplicity-aware scenario-loss diff (rule 8).

**Python LOC estimate (delta-only core, the B2 target):**
| piece | LOC |
|---|---|
| BOM/CRLF normalize + fence mask | ~25 |
| section split + case-insensitive delta lookup (merge repeats) | ~30 |
| requirement block parse (header/body/scenario split) | ~40 |
| scenario name/body + SHALL/MUST + body extraction | ~35 |
| rules engine (dup, cross-section, scenario≥1, body, rename pairs, counts) | ~110 |
| scenario-loss vs main spec (rule 8, reuses block parse) | ~35 |
| report/verdict + messages | ~20 |
| **total (delta validator)** | **~295** |
| + optional `validate <spec>` main-spec path (§5) | +60 |

vs full validator.js 1433 LOC (923 validator + parsers). **Thin port ≈ 300 LOC**, dropping archive dry-run, task lint, skip_specs marker, Windows path handling, Zod proposal schema.

**One runnable check to leave behind:** an `assert`-based `demo()` running the 6 fixtures above (5 pairs + bonus) — each asserts `valid` and the presence of the expected error substring.

---

## 5. (Optional) main-spec `validate <spec>` rules — port only if needed
- Parse sections; **ERROR** (thrown) if no `## Purpose` or no `## Requirements`. (markdown-parser.js:20-25)
- **ERROR** delta header inside a main spec; **ERROR** `### Requirement:` outside `## Requirements`; **ERROR** duplicate requirement name. (spec-structure.js)
- Schema: ≥1 requirement (`Spec must have at least one requirement`), each requirement text non-empty + ≥1 scenario. (spec/base.schema.js)
- **WARNING** Purpose < 50 chars or is a `TBD - created by archiving change .../TODO` placeholder; **INFO** requirement text > 500 chars; **WARNING/ERROR** body SHALL/MUST (same as delta). (validator.js:671-741, constants.js)

## Thresholds (constants.js)
MIN_WHY=50, MAX_WHY=1000, MIN_PURPOSE=50, MAX_REQUIREMENT_TEXT=500, MAX_DELTAS_PER_CHANGE=10.
