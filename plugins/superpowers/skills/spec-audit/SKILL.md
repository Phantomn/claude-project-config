---
name: spec-audit
description: SPEC/PLAN을 이름 지정 병렬 opus 감사자(실재 정합·완결성·근본성, 필요 시 원본 대조, Agent 도구 스폰)로 실제 소스와 교차 검증하고, 감사→수정→재감사 루프를 ❌0·⚠️0까지 소유하는 구현 전 관문.
when_to_use: /spec-audit, spec audit, spec 검증, self-contained 검토 요청 시, 또는 writing-plans 핸드오프 직전
---

# spec-audit

## 1.2 라운드 상한 (D5)

| ID | 결정 | 단계 |
|---|---|---|
| D5 | 라운드 상한 5. 라운드 5에서 합격하지 못하면 불합격 보고 후 멈춘다. 이어서 하려면 사용자가 문서를 고친 뒤 새로 호출한다 | 1 |

## 4.3 루프

**리드는 감사 판정을 하지 않는다**(심볼·경로 확인, 측정, 실행 금지 — 정본 수집·스냅샷은 C1·C2가 한다). 명령 형식은 4.7 C표만 따른다. C명령이 이 절에 정한 처리
없이 실패(exit ≠ 0)하면 리드는 그 stderr를 그대로 사용자에게 보이고, `ws`를 얻은 뒤의 실패면 C5 후, C1 실패면 C5 없이 멈춘다. **불합격 보고** = 마지막 `aggregate.md`(있으면) + 사유 한 줄(`target-modified`·
`report-invalid`·`cap`·`rejected` 중 하나), 이어서 C5 후 멈춘다.

- **S0 대상 확정**
  1. 인자에 파일 경로가 있으면 그 파일들. 없으면(인자가 지시문뿐이어도) 이 대화에서 직전에 작성·수정·언급한 spec·plan. 정할 수 없으면 AskUserQuestion으로 경로를 받는다.
  2. 역할: 경로의 디렉토리 이름 중 `plans`가 있거나 basename(소문자)에 `plan`이 있으면 plan, 디렉토리 이름 `specs` 또는 basename에 `spec`·`design`이 있으면
     spec, 아니면 AskUserQuestion. writing-plans 핸드오프에서 호출되면 방금 저장한 파일이 plan. **plan은 최대 1개**.
  3. 대상 문서가 다른 로컬 저장소를 구현 대상으로 적고 있으면 리드는 C1에 `--tree <그 저장소>`를 넘긴다. 후보 저장소가 둘 이상이면 AskUserQuestion으로 하나를 받는다.
- **S1 시작**: C1(`--skill-version` = 로드된 SKILL.md의 `스킬 버전:` 줄 값). 출력의 `ws`를 이후 모든 C명령의 `--ws`로 쓴다.
- **S2 스폰**: C1·C2의 `agents`, C3의 `invalid[].retry` 항목을 **한 메시지에서 병렬** `Agent`로 스폰: `subagent_type "general-purpose"`, `model "opus"`,
  `name <항목 name>`, `description "spec-audit <항목 name>"`, `prompt "다음 파일을 Read하고 그 지시만 따르라: <항목 prompt>"`. 매 라운드 새로 스폰하고,
  이전 감사자에게 SendMessage로 재감사를 맡기지 않는다. 스폰부터 S3의 C3가 성공할 때까지 리드는 대상 문서를 수정하지 않는다.
- **S3 집계**: 스폰한 감사자가 모두 응답하면 C3. exit 3이고 `target_modified`가 있으면 불합격 보고(`target-modified`). `invalid`가 있으면: 모든 `retry`가
  null이 아니면 그 항목들을 S2로 스폰하고 S3 반복, 하나라도 null이면 불합격 보고(`report-invalid`, `invalid[].reason` 목록을 함께 보인다).
- **S4 판정**: C4. action별 행동은 J1 "리드 행동" 열.
- **S5 수정**: C4 `fix.align` 항목은 리드가 바로 반영한다 — 각 항목의 `affected`까지 한 번에. `fix.approval` 항목은 항목별 수정안 diff와 함께 AskUserQuestion 1회
  ("전부 승인" / "거절"). 사용자는 항목별로 다른 수정 지시를 적을 수 있고, 리드는 그 지시대로 반영한다(승인으로 본다). 리드는 finding의 옳고 그름을 확인하지
  않는다 — 사용자의 승인·거절만 받는다(재판정 경로 없음, L12). 거절된 항목이 하나라도 있으면 반영분은 둔 채 불합격 보고(`rejected`). `fix`가 비어 있으면(미검토 줄만 남은 경우) 바로 S6.
  반영 후 C9. `failed` 중 `fix_class`가 `align`인 항목은 다시 고치고 C9를 한 번 더 부른다(S5에서 C9는 최대 두 번, 리드는 check 결과를 판정하지 않는다). 남은 실패는 두고
  S6 — 다음 C3가 finding으로 다시 낸다. 반영 후 수정 여부를 다시 묻지 않고 S6. 리드는 stash·커밋·되돌리기를 하지 않고 미커밋 변경을 묻지 않는다.
- **S6 다음 라운드**: C2(`--round` = 직전 N + 1) → S2.
- **끝**: 합격(J1 `pass`)이면 `aggregate.md`를 보고하고 C5. 단독 호출이면 멈춘다(합격 ≠ 구현 승인). writing-plans 핸드오프에서 호출됐으면 합격 시 핸드오프로
  돌아가고 불합격이면 멈춘다. 사용자가 중단을 원하면 C5 후 멈춘다.

**닫힘**: C2는 S5 뒤에만, `cap`은 라운드 상한(D5)에서 나오므로 라운드는 상한을 넘지 않는다. S3·S4·S5의 모든 분기는 "다음 라운드" 또는 "보고 후 멈춤"이다. 원본 재현 문서의
심판 부재는 라운드 1의 `oracle-missing`과 oracle 감사자로 처리한다(4.6).

## 4.4.0 결함 판정 기준

finding은 아래 유형 중 하나여야 하고 그 유형의 필수 근거를 `evidence`에 모두 담아야 한다. 하나라도 없으면 finding이 아니다.

| 유형 | 판정 질문 | 필수 근거 | class |
|---|---|---|---|
| 사실 불일치 | 현존하는 것(파일·심볼·줄·명령 동작)에 대한 진술이 실제와 다른가 | 대상 줄 + 실제를 보이는 출력 또는 `file:line` | `ref-missing` `ref-mismatch` `exec-fail` `oracle-deviation` |
| 내부 모순 | 두 진술이 동시에 참일 수 없는가 | 두 줄 + 둘이 충돌하는 입력 하나 | `cross-doc-conflict` `sync-miss` `ordering` `interface-mismatch` `constraint-drift` |
| 계약 공백 | 문서의 다른 지점이 기대는 동작이 정해지지 않았는가 | 기대는 지점(줄) + 그 지점에 다른 결과를 내는 두 구현 | `contract-gap` `placeholder` |
| 검증 불가 | 요구가 있는데 합격을 판정할 수단(테스트·F·명령·SC)이 없는가. | 그 요구 줄 + 수단 부재 확인 | `unverifiable-step` `assumption-form` |
| 전제 반증 | 기대는 가정이 실측으로 거짓인가 | 가정 줄 + 실측 명령과 출력 | `premise` |
| 근본성 결함 | 문서가 밝힌 원인을 처방이 제거하지 못하는가 | 원인 진술 줄 + 처방 후 증상이 재발하는 경로 | `root-cause` `regression` `security` `concurrency` |
| 범위 결함 | 같은 원인의 다른 발생지가 빠졌는가, 기대는 곳 없는 요소가 있는가 | 그 발생지 또는 기대는 곳 부재 확인 | `under-scope` `over-scope` `requirement-uncovered` `oracle-missing` |
| 규칙 위반 | 프로젝트 규칙 파일 조항이나 대상 문서의 결정을 어기는가 | 규칙 `path:line` 또는 결정 ID + 위반 줄 | `rule-violation` |

**결함이 아닌 것**(finding으로 쓰지 않는다): 기대는 지점을 댈 수 없는 동작의 미정(구현 재량, 0절 2), 모호함 없는 표현·문체 선호, 결함 유형 없이 "더 나은 설계"
제안, 배정 범위와 겹치지 않는 줄(예외는 4.4.1 refs 짝 동기화), **대상 문서의 LIMITS·Out-of-scope에 이미 받아들인 경우를 다시 지적하는 것**,
**문서가 다루지 않는 경우(장치 부재)를 지적하면서 그 경우가 실제로 일어남을 실행한 명령의 출력(X 또는 X/head) 또는 기록된 관찰(로그·문서)로
보이지 못하는 것** — 지어낸 입력만으로는 부족하고, 기록된 관찰은 대상 문서 밖의 로그·문서다. 이런 LIMITS 추가 제안은 ⚠️가 아니라 보고 파일의 메모(4.5.3)로
쓴다. 이 제외는 4.4.1이 소유 검사로 정한 누락(`oracle-missing`·`requirement-uncovered`·`unverifiable-step`·`under-scope`·`assumption-form`)과 규칙 위반에는
적용하지 않는다 — 표의 필수 근거로 충분하다. 문서가 이미 정한 규칙의 모호함(계약 공백)·모순도 구성한 입력으로 충분하다.

## 4.4.1 감사 축

| axis | 소유 검사 |
|---|---|
| `refs` | 참조 실재(4.4.3), 심볼 3분류·경로 해석·파일 참조(4.4.2), 문서 간·문서 내부 충돌(class `cross-doc-conflict`: 대상 각 문서의 내부 모순, 대상 사이, 대상·other, other 내부), PLAN 내부 정합(Task Consumes ⊆ 앞선 Task Produces, Global Constraints 값 = spec 원문 값, 생성 Step이 사용보다 앞, 삭제 Step이 마지막 사용보다 뒤), N≥2 짝 동기화(직전 diff가 바꾼 용어·값·심볼을 언급하는 **모든 곳** — 배정 범위 밖 target 허용) |
| `selfcontained` | placeholder(4.4.4), **요건→Task** 커버리지(유일 소유), Step의 검증 가능한 결과, Review Focus 각 줄의 고정 테스트, Success Criteria의 기계적 판정 가능성, 구현 전 검증 가능한 명령·코드의 실제 실행(4.4.5), D7 가정 형식(4.4.7) |
| `rootcause` | 임시 처방 여부, 과소범위, 과잉범위(spec에 없는 기능·구현 1개 인터페이스·미사용 스캐폴딩·투기적 추상화), 전제 반증(X에서 실측 가능), 회귀·동시성·보안, 프로젝트 규칙(4.4.6), 재현·이식·마이그레이션 spec의 Reference Oracle 누락(`oracle-missing`), D7 대안의 실행 가능성 |
| `oracle` | 스폰 조건(4.6)일 때만. Reference Oracle 절이 지정한 원본(경로·버전·범위)과 spec·plan의 동작·구조·값 대조 |

결함인지는 4.4.0으로만 판정한다. 대상 문서가 자기 계약/재량 경계를 선언하면 그 선언이 판정 근거가 된다.

## 4.4.7 D7 가정 형식

가정 항목이 ① 가정(한 문장) ② 실측 프로브(PLAN의 구체 Step: 명령 + 기대 결과, 그 사실에 기대는 첫 Task 이전 또는 그 Task의 첫 Step. spec 단독 감사면
"구현 Task 1" 지정만 확인) ③ 실패 시 대안(구체 행동)을 모두 가지면 그 검증 불가 사항은 finding이 아니다. 형식 위반은 selfcontained `assumption-form`(`align`),
대안 실행 불가는 rootcause `premise`(`requirement`).

## 4.5.4 집계 원칙과 사용자 보고

- 축이 다른 finding은 충돌로 보지 않고 모두 남긴다. ❌를 ⚠️로 내리는 경로도, finding을 빼는 재판정 경로도 없다.
- **미검토 줄**(review-gap): 축별로 (각 감사자 coverage ∩ 그 감사자 배정 범위, 그 감사자 `context` finding target 제외)의 합집합이 그 축 배정 범위 합집합을 덮지 못한 줄.
- **직전 미해소**: `resolved` 블록에서 `unresolved`인 id.
- `aggregate.md`(C4가 쓰고 리드가 그대로 보인다):
```markdown
# SPEC Audit · round <N> · <action>
대상: <targets rel> · 플러그인 <plugin_version> · 감사자: <name 목록>
fail <n> · unverified <n> · review-gap <n줄> · 직전 미해소 <n>

| id | 판정 | 축 | 위치 | 주장 | 근거 | 수정 분류 | 영향 위치 |
|---|---|---|---|---|---|---|---|
```

## 4.7 J1 판정 규칙

| action | 조건 | 리드 행동 |
|---|---|---|
| `pass` | counts.fail 0 ∧ counts.unverified 0 ∧ review-gap 0 ∧ 직전 미해소 0 | 4.3 "끝"의 합격 |
| `cap` | N ≥ 라운드 상한(D5) | 불합격 보고(`cap`) |
| `fix` | 그 외 | S5 |

## 4.7 명령 (audit_ws.py)

호출 형식: `python3 <Base directory>/scripts/audit_ws.py <명령>`

스킬 버전: 88bde9bd251b

| ID | 명령·형식 | 동작 |
|---|---|---|
| C1 | `init --round 1 --skill-version V [--plan P] [--spec S]... [--tree DIR]` | `V`가 디스크 SKILL.md(`audit_ws.py` 기준 `parents[1]/SKILL.md`)의 내용 해시 — 그 파일에서 `스킬 버전:` 줄을 뺀 내용의 sha256 앞 12자, `audit_ws.skill_hash()`(정규화는 구현 재량) — 와 다르면 실패(stderr에 `` `/reload-plugins`(플러그인을 캐시에서 로드하는 설치면 세션 재시작) 필요 ``). plan 0–1개, spec 0개 이상, 합계 1개 이상(아니면 실패). 인자 파일이 없거나 `<tree>`가 git인데 HEAD가 없으면 실패. W와 `TMPROOT/spec-audit/<slug>/`가 있으면 지우고 새로 만든다(D6). **정본 자동 수집**: spec·plan 본문에서 "정본"(부분 문자열 — "상위 정본"·"XML 정본" 등 포함)·"canonical"과 같은 줄의 백틱 토큰(첫 공백 앞까지, `~/`로 시작하면 홈 디렉토리로 펼친다) 중 `.md`로 끝나고 4.4.2 경로 해석 후보(①②③) 중 작업트리에 실재하는 파일 전부에서 C1 인자로 받은 plan·spec(realpath)을 뺀 것을 other로 추가. `.gitignore`·targets.json·스냅샷·assign.json·prompts·X 생성. stdout = C8 |
| C2 | `init --ws W --round N` (N≥2) | `W/round-<N-1>/`의 targets.json·스냅샷·aggregate.json이 없거나 대상 파일이 없으면 실패. 대상 = 직전 라운드 targets와 같은 파일. 새 스냅샷·targets.json·diff.patch·scope.json(C7)·배정(4.6)·prompts·X 생성. stdout = C8 |
| C3 | `aggregate --ws W --round N` | ① 대상 변경 탐지(4.5.5) — 바뀐 대상이 있으면 exit 3, stdout `{"target_modified":[rel]}`. ② reports/ 전체를 다시 읽는다. `<name>-retry` 보고가 있으면 원래 보고 무시. 검증 위반(4.5.1·4.5.2·4.5.3 형식, `resolved`의 비배정 id·배정 id 누락·가리킨 finding id 부재, finding `target`이 그 축의 대상 줄과 겹치지 않거나 N≥2에서 그 감사자 배정 범위와 겹치지 않음(refs 예외는 4.4.1), target·affected의 라운드가 이 라운드가 아님, `check`가 null이 아닌데 R/snapshot과 각 대상 사본 맨 앞에 그 파일의 줄 수만큼 빈 줄을 넣은 사본(위치는 구현 재량 — 앞에서 센 줄·범위 주소는 원래 내용을 가리키지 못한다) 중 하나에서라도 exit 1이 아님(0·check 오류 — 줄 위치에 묶인 check를 거른다), 배정 감사자 보고 누락) → exit 3, stdout `{"invalid":[{"reason","retry": <C8 agents 원소 또는 null>}]}`(retry 생성 = assign.json 추가·프롬프트·X). ③ 정상 → N≥2면 먼저 직전 aggregate.json `checks`의 각 finding을 이번 스냅샷 위치(target·affected, C7 새 위치)로 옮기고 check를 R/snapshot에서 실행 — exit 0이 아니면 그 finding을 옮긴 위치로 이번 라운드 findings에 넣는다(id·키 그대로, `evidence` = `exit <code>` 한 줄 + 실행 출력). 단 이번 라운드 `resolved`에서 `unresolved`로 표시된 id는 넣지 않는다(감사자가 다시 쓴 finding이 대신한다). aggregate.json = `{"findings":[유효 finding과 다시 넣은 finding],"review_gap":{axis:[범위]},"unresolved":[id],"counts":{"fail","unverified"},"checks":{id: finding}}` 작성 — `checks` = 옮긴 직전 `checks` ∪ 이번 보고의 유효 finding 중 `check`가 null이 아닌 것. stdout `{}` |
| C4 | `decide --ws W --round N` | J1로 action 결정, decision.json·aggregate.md 작성. stdout = `{"action","fix":{"align":[id],"approval":[id]}}` — `fix`는 이번 라운드 finding(4.5.1)을 `fix_class`로 나눈다 |
| C5 | `clean --ws W` | `TMPROOT/spec-audit/<slug>/` 삭제(W 유지) |
| C9 | `check --ws W` | W의 가장 큰 N의 `round-<N>/aggregate.json`이 없으면 실패. K를 새로 만들어 현재 대상 파일을 그 라운드 스냅샷과 같은 이름으로 복사하고, 그 `checks`를 K에서 실행(실행 조건은 4.5.1 `check`). stdout `{"failed":[{"id","fix_class","claim","output"}]}` — exit 0이 아닌 check, `output` 형식은 C3 ③ `evidence`와 같다 |
