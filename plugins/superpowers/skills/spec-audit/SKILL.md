---
name: spec-audit
description: SPEC/PLAN을 병렬 opus 감사자(실재 정합·완결성·근본성, 필요 시 원본 대조)로 실제 소스와 교차 검증하는 구현 전 관문. 감사는 최대 2회(전체 1회 + 수정분 재검토 1회)이고, 모든 지적에 처분(반영·기각·수용)을 기록하고 반영분의 check가 통과하면 끝난다.
when_to_use: /spec-audit, spec audit, spec 검증, self-contained 검토 요청 시, 또는 writing-plans 핸드오프 직전
---

# spec-audit

## 1.2 끝의 정의 (D23)

| ID | 결정 |
|---|---|
| D23 | 감사는 최대 2회다 — 라운드 1 = 전체 감사, 라운드 2 = 라운드 1 뒤 리드가 고친 줄만 1회 재검토(고친 것이 없으면 없음). 라운드 3은 없다. **끝 = 모든 지적에 처분(`apply` 반영 · `reject` 기각 · `accept` 한계로 수용) ∧ 반영한 지적의 check 통과 ∧ (라운드 1 뒤 고쳤으면) 라운드 2를 거침.** 판정은 C6 `finish`가 한다. "감사자가 0건을 찾을 때까지"는 끝의 정의가 아니다 — 새 감사자는 이력과 무관하게 문서 1,000줄당 15~26건을 찾아 수렴하지 않았다(DECISIONS.md D23 근거) |

## 4.3 절차

**리드는 감사 판정을 하지 않는다**(감사 중 심볼·경로 확인, 측정, 실행 금지 — 정본 수집·스냅샷은 C1·C2가 한다). 명령 형식은 4.7 C표만 따른다. C명령이 이 절에 정한 처리
없이 실패(exit ≠ 0)하면 리드는 그 stderr를 그대로 사용자에게 보이고 C5 후 멈춘다(C1 실패면 C5 없이).

- **S0 대상 확정**
  1. 인자에 파일 경로가 있으면 그 파일들. 없으면(인자가 지시문뿐이어도) 이 대화에서 직전에 작성·수정·언급한 spec·plan. 정할 수 없으면 AskUserQuestion으로 경로를 받는다.
  2. 역할: 경로의 디렉토리 이름 중 `plans`가 있거나 basename(소문자)에 `plan`이 있으면 plan, 디렉토리 이름 `specs` 또는 basename에 `spec`·`design`이 있으면
     spec, 아니면 AskUserQuestion. writing-plans 핸드오프에서 호출되면 방금 저장한 파일이 plan. **plan은 최대 1개**.
  3. 대상 문서가 다른 로컬 저장소를 구현 대상으로 적고 있으면 리드는 C1에 `--tree <그 저장소>`를 넘긴다. 후보 저장소가 둘 이상이면 AskUserQuestion으로 하나를 받는다.
- **S1 시작**: C1(`--skill-version` = 로드된 SKILL.md의 `스킬 버전:` 줄 값). 출력의 `ws`를 이후 모든 C명령의 `--ws`로 쓴다.
- **S2 스폰**: C1·C2의 `agents`, C3의 `invalid[].retry` 항목을 **한 메시지에서 병렬** `Agent`로 스폰: `subagent_type "superpowers:spec-auditor"`, `model "opus"`,
  `description "spec-audit <항목 name>"`, `prompt "다음 파일을 Read하고 그 지시만 따르라: <항목 prompt>"`. **`name` 인자는 주지 않는다** — 주면 감사자가 teammate 세션으로
  떠서 audit-guard가 감사자로 식별하지 못한 관찰이 있다(LIMITS L38). 스폰부터 C3까지 리드는 대상 문서 수정과 `<tree>`·감사자 실행 디렉토리 조회를 하지 않는다(훅이 막는다).
- **S3 집계**: 스폰한 감사자가 모두 응답하면 C3. exit 3이고 `target_modified`가 있으면 사유를 보이고 C5 후 멈춘다. `invalid`가 있으면: 모든 `retry`가
  null이 아니면 그 항목들을 S2로 스폰하고 S3 반복, 하나라도 null이면 `invalid[].reason` 목록을 보이고 C5 후 멈춘다.
- **S4 처분**: `aggregate.md`를 사용자에게 보이고, 리드는 지적마다 처분 권고(`apply`·`reject`·`accept`)와 근거 한 줄을 붙여 **AskUserQuestion 1회**로 확정받는다
  ("권고대로 확정" / 항목별 지시). 사용자는 항목별로 다른 처분·수정 지시를 적을 수 있고 리드는 그대로 따른다. 리드는 권고를 위해 `<tree>`를 조회·실측할 수 있다(감사는 끝났다).
  확정한 처분을 `W/dispositions.json`(4.7 C6 형식)에 누적해 쓴다 — 라운드 2의 지적도 같은 파일에 더한다.
- **S5 반영**: `apply` 항목을 고친다 — 각 항목의 `affected`까지 한 번에. 같은 사실이 문서 여러 곳에 적혀 있으면 모두 같이 고친다. 리드는 stash·커밋·되돌리기를 하지 않는다.
- **S6 끝 판정**: C6. `done`이면 끝. 아니면 출력대로 한다 — `invalid`(처분 누락·사유 없음)는 S4로, `failed`(반영했는데 check가 아직 실패)는 다시 고친 뒤 C6,
  `review_needed`(라운드 1 뒤 고쳤고 라운드 2가 아직 없음)는 C2 → S2(라운드 2) → S3 → S4(새 지적만) → S5 → C6. **라운드 2 뒤에는 감사를 다시 열지 않는다** — 그 뒤 남은 것은
  처분과 check뿐이다(D23).
- **끝**: 완료면 `result.md`를 보고하고 C5. 단독 호출이면 멈춘다(완료 ≠ 구현 승인). writing-plans 핸드오프에서 호출됐으면 완료 시 핸드오프로 돌아간다. 사용자가 중단을
  원하면 C5 후 멈춘다.

**닫힘**: 감사(S2)는 C1·C2에서만 열리고 C2는 한 번만 성공한다(라운드 2가 있으면 실패). S6의 나머지 분기(처분·check 재실행)는 결정론이라 리드의 수정으로 끝난다.

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
| `refs` | 참조 실재(4.4.3), 심볼 3분류·경로 해석·파일 참조(4.4.2), 문서 간·문서 내부 충돌(class `cross-doc-conflict`: 대상 각 문서의 내부 모순, 대상 사이, 대상·other, other 내부), PLAN 내부 정합(Task Consumes ⊆ 앞선 Task Produces, Global Constraints 값 = spec 원문 값, 생성 Step이 사용보다 앞, 삭제 Step이 마지막 사용보다 뒤), 라운드 2 짝 동기화(diff.patch가 바꾼 용어·값·심볼을 언급하는 **모든 곳** — 배정 범위 밖 target 허용) |
| `selfcontained` | placeholder(4.4.4), **요건→Task** 커버리지(유일 소유), Step의 검증 가능한 결과, Review Focus 각 줄의 고정 테스트, Success Criteria의 기계적 판정 가능성, 구현 전 검증 가능한 명령·코드의 실제 실행(4.4.5), D7 가정 형식(4.4.7) |
| `rootcause` | 임시 처방 여부, 과소범위, 과잉범위(spec에 없는 기능·구현 1개 인터페이스·미사용 스캐폴딩·투기적 추상화), 전제 반증(X에서 실측 가능), 회귀·동시성·보안, 프로젝트 규칙(4.4.6), 재현·이식·마이그레이션 spec의 Reference Oracle 누락(`oracle-missing`), D7 대안의 실행 가능성 |
| `oracle` | 스폰 조건(4.6)일 때만. Reference Oracle 절이 지정한 원본(경로·버전·범위)과 spec·plan의 동작·구조·값 대조 |

결함인지는 4.4.0으로만 판정한다. 대상 문서가 자기 계약/재량 경계를 선언하면 그 선언이 판정 근거가 된다.

## 4.4.7 D7 가정 형식

가정 항목이 ① 가정(한 문장) ② 실측 프로브(PLAN의 구체 Step: 명령 + 기대 결과, 그 사실에 기대는 첫 Task 이전 또는 그 Task의 첫 Step. spec 단독 감사면
"구현 Task 1" 지정만 확인) ③ 실패 시 대안(구체 행동)을 모두 가지면 그 검증 불가 사항은 finding이 아니다. 형식 위반은 selfcontained `assumption-form`(`align`),
대안 실행 불가는 rootcause `premise`(`requirement`).

## 4.5.4 집계와 사용자 보고

- 축이 다른 finding은 충돌로 보지 않고 모두 남긴다. finding을 빼는 재판정 경로는 없다 — 틀렸다고 보면 사유와 함께 `reject`로 처분한다.
- **미검토 줄**: 축별로 (각 감사자 coverage ∩ 그 감사자 배정 범위, 그 감사자 `context` finding target 제외)의 합집합이 그 축 배정 범위 합집합을 덮지 못한 줄.
  `aggregate.md` 머리에 줄 수로 보인다. 끝을 막지 않는다 — 사용자가 S4에서 보고 판단한다.
- `aggregate.md`(C3가 쓰고 리드가 그대로 보인다): 머리 3줄(라운드·지적 수 / 대상·플러그인 버전·감사자 / fail·unverified·미검토 줄) + `| id | 판정 | 축 | 위치 | 주장 | 근거 | 권고 | 영향 위치 |` 표.
- `result.md`(C6가 쓴다): 완료 여부, 처분 수, check 실패 수, 지적별 처분·사유.

## 4.7 명령 (audit_ws.py)

호출 형식: `python3 <Base directory>/scripts/audit_ws.py <명령>`

스킬 버전: 4a9d09354e4b

| ID | 명령·형식 | 동작 |
|---|---|---|
| C1 | `init --skill-version V [--plan P] [--spec S]... [--tree DIR]` | 라운드 1. `V`가 디스크 SKILL.md(`audit_ws.py` 기준 `parents[1]/SKILL.md`)의 내용 해시(`스킬 버전:` 줄을 뺀 내용의 sha256 앞 12자, `audit_ws.skill_hash()`)와 다르면 실패(stderr에 `` `/reload-plugins`(플러그인을 캐시에서 로드하는 설치면 세션 재시작) 필요 ``). plan 0–1개, spec 0개 이상, 합계 1개 이상(아니면 실패). 인자 파일이 없거나 `<tree>`가 git인데 HEAD가 없으면 실패. 같은 대상의 이전 W가 있으면 지우지 않고 `<W>.<시각>`으로 옮긴다. `TMPROOT/spec-audit/<slug>/`는 지운다. **정본 자동 수집**: spec·plan 본문에서 "정본"(부분 문자열)·"canonical"과 같은 줄의 백틱 토큰(첫 공백 앞까지, `~/`는 홈으로 펼침) 중 `.md`로 끝나고 4.4.2 경로 해석 후보(①②③) 중 작업트리에 실재하는 파일 전부에서 C1 인자의 plan·spec(realpath)을 뺀 것을 other로 추가. `.gitignore`·targets.json·스냅샷·assign.json·prompts·X 생성, open.json 기록. stdout = C8 |
| C2 | `review --ws W` | 라운드 2(수정분 재검토, 1회). `W/aborted`가 있거나, 라운드 1 aggregate.json이 없거나, 라운드 2가 이미 있거나, 라운드 1 스냅샷 뒤 바뀐 줄이 없으면 실패. 대상 = 라운드 1과 같은 파일(정본 재수집 없음). 새 스냅샷·diff.patch, 축별 배정 범위 = 바뀐 줄 ∩ 그 축의 대상 줄(삭제만이면 삭제 지점 앞뒤 1줄). prompts·X 생성, open.json 기록. stdout = C8 |
| C3 | `aggregate --ws W` | 가장 큰 라운드를 집계한다. `W/aborted`가 있으면 실패. ① 대상 변경 탐지(4.5.5) — 바뀐 대상이 있으면 exit 3, stdout `{"target_modified":[rel]}`. ② reports/ 전체를 다시 읽는다. `<name>-retry` 보고가 있으면 원래 보고 무시. 검증 위반(4.5.1·4.5.2·4.5.3 형식, finding `target`이 그 축의 대상 줄과 겹치지 않음, 라운드 2에서 refs 밖 축의 target이 배정 범위와 겹치지 않음, target·affected의 라운드가 이 라운드가 아님, `check`가 null이 아닌데 R/snapshot 사본과 각 파일 앞에 그 줄 수만큼 빈 줄을 넣은 사본 중 하나에서라도 exit 1이 아님, `check`가 종료코드 가림(파이프라인의 종료코드로 `&&`·`\|\|`·`if`/`while` 조건을 정하는데 그 파이프라인이 `cut`·`sed`·`head` 등 늘 0인 필터로 끝남 — `audit_ws.masked_exit`), 배정 감사자 보고 누락) → exit 3, stdout `{"invalid":[{"reason","retry": <C8 agents 원소 또는 null>}]}`(retry는 한 번만). ③ 정상 → aggregate.json `{"findings","review_gap":{axis:[범위]},"counts":{"fail","unverified"}}`·aggregate.md 작성, open.json 삭제, stdout `{}` |
| C5 | `clean --ws W` | `TMPROOT/spec-audit/<slug>/` 삭제(W 유지). 그때 open.json이 있었으면(열린 감사를 끝내는 것 = 감사 중단) 먼저 `W/aborted`를 만든다 |
| C6 | `finish --ws W --dispositions F` | D23 끝 판정. F = `{"findings": {"<id>": {"d": "apply"\|"reject"\|"accept", "why": "<사유>"}}}` — 집계된 모든 라운드의 finding(`context` 제외) 각각에 처분, `reject`·`accept`는 `why` 필수. 반영(`apply`)한 finding 중 check가 있는 것을 현재 대상 파일 사본 K(스냅샷과 같은 파일 이름, 환경변수 `TREE`)에서 실행해 exit 0이 아니면 실패. 라운드 2가 없는데 대상이 라운드 1 스냅샷과 다르면 `review_needed`. stdout `{"done","invalid":[사유],"failed":[{"id","claim","output"}],"review_needed"}`, 완료면 exit 0 아니면 exit 1. 마지막 라운드에 result.md·result.json 작성. 완료이고 대상에 plan이 있으면 `STATE/audit-pass/<plan 현재 내용 sha256>.json`에 plan·spec의 현재 sha256으로 합격 기록을 쓴다(C11) |
| C11 | `gate PLAN` | PLAN 내용 sha256의 합격 기록이 있고 기록의 plan 외 targets(spec) 각 `path`의 현재 sha256이 기록과 같으면 exit 0(출력 없음), 아니면 exit 1 + stderr 한 줄(기록 없음 또는 대상 변경·부재 — finish 재실행 안내). 실행 관문(opt-in `SUPERPOWERS_AUDIT_GATE=1`)이 `sdd-workspace` 경유로 부른다 |
