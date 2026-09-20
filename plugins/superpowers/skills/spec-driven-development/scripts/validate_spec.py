# ported (thin B2) from @fission-ai/openspec@1.13.1 core/validation/validator.js (~1433 LOC -> ~284)
# fork-drift guard: upstream major bump 시 references/validator-port-spec.md 규칙 재대조 필요.
# validate_spec.py  — transcribed VERBATIM from CONSOLIDATION-PLAN.md Task 1/2/3
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
            fence = m.group(1); mask.append(True); continue   # preserve full marker length
        if fence is not None:
            mask.append(True)
            if re.match(rf'^\s*{re.escape(fence[0])}{{{len(fence)},}}\s*$', ln):
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

# ---- Task 2 ----

def has_shall(body):
    return re.search(r'\b(SHALL|MUST)\b', body) is not None

def _parse_removed(body_lines, mask):
    names = []
    for ln in body_lines:
        m = re.match(r'^\s*[-*+]?\s*`?###\s*Requirement:\s*(.+?)`?\s*$', ln, re.I)
        if m: names.append(_norm_name(m.group(1)))
    return names

def _parse_renamed(body_lines):
    # returns (pairs, from_names, to_names). from/to name lists are the FULL declared
    # names (paired or not) — openspec rule 11/12 fold ALL FROM/TO names, not just paired.
    pairs, pending, froms, tos = [], [], [], []
    for ln in body_lines:
        fm = re.match(r'^\s*[-*+]?\s*FROM:\s*`?###\s*Requirement:\s*(.+?)`?\s*$', ln, re.I)
        tm = re.match(r'^\s*[-*+]?\s*TO:\s*`?###\s*Requirement:\s*(.+?)`?\s*$', ln, re.I)
        if fm:
            name = _norm_name(fm.group(1)); froms.append(name)
            if pending: pairs.append(("UNPAIRED", pending.pop()))   # 이전 FROM이 TO 못 만남
            pending.append(name)
        elif tm:
            name = _norm_name(tm.group(1)); tos.append(name)
            if pending: pairs.append((pending.pop(), name))
            else: pairs.append(("NO_FROM", name))
    pairs += [("UNPAIRED", f) for f in pending]
    return pairs, froms, tos

def validate_delta_text(text, main_specs_dir=None):
    lines = normalize(text).split("\n"); mask = fence_mask(lines)
    sections = split_sections(lines, mask)
    return check_delta(sections, mask, main_specs_dir)

def check_delta(sections, mask, main_specs_dir=None):
    issues = []; total = 0
    added = parse_requirements(sections.get("added requirements", []), mask)
    modified = parse_requirements(sections.get("modified requirements", []), mask)
    removed = _parse_removed(sections.get("removed requirements", []), mask)
    renamed, rfroms, rtos = _parse_renamed(sections.get("renamed requirements", []))
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
    # dup within section (rule 11 — incl. RENAMED FROM/TO)
    for label, names in (("ADDED", [r["name"] for r in added]), ("MODIFIED", [r["name"] for r in modified]),
                         ("REMOVED", removed), ("RENAMED-FROM", rfroms), ("RENAMED-TO", rtos)):
        seen = set()
        for n in names:
            if n in seen: issues.append({"level": "ERROR", "msg": f'Duplicate requirement in {label}: "{n}"'})
            seen.add(n)
    # rename pairs (rule 10)
    for a, b in renamed:
        if a == "UNPAIRED": issues.append({"level": "ERROR", "msg": f'RENAMED FROM: "{b}" has no matching TO: line'})
        elif a == "NO_FROM": issues.append({"level": "ERROR", "msg": f'RENAMED TO: "{b}" has no matching FROM: line'})
    # cross-section conflicts (rule 12) — FROM/TO sets fold ALL declared names (paired or not)
    A = {r["name"] for r in added}; M = {r["name"] for r in modified}
    R = set(removed); F = set(rfroms); T = set(rtos)
    for n in F & R: issues.append({"level": "ERROR", "msg": f'"{n}" present in both RENAMED and REMOVED'})
    for n in A & M: issues.append({"level": "ERROR", "msg": f'"{n}" present in both ADDED and MODIFIED'})
    for n in M & R: issues.append({"level": "ERROR", "msg": f'"{n}" present in both MODIFIED and REMOVED'})
    for n in A & R: issues.append({"level": "ERROR", "msg": f'"{n}" present in both ADDED and REMOVED'})
    for n in F & M: issues.append({"level": "ERROR", "msg": f'MODIFIED "{n}" references old name from RENAMED FROM'})
    for n in T & A: issues.append({"level": "ERROR", "msg": f'RENAMED TO "{n}" collides with ADDED'})
    # empty section header present but no entries (rule 13)
    for title in _DELTA_TITLES:
        if title in sections:
            rp, rf, rt = _parse_renamed(sections[title])
            if not parse_requirements(sections[title], mask) \
               and not _parse_removed(sections[title], mask) and not (rp or rf or rt):
                issues.append({"level": "ERROR", "msg": f'Delta section "{title}" found, but no requirement entries parsed'})
    if total == 0:
        issues.append({"level": "ERROR", "msg": "Change must have at least one delta"})
    return issues

# ---- Task 3 ----

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

# ---- fixtures for demo (references §3) ----

_FX_A = """## ADDED Requirements

### Requirement: User Login
The system SHALL authenticate users by email and password.

#### Scenario: Valid credentials
- **WHEN** a user submits a correct email and password
- **THEN** the system grants a session
"""

_FX_B_MAIN = """## Requirements

### Requirement: User Login
The system SHALL authenticate users.

#### Scenario: Valid credentials
- **WHEN** correct creds
- **THEN** grant session

#### Scenario: Locked account
- **WHEN** account is locked
- **THEN** deny with 423
"""

_FX_B = """## MODIFIED Requirements

### Requirement: User Login
The system SHALL authenticate users, now with rate limiting.

#### Scenario: Valid credentials
- **WHEN** correct creds
- **THEN** grant session
"""

_FX_C = """## Notes

### Requirement: Something
The system SHALL do a thing.

#### Scenario: x
- **WHEN** a
- **THEN** b
"""

_FX_D = """## ADDED Requirements

### Requirement: Password Reset
The system SHALL allow a user to reset a password via email.
"""

_FX_E = """## RENAMED Requirements

- FROM: `### Requirement: Old Login`
- FROM: `### Requirement: Old Signup`
- TO: `### Requirement: New Signup`

## REMOVED Requirements

### Requirement: Old Login
"""

_FX_BONUS = """## ADDED Requirements

### Requirement: Export Data
The system exports the user's data as JSON.

#### Scenario: Basic export
- **WHEN** user clicks export
- **THEN** a JSON file downloads
"""

def demo():
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
