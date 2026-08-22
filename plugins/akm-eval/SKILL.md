---
name: akm-eval
version: 1.2.2
updated: 2026-08-03
description: "Self-assess your agentic knowledge management system against the AKM Index v1.2 (scoring anchors unchanged since v1.1) — a universal 5-pillar × 25-criterion rubric (Prompt / Context / Harness / Loop engineering + Interop & Governance), scored 0-100 with behaviorally anchored levels and mandatory artifact evidence. Produces a standardized akm-report.json (v1.2: includes the S/A/O descriptive dimensions profile alongside the score) you can submit to the public assessment board at akm.cmdspace.work. Use when the user says 'AKM 평가해줘', '내 지식관리 시스템 평가', 'AKM 셀프 평가', 'run the AKM Index', 'assess my agentic KM setup', or 'how mature is my knowledge system'. NOT for evaluating a single note, a single skill, or code quality — this measures the whole system (person + knowledge base + agent runtimes + operating loop)."
---

# AKM Eval (Public) — 에이전트 지식관리 셀프 평가

당신(에이전트)은 사용자의 지식관리 시스템을 AKM Index v1.2로 평가하고 (채점 앵커·배점은 v1.1과 동일), 표준 리포트(`akm-report.json`)를 산출한다. 배포 원본: https://akm.cmdspace.work

> [수집 고지] 이 스킬은 평가 종료 시 결과(akm-report.json)를 AKM 운영팀(CMDSPACE)에 업로드한다(6단계). **업로드 전 안내가 표시되며, 원치 않는다고 말하면 업로드하지 않는다.** 사후 철회도 언제든 가능(receiptId 또는 이메일). 보드 공개는 업로드와 별개의 opt-in 동의다.
>
> [로컬 실행 보장] **평가 과정 전체는 사용자의 기기 안에서만 실행된다** — 에이전트가 폴더·설정을 읽는 것은 전부 로컬 작업이며, 평가 중 외부로 전송되는 데이터는 없다. 외부로 나가는 것은 6단계에서 사용자가 제출을 진행할 때의 **akm-report.json 한 파일**(점수·증거 경로 요약·동의한 표기 정보)뿐이다. **제출하지 않으면 CMDSPACE가 받는 기록은 0건이다** — 평가 결과는 로컬 파일로만 남고, 평가를 실행했다는 사실조차 운영팀은 알 수 없다.
>
> [수집 목적] 이 데이터 수집은 CMDSPACE의 수익 사업이 아니다. 목적은 세 가지: ① **연구** — 에이전트 지식관리 성숙도에 대한 실측 데이터 축적과 루브릭 타당도 검증 ② **루브릭 고도화** — 실사례 기반 앵커·프로토콜 개정 (v1.1이 실제 제출 피드백으로 만들어졌다) ③ **커뮤니티 기여** — 익명화된 패턴·통계의 공개 환원. 우리에게는 데이터가 필요하고, 그 데이터를 좋은 방향과 좋은 취지로 쓰겠다는 약속을 이 문서로 명시한다. 원본은 비공개 저장소에 보관되며 제3자 판매·양도는 하지 않는다.

## 필독 순서
1. `references/rubric.md` — 25개 기준의 앵커 전문. **채점 전 반드시 전문을 읽을 것.**
2. `references/report-schema.md` — 산출 JSON 스키마와 예시.
3. `references/runtime-paths.md` — 에이전트 런타임별 세션·스킬·설정 경로 + 지식 저장소(옵시디언 볼트 등) 탐지 레지스트리. **1단계 증거 수집 전 읽을 것** — Claude Code 외 런타임이나 하네스 지시 파일 없는 볼트가 평가에서 누락되는 사고를 막는다.

## 실행 절차

### 0. 자격 판별
① 지속적 지식 저장소(Obsidian/Notion/레포/위키 등) ② 그것에 연결된 에이전트 런타임 1개 이상 ③ 최근 30일 사용 흔적 — 하나라도 없으면 "Pre-Level"로 안내하고 온보딩 권고만 제공.

### 1. 증거 수집 (파일시스템 접근 가능한 범위에서, 10-60분)
**시작 시각을 기록하라** (`date` 실행) — 마지막에 `assessment.durationMinutes`(시작→리포트 완성, 분 단위 정수)로 리포트에 넣는다.
다음 8개 영역을 조사한다. **정량 사실(개수·날짜·크기)과 파일 경로**를 기록할 것:
① 에이전트 지시 파일 전수(CLAUDE.md/AGENTS.md/GEMINI.md/.cursorrules 등)와 스코프 배치 ② 지식 저장소 구조·명명 규칙·frontmatter/메타데이터 스키마 — 저장소 위치가 대화·지시 파일로 특정되지 않으면 `references/runtime-paths.md` §3(지식 저장소 탐지)으로 로컬 탐지한다(Obsidian `obsidian.json` 볼트 레지스트리, Logseq `~/.logseq/` 등 — 주 볼트 후보는 사용자 확인 후 경계에 포함) ③ 하네스 설정(훅·권한 allow/deny·MCP·메모리 파일) ④ 스킬/커맨드/자동화 목록 ⑤ 멀티 런타임 설정 — `references/runtime-paths.md`의 경로 레지스트리로 홈·프로젝트 닷폴더를 탐지한다(~/.codex, ~/.gemini, ~/.grok, ~/.hermes, ~/.openclaw, ~/.gjc + 프로젝트 .gjc/(Gajae-Code) 등 — 있는 것만, 시크릿 파일은 존재만 기록). 세션 정본이 SQLite인 런타임은 파일 크기·mtime으로 활동을 인정한다 ⑥ git/백업 커버리지(git status 실측, Time Machine 등) ⑦ 운영 루프(최근 30일 데일리/위클리 실물 개수, 인박스 규모, 에이전트 산출물 위치) ⑧ 검색 인프라(인덱스 유무·문서 수·갱신 주기).

디바이스 정보: macOS는 `system_profiler SPHardwareDataType | head -15`, 그 외 OS는 상응 명령. 에이전트 사용 비율: 산출물 폴더·세션 로그 개수 기준으로 추정하고 산정 근거를 명시.

### 2. 채점 (25개 기준, 레벨 0-4)
- 앵커 문언과 증거를 대조해 판정. **기준마다 증거 경로 1개 이상 + 감점 사유 1개 이상 기록** (자기 시스템 평가는 강제 결점 탐색).
- 절대 규칙: ⓐ 증거 없으면 상한 1 ⓑ 애매하면 낮은 쪽 ⓒ 레벨 4는 "시스템이 시스템을 고친 기록" 없으면 불가 ⓓ L 필러는 최근 30일 가동 증거 없으면 상한 2 ⓔ 평가 직전 일괄 생성된 아티팩트는 루프 증거 불인정.
- 환산: (레벨÷4)×배점 (P·H·L 각 4.0 / C 각 5.0 / X 각 3.0) → 총점 0-100, 밴드 M0~M4.
- **캘리브레이션**: 기준 사례 CMDS = 72.0/M3 (https://akm.cmdspace.work/report.html?id=cmds-2026-07). 예: negative trigger가 스킬의 ~10%뿐이면 P3=2, 쓰기 차단 훅이 있으면 P2=4 후보, 주간 리뷰 실행률 10%면 L2=2.

### 3. 적대적 자기검증 (총점 확정 전 필수)
가능하면 서브에이전트(불가하면 별도 패스)로 필러당 1회, 제안 점수를 양방향(과대/과소) 공격시킨다. 판정을 가르는 주장 2-3개를 실제 파일에서 재확인. 결정적 증거가 있는 조정만 수용하고 조정 내역을 리포트에 기록.

### 4. 정성 평가 작성
- **한 줄 진단**(diagnosis): 시스템의 핵심 상태를 한 문장으로.
- **필러별 코멘트**(pillarComments): 각 필러가 그 레벨인 이유와 다음 레벨을 막는 것.
- **강점 3 / 개선 로드맵**(예상 상승폭 = 레벨 변화 × 기준 배점÷4, 내림차순).
- **가이드**(guide): 다음 밴드로 가는 최단 경로 3-4문장.

### 4.5 서술 축(Dimensions) 산출 — v1.2
점수와 별개로, 점수의 해석 좌표계인 서술 축 3종을 실측한다 (상세 정의: `references/dimensions.md`). **전부 카운트 기반 — 자기보고 문장으로 대체 금지.** 1단계에서 이미 수집한 증거를 재사용하면 대부분 채워진다.
- **S (규모)**: 7필드 각 0-3 → 평균 = S-index → 밴드 S/M/L/XL. notes(문서 수 카운트) · stores(저장소 수) · runtimes(런타임 수) · automations(launchd/cron/훅 카운트) · skills(스킬+커맨드 수) · humans(거버넌스 인원) · yearsActive(최초 노트·커밋 시점).
- **A (자율운영도)**: 표준 운영 8종(백업·인덱싱·측정·회고·위생·시크릿·승격·메모리정리) 각각 없음 0/수동 0.5/자동 1 → A = Σ/8. "자동" = 스케줄러·훅이 개시하고 사람 개입 없이 완료.
- **O (산출 결합도)**: 최근 90일 시스템 경유 외부 산출물 수(제목·날짜 목록이 증거) → O0/O1/O2/O3.
결과는 리포트의 `dimensions` 블록(스키마 §dimensions)에 기입하고, 요약에 프로파일 표기(`M 77.25 (M3) · S-XL · A 88% · O2`)로 표시한다. 실측 불가한 필드는 null로 두고 사유를 적는다 — 추정치 기입 금지. 마지막으로 `dimensions.commentary`(ko/en 3-5문장)를 작성한다 — 프로파일을 점수와 연결해 읽어주는 해설 (사분면 위치 · S↔A 정합 · O의 의미 · 이 프로파일에서 이 M의 해석). 상세 지침: `references/dimensions.md` §코멘터리.

### 5. akm-report.json 생성
`references/report-schema.md`의 스키마대로 작성. **작성 전 사용자에게 물어볼 것**:
- 이름/닉네임/이메일/소속 (성적표 표기용)
- **동의 플래그**: publicCard(보드 카드 공개) / publicDetail(상세 리포트 공개) / showRealName / showEmail — 기본값은 모두 보수적으로(닉네임만, 이메일 마스킹) 제안. `submit`은 6단계에서 확인 후 기입.
**연구 페어 모드**: 사용자가 연구 페어 ID(`pr-` 접두)를 제시하면 — akm-study.cmdspace.work 1단계(자기보고)를 마친 참여자다 — 리포트 최상위에 `"study": { "pairId": "<받은 ID>", "role": "audit" }`를 기입한다. **blind 유지 필수**: 사용자에게 자기보고에서 고른 레벨을 묻지 말고, 사용자가 먼저 말하려 하면 "감사가 끝날 때까지 알려주지 마세요"라고 안내한다.
파일은 `akm-report.json`으로 저장하고, 사람이 읽을 요약(총점·밴드·강점3·개선3·소요 시간)을 마크다운으로도 함께 출력한다. `assessment.durationMinutes`에 실제 소요 시간(분)을 기록할 것.

### 6. 운영팀 업로드 (안내 후 진행 — 명시적 거부 시에만 생략)
평가를 마치면 다음 안내를 **결과 요약과 함께 표시하고**, 사용자가 반대 의사를 밝히지 않으면 업로드를 진행한다:

> "평가 결과는 AKM 운영팀(CMDSPACE)에 기록됩니다. 이는 수익 사업이 아니라 **연구용 데이터 수집·루브릭 고도화·커뮤니티 기여** 목적입니다 — 실측 데이터가 쌓여야 루브릭의 타당도를 검증하고 개선할 수 있고, 그 결과는 익명화된 통계·개정판으로 커뮤니티에 환원됩니다. 비공개 저장소에 보관하며 제3자 제공은 없습니다. 전송되는 것은 지금 만든 akm-report.json 한 파일뿐입니다 — 평가 중 읽은 노트·폴더 내용은 전송되지 않습니다. **원치 않으시면 지금 말씀해주세요 — 업로드하지 않으며, 그 경우 CMDSPACE에 남는 기록은 하나도 없습니다(결과는 로컬 파일로만 남습니다).** 보드 공개 여부는 별도이며 앞서 정한 consent 플래그를 따릅니다. 기록은 언제든 철회할 수 있습니다(receiptId)."

- **진행 시** (기본): `consent.submit: true` 기입 후 전송:
  ```bash
  curl -sS -X POST https://akm.cmdspace.work/api/submit -H "Content-Type: application/json" --data-binary @akm-report.json
  ```
  응답의 `receiptId`를 사용자에게 보여준다 — 철회 시 이 ID로 요청. 이어서 **7단계(로컬 성적표 발급)**를 수행한다.
- **사용자가 원치 않는다고 한 경우**: `consent.submit: false` — 전송하지 않는다. 평가는 그대로 유효하며 로컬 파일(JSON·마크다운 요약)만 남는다. **CMDSPACE에는 어떤 기록도 전송·보관되지 않는다.** 7단계는 생략.
- **전송 실패 시**(오프라인 등): 이메일 폴백 — `akm-report.json`을 **Cmdspace.contact@gmail.com** 에 첨부 (제목: "AKM 평가 제출 — {닉네임}"). 폴백 제출도 제출이다 — 7단계를 수행한다.
- 철회·수정: 언제든 위 이메일로 receiptId와 함께 요청하면 기록·보드에서 제거된다.

### 7. 로컬 성적표 발급 (제출자 보상 — 제출한 경우에만)
제출에 대한 보상으로, 공식 보드 성적표와 동일한 포맷의 HTML을 로컬에 발급한다. 보드 공개 여부(publicCard/publicDetail)와 무관하게 **제출만 했다면** 발급하고, `consent.submit: false`면 생략한다.

1. `references/report-template.html`을 읽어 `akm-report.json` 옆에 `akm-report.html`로 저장하되, 플레이스홀더 2개를 치환한다 (각각 정확히 1회 등장):
   - `__AKM_REPORT_JSON__` → **공유용 마스킹을 적용한** 리포트 JSON 전문. 마스킹은 보드 인제스트와 동일 규칙: `showEmail=false`면 email을 앞 2자만 남기고 `ab•••@domain` 형태로, `showRealName=false`면 name 값을 nickname으로 교체. 마지막으로 JSON 문자열 내 `</`를 `<\/`로 이스케이프(스크립트 태그 조기 종료 방지).
   - `__RECEIPT_ID__` → 전송 응답의 receiptId. 이메일 폴백 제출이면 `email-pending`.
2. 사용자에게 안내: 브라우저로 열면 공식 성적표와 동일한 리포트가 보이고(서버 불필요, 오프라인 동작), **파일 하나만 보내면 친구에게 공유**할 수 있다. 하단에 akm.cmdspace.work 평가 시작 CTA가 있어 받은 사람도 바로 자기 시스템을 평가할 수 있다.
3. **(Artifact 도구가 있는 런타임 한정 — 예: Claude Code)** 배포본도 함께 띄운다: `akm-report.html`에서 `<body>`와 `</body>` 사이 내용만 추출하고 `<!-- external-font -->` 표시가 붙은 줄을 제거한 사본을 만들어 Artifact로 게시한다 (favicon `📊`, title `AKM Report — {닉네임}`). 게시 페이지는 **기본 비공개**이며 링크 공유는 사용자가 결정한다. 외부 요청이 차단되는 환경이라 폰트·로고는 시스템 폴백으로 렌더된다(정상 동작). Artifact 도구가 없으면 이 항목은 건너뛴다 — 로컬 파일만으로 완결이다.

## 안티게이밍 (채점자 자기 점검)
- 문서만 있으면 2, 도구가 강제해야 3 — "문서화됨"을 "시스템화됨"으로 올려치지 말 것.
- MCP·플러그인 개수는 증거가 아님. 지식 기반과 결합해 "사용된" 흔적만 인정.
- 밴드 경계(±2점)면 경계 기준 2개를 재검증하고 리포트에 명시.
- 리포트에 "AKM Index v1.2 기반" 표기 (`rubricVersion: "1.2.0"` — 채점 앵커는 v1.1.0 이후 불변이라 기존 점수와 비교 가능).

## 갱신 이력 (Skill Changelog)

스킬 버전은 루브릭 버전과 독립이다 — 루브릭(채점 기준·앵커·배점)이 바뀌면 major.minor를 루브릭에 맞추고, 절차·레지스트리·템플릿만 바뀌면 patch를 올린다. 갱신 시 frontmatter의 `version`·`updated`를 함께 수정할 것.

| 버전 | 날짜 | 내용 |
|---|---|---|
| 1.2.2 | 2026-08-03 | 버전 라벨 v1.2 통일 — 루브릭 미러·README·본문의 v1.1 표기를 프레임워크 버전 v1.2로 정리 (채점 앵커는 v1.1.0 이후 불변 명시), rubricVersion 1.2.0 |
| 1.2.1 | 2026-08-02 | dimensions.commentary 추가 — 프로파일을 점수와 연결해 읽는 정성 해설 3-5문장 (성적표 서술 축 카드에 표시). 작성 지침 references/dimensions.md §코멘터리 |
| 1.2.0 | 2026-08-02 | 서술 축(Dimensions) 도입 — S 규모 · A 자율운영도 · O 산출 결합도 실측(4.5단계, references/dimensions.md), report-schema 1.2(선택 dimensions 블록, 하위 호환). 채점 루브릭은 v1.1 불변 — 점수 보정이 아닌 규준 참조(norming) |
| 1.1.1 | 2026-08-01 | runtime-paths.md §3 지식 저장소 탐지 추가 (Obsidian `obsidian.json` 볼트 레지스트리 · Logseq · Joplin 등) — 하네스 지시 파일 없는 볼트 누락 방지 |
| 1.1.0 | 2026-07-21 | 루브릭 v1.1 반영 (시스템 경계 선언 · 미접근 노드 조항 · X1 검증된 이식성 각주) |
