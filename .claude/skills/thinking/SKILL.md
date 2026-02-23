---
name: thinking
description: Sequential Thinking MCP를 활용한 구조적 사고 전략. 문제 유형에 따라 7가지 추론 패턴을 자동 선택하거나 명시적으로 지정합니다.
triggers:
  - "/thinking"
  - "/think"
  - "구조적 분석"
  - "깊이 생각"
  - "단계별 추론"
  - "structured thinking"
---

# Thinking Skill

Sequential Thinking MCP의 파라미터를 **7가지 사고 전략**으로 구조화하여 문제 유형에 맞는 추론 패턴을 적용합니다.

## 원칙

- **자동 라우팅 기본**: 키워드 감지로 최적 전략 자동 선택
- **명시적 오버라이드**: `--cot`, `--tot` 등 플래그로 전략 강제 지정
- **직교 관계**: `--think` = 깊이(depth), `/thinking` = 전략(strategy) → 독립적으로 조합 가능

---

## 자동 라우팅 의사결정 트리

사용자 입력을 분석하여 아래 순서로 매칭합니다. 먼저 매칭되는 전략을 적용합니다.

| 순서 | 감지 키워드 | 전략 | 플래그 |
|------|------------|------|--------|
| 1 | "A vs B", "비교", "선택", "트레이드오프" | ToT | `--tot` |
| 2 | "왜", "근본 원인", "반복되는", "막혔" | Step-Back | `--step-back` |
| 3 | "어떻게 동작", "구조", "전체 흐름" | Self-Ask | `--self-ask` |
| 4 | "버그", "디버그", "원인 찾아", "성능 분석" | ReAct | `--react` |
| 5 | "위험", "롤백 불가", "프로덕션", "삭제" | Ulysses | `--ulysses` |
| 6 | "빠르게 판단", "상황 변화", "대응", "모니터링" | OODA | `--ooda` |
| 7 | 기본값 | CoT | `--cot` |

---

## 7가지 전략 카탈로그

### 전략 1: CoT (Chain of Thought) `--cot`

**용도**: 선형적 문제 풀이, 알고리즘 설계, 수학적 증명, 순차적 논리 전개

**Sequential Thinking 매핑**:
- 순차적 `thought` 호출, 분기/수정 없음
- `thought`, `thoughtNumber`, `totalThoughts`, `nextThoughtNeeded`만 사용

**패턴**:
```
문제정의(T1) → 단계1(T2) → 단계2(T3) → ... → 결론(Tn)
```

**호출 예시**:
```
sequentialthinking(thought="문제: X를 해결해야 한다. 접근법을 정의한다.",
  thoughtNumber=1, totalThoughts=5, nextThoughtNeeded=true)
sequentialthinking(thought="단계 1: ...",
  thoughtNumber=2, totalThoughts=5, nextThoughtNeeded=true)
...
sequentialthinking(thought="결론: ...",
  thoughtNumber=5, totalThoughts=5, nextThoughtNeeded=false)
```

---

### 전략 2: ToT (Tree of Thoughts) `--tot`

**용도**: 비교/선택, 아키텍처 대안 평가, 트레이드오프 분석, "A vs B" 문제

**Sequential Thinking 매핑**:
- `branchFromThought` + `branchId`로 분기 생성
- 각 분기를 독립 평가 후 수렴

**패턴**:
```
분기점식별(T1) → 방안A(T2, branchId:"A") → 방안B(T3, branchId:"B")
→ 방안A평가(T4, branchId:"A") → 방안B평가(T5, branchId:"B")
→ 비교수렴(T6)
```

**호출 예시**:
```
sequentialthinking(thought="분기점: REST vs gRPC 선택. 두 방안을 분석한다.",
  thoughtNumber=1, totalThoughts=6, nextThoughtNeeded=true)
sequentialthinking(thought="방안A(REST): 장점은..., 단점은...",
  thoughtNumber=2, totalThoughts=6, nextThoughtNeeded=true,
  branchFromThought=1, branchId="REST")
sequentialthinking(thought="방안B(gRPC): 장점은..., 단점은...",
  thoughtNumber=3, totalThoughts=6, nextThoughtNeeded=true,
  branchFromThought=1, branchId="gRPC")
sequentialthinking(thought="비교 수렴: 기준별 평가표...",
  thoughtNumber=4, totalThoughts=4, nextThoughtNeeded=false)
```

---

### 전략 3: Step-Back Abstraction `--step-back`

**용도**: "왜" 질문, 근본 원인 분석, 문제에 막혔을 때, 반복되는 실패 패턴

**Sequential Thinking 매핑**:
- `isRevision` + `revisesThought`로 추상화 후 원래 문제 재방문

**패턴**:
```
구체적문제(T1) → 한단계추상화(T2) → 일반원리정리(T3)
→ 재적용(T4, isRevision=true, revisesThought=1) → 해결책(T5)
```

**호출 예시**:
```
sequentialthinking(thought="구체적 문제: API 응답이 간헐적으로 타임아웃...",
  thoughtNumber=1, totalThoughts=5, nextThoughtNeeded=true)
sequentialthinking(thought="한 단계 추상화: 이 문제의 상위 카테고리는 '분산 시스템의 일시적 장애'...",
  thoughtNumber=2, totalThoughts=5, nextThoughtNeeded=true)
sequentialthinking(thought="일반 원리: 분산 시스템 장애의 일반적 원인은...",
  thoughtNumber=3, totalThoughts=5, nextThoughtNeeded=true)
sequentialthinking(thought="재적용: 일반 원리를 원래 문제에 적용하면...",
  thoughtNumber=4, totalThoughts=5, nextThoughtNeeded=true,
  isRevision=true, revisesThought=1)
sequentialthinking(thought="해결책: ...",
  thoughtNumber=5, totalThoughts=5, nextThoughtNeeded=false)
```

---

### 전략 4: Self-Ask `--self-ask`

**용도**: 복잡한 시스템 이해, 다층 질문, 연구형 질문, "어떻게 동작하는가"

**Sequential Thinking 매핑**:
- 핵심 질문을 하위 질문으로 분해
- `needsMoreThoughts`로 동적 확장

**패턴**:
```
핵심질문+하위질문도출(T1) → Q1답변(T2) → Q2답변(T3) → Q3답변(T4)
→ 추가질문점검(T5, needsMoreThoughts) → 종합(T6)
```

**호출 예시**:
```
sequentialthinking(thought="핵심질문: Kubernetes의 스케줄링은 어떻게 동작하는가? 하위질문: Q1)노드선택 기준? Q2)리소스할당? Q3)어피니티 규칙?",
  thoughtNumber=1, totalThoughts=5, nextThoughtNeeded=true)
sequentialthinking(thought="Q1 답변: 노드 선택은...",
  thoughtNumber=2, totalThoughts=5, nextThoughtNeeded=true)
...
sequentialthinking(thought="추가 질문 점검: Q4가 필요한가?",
  thoughtNumber=5, totalThoughts=6, nextThoughtNeeded=true, needsMoreThoughts=true)
sequentialthinking(thought="종합: ...",
  thoughtNumber=6, totalThoughts=6, nextThoughtNeeded=false)
```

---

### 전략 5: ReAct (Reason + Act) `--react`

**용도**: 증거 기반 조사, 디버깅, 장애 분석, 성능 병목 추적

**Sequential Thinking 매핑**:
- Observe-Hypothesize-Act-Analyze 루프
- `isRevision`으로 가설 업데이트
- **특이점**: Sequential Thinking 호출 **사이에** 실제 도구(Read, Grep, Bash) 호출

**패턴**:
```
관찰+가설(T1) → 행동계획(T2) → [도구 호출] → 증거분석(T3, isRevision)
→ 가설수정(T4) → [도구 호출] → 결론(T5)
```

**호출 예시**:
```
sequentialthinking(thought="관찰: 메모리 사용량이 점진적 증가. 가설: 이벤트 리스너 미해제",
  thoughtNumber=1, totalThoughts=5, nextThoughtNeeded=true)
sequentialthinking(thought="행동 계획: addEventListener 호출을 검색하고 removeEventListener 쌍을 확인",
  thoughtNumber=2, totalThoughts=5, nextThoughtNeeded=true)
# --- 여기서 Grep/Read 등 실제 도구 호출 ---
sequentialthinking(thought="증거 분석: 3곳에서 리스너 미해제 발견. 가설 수정: ...",
  thoughtNumber=3, totalThoughts=5, nextThoughtNeeded=true,
  isRevision=true, revisesThought=1)
```

---

### 전략 6: OODA Loop `--ooda`

**용도**: 빠른 의사결정, 상황 변화 대응, 실시간 모니터링, 인시던트 대응

**Sequential Thinking 매핑**:
- 4단계 고정 구조 (Observe/Orient/Decide/Act)
- 필요시 `needsMoreThoughts`로 루프 반복

**패턴**:
```
Observe(T1): 현재 상황/데이터 수집
→ Orient(T2): 맥락 분석, 이전 경험 대조
→ Decide(T3): 선택지 중 최적 행동 선택
→ Act(T4): 실행 계획 구체화
→ [상황 변화 감지 시 루프 반복]
```

**호출 예시**:
```
sequentialthinking(thought="Observe: CPU 사용률 95%, 응답 지연 3초 이상...",
  thoughtNumber=1, totalThoughts=4, nextThoughtNeeded=true)
sequentialthinking(thought="Orient: 최근 배포 이력 확인, 유사 사례 대조...",
  thoughtNumber=2, totalThoughts=4, nextThoughtNeeded=true)
sequentialthinking(thought="Decide: 즉시 롤백 vs 스케일아웃 → 롤백 선택 (근거: ...)",
  thoughtNumber=3, totalThoughts=4, nextThoughtNeeded=true)
sequentialthinking(thought="Act: 1) kubectl rollout undo... 2) 모니터링 확인...",
  thoughtNumber=4, totalThoughts=4, nextThoughtNeeded=false)
```

---

### 전략 7: Ulysses Protocol `--ulysses`

**용도**: 고위험 의사결정, 프로덕션 변경, 되돌릴 수 없는 작업, 데이터 삭제

**Sequential Thinking 매핑**:
- 자기구속(pre-commitment) 패턴
- `branchFromThought`로 "편향 없는 분석" 분기 생성

**패턴**:
```
사전구속(T1): 위험 요소 및 인지 편향 목록화 (매몰비용, 확증편향, 낙관편향)
→ 분석(T2, branchId:"unbiased"): 편향 체크리스트를 의식하며 분석
→ 레드팀(T3, branchId:"devil"): 의도적으로 반대 논거 구성
→ 수렴(T4): 두 분기 비교 → 편향 보정된 최종 결정
→ 안전장치(T5): 롤백 계획 필수 포함
```

**호출 예시**:
```
sequentialthinking(thought="사전 구속: DB 마이그레이션 결정. 인지 편향 체크리스트: 매몰비용(이미 투자한 시간), 확증편향(성공 사례만 기억), 낙관편향(장애 확률 과소평가)",
  thoughtNumber=1, totalThoughts=5, nextThoughtNeeded=true)
sequentialthinking(thought="편향 의식 분석: 체크리스트를 참조하며 객관적 평가...",
  thoughtNumber=2, totalThoughts=5, nextThoughtNeeded=true,
  branchFromThought=1, branchId="unbiased")
sequentialthinking(thought="레드팀: 이 마이그레이션이 실패할 수 있는 모든 시나리오...",
  thoughtNumber=3, totalThoughts=5, nextThoughtNeeded=true,
  branchFromThought=1, branchId="devil")
sequentialthinking(thought="수렴: 두 분기 비교. 편향 보정 후 최종 결정...",
  thoughtNumber=4, totalThoughts=5, nextThoughtNeeded=true)
sequentialthinking(thought="안전장치: 롤백 계획 - 1) pg_dump 백업 2) 마이그레이션 다운 스크립트 3) 블루-그린 전환점...",
  thoughtNumber=5, totalThoughts=5, nextThoughtNeeded=false)
```

---

## 기존 플래그와의 통합

| 조합 | 깊이 | 전략 | 동작 |
|------|------|------|------|
| `--think` (단독) | 4K | 기본 Sequential | 기존대로 |
| `/thinking` (단독) | 자동 | 자동 라우팅 | 전략만 적용 |
| `--think-hard --tot` | 10K | ToT 고정 | 깊이+전략 |
| `--ultrathink /thinking` | 32K | 자동 라우팅 | 최대 깊이+전략 |

**우선순위**: 명시적 전략 플래그 > 자동 라우팅 > 기본값(CoT)

---

## 사용 예시

### 예시 1: 아키텍처 비교 (자동 → ToT)
```
사용자: "REST vs gRPC 비교해줘 /thinking"
→ "비교" 키워드 감지 → ToT 자동 선택
→ 분기 생성(REST/gRPC) → 기준별 평가 → 수렴
```

### 예시 2: 디버깅 (명시적 ReAct)
```
사용자: "메모리 누수 원인 찾아줘 --react"
→ 명시적 ReAct 오버라이드
→ 관찰→가설→[Grep/Read]→증거분석→결론
```

### 예시 3: 프로덕션 변경 (자동 → Ulysses)
```
사용자: "프로덕션 DB 스키마 변경해야 해 /thinking"
→ "프로덕션" 키워드 감지 → Ulysses 자동 선택
→ 편향 인식→분석→레드팀→안전장치 포함 결정
```

### 예시 4: 깊이+전략 조합
```
사용자: "이 시스템 전체 흐름 분석해줘 --think-hard --self-ask"
→ 깊이 10K + Self-Ask 전략
→ 하위 질문 분해→개별 답변→동적 확장→종합
```
