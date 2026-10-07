# spec-audit

SPEC/PLAN을 병렬 opus 감사자로 실제 소스와 교차 검증하는 구현 전 관문. 감사는 최대 2회(전체 1회 + 수정분 재검토 1회)이고, 모든 지적에 처분(반영·기각·수용)을 기록하고 반영분 check가 통과하면 끝난다(D23). 리드 절차는 `SKILL.md`, 판정 근거는 `auditors/*.md`, 결정 이유는 `DECISIONS.md`, 받아들인 한계는 `LIMITS.md`.

## 구성

```
writing-plans (upstream, Execution Handoff 문단 수정)
   │ 계획 저장·Self-Review 후
   ▼
spec-audit/SKILL.md  ── 리드(스킬을 실행하는 메인 대화) 절차 S0–S6, 명령은 C표만
   │  python3 <Base directory>/scripts/audit_ws.py <C명령>     작업공간·스냅샷·프롬프트·집계·판정
   │  Agent(superpowers:spec-auditor, opus, name 없음)  감사자(에이전트 + 프롬프트 파일)
   ▼
<tree>/.superpowers/audit/<slug>/round-<N>/          라운드 작업공간
```

## 절차 (S0–S6)

- **S0 대상 확정**: 인자 또는 직전에 다룬 spec·plan을 대상으로 잡고 역할(spec·plan)과 구현 대상 저장소를 정한다.
- **S1 시작**: C1이 라운드 1(전체 범위) 작업공간·스냅샷·감사자 프롬프트를 만든다. 이전 W는 보관한다.
- **S2 스폰**: 감사자를 한 메시지에서 병렬로 새로 스폰한다(`name` 없이).
- **S3 집계**: 모든 감사자가 응답하면 C3이 보고를 검증·집계하고, 무효 보고는 한 번 재시도한다.
- **S4 처분**: 리드가 지적마다 반영·기각·수용을 권고하고 사용자가 한 번에 확정한다.
- **S5 반영**: 반영 항목을 `affected`까지 고친다.
- **S6 끝 판정**: C6 `finish`. 라운드 1 뒤 고쳤으면 C2로 수정분을 한 번 재검토하고(라운드 2) 새 지적만 처분한다. 라운드 3은 없다.

## 강제 계층

| 대상 | 내용 |
|---|---|
| 감사자 에이전트 | `agents/spec-auditor.md` — 쓰기 도구 없음 |
| audit-guard | G1–G3 감사자(쓰기·시크릿·파괴적 명령), M1–M2 감사 중 리드(대상 수정·`<tree>` 조회) 차단 |
| 실행 관문 | opt-in — 켜는 법: 쓰는 프로젝트의 `.claude/settings.json` `env.SUPERPOWERS_AUDIT_GATE="1"` |
