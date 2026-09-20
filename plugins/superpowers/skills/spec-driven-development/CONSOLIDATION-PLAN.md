# spec-driven-development 통합 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** spec/plan 워크플로우 3계보(superpowers·spec-driven·openspec)를 spec-driven-development 단일 정본으로 수렴하고, openspec 생명주기의 유일한 결정론 엔진(validate)을 CLI 없이 얇게 포팅해 흡수한다.

**Architecture:** spec-driven-development가 통합 진입점(SPECIFY→PLAN→TASKS→IMPLEMENT + spec 생명주기). PLAN/IMPLEMENT는 superpowers 스킬에 **위임**(편집 아님, 호출). openspec 생명주기 중 병합은 지시문(이미 LLM화), validate는 stdlib Python 스크립트로 B2 포팅. 흡수 완료·검증 후 sdd-harness·openspec 산물 제거, 재발방지 게이트.

**Tech Stack:** Python 3(stdlib only, regex — CommonMark 라이브러리 불요) · Markdown 스킬 문서 · bash(제거/게이트) · check-canon.sh

**Spec:**
- 설계·근본원인: `.agents/skills/spec-driven-development/CONSOLIDATION-DESIGN.md`
- validate 포팅 상세(규칙 17개·문법·fixture): `.agents/skills/spec-driven-development/references/validator-port-spec.md`
- 부활 베이스: 현 `SKILL.md`(DEPRECATED 헤더 아래 SPECIFY→IMPLEMENT 원문)

## Global Constraints

- validate verdict: `valid = (errors == 0)`; `--strict`: `valid = (errors == 0 and warnings == 0)`. (validator.js:849)
- 파서 불변식: BOM/CRLF 정규화 → **fence-mask를 모든 헤더/섹션/시나리오 스캔 *전에* 적용**(load-bearing). 펜스 = `^\s*(``{3,}|~{3,})`, 동일 마커 길이 이상으로 닫힘. 마스크된 라인은 모든 매칭에서 불가시.
- 시나리오 = **모든 non-fenced `^#### ` 레벨4 헤더**(`#### Scenario:`만 아님), body 비면 미카운트.
- 델타 섹션 헤더 = `^##\s+`, title은 `title.lower() ∈ {added/modified/removed/renamed requirements}` **내부 공백까지 정확**(`ADDED  Requirements` 이중공백 불일치). 반복 헤더는 **병합**(마지막만 유지 금지).
- requirement name 정규화: 끝의 ATX close run `/[ \t]+#+[ \t]*$/` 제거 후 strip (`C#`의 `#`는 보존).
- SHALL/MUST: `\b(SHALL|MUST)\b` 대소문자 구분 whole-word.
- superpowers 스킬은 **위임(호출)만** — marketplace repo 편집 금지(fork divergence 방지).
- 제거(sdd-harness·openspec 산물)는 **흡수·검증 완료 후에만**. 각 제거 후 `check-canon.sh` dangling 0 확인.
- validate 포팅 = **얇게**(rule 1–15, WARNING 16/INFO 17 생략 가능). stdlib only, 단일 스크립트(.agents 관행: notebooklm/recall scripts/*.py).
- Python 스크립트는 `shellcheck` 대상 아님 — `python -m py_compile` 통과 필수.

---

## File Structure

- `spec-driven-development/scripts/validate_spec.py` (신규) — 델타/메인 스펙 검증기(~295 LOC). 단일 파일: 파서 + 규칙엔진 + verdict + CLI + demo.
- `spec-driven-development/scripts/test_validate_spec.py` (신규) — 6 fixture pytest.
- `spec-driven-development/SKILL.md` (재작성) — DEPRECATED 헤더 제거, 통합 정본.
- `spec-driven-development/references/validator-port-spec.md` (존재) — 포팅 상세 스펙.
- 제거: `.agents/skills/sdd-harness/`, `.claude/skills/sdd-harness`(심링크), bounty `.claude/skills/openspec-*`(6), `.claude/commands/opsx/`, `openspec/`.
- `check-canon.sh`(정합) — openspec 산물 재유입 탐지.

---

## Task 1: 델타 스펙 파서 코어

> **✅ Phase 1(Task 1-3) 산출물 확정 (2026-09-20 감사 후)** — auditor-validate TDD 적대검증으로 `scripts/validate_spec.py`(286 LOC) + `test_validate_spec.py`(130) 배치·**17 passed**·demo OK. 아래 Task 1-3 코드는 초기 스케치이며 **배치본이 정본**(감사 반영: rule12 4종·rule11 dup·BUG-1 unpaired-FROM·fence 길이 수정). 실행 시 배치본 사용, 재구현 불필요.
> 잔여 TODO: rule12 신규 메시지(RENAMED-FROM∩MODIFIED, RENAMED-TO∩ADDED) openspec `validator.js` 원문 축자 대조 — 검출·verdict는 정합, 문구만 미확인.

**Files:**
- Create: `spec-driven-development/scripts/validate_spec.py`
- Test: `spec-driven-development/scripts/test_validate_spec.py`

**Interfaces:**
- Produces:
  - `normalize(text: str) -> str` — BOM 제거, `\r\n?`→`\n`.
  - `fence_mask(lines: list[str]) -> list[bool]` — 라인별 마스크(True=코드펜스 내부/펜스라인).
  - `split_sections(lines, mask) -> dict[str, list[str]]` — 델타 섹션명(소문자 정규화)→body 라인들. 반복 헤더 병합.
  - `parse_requirements(body_lines, mask_slice) -> list[Req]` where `Req = {"name": str, "body": str, "scenarios": list[str]}`. name 정규화·scenario는 non-empty body인 `#### ` 헤더만.
  - `count_scenarios(req) -> int`.

- [ ] **Step 1: 실패 테스트 작성** (fixture (a) PASS delta 파싱)

```python
# test_validate_spec.py
from validate_spec import normalize, fence_mask, split_sections, parse_requirements

FIXTURE_A = """## ADDED Requirements

### Requirement: User Login
The system SHALL authenticate users by email and password.

#### Scenario: Valid credentials
- **WHEN** a user submits a correct email and password
- **THEN** the system grants a session
"""

def test_parse_added_delta():
    lines = normalize(FIXTURE_A).split("\n")
    mask = fence_mask(lines)
    sections = split_sections(lines, mask)
    assert "added requirements" in sections
    reqs = parse_requirements(sections["added requirements"], mask)
    assert len(reqs) == 1
    assert reqs[0]["name"] == "User Login"
    assert "SHALL" in reqs[0]["body"]
    assert reqs[0]["scenarios"] == ["Valid credentials"]

def test_fence_masks_headers():
    lines = normalize("```\n## ADDED Requirements\n```\n## MODIFIED Requirements").split("\n")
    mask = fence_mask(lines)
    sections = split_sections(lines, mask)
    assert "added requirements" not in sections   # 펜스 내부 → 불가시
    assert "modified requirements" in sections
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd spec-driven-development/scripts && python -m pytest test_validate_spec.py -k "parse_added or fence_masks" -v`
Expected: FAIL (ImportError: validate_spec 없음)

- [ ] **Step 3: 최소 구현**

```python
# validate_spec.py
import re

_FENCE = re.compile(r'^\s*(`{3,}|~{3,})')
_SECTION = re.compile(r'^##\s+(.+?)\s*$')
_REQ = re.compile(r'^###\s*Requirement:\s*(.+?)\s*$', re.I)
_SCEN = re.compile(r'^####\s+(.+?)\s*$')
_ATX = re.compile(r'[ \t]+#+[ \t]*$')
_DELTA_TITLES = {"added requirements", "modified requirements",
                 "removed requirements", "renamed requirements"}

def normalize(text):
    return text.lstrip('﻿').replace('\r\n', '\n').replace('\r', '\n')

def fence_mask(lines):
    mask, fence = [], None
    for ln in lines:
        m = _FENCE.match(ln)
        if fence is None and m:
            fence = m.group(1)[0] * 3; mask.append(True); continue
        if fence is not None:
            mask.append(True)
            if re.match(rf'^\s*{re.escape(fence[0])}{{{len(fence)},}}\s*$'.replace(str(len(fence)), str(len(fence))), ln):
                fence = None
            continue
        mask.append(False)
    return mask

def _norm_name(s):
    return _ATX.sub('', s).strip()

def split_sections(lines, mask):
    out, cur = {}, None
    for i, ln in enumerate(lines):
        if mask[i]:
            if cur is not None: out[cur].append(ln)
            continue
        m = _SECTION.match(ln)
        if m and m.group(1).lower() in _DELTA_TITLES:
            cur = m.group(1).lower(); out.setdefault(cur, [])
        elif m:                # 다른 ## 헤더 → 섹션 종료
            cur = None
        elif cur is not None:
            out[cur].append(ln)
    return out

def parse_requirements(body_lines, mask):
    reqs, cur = [], None
    for ln in body_lines:
        rm = _REQ.match(ln)
        if rm:
            cur = {"name": _norm_name(rm.group(1)), "body_lines": [], "scen_lines": [], "_scen": None}
            reqs.append(cur); continue
        if cur is None: continue
        sm = _SCEN.match(ln)
        if sm:
            name = re.sub(r'^Scenario:\s*', '', _norm_name(sm.group(1)), flags=re.I)
            cur["_scen"] = {"name": name, "body": []}; cur["scen_lines"].append(cur["_scen"]); continue
        if cur["_scen"] is not None: cur["_scen"]["body"].append(ln)
        else: cur["body_lines"].append(ln)
    result = []
    for r in reqs:
        scen = [s["name"] for s in r["scen_lines"] if "".join(s["body"]).strip()]
        result.append({"name": r["name"], "body": "\n".join(r["body_lines"]).strip(), "scenarios": scen})
    return result

def count_scenarios(req):
    return len(req["scenarios"])
```
> 세부 정규화·엣지(REMOVED 불릿·RENAMED FROM/TO·metadata 라인)는 `references/validator-port-spec.md` §2 참조. 이 태스크는 ADDED/헤더/시나리오 파싱까지.

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest test_validate_spec.py -k "parse_added or fence_masks" -v`
Expected: PASS 2건

- [ ] **Step 5: 커밋**

```bash
git -C /home/phantom/.agents add skills/spec-driven-development/scripts/validate_spec.py skills/spec-driven-development/scripts/test_validate_spec.py
git -C /home/phantom/.agents commit -m "feat(sdd): delta spec 파서 코어 (fence-mask/section/requirement/scenario)"
```

---

## Task 2: 델타 구조 규칙 엔진

**Files:**
- Modify: `spec-driven-development/scripts/validate_spec.py`
- Test: `spec-driven-development/scripts/test_validate_spec.py`

**Interfaces:**
- Consumes: `parse_requirements`, `count_scenarios`, `split_sections` (Task 1).
- Produces:
  - `Issue = {"level": "ERROR"|"WARNING"|"INFO", "msg": str}`.
  - `check_delta(sections) -> list[Issue]` — rule 1–7, 9–14 적용(main spec 불요분).
  - `has_shall(body) -> bool`.

규칙(references §1): 1 델타전무 / 2 ADDED body없음 / 3 ADDED·MOD SHALL없음(WARNING) / 4 ADDED scenario0 / 5 MOD body없음 / 6 MOD SHALL없음(WARNING) / 7 MOD scenario0 / 9 REMOVED 이름만+dup / 10 RENAMED unpaired / 11 섹션내 dup / 12 교차섹션충돌 / 13 빈 델타섹션 / 14 델타섹션 전무.

- [ ] **Step 1: 실패 테스트 작성** (fixture c·d·e·bonus)

```python
from validate_spec import validate_delta_text   # (sections 래핑 진입점, Step 3에서 정의)

def _errs(text):
    issues = validate_delta_text(text)
    return [i["msg"] for i in issues if i["level"] == "ERROR"]

def test_added_no_scenario():          # fixture (d), rule 4
    t = "## ADDED Requirements\n\n### Requirement: Password Reset\nThe system SHALL allow a user to reset a password via email.\n"
    assert any('must include at least one scenario' in m for m in _errs(t))

def test_no_delta_sections():          # fixture (c), rule 14 + 1
    t = "## Notes\n\n### Requirement: Something\nThe system SHALL do a thing.\n\n#### Scenario: x\n- **WHEN** a\n- **THEN** b\n"
    errs = _errs(t)
    assert any('No delta sections' in m for m in errs)
    assert any('at least one delta' in m for m in errs)

def test_renamed_unpaired_and_conflict():   # fixture (e), rules 10,12
    t = ("## RENAMED Requirements\n\n- FROM: `### Requirement: Old Login`\n"
         "- FROM: `### Requirement: Old Signup`\n- TO: `### Requirement: New Signup`\n\n"
         "## REMOVED Requirements\n\n### Requirement: Old Login\n")
    errs = _errs(t)
    assert any('no matching TO' in m for m in errs)
    assert any('RENAMED and REMOVED' in m for m in errs)

def test_shall_warning_not_error():    # fixture (bonus), rule 3
    t = "## ADDED Requirements\n\n### Requirement: Export Data\nThe system exports the user's data as JSON.\n\n#### Scenario: Basic export\n- **WHEN** user clicks export\n- **THEN** a JSON file downloads\n"
    issues = validate_delta_text(t)
    assert not [i for i in issues if i["level"] == "ERROR"]
    assert any(i["level"] == "WARNING" and 'SHALL or MUST' in i["msg"] for i in issues)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest test_validate_spec.py -k "added_no_scenario or no_delta or renamed_unpaired or shall_warning" -v`
Expected: FAIL (validate_delta_text 없음)

- [ ] **Step 3: 최소 구현** (validate_spec.py에 추가)

```python
def has_shall(body):
    return re.search(r'\b(SHALL|MUST)\b', body) is not None

def _parse_removed(body_lines, mask):
    names = []
    for ln in body_lines:
        m = re.match(r'^\s*[-*+]?\s*`?###\s*Requirement:\s*(.+?)`?\s*$', ln, re.I)
        if m: names.append(_norm_name(m.group(1)))
    return names

def _parse_renamed(body_lines):
    pairs, froms = [], []
    for ln in body_lines:
        fm = re.match(r'^\s*[-*+]?\s*FROM:\s*`?###\s*Requirement:\s*(.+?)`?\s*$', ln, re.I)
        tm = re.match(r'^\s*[-*+]?\s*TO:\s*`?###\s*Requirement:\s*(.+?)`?\s*$', ln, re.I)
        if fm:
            if froms: pairs.append(("UNPAIRED", froms.pop()))   # 이전 FROM이 TO 못 만남
            froms.append(_norm_name(fm.group(1)))
        elif tm:
            if froms: pairs.append((froms.pop(), _norm_name(tm.group(1))))
            else: pairs.append(("NO_FROM", _norm_name(tm.group(1))))
    pairs += [("UNPAIRED", f) for f in froms]
    return pairs

def validate_delta_text(text, main_specs_dir=None):
    lines = normalize(text).split("\n"); mask = fence_mask(lines)
    sections = split_sections(lines, mask)
    return check_delta(sections, mask, main_specs_dir)

def check_delta(sections, mask, main_specs_dir=None):
    issues = []; total = 0
    added = parse_requirements(sections.get("added requirements", []), mask)
    modified = parse_requirements(sections.get("modified requirements", []), mask)
    removed = _parse_removed(sections.get("removed requirements", []), mask)
    renamed = _parse_renamed(sections.get("renamed requirements", []))
    total = len(added) + len(modified) + len(removed) + len(renamed)

    if not sections:
        issues.append({"level": "ERROR", "msg": 'No delta sections found. Add headers such as "## ADDED Requirements"'})
    for label, reqs in (("ADDED", added), ("MODIFIED", modified)):
        for r in reqs:
            if not r["body"]:
                issues.append({"level": "ERROR", "msg": f'{label} "{r["name"]}" is missing requirement text'})
            elif not has_shall(r["body"]):
                issues.append({"level": "WARNING", "msg": f'{label} "{r["name"]}" should contain SHALL or MUST (RFC 2119)'})
            if count_scenarios(r) < 1:
                issues.append({"level": "ERROR", "msg": f'{label} "{r["name"]}" must include at least one scenario'})
    # dup within section
    for label, names in (("ADDED", [r["name"] for r in added]), ("MODIFIED", [r["name"] for r in modified]),
                         ("REMOVED", removed)):
        seen = set()
        for n in names:
            if n in seen: issues.append({"level": "ERROR", "msg": f'Duplicate requirement in {label}: "{n}"'})
            seen.add(n)
    # rename pairs
    for a, b in renamed:
        if a == "UNPAIRED": issues.append({"level": "ERROR", "msg": f'RENAMED FROM: "{b}" has no matching TO: line'})
        elif a == "NO_FROM": issues.append({"level": "ERROR", "msg": f'RENAMED TO: "{b}" has no matching FROM: line'})
    # cross-section: RENAMED-FROM ∩ REMOVED
    rfrom = {a for a, b in renamed if a not in ("UNPAIRED", "NO_FROM")}
    for n in rfrom & set(removed):
        issues.append({"level": "ERROR", "msg": f'"{n}" present in both RENAMED and REMOVED'})
    amod = {r["name"] for r in added} & {r["name"] for r in modified}
    for n in amod: issues.append({"level": "ERROR", "msg": f'"{n}" present in both ADDED and MODIFIED'})
    # empty section header present but no entries
    for title in _DELTA_TITLES:
        if title in sections and not parse_requirements(sections[title], mask) \
           and not _parse_removed(sections[title], mask) and not _parse_renamed(sections[title]):
            issues.append({"level": "ERROR", "msg": f'Delta section "{title}" found, but no requirement entries parsed'})
    if total == 0:
        issues.append({"level": "ERROR", "msg": "Change must have at least one delta"})
    return issues
```
> rule 12 나머지(MOD∩REM, RENAMED-FROM∩MODIFIED, RENAMED-TO∩ADDED)·rule 8은 Task 3. 정확한 메시지 문자열은 references §1 인용.

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest test_validate_spec.py -k "added_no_scenario or no_delta or renamed_unpaired or shall_warning" -v`
Expected: PASS 4건

- [ ] **Step 5: 커밋**

```bash
git -C /home/phantom/.agents add skills/spec-driven-development/scripts/
git -C /home/phantom/.agents commit -m "feat(sdd): 델타 구조 규칙 엔진 (body/scenario/dup/rename/counts)"
```

---

## Task 3: main-spec 시나리오 드롭(rule 8) + verdict + CLI + demo

**Files:**
- Modify: `spec-driven-development/scripts/validate_spec.py`
- Test: `spec-driven-development/scripts/test_validate_spec.py`

**Interfaces:**
- Consumes: `parse_requirements`, `check_delta`.
- Produces:
  - `check_scenario_loss(modified: list[Req], main_spec_text: str) -> list[Issue]` — MODIFIED가 main의 기존 시나리오를 드롭하면 ERROR(multiplicity-aware). main 없으면 침묵.
  - `validate(text, main_spec_text=None, strict=False) -> dict` = `{"valid": bool, "issues": [...]}`.
  - `demo()` — 6 fixture assert.
  - `__main__`: `python validate_spec.py <delta.md> [--main <spec.md>] [--strict]` → exit 0/1.

- [ ] **Step 1: 실패 테스트 작성** (fixture (a) PASS, (b) 시나리오 드롭 FAIL)

```python
from validate_spec import validate

def test_valid_added_passes():        # fixture (a)
    t = "## ADDED Requirements\n\n### Requirement: User Login\nThe system SHALL authenticate users by email and password.\n\n#### Scenario: Valid credentials\n- **WHEN** correct\n- **THEN** session\n"
    assert validate(t)["valid"] is True

def test_modified_drops_scenario():   # fixture (b), rule 8
    main = "## Requirements\n\n### Requirement: User Login\nThe system SHALL authenticate users.\n\n#### Scenario: Valid credentials\n- **WHEN** correct creds\n- **THEN** grant session\n\n#### Scenario: Locked account\n- **WHEN** locked\n- **THEN** deny 423\n"
    delta = "## MODIFIED Requirements\n\n### Requirement: User Login\nThe system SHALL authenticate users, now with rate limiting.\n\n#### Scenario: Valid credentials\n- **WHEN** correct creds\n- **THEN** grant session\n"
    r = validate(delta, main_spec_text=main)
    assert r["valid"] is False
    assert any('omits scenario' in i["msg"] and 'Locked account' in i["msg"] for i in r["issues"])

def test_demo_runs():
    from validate_spec import demo
    demo()   # 내부 assert 6건
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest test_validate_spec.py -k "valid_added or modified_drops or demo_runs" -v`
Expected: FAIL (validate/demo 없음)

- [ ] **Step 3: 최소 구현**

```python
def _main_scenarios(main_text, req_name):
    lines = normalize(main_text).split("\n"); mask = fence_mask(lines)
    # main: 단일 ## Requirements 섹션 → parse_requirements 재사용 위해 헤더 아래 전체 전달
    body = [ln for i, ln in enumerate(lines)]
    for r in parse_requirements(body, mask):
        if r["name"] == req_name: return r["scenarios"]
    return None

def check_scenario_loss(modified, main_text):
    issues = []
    if not main_text: return issues
    for r in modified:
        cur = _main_scenarios(main_text, r["name"])
        if cur is None: continue                    # sister change가 추가할 수 있음 → 침묵
        from collections import Counter
        incoming = Counter(r["scenarios"]); missing = []
        for name, n in Counter(cur).items():
            gap = n - incoming.get(name, 0)
            if gap > 0: missing.append(name)
        if missing:
            issues.append({"level": "ERROR",
                "msg": f'MODIFIED "{r["name"]}" omits scenario(s) the current spec still has: ' +
                       ", ".join(f'"{m}"' for m in missing)})
    return issues

def validate(text, main_spec_text=None, strict=False):
    lines = normalize(text).split("\n"); mask = fence_mask(lines)
    sections = split_sections(lines, mask)
    issues = check_delta(sections, mask)
    issues += check_scenario_loss(parse_requirements(sections.get("modified requirements", []), mask), main_spec_text)
    errs = sum(1 for i in issues if i["level"] == "ERROR")
    warns = sum(1 for i in issues if i["level"] == "WARNING")
    valid = errs == 0 and (warns == 0 if strict else True)
    return {"valid": valid, "issues": issues}

def demo():
    # references/validator-port-spec.md §3 의 6 fixture — 각 valid + 기대 substring assert
    assert validate(_FX_A)["valid"] is True
    assert not validate(_FX_B, main_spec_text=_FX_B_MAIN)["valid"]
    assert not validate(_FX_C)["valid"]
    assert not validate(_FX_D)["valid"]
    assert not validate(_FX_E)["valid"]
    assert validate(_FX_BONUS)["valid"] is True and not validate(_FX_BONUS, strict=True)["valid"]
    print("demo OK: 6 fixtures")

if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if not args: demo(); sys.exit(0)
    strict = "--strict" in args; args = [a for a in args if a != "--strict"]
    main_text = None
    if "--main" in args:
        j = args.index("--main"); main_text = open(args[j+1]).read(); del args[j:j+2]
    text = open(args[0]).read()
    r = validate(text, main_spec_text=main_text, strict=strict)
    for i in r["issues"]: print(f'{i["level"]}: {i["msg"]}')
    sys.exit(0 if r["valid"] else 1)
```
> `_FX_A.._FX_BONUS` 상수는 references §3 마크다운을 그대로 모듈 상단에 붙인다(6개). demo가 남길 유일 runnable check.

- [ ] **Step 4: 테스트 통과 + 컴파일 + demo**

Run: `python -m pytest test_validate_spec.py -v && python -m py_compile validate_spec.py && python validate_spec.py`
Expected: 전체 PASS, `demo OK: 6 fixtures`

- [ ] **Step 5: 커밋**

```bash
git -C /home/phantom/.agents add skills/spec-driven-development/scripts/
git -C /home/phantom/.agents commit -m "feat(sdd): rule8 시나리오드롭 + verdict + CLI + 6-fixture demo (validate B2 포팅 완료)"
```

---

## Task 4: spec-driven-development SKILL.md 통합 정본 재작성

**Files:**
- Modify: `spec-driven-development/SKILL.md` (DEPRECATED 헤더 제거, 재작성)

**해당 태스크는 문서 산출** — TDD 대신 구조·검증 게이트로 진행.

- [ ] **Step 1: DEPRECATED 헤더(1–11행) 제거, description 갱신**

frontmatter description(현 "DEPRECATED…"):
```
description: "구조화 spec을 먼저 쓰고 gated 워크플로우로 구현하는 단일 정본. SPECIFY→PLAN→TASKS→IMPLEMENT. PLAN/구현은 superpowers 스킬에 위임하고, spec 생명주기(delta·검증)를 흡수한다. spec 기반 개발·다파일 변경·아키텍처 결정 시 사용."
```

- [ ] **Step 2: 본문 구조 재작성** (원 SPECIFY→IMPLEMENT 골격 유지 + 위임/생명주기 흡수)

담을 내용(references·DESIGN §5 기준):
- **SPECIFY**: 원문 6영역 템플릿 + success-criteria 리프레이밍(원 :124-136 보존) + assumptions surfacing. openspec propose의 "변경단위=delta" 개념 흡수 = spec 문서가 곧 변경 단위.
- **PLAN**: "→ superpowers:writing-plans에 위임" 명시(복제 금지). update 양방향 재조정을 여기 흡수(기존 spec 세트 재개정 절차 1문단).
- **TASKS**: writing-plans 태스크 분해 위임.
- **IMPLEMENT**: "→ superpowers:subagent-driven-development(권장)/executing-plans 위임 + TDD·worktrees·code-review 횡단".
- **생명주기(Keeping Spec Alive 확장)**: delta→main 병합은 agent-driven 편집 지시문(openspec sync 흡수, references §2 문법). archive=파일 mkdir+mv. **validate=`python scripts/validate_spec.py <delta.md> --main <spec.md>` 호출**(결정론 가드).
- **라우팅 우선권 + 한계(감사 GAP3)**: description이 spec/plan/아키텍처 트리거를 선점해 spec-driven을 상위 진입점으로. 단 superpowers writing-plans/brainstorming도 model-invoked 자동발견되므로 **직접진입 완전차단은 불가 = 알려진 한계(LIMITS)**. 본문에 "spec 없이 plan부터 진입했다면 SPECIFY로 회귀" 가드 1문단. (superpowers는 하위 실행엔진 — marketplace 편집 안 함, fork divergence 회피.)

- [ ] **Step 3: 검증 게이트**

```bash
python3 /home/phantom/bounty/.claude/tools/skill-audit.py --strict   # frontmatter name/description/중복명
grep -c "DEPRECATED" /home/phantom/.agents/skills/spec-driven-development/SKILL.md   # → 0
grep -c "openspec\|opsx" /home/phantom/.agents/skills/spec-driven-development/SKILL.md # → 0 (CLI 의존 없음)
# 흡수 패턴 실재(AC-3): success-criteria 리프레이밍 + update 양방향 재조정이 본문에 있고 원본 축자복제 아닌 지침인지
grep -ci "success criteria\|성공 기준" /home/phantom/.agents/skills/spec-driven-development/SKILL.md  # ≥1
grep -ci "재조정\|재개정\|reconcile" /home/phantom/.agents/skills/spec-driven-development/SKILL.md      # ≥1
```
Expected: skill-audit 통과, DEPRECATED 0, openspec 참조 0, 흡수 패턴 각 ≥1.

- [ ] **Step 4: 커밋**

```bash
git -C /home/phantom/.agents add skills/spec-driven-development/SKILL.md skills/spec-driven-development/references/ skills/spec-driven-development/CONSOLIDATION-DESIGN.md skills/spec-driven-development/CONSOLIDATION-PLAN.md
git -C /home/phantom/.agents commit -m "feat(sdd): 통합 정본 재작성 — superpowers 위임 + validate 흡수, DEPRECATED 해제"
```

---

## Task 5: sdd-harness 제거

**Files:**
- Delete: `/home/phantom/.agents/skills/sdd-harness/` (실체), `/home/phantom/.claude/skills/sdd-harness` (심링크)

- [ ] **Step 1: 잔여 호출처 재확인**(제거 전 영향 0 실측)

```bash
grep -rn "sdd-harness" /home/phantom/.agents /home/phantom/.claude/rules /home/phantom/bounty/.claude \
  --include="*.md" --include="*.sh" --include="*.json" 2>/dev/null | grep -v "skills/sdd-harness/" | grep -v "/cache/"
```
Expected: 활성 참조 0 (메모리 언급만 — 무해).

- [ ] **Step 2: 제거**

```bash
rm -rf /home/phantom/.agents/skills/sdd-harness
rm /home/phantom/.claude/skills/sdd-harness
```

- [ ] **Step 3: canon 게이트 확인**

```bash
bash /home/phantom/.claude/check-canon.sh   # dangling 심링크 0, selftest 통과
```
Expected: 통과(dangling 0).

- [ ] **Step 4: 커밋**

```bash
git -C /home/phantom/.agents add -A skills/
git -C /home/phantom/.agents commit -m "chore: sdd-harness 제거 — 파이프 무관 별개도구(호출처 0), spec 통합서 분리"
```

---

## Task 6: openspec 프로젝트 산물 제거 (owned 7 프로젝트)

**Files (각 프로젝트에서):** `.claude/skills/openspec-{apply-change,archive-change,explore,propose,sync-specs,update-change}`, `.claude/commands/opsx/`, `openspec/`

**대상 7 프로젝트** (전부 Phantomn 소유·`openspec/` 실파일 0 실측): `/home/phantom/agent` · `analysis` · `bounty` · `mobius-py` · `obsidian` · `phantomn.github.io` · `tools/seller`.

**전제:** Task 3(validate 포팅)+Task 4(정본) 완료·검증 후. 생명주기가 spec-driven 정본으로 흡수됐음을 확인한 뒤.
**범위 근본근거(감사 GAP1):** openspec은 09-18에 7곳 init 후 실사용 0(전부 빈 스캐폴딩). bounty만 제거하면 "미정리 누적"(4계보 6벌 동형) 병리를 그대로 재현 → owned 전 프로젝트 **동시 제거**가 정공법.

- [ ] **Step 1: 7곳 실데이터 없음 재확인** (제거 안전 게이트)

```bash
for p in /home/phantom/agent /home/phantom/analysis /home/phantom/bounty \
         /home/phantom/mobius-py /home/phantom/obsidian \
         /home/phantom/phantomn.github.io /home/phantom/tools/seller; do
  n=$(find "$p/openspec" -type f ! -name ".gitkeep" ! -name "config.yaml" 2>/dev/null | wc -l)
  echo "$p: 실파일 $n"
done
```
Expected: 전부 `실파일 0`. 하나라도 >0이면 그 프로젝트만 **중단·사용자 확인**(실사용 spec 손실 방지).

- [ ] **Step 2: 7곳 제거**

```bash
for p in /home/phantom/agent /home/phantom/analysis /home/phantom/bounty \
         /home/phantom/mobius-py /home/phantom/obsidian \
         /home/phantom/phantomn.github.io /home/phantom/tools/seller; do
  rm -rf "$p"/.claude/skills/openspec-apply-change "$p"/.claude/skills/openspec-archive-change \
         "$p"/.claude/skills/openspec-explore "$p"/.claude/skills/openspec-propose \
         "$p"/.claude/skills/openspec-sync-specs "$p"/.claude/skills/openspec-update-change \
         "$p"/.claude/commands/opsx "$p"/openspec
  echo "removed: $p"
done
```

- [ ] **Step 3: 잔존 참조 스캔** (7곳)

```bash
for p in /home/phantom/agent /home/phantom/analysis /home/phantom/bounty \
         /home/phantom/mobius-py /home/phantom/obsidian \
         /home/phantom/phantomn.github.io /home/phantom/tools/seller; do
  grep -rn "opsx\|openspec-propose\|openspec init" "$p/.claude" "$p/CLAUDE.md" \
    --include="*.md" --include="*.json" 2>/dev/null | grep -v "check-canon\|memory"
done
```
Expected: 워크플로우 참조 0.

- [ ] **Step 4: 프로젝트별 커밋** (각 repo 독립 — bounty=no-remote, 나머지 Phantomn)

```bash
for p in /home/phantom/agent /home/phantom/analysis /home/phantom/bounty \
         /home/phantom/mobius-py /home/phantom/obsidian \
         /home/phantom/phantomn.github.io /home/phantom/tools/seller; do
  git -C "$p" add -A .claude/ openspec 2>/dev/null
  git -C "$p" commit -m "chore: openspec 산물 제거 — spec-driven 정본으로 수렴(미사용 스캐폴딩)" 2>/dev/null \
    && echo "committed: $p" || echo "nochange: $p"
done
```
> **순서 불변식(감사 GAP2):** Task 6(7곳 제거)은 반드시 Task 7(게이트 위반화) **앞**. 지울 산물이 남은 채 Task 7이 openspec을 위반화하면 전역 게이트가 상시 실패한다.

---

## Task 7: 재발방지 — check-canon.sh openspec 폐기물 재유입 탐지

**Files:**
- Modify: `/home/phantom/.claude/check-canon.sh`

**설계 근거(감사 GAP2·AC-6 해소):** 현행 `is_tool_generated()`(check-canon.sh:48, `generatedBy` provenance)가 openspec-* 스킬을 canon 중복검출에서 **의도적 면제** 중(NEG13 selftest:289-294 보호). 이 면제는 "정당한 CLI 배포물"용 **범용 오라클**이라 **건드리지 않는다**. openspec은 이제 *폐기된* 워크플로우이므로 면제와 **별개 blocklist 채널**로 폐기물 재유입만 위반화한다(정당배포물 면제 ≠ 폐기물 차단, 목적이 다르다 — variant/ignore-allowlist에는 openspec 항목 없음, 실측 확인). Task 6이 7곳을 이미 비웠으므로 시작 위반 0(순서 불변식).

- [ ] **Step 1: 통합 지점 확인** (실로직)

```bash
sed -n '33p;48,58p;364,371p' /home/phantom/.claude/check-canon.sh
```
확인: `SCAN_ROOT="${SCAN_ROOT:-$HOME}"`(33) · `is_tool_generated()`(48, generatedBy 면제) · 메인 `for a in $ASSETS_LIST; do check_asset "$a"; done` + `BAD` 집계 → `exit 0/1`(366-371).

- [ ] **Step 2: 폐기물 탐지 함수 추가** (`check_asset` 정의 뒤, selftest 블록 `if [ "${1:-}" = "--selftest" ]`(242) 앞)

```bash
# 폐기된 openspec 워크플로우 재유입 탐지 (2026-09-20 폐기 → spec-driven-development 정본).
#   is_tool_generated 면제는 정당 CLI 배포물용 범용 오라클이라 유지. openspec 은 폐기물이라
#   별도 blocklist 로 재유입만 차단(목적이 다르다). openspec init 재실행이 주 재유입원.
check_openspec_retired() {
    local d root
    while read -r d; do
        root="${d%/.claude}"; [ -n "$root" ] || continue
        is_ignored "$root" && continue
        if compgen -G "$root/.claude/skills/openspec-*" >/dev/null 2>&1 \
           || [ -d "$root/.claude/commands/opsx" ] || [ -d "$root/openspec" ]; then
            echo "위반(폐기 openspec 재유입 — 제거 대상): $root"
            BAD=$((BAD+1))
        fi
    done < <(find "$SCAN_ROOT" -mindepth 1 -maxdepth 2 -type d -name .claude 2>/dev/null)
}
```

- [ ] **Step 3: 메인 루프에 연결** (line 366 직후, `exit` 판정 전)

```bash
# 기존 366:  for a in $ASSETS_LIST; do check_asset "$a"; done
# 추가:       check_openspec_retired
```
`BAD` 공유 → 재유입 시 기존 `exit 1` 경로(370-371)로 자연 실패.

- [ ] **Step 4: selftest 케이스 추가** (`--selftest` 블록, NEG13(289-294) 뒤 — 그 패턴을 복제)

NEG13는 `run()` 헬퍼(252: `AGENTS_DIR/CLAUDE_DIR/SCAN_ROOT` 오버라이드 + `$T/o` 캡처)를 쓴다. 동일 헬퍼로:
```bash
    # POS-OSP openspec 재유입 → 위반 탐지 (BAD>0, rc=1)
    mkdir -p "$T/root/proj/.claude/commands/opsx"
    { [ "$(run)" = "1" ] && grep -q '폐기 openspec' "$T/o"; } \
      && echo "  ✓ POS-OSP openspec 재유입 탐지" || { echo "  ✗ POS-OSP"; cat "$T/o"; fail=1; }
    rm -rf "$T/root/proj/.claude/commands/opsx"
```

- [ ] **Step 5: 검증**

```bash
bash /home/phantom/.claude/check-canon.sh --selftest   # 전량 PASS(+POS-OSP)
bash /home/phantom/.claude/check-canon.sh               # Task6 후: openspec 위반 0 → 정상 exit 0
```
Expected: selftest 전량 PASS, 실행 시 openspec 위반 0(7곳 제거 전제).

- [ ] **Step 6: 커밋**

```bash
# check-canon.sh 는 ~/.claude 실체(심링크 아님) — 그 repo 로 커밋
git -C /home/phantom/.claude add check-canon.sh 2>/dev/null \
  && git -C /home/phantom/.claude commit -m "feat(canon): openspec 폐기물 재유입 탐지 — 정당배포물 면제와 별개 채널" 2>/dev/null || true
```

---

## Task 8: 통합 검증 (폐루프 dry-run)

**전 태스크 완료 후 — 새 실코드 없음, 전수 검증만.**

- [ ] **Step 1: validate 포팅 회귀**

```bash
cd /home/phantom/.agents/skills/spec-driven-development/scripts
python -m pytest test_validate_spec.py -v && python validate_spec.py   # demo OK
```

- [ ] **Step 2: 스킬 라우팅**(spec-driven 진입점이 노출·발견되나)

```bash
grep -c "DEPRECATED" /home/phantom/.agents/skills/spec-driven-development/SKILL.md   # 0
python3 /home/phantom/bounty/.claude/tools/skill-audit.py --strict
```

- [ ] **Step 3: 계보 단일화 확인**(3계보 → 1정본 + superpowers 위임)

```bash
ls /home/phantom/.agents/skills/ | grep -E "sdd-harness|spec-driven"   # spec-driven만(sdd-harness 없음)
for p in /home/phantom/agent /home/phantom/analysis /home/phantom/bounty \
         /home/phantom/mobius-py /home/phantom/obsidian \
         /home/phantom/phantomn.github.io /home/phantom/tools/seller; do
  ls "$p"/.claude/skills/ 2>/dev/null | grep openspec
  ls "$p"/.claude/commands/ 2>/dev/null | grep opsx
  ls -d "$p"/openspec 2>/dev/null
done   # 전부 출력 없음 = 7곳 openspec 산물 0
```
Expected: spec-driven-development 단독, 7곳 openspec 산물 0.

- [ ] **Step 4: 게이트 전수**

```bash
find /home/phantom/.agents/skills/spec-driven-development -name "*.py" -exec python -m py_compile {} \;
bash /home/phantom/.claude/check-canon.sh
```
Expected: 전부 통과.

- [ ] **Step 5: 최종 커밋 + rulings 기록**

```bash
git -C /home/phantom/.agents log --oneline -8
git -C /home/phantom/bounty log --oneline -3
```
CONSOLIDATION-DESIGN §11 미결 처리 결과를 커밋 메시지/문서에 기록.

---

## Self-Review

**1. Spec coverage** (CONSOLIDATION-DESIGN §9 6 Phase 대조):
- Phase 1 validate 포팅 → Task 1–3 ✅
- Phase 2 spec-driven 재작성 → Task 4 ✅
- Phase 3 gap 흡수 → **Task 4에 병합**(update 재조정=PLAN, success-criteria=SPECIFY; superpowers 편집 불요로 축소) ✅
- Phase 4 제거 → Task 5(sdd-harness)·6(openspec) ✅
- Phase 5 재발방지 → Task 7 ✅
- Phase 6 통합검증 → Task 8 ✅

**2. Placeholder scan:** validate 포팅 3태스크는 실 fixture+구현 코드 포함(배치본 17 passed). Task 4·7은 문서/게이트 태스크라 코드블록 대신 검증 명령 명시. Task 7은 감사(AC-6) 후 재설계 — `is_tool_generated` 실로직 기반 폐기물 blocklist를 Step 2에 구체 코드로 명시(초판의 "실로직 미확인 open 지점" 해소).

**3. Type consistency:** `Req` dict 키(name/body/scenarios), `Issue`(level/msg), `validate()→{valid,issues}` 시그니처가 Task 1→2→3 일관. `validate_delta_text`(Task 2)와 `validate`(Task 3)는 별개 진입점(전자=main 없는 델타전용, 후자=main 포함 최종) — 의도적.

**미결(CONSOLIDATION-DESIGN §11) 처리:**
1. 위임 vs 복제 → **위임 확정**(Task 4 Step 2).
2. 포팅 언어 → **Python stdlib 확정**.
3. superpowers marketplace 편집 → **불요 확정**(gap을 spec-driven에 흡수).
4. sdd-harness 완전폐기 → **확정**(Task 5, 사용자 2회 지시).

---

## 팀 감사 이력 (team-assemble + spec-audit, 2026-09-20)

3 auditor 병렬 적대검증 → **초판 Self-Contained FAIL(3/8 AC)** → 전면 개정 완료.

| AC | 초판 | 발견 | 개정 |
|----|------|------|------|
| AC-6 placeholder | ❌ | Task7이 `is_tool_generated` provenance 면제(check-canon:48, NEG13) 미인지, 뒤집는 코드 없이 서술 | Task7 재설계 — 면제 유지 + 폐기물 blocklist 별도 채널(self-contained 코드) |
| AC-7 validate 실행 | ❌ | 실 pytest 8/9, BUG-1(rule12 unpaired-FROM) + rule12 4종·rule11 dup 미구현 | auditor-validate support fix → **17 passed**, `scripts/`에 배치 확정 |
| AC-8 근본성 | ❌ | GAP1 제거 과소범위(openspec 7프로젝트 확산, bounty만 제거=진단한 병리 재현) + GAP2 게이트 자기모순 | Task6 → owned 7곳 동시제거 + 순서 불변식(Task6→7) |
| AC-1,2,5 | ✅ | 경로·의존·트리 정합 | — |
| AC-3 | ⚠️ | held-out 검증 게이트 생략 | Task4 Step3 흡수패턴 검증 추가 |

**SOFT**: GAP3(superpowers 직접진입 한계, 자동발견 특성상 완전차단 불가) → Task4 라우팅 우선권 + LIMITS 명시 · GAP4(fork divergence) → `validate_spec.py` fork-drift 스탬프.

**잔여 TODO**: rule12 신규 메시지(RENAMED-FROM∩MODIFIED, RENAMED-TO∩ADDED)를 openspec `validator.js` 원문과 축자 대조(cosmetic — 검출·verdict는 정합).
