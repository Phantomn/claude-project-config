# akm-report.json 스키마 v1.2

산출 계약: 이 스키마를 따르는 JSON 하나가 평가의 최종 산출물이다. akm.cmdspace.work 보드는 이 파일을 그대로 인제스트한다.

## 최상위 구조

```json
{
  "schemaVersion": "1.2",
  "id": "kebab-case-id-YYYY-MM",
  "assessment": { ... },
  "subject": { ... },
  "environment": { ... },
  "scores": { ... },
  "qualitative": { ... },
  "history": [ ... ]
}
```

규칙: `id`는 `[a-z0-9-]{3,64}` (예: `hong-gildong-2026-07`). 이중언어 필드는 `{ "ko": "...", "en": "..." }` — 한쪽만 있어도 됨.

## assessment
```json
{
  "date": "YYYY-MM-DD",
  "durationMinutes": 75,
  "rubricVersion": "1.2.0",
  "mode": "self-run | remote-kit | local-parallel-audit",
  "modeLabel": { "ko": "셀프 평가", "en": "Self-run" },
  "evaluator": "채점한 에이전트/사람 (예: Claude Code + self adversarial pass)",
  "verification": {
    "panels": 5, "spotChecks": 12,
    "adjustments": [ { "criterion": "P3", "from": 3, "to": 2, "reason": "..." } ]
  }
}
```

`durationMinutes` (선택): 평가 시작→리포트 완성까지 실제 소요 시간(분, 정수). 성적표에 표시된다.

## subject — 신원과 동의 (⚠ 반드시 사용자 확인 후 기입)
```json
{
  "name": "실명", "nickname": "닉네임", "email": "메일", "affiliation": "소속",
  "consent": { "submit": true, "publicCard": true, "publicDetail": false, "showRealName": false, "showEmail": false }
}
```
- `submit`: 운영팀 전송 동의 — **사용자에게 1회 확인 후 기입**. /api/submit 은 submit=true 아니면 422로 거부한다.
- publicCard=false면 보드에 오르지 않는다 (전송·백업 보관만 가능).
- 마스킹(이메일·실명)은 인제스트 단계에서 자동 적용되므로 원본 값을 그대로 넣어도 된다.

## environment
```json
{
  "device": "MacBook Pro 16″ · Apple M5 Max",
  "os": "macOS (Darwin 25)",
  "knowledgeBase": { "type": "Obsidian · 단일 볼트", "notes": 3200, "detail": "..." },
  "runtimes": [
    { "name": "Claude Code", "role": "primary", "usageShare": 0.85 },
    { "name": "Cursor", "role": "specialized", "usageShare": 0.15 }
  ],
  "usageBasis": { "ko": "산정 근거 (산출물 폴더 파일 수 등)", "en": "..." },
  "metrics": [
    { "key": "skills", "label": { "ko": "커스텀 스킬", "en": "custom skills" }, "value": "12" },
    { "key": "mcp", "label": { "ko": "MCP 서버", "en": "MCP servers" }, "value": "4" },
    { "key": "hooks", "label": { "ko": "훅", "en": "hooks" }, "value": "2" },
    { "key": "index", "label": { "ko": "검색 인덱스 문서", "en": "indexed docs" }, "value": "0" },
    { "key": "inbox", "label": { "ko": "인박스 비중", "en": "inbox ratio" }, "value": "31%" }
  ]
}
```
- `usageShare` 합계는 1.0 이하 (dormant 런타임은 0).
- metrics는 자유 확장 가능하나 위 5종을 기본 포함 권장.

## scores
```json
{
  "total": 47.5, "band": "M2", "bandLabel": { "ko": "체계화", "en": "Structured" },
  "pillars": {
    "P": { "score": 11.0, "max": 20, "name": { "ko": "프롬프트", "en": "Prompt" } },
    "C": { "score": 13.75, "max": 25, "name": { "ko": "컨텍스트", "en": "Context" } },
    "H": { "score": 9.0,  "max": 20, "name": { "ko": "하네스", "en": "Harness" } },
    "L": { "score": 8.0,  "max": 20, "name": { "ko": "루프", "en": "Loop" } },
    "X": { "score": 5.75, "max": 15, "name": { "ko": "이식성·거버넌스", "en": "Interop & Gov" } }
  },
  "criteria": [
    { "id": "P1", "name": { "ko": "지시 계층화", "en": "Instruction layering" }, "level": 3, "note": "근거+감점 사유 한 줄" }
    // ... P1~X5 정확히 25개, level은 정수 0-4
  ]
}
```
- 검증 규칙: `total` = pillars score 합 (±0.05), criteria 25개 필수.
- 기준 ID 순서: P1-P5, C1-C5, H1-H5, L1-L5, X1-X5.

## qualitative
```json
{
  "diagnosis": { "ko": "한 줄 진단", "en": "One-line diagnosis" },
  "pillarComments": { "P": "...", "C": "...", "H": "...", "L": "...", "X": "..." },
  "strengths": [ { "ko": "...", "en": "..." }, ... 3개 ],
  "improvements": [
    { "action": { "ko": "...", "en": "..." }, "target": "C1", "gain": 1.25, "applied": null }
  ],
  "guide": { "ko": "다음 밴드로 가는 가이드 3-4문장", "en": "..." }
}
```
- `gain` = 레벨 변화 × (기준 배점 ÷ 4). `applied`는 실행 완료 시 날짜 문자열.

## dimensions (선택 — v1.2 서술 축, 없어도 유효)
```json
{
  "scale": {
    "notes": 8200, "stores": 7, "runtimes": 4, "automations": 6,
    "skills": 90, "humans": 6, "yearsActive": 3.5,
    "index": 2.71, "band": "XL"
  },
  "autonomy": {
    "checklist": { "backup": "auto", "indexing": "auto", "measurement": "auto", "retrospective": "auto", "hygiene": "auto", "secrets": "auto", "promotion": "manual", "memoryGc": "manual" },
    "score": 0.875
  },
  "output": { "count90d": 6, "band": "O2", "kinds": ["newsletter", "lecture"] },
  "commentary": { "ko": "프로파일 해설 3-5문장 (점수와 연결)", "en": "3-5 sentence profile reading tied to the score" }
}
```
- 점수와 무관한 해석 좌표계 (규준 참조). 산출 방법: `references/dimensions.md` · 전문: https://akm.cmdspace.work/dimensions.html
- 전 필드 카운트 실측 — 추정 금지, 실측 불가 시 null + 사유. checklist 값은 `auto|manual|none`, autonomy.score = (auto×1 + manual×0.5)/8.
- band 검증: scale.band ∈ S/M/L/XL (index 임계 0.75/1.5/2.25) · output.band ∈ O0-O3 (0 / 1-2 / 3-9 / 10+).
- `commentary` (권장): `{ "ko": "...", "en": "..." }` — 프로파일을 **점수와 연결해 해석**하는 정성 해설 3-5문장. 사분면 위치(쾌속정/함대/출항 준비/과적), 정합선 대비 위치(S↔A), O가 말해주는 것, 그리고 "이 프로파일에서 이 M점수가 의미하는 것"을 서술. 성적표의 서술 축 카드에 표시된다.

## history (선택)
```json
[ { "date": "YYYY-MM-DD", "total": 47.5, "band": "M2", "note": "initial assessment" } ]
```
재평가 시 항목을 추가해 성장 궤적을 기록한다.

## 전송 (POST /api/submit)

```bash
curl -sS -X POST https://akm.cmdspace.work/api/submit -H "Content-Type: application/json" --data-binary @akm-report.json
```

성공: `{ "ok": true, "receiptId": "sub_...", "storage": "..." }` — receiptId는 철회 요청용.
검증: schemaVersion 1.x · id kebab-case · pillars 5종 · criteria 25개 · 총점 합 일치 · **consent.submit=true** · 300KB 이하.
서버는 제출물을 `{ receiptId, receivedAt, report }` 로 래핑해 비공개 저장소에 보관한다.
