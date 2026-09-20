---
name: spec-audit
description: SPEC 문서의 심볼/파일 참조를 실제 소스와 교차 검증. 팀 스폰 전 Self-Contained 품질 게이트.
triggers:
  - /spec-audit
  - spec audit
  - spec 검증
  - self-contained 검토
---

# /spec-audit — SPEC Cross-Document Audit

## 목적

SPEC/plan/todo 다중 문서를 팀 스폰 전에 실제 소스 대비 교차 검증.
심볼 누락, 경로 오류, 의존성 누락, 문서 간 충돌을 사전 탐지.

## 트리거

```
/spec-audit <spec-file> [plan-file] [todo-file]
```

## 검증 파이프라인 (순서 고정)

### Step 1: 심볼 존재 검증
SPEC에 언급된 모든 심볼(함수명, 클래스명, 상수명)을 Serena `find_symbol`로 실제 소스에서 확인.

```
find_symbol(name: "<symbol>", relative_path: "src/")
```

- 존재 → ✅
- 미존재 → ❌ (제거/이름 변경 여부 확인 필요)

### Step 2: 파일 경로 검증
SPEC에 언급된 모든 파일 경로가 실제로 존재하는지 확인.

```bash
ls <mentioned-path> 2>&1
```

- 존재 → ✅
- 미존재 → ❌ (생성 예정 파일은 별도 표시)

### Step 3: 의존성 체인 검증
plan/todo의 Task 간 `blockedBy` 의존성이 올바른지 확인.
- 삭제 대상 파일 Task가 해당 파일 참조 테스트 수정 Task보다 **후행**인지 검증
- 순환 의존성 탐지

### Step 4: 문서 간 충돌 탐지
동일 심볼/파일이 SPEC, plan, todo에서 **다른 처리 방침**으로 기술됐는지 확인.
예: SPEC은 "삭제", plan은 "수정 후 유지"

### Step 5: 테스트 픽스처 충족도
plan에 기술된 코드 변경에 대응하는 테스트 수정 Task가 존재하는지 확인.

### Step 6: SPEC 참조 파일 ⊆ 파일트리 (구현 전 SPEC 필수)
SPEC 본문(§Command·§Interface Contracts·§Testing 등)이 **참조하는 모든 파일 경로가 §파일트리 블록에 등재**됐는지 대조. "구현자가 트리대로 생성하면 완성"을 명시한 SPEC은, 트리 누락 파일이 있으면 그 명제가 깨져 Self-Contained 위반(❌).

```bash
# SPEC 본문 참조 파일명(*.py/*.c/*.xml/*.conf/fixtures 등) 추출 → 파일트리 블록 내 존재 여부
# 트리 밖에서만 언급된 파일 = ❌ 트리누락
grep -oE '[A-Za-z0-9_./-]+\.(py|c|xml|conf|json|sh|txt|pem|tle|bin)|fixtures/|_stub[A-Za-z_]*' <spec-file> | sort -u
# 각 항목이 파일트리 코드블록(```…```) 내에도 나타나는지 수동/스크립트 대조
```

- 전 참조 파일 트리 등재 → ✅
- §Command/§Interface가 참조하나 트리 미기재 → ❌ (트리에 추가). wt-sat 사례: `fixtures/`·`_stub_base.py` 2R 연속 검출(동형 재발).

## 출력 형식

```markdown
# SPEC Audit 결과

## ✅ 통과 (N개)
- [심볼/파일]: 확인됨

## ❌ 실패 (N개)
- [심볼/파일]: 미존재 — [권장 조치]

## ⚠️ 경고 (N개)
- [항목]: [충돌/누락 내용]

## 의존성 체인
- [Task A] → [Task B]: ✅ 올바름 / ❌ 역전 위험

## 결론
[팀 스폰 가능 여부] + [해소 필요 항목 수]
```

## 합격 기준

- ❌ 0개 → 팀 스폰 허용
- ❌ 1개 이상 → 해소 후 재감사 필수
- ⚠️ 3개 이상 → 사용자 확인 후 진행

## 합격 후 구버전 심볼 일괄 교체 (CTF 저작 — `challenges/` 프로젝트 한정)

> `.claude/scripts/doc-replace.py` 를 가진 프로젝트에서만 해당. 다른 프로젝트는 이 절을 건너뛴다.

audit 결과 구버전 심볼이 다수 문서에 잔류할 경우, Edit 도구 대신 아래 스크립트를 사용한다.
(한국어 멀티바이트 파일에서 Edit 도구 매칭 실패가 반복될 때 우선 적용)

```bash
# 단일 심볼 교체 (dry-run으로 카운트 먼저 확인)
python3 .claude/scripts/doc-replace.py --dry-run OLD_SYMBOL NEW_SYMBOL \
  challenges/<slug>/SPEC.md challenges/<slug>/DESIGN.md \
  challenges/<slug>/tasks/CORE-plan.md challenges/<slug>/tasks/CORE-todo.md

# 확인 후 실제 적용
python3 .claude/scripts/doc-replace.py OLD_SYMBOL NEW_SYMBOL \
  challenges/<slug>/SPEC.md challenges/<slug>/DESIGN.md \
  challenges/<slug>/tasks/CORE-plan.md challenges/<slug>/tasks/CORE-todo.md

# 여러 심볼 일괄 교체 (map.json)
# map.json: [{"old": "DEBUG_BLOB", "new": "FAKE_SHAMIR"}, ...]
python3 .claude/scripts/doc-replace.py --map map.json \
  challenges/<slug>/SPEC.md challenges/<slug>/DESIGN.md \
  challenges/<slug>/tasks/CORE-plan.md challenges/<slug>/tasks/CORE-todo.md
```

## 연관 스킬

- `/thinking --panel`: 다중 관점 교차 검증 (이 스킬 실행 전 선행 권장)
- `/superpowers:team-assemble` (+ `/build`): 이 스킬 합격 후 스폰
