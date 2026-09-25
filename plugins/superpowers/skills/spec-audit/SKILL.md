---
name: spec-audit
description: SPEC/PLAN을 3인 적대 감사팀(병렬 opus teammate)으로 실제 소스와 교차 검증해 Self-Contained·근본성까지 엄격 판정하는 구현 전 게이트. 감사팀이 이 스킬에 내장돼 있어 /team-assemble 병행 호출이 필요 없다. 감사만 하며 구현은 착수하지 않는다.
triggers:
  - /spec-audit
  - spec audit
  - spec 검증
  - self-contained 검토
---

# /spec-audit — SPEC 적대 감사팀

## 목적

SPEC/plan/todo를 구현 전에 **감사팀으로** 실제 소스 대비 교차 검증한다. 참조 오류뿐 아니라
"맥락 없는 구현자가 이 문서만으로 완성할 수 있는가(Self-Contained)"와 "임시 처방이 아닌가(근본성)"를 판정한다.

> 왜 팀이 내장인가(2026-09-25 실측, 51세션·28프로젝트): 사용자가 `/team-assemble`+`/spec-audit`을 같은
> 인자로 240회+ 짝 호출했고, 단독 실행 시 리드가 혼자 grep 감사 후 합격 선언·승인 없는 구현 착수가 반복됐다.
> 팀이 잡은 FAIL(placeholder·실행·근본성)은 정적 Step 1–6 밖에 있었다. 그래서 감사팀이 이 스킬의 본체다.

## 트리거

```
/spec-audit <spec-file> [plan-file] [todo-file]
```

인자가 없으면 최근 변경된 SPEC/PLAN을 찾아 대상으로 삼고, 보고서 머리에 대상 목록을 적는다.
SPEC과 PLAN이 모두 있으면 **둘 다** 감사한다.

## 실행 모델 (고정 — 생략 불가)

**기본 자세(인자 없이도 적용):** 순차적으로 단계를 나눠 사고, 임시 처방이 아닌 근본 원인 기준,
Self-Contained 엄격 판정. 사용자가 매번 이 문장을 붙일 필요가 없다.

1. **리드(나)는 감사하지 않는다.** 대상 문서 확정 → 감사팀 병렬 스폰 → 종합만 한다.
   리드가 직접 grep/Bash로 감사해 결론을 내면 이 스킬 위반이다.
2. **팀 구성 확인 질문 없이 바로 스폰한다**(실측 62건 중 48건 권장안 그대로 승인 — 형식적 마찰).
   사용자가 "넓게"를 요구하면 축을 쪼개 4–7명으로 늘린다.
3. `Agent` 도구로 **한 메시지에 3명 병렬**: `subagent_type: "general-purpose"`, `model: "opus"`,
   `name` 필수(없으면 SendMessage 재질의 불가). 프롬프트에 대상 문서 전 경로·자기 축·
   **"파일 수정 금지(read-only)"**·출력 형식(항목별 ✅/❌/⚠️ + 근거 `file:line` + 권장 조치)을 넣는다.

| name | 축 | 체크 |
|------|----|------|
| `auditor-refs` | 참조 실존·문서 정합 | 아래 정적 Step 1–6 |
| `auditor-selfcontained` | 맥락 없는 구현 가능성 | placeholder 0(TBD·TODO·"적절히"·"등"), 인터페이스·타입·시그니처 명세, 요건→태스크 커버리지(누락 요건), **문서 속 명령·코드 실제 실행** |
| `auditor-rootcause` | 근본성·반증 | 임시 처방 여부, 과소범위(같은 병리의 다른 발생지 누락), 전제 반증, 회귀·동시성·보안 |

**실행 검증 규칙:** 문서의 명령·코드 블록은 스크래치 디렉토리에서 실제로 돌린다. 못 돌렸으면
"⚠️ 미검증(사유)"이지 ✅가 아니다. 정적 대조만으로 실행 축을 ✅ 처리하지 않는다.

## auditor-refs 체크리스트 — 정적 Step 1–6 (순서 고정)

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

## 종합 (리드)

세 보고서를 합친다. 중복 제거, 감사자 간 판정이 갈리면 근거(`file:line`·실행 출력)가 있는 쪽을 채택하고
판단이 안 서면 ⚠️로 둔다. 각 항목에 출처 감사자를 붙인다.

## 출력 형식

```markdown
# SPEC Audit 결과
대상: [감사한 문서 경로] · 감사팀: auditor-refs / auditor-selfcontained / auditor-rootcause

## ✅ 통과 (N개)
- [심볼/파일]: 확인됨

## ❌ 실패 (N개)
- [심볼/파일]: 미존재 — [권장 조치]

## ⚠️ 경고 (N개)
- [항목]: [충돌/누락 내용]

## 의존성 체인
- [Task A] → [Task B]: ✅ 올바름 / ❌ 역전 위험

## 결론
[감사 합격 여부] + [해소 필요 항목 수] + [미검증 항목과 사유]
```

## 합격 기준

- ❌ 0개 → 감사 합격
- ❌ 1개 이상 → 문서 수정 후 **같은 3축 팀으로 재감사**(이전 ❌ 해소 여부부터 확인)
- ⚠️ 3개 이상 → 사용자 확인 후 진행

## 합격 후 — 여기서 멈춘다

**감사 합격 ≠ 구현 승인.** 보고서를 내고 종료한다. 구현은 사용자가 명시적으로 승인할 때
`superpowers:spec-driven-development` Phase 4(Implement)로 진행한다. 승인 없이 구현에 착수하지 않는다.

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
- `/superpowers:team-assemble`: 범용 동적 팀 구성기. SPEC 감사에는 쓰지 않는다(감사팀은 위에 내장).
  함께 호출돼도 이 스킬의 실행 모델을 따른다.
- `/superpowers:spec-driven-development`: 이 감사는 그 파이프라인의 Tasks→Implement 사이 게이트다.
