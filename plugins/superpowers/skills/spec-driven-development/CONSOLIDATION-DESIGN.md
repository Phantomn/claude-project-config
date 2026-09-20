# spec-driven-development 통합 설계 — 근본원인 & 정공법

> 작성 2026-09-20 · 상태: 설계(구현 전) · 근거: 4 전수조사(W1 인벤토리·W2 엔진분류·W3 git이력·gap분석) + 직접 반증
> 결정 확정: validate = **B2(완전 포팅, CLI-less)** · 정본 = **spec-driven-development**(superpowers를 실행엔진으로 흡수)

---

## 1. 문제 정의

spec/plan 개발 워크플로우가 **3계보로 분산**되어 진입점이 혼란스럽다.

| 계보 | 실체 | 소유 |
|------|------|------|
| superpowers | brainstorming→writing-plans→subagent-driven/executing→finishing (14스킬) | 플러그인(marketplace) |
| spec-driven-development | SPECIFY→PLAN→TASKS→IMPLEMENT 단일 스킬 | canon `.agents` |
| openspec | opsx 6커맨드 + openspec-* 6스킬 + `openspec` CLI + openspec/ 디렉토리 | npm 전역 + 프로젝트 산물 |

(sdd-harness = 이름만 SDD, 실체는 코드→설계문서 리버스 생성 = **파이프 무관 별개 도구**. source-driven-development = 문서근거 코딩 규율, **무관·제외**.)

## 2. 근본원인 (git 확정 — 임시처방 금지)

**미정리 누적**. auto-approve "4계보 6벌"과 **동형 병리**(CLAUDE.md 기록).

```
08-24  canon spec-driven-development 도입 (9387195)
08-30  superpowers 플러그인 도입 (ec55bfb5)      ← 앞 계보 미정리
09-18  openspec init 산물 도입                     ← spec-driven을 DEPRECATED 포인터로만 남김,
                                                     superpowers는 이 결정에서 누락
```

- 09-18 교체는 **삭제가 아니라 DEPRECATED frontmatter 포인터**(3fec3f0) = "미정리 누적" 직접 증거.
- "통합이 두 번, 서로를 모르고 일어남" — superpowers(범용 plan)가 openspec 교체 결정에서 빠짐.

## 3. 재발조건 (실측 확정)

- **주범 = openspec init의 프로젝트별 산물 재설치** — 단일소유 메커니즘 없음(플러그인화 미결).
- **격리 유실**: 현행 `.gitignore` openspec=0, 산물 전부 `??`(untracked 림보).
- **핵심 구분**: `openspec` **CLI 바이너리**(npm 전역 1벌, 단일소유 OK) ≠ **프로젝트 산물**(재발 주범).

## 4. 흡수 비용 (소스 LOC 확정 — "이식 38292 LOC"는 과대 프레임)

| openspec 기능 | 분류 | 실제 흡수 방법 |
|---|---|---|
| explore/propose/apply/status/list/show/context/instructions | LLM_REPLACEABLE | superpowers/spec-driven 지시문 |
| new change / archive 이동 | THIN_REIMPL (~35 LOC) | mkdir + mv 지시문 |
| **delta→main 병합 (specs-apply 1177 + archive 1726 = 2903 LOC)** | 이미 **agent-driven LLM화**(sync.md L11) | **재구현 불필요** |
| **validate (validator 923 + requirement-blocks 510 ≈ 1433 LOC 핵심)** | HEAVY_ENGINE (유일 결정론) | **B2 포팅** |

- 직접 반증: opsx의 `openspec archive` 8회는 전부 **설명 인용**("exactly as archive does")이지 실행 호출 아님. 실제 병합은 LLM.
- validate = 변환기 아닌 **검증기**: LLM 병합이 시나리오를 떨어뜨렸는지 잡는 안전망(sync.md:176,253).

## 5. 목표 아키텍처

**spec-driven-development = 통합 정본 진입점**, superpowers = 실행 엔진(흡수), openspec 생명주기 = 지시문+validate 포팅으로 흡수.

```
spec-driven-development (정본 진입점, 게이트 오케스트레이터)
├─ SPECIFY   : 6영역 spec 템플릿 + success-criteria 리프레이밍 + assumptions
│              (openspec propose의 delta 개념 흡수 = spec 문서가 곧 변경단위)
├─ PLAN      : → superpowers:writing-plans 위임
├─ TASKS     : → writing-plans 태스크 분해 (+ update 양방향 재조정 흡수)
├─ IMPLEMENT : → superpowers:subagent-driven-development / executing-plans 위임
│              (+ TDD·worktrees·code-review 횡단)
└─ 생명주기  : spec 살아있는 문서 관리
   ├─ archive : 파일 mkdir+mv 지시문 (openspec archive 흡수)
   ├─ sync    : delta→main LLM 편집 지시문 (openspec sync 흡수, 이미 LLM)
   └─ validate: scripts/validate-spec (B2 포팅, CLI-less 결정론 가드)
```

"superpowers로 흡수"(실행엔진) + "spec-driven-development 정본"(진입점) 양립.

## 6. validate B2 포팅 설계 (유일한 신규 코드)

- 대상: openspec validator 핵심 규칙만(full 1433 재현 아님 — load-bearing 규칙만 얇게).
- 필수 검증 규칙: (a) requirement 블록 문법 파싱 (b) MODIFIED가 main의 시나리오를 드롭했는지 (c) ADDED 최소 1개(REMOVED-only 거부) (d) delta↔main 정합.
- 산출: `spec-driven-development/scripts/validate-spec.py` + 유닛테스트(mutation-guard: 가드 라인 손상 시 FAIL).
- **리스크(기록)**: upstream openspec validator와 갈라지는 fork divergence 새 축 — 사용자 감수 결정(B2). 완화: 규칙 최소화 + 테스트로 계약 고정.

## 7. 흡수 매핑 (gap 2패턴)

- **update 양방향 재조정**(opsx/update.md) → superpowers `writing-plans` Self-Review 확장.
- **success-criteria 리프레이밍**(원 SKILL.md:124-136) → superpowers `brainstorming` 예시 + spec-driven SPECIFY에 보존.
- superpowers 편집 = marketplace repo(phantomn-harness) 소스 수정 필요.

## 8. 제거 대상 + 순서 (흡수·검증 완료 후에만)

| 대상 | 처리 | 조건 |
|------|------|------|
| spec-driven-development DEPRECATED 헤더 | 걷어내고 **재작성**(정본화) | Phase 2 |
| sdd-harness | 순수 제거(파이프 무관, 호출처 0) | 독립 가능 |
| openspec 산물(스킬6/커맨드6/openspec/) | 제거(재발 주범 차단) | 흡수 검증 후 |
| openspec `.agents` 심링크 정리 | canon 게이트 정합 | 제거와 동시 |

## 9. 세부 실행 단계 (순차 — 각 단계 검증 게이트)

- **Phase 0** (완료): 이 설계 문서.
- **Phase 1 — validate B2 포팅** (foundational, 먼저): validate-spec 스크립트 + 테스트. **게이트**: 양성대조(시나리오 드롭 delta→FAIL) + 음성대조(정상 delta→PASS).
- **Phase 2 — spec-driven-development 재작성**: 통합 정본 SKILL.md(§5 아키텍처). superpowers 위임 + 생명주기 흡수 + validate 호출. **게이트**: skill-audit frontmatter 통과.
- **Phase 3 — gap 2패턴 흡수**: writing-plans/brainstorming 편집(marketplace repo). **게이트**: 흡수 패턴이 held-out 예시로 작동.
- **Phase 4 — 제거**: sdd-harness → openspec 산물 → 심링크. **게이트**: check-canon.sh 통과(dangling 0).
- **Phase 5 — 재발방지**: openspec init 재유입 차단(§10). **게이트**: 재유입 시 탐지.
- **Phase 6 — 통합 검증**: spec-driven 진입→superpowers 실행→validate 폐루프 dry-run.

## 10. 재발방지 (근본원인 = 미정리 누적 → 단일소유 강제)

- openspec CLI를 워크플로우에서 **안 씀** → `openspec init` 실행 안 함(산물 재유입원 차단).
- check-canon.sh 확장 검토: `.claude/skills/openspec-*`·`.claude/commands/opsx/` 재출현 탐지(canon 위반으로).
- spec-driven-development를 **단일 정본**으로 명시(다음 계보 도입 시 여기로 수렴 강제).

## 11. 미결 결정 (구현 착수 전 확인)

1. spec-driven-development 재작성 = superpowers를 **명시적 위임**(스킬 호출)인가, 내용 **복제**인가? (위임 권장 — 복제는 divergence)
2. validate 포팅 언어 = Python(하네스 관행) vs JS(openspec 원본 대조 용이)?
3. gap 흡수를 위한 superpowers marketplace repo 편집 = fork 관행 확인(FORK-NOTICE 방식).
4. sdd-harness 제거 = 문서생성 기능 완전 폐기 확정인가(대체 없음)?
