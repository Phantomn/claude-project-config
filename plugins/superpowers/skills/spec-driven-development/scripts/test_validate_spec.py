# test_validate_spec.py — transcribed VERBATIM from CONSOLIDATION-PLAN.md Task 1/2/3
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

# ---- Task 2 ----
from validate_spec import validate_delta_text

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

# ---- Task 3 ----
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

# ---- fix regression fixtures (BUG-1, GAP-1, GAP-2, LOW) ----
BT = chr(96)

def test_bug1_unpaired_from_in_removed():   # BUG-1: fixture (e) 두 번째 에러
    t = ("## RENAMED Requirements\n\n"
         f"- FROM: {BT}### Requirement: Old Login{BT}\n"
         f"- FROM: {BT}### Requirement: Old Signup{BT}\n"
         f"- TO: {BT}### Requirement: New Signup{BT}\n\n"
         "## REMOVED Requirements\n\n### Requirement: Old Login\n")
    errs = _errs(t)
    assert any('no matching TO' in m for m in errs)
    assert any('RENAMED and REMOVED' in m and 'Old Login' in m for m in errs)

def test_gap1_mod_removed():                # GAP-1 rule12 MOD∩REMOVED
    t = ("## MODIFIED Requirements\n\n### Requirement: Foo\nThe system SHALL x.\n\n#### Scenario: s\n- WHEN\n- THEN\n\n"
         "## REMOVED Requirements\n\n### Requirement: Foo\n")
    assert any('present in both MODIFIED and REMOVED' in m for m in _errs(t))

def test_gap1_added_removed():              # GAP-1 rule12 ADDED∩REMOVED
    t = ("## ADDED Requirements\n\n### Requirement: Foo\nThe system SHALL x.\n\n#### Scenario: s\n- WHEN\n- THEN\n\n"
         "## REMOVED Requirements\n\n### Requirement: Foo\n")
    assert any('present in both ADDED and REMOVED' in m for m in _errs(t))

def test_gap1_renamed_from_modified():      # GAP-1 rule12 RENAMED-FROM∩MODIFIED
    t = ("## MODIFIED Requirements\n\n### Requirement: Old\nThe system SHALL x.\n\n#### Scenario: s\n- WHEN\n- THEN\n\n"
         f"## RENAMED Requirements\n\n- FROM: {BT}### Requirement: Old{BT}\n- TO: {BT}### Requirement: New{BT}\n")
    assert any('references old name from RENAMED' in m for m in _errs(t))

def test_gap1_renamed_to_added():           # GAP-1 rule12 RENAMED-TO∩ADDED
    t = ("## ADDED Requirements\n\n### Requirement: New\nThe system SHALL x.\n\n#### Scenario: s\n- WHEN\n- THEN\n\n"
         f"## RENAMED Requirements\n\n- FROM: {BT}### Requirement: Old{BT}\n- TO: {BT}### Requirement: New{BT}\n")
    assert any('RENAMED TO "New" collides with ADDED' in m for m in _errs(t))

def test_gap2_dup_renamed_to():             # GAP-2 rule11 RENAMED-TO dup
    t = ("## RENAMED Requirements\n\n"
         f"- FROM: {BT}### Requirement: A{BT}\n- TO: {BT}### Requirement: Z{BT}\n"
         f"- FROM: {BT}### Requirement: B{BT}\n- TO: {BT}### Requirement: Z{BT}\n")
    assert any('Duplicate requirement in RENAMED-TO' in m for m in _errs(t))

def test_gap2_dup_renamed_from():           # GAP-2 rule11 RENAMED-FROM dup
    t = ("## RENAMED Requirements\n\n"
         f"- FROM: {BT}### Requirement: A{BT}\n- TO: {BT}### Requirement: X{BT}\n"
         f"- FROM: {BT}### Requirement: A{BT}\n- TO: {BT}### Requirement: Y{BT}\n")
    assert any('Duplicate requirement in RENAMED-FROM' in m for m in _errs(t))

def test_low_fence_length_preserved():      # LOW: 4틱 펜스는 3틱에 안 닫힘
    doc = (BT * 4) + "\n## ADDED Requirements\n" + (BT * 3) + "\n### Requirement: X\nbody\n"
    lines = normalize(doc).split("\n"); mask = fence_mask(lines)
    # every line after the 4-tick open stays masked (short 3-tick line does NOT close it)
    assert all(mask[1:]), mask
