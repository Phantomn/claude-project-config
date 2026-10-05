# spec-audit

SPEC/PLAN을 이름 지정 병렬 opus 감사자로 실제 소스와 교차 검증하고, 감사→수정→재감사 루프를 ❌0·⚠️0까지 소유하는 구현 전 관문. 리드 절차는 `SKILL.md`, 판정 근거는 `auditors/*.md`, 결정 이유는 `DECISIONS.md`, 받아들인 한계는 `LIMITS.md`.

## 구성

```
writing-plans (upstream, Execution Handoff 문단 수정)
   │ 계획 저장·Self-Review 후
   ▼
spec-audit/SKILL.md  ── 리드(스킬을 실행하는 메인 대화) 절차 S0–S6, 명령은 C표만
   │  python3 <Base directory>/scripts/audit_ws.py <C명령>     작업공간·스냅샷·프롬프트·집계·판정
   │  Agent(general-purpose, opus, name=<감사자 이름>)  감사자(프롬프트 파일)
   ▼
<tree>/.superpowers/audit/<slug>/round-<N>/          라운드 작업공간
```

## 루프 (S0–S6)

- **S0 대상 확정**: 인자 또는 직전에 다룬 spec·plan을 대상으로 잡고 역할(spec·plan)과 구현 대상 저장소를 정한다.
- **S1 시작**: C1이 작업공간·스냅샷·감사자 프롬프트를 만든다.
- **S2 스폰**: 감사자를 한 메시지에서 병렬로 새로 스폰한다.
- **S3 집계**: 모든 감사자가 응답하면 C3이 보고를 검증·집계하고, 무효 보고는 한 번 재시도한다.
- **S4 판정**: C4가 J1로 `pass`·`cap`·`fix`를 정한다.
- **S5 수정**: 정합 수정은 리드가 반영하고 요구 변경은 항목별 승인을 받은 뒤 C9로 check를 다시 돌린다.
- **S6 다음 라운드**: C2로 새 라운드를 만들고 S2로 돌아간다. 라운드 상한은 5.

## 2단계 예고

1단계 머지 뒤 별도 spec으로 다룬다.

| 대상 | 내용 |
|---|---|
| 감사자 정책 훅 | 쓰기 도구·Agent·MCP 쓰기·시크릿·파괴적 명령 차단(opt-in) |
| 작업트리 변경 사후 탐지 | gitignore 경로·빈 디렉토리 사각지대를 포함한 재설계 |
| 실행 관문 | 감사 합격 확인 + 구현 디스패치 훅 |
| 감사 중 대상 문서 잠금 | 감사 도중 문서 수정을 막는다 |
| 리드의 직접 감사 차단 | 감사 중 리드의 `<tree>` 조회 도구 제한 |
