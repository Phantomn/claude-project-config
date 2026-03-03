---
name: Red vs Blue Security Loop
flag: --red-blue
description: "Red(공격 PoC 생성) vs Blue(유효성 비판 + Duplicate 필터링) 보안 대립 분석"
---

# Red vs Blue Security Loop

## 개요
**Red Agent**(공격)와 **Blue Agent**(방어/검증) 2개 에이전트를 **순차 실행**하여, 실제 악용 가능한 취약점만 필터링한다.
Adversarial 모드와 달리 **순차 실행**(Red → Blue)이며, 보안 도메인에 특화된 역할과 판정 기준을 사용한다.

## vs Adversarial 모드
| | Adversarial | Red vs Blue |
|---|---|---|
| 실행 순서 | 병렬 (Advocate + Critic 동시) | 순차 (Red → Blue) |
| 역할 | 범용 찬반 논쟁 | 보안 공격/방어 |
| 기반 전략 | CoT + Step-Back/Ulysses | Flow-Injection + Invariant / Step-Back + ReAct |
| 판정 | 균형 잡힌 결론 | VALID_NOVEL / VALID_KNOWN / INVALID |
| Duplicate 필터 | 없음 | Blue가 CWE + Duplicate 확률 판정 |

## 역할 정의

### Red Agent (공격)
- **기반 전략**: Flow-Injection + Invariant
- **목표**: 실제 악용 가능한 취약점 경로 발견 + PoC 구성
- **행동 원칙**:
  - Source→Sink 추적으로 기술적 경로 확보
  - 불변 규칙 우회로 비즈니스 로직 결함 탐색
  - 추측 금지, 도구로 코드를 직접 읽고 분석

### Blue Agent (방어/검증)
- **기반 전략**: Step-Back + ReAct
- **목표**: Red의 PoC 실현 가능성 검증 + 알려진 패턴(Duplicate) 필터링
- **행동 원칙**:
  - Step-Back으로 Red의 주장을 한 단계 추상화하여 전제조건 점검
  - ReAct로 실제 코드를 읽어 Red의 PoC가 트리거 가능한지 증거 기반 검증
  - CWE 매핑 + Duplicate 확률 추정

## 실행 절차

### 1. Red Agent 호출

```
Agent(subagent_type="general-purpose",
  description="Red Agent 보안 분석",
  prompt="""당신은 **Red Agent(공격자)**입니다.

주어진 코드에서 실제 악용 가능한 취약점을 찾으세요.
Sequential Thinking MCP를 사용하되, 두 가지 전략을 결합합니다:

**전략 1 - Flow Injection**: Source(신뢰 경계 외부 입력) → Sink(위험 함수) 경로 추적
**전략 2 - Invariant**: 비즈니스 불변 규칙 도출 → 우회 엣지케이스 역추적

규칙:
1. Read/Grep/LSP 도구로 코드를 **직접 읽고** 분석 (추측 금지)
2. 각 취약점에 Source→Sink 또는 불변 규칙→우회 경로 명시
3. PoC 스텝을 구체적으로 작성 (요청 형태, 파라미터, 기대 결과)
4. 한글로 분석

## 분석 대상
[사용자가 지정한 파일/코드]

## 출력 형식
각 취약점 후보를 다음 형식으로:

### 후보 N: [취약점 제목]
- **유형**: Flow Injection / Invariant 위반
- **Source→Sink 경로** 또는 **위반 규칙**: [상세]
- **전제조건**: [필요한 조건]
- **PoC 스텝**: [구체적 단계]
- **예상 CWE**: [CWE-XXX]
- **예상 영향**: [기밀성/무결성/가용성]
""")
```

### 2. Blue Agent 호출 (Red 결과를 입력으로)

```
Agent(subagent_type="general-purpose",
  description="Blue Agent 검증",
  prompt="""당신은 **Blue Agent(방어자/검증자)**입니다.

Red Agent가 발견한 취약점 후보들의 **유효성을 검증**하세요.
Sequential Thinking MCP를 사용하되, 두 가지 전략을 결합합니다:

**전략 1 - Step-Back**: Red의 각 주장을 한 단계 추상화하여 전제조건과 숨겨진 가정 점검
**전략 2 - ReAct**: 실제 코드를 읽어 Red의 PoC가 트리거 가능한지 증거 기반 검증

규칙:
1. Read/Grep/LSP 도구로 코드를 **직접 읽고** 검증 (Red의 주장을 맹신 금지)
2. 각 후보에 대해:
   a. 실제 트리거 가능한가? (전제조건, 인증, 환경 제약)
   b. 방어 코드가 이미 존재하는가? (Red가 누락한 검증)
   c. 알려진 low-hanging fruit 패턴인가? (CWE 매핑)
   d. Duplicate 확률 (0-100%) + 근거
3. 판정 분류: VALID_NOVEL / VALID_KNOWN / INVALID
4. 한글로 분석

## Red Agent 분석 결과
{Red Agent의 전체 출력}

## 분석 대상
[사용자가 지정한 파일/코드]

## 출력 형식
각 후보에 대해:

### 후보 N: [취약점 제목]
- **Red 주장 요약**: [1-2줄]
- **검증 결과**:
  - 트리거 가능성: [가능/불가능 + 근거]
  - 기존 방어 코드: [있음/없음 + 위치]
  - Duplicate 확률: [0-100%] + [근거]
- **판정**: `VALID_NOVEL` / `VALID_KNOWN` / `INVALID`
- **판정 근거**: [상세]
""")
```

### 3. 결과 합성

메인 에이전트가 두 결과를 수신한 후 합성:

```markdown
## Red vs Blue 보안 분석 결과

### 최종 발견 (VALID_NOVEL)
| # | 취약점 | CWE | Source→Sink / 위반 규칙 | 공격 복잡도 | Blue 검증 |
|---|--------|-----|----------------------|-----------|----------|

### 알려진 패턴 (VALID_KNOWN) — 참고용
| # | 취약점 | CWE | Duplicate 확률 | 이유 |
|---|--------|-----|---------------|------|

### Red 주장 → Blue 기각 (INVALID)
| # | Red 주장 | Blue 기각 근거 |
|---|---------|--------------|

### 에스컬레이션
[VALID_NOVEL 항목의 심층 분석이 필요하면 → `/panel --security`]
```

## 주의사항
- Red → Blue **순차** 실행 (Blue는 Red 결과에 의존)
- Blue는 가능하면 다른 모델 사용 **권장** (동일 편향 방지, 강제 아님)
- 각 에이전트에 **분석 대상 파일 원문** 포함 필수 (파일 경로 전달)
- Red의 PoC가 모두 INVALID이면 "방어가 적절함" 결론도 유효
- VALID_KNOWN은 "이미 보고된 가능성 높음"이므로 신규 제출에 부적합
