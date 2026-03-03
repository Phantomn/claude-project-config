---
name: thinking
description: 구조적 사고 전략 오케스트레이터. 9가지 추론 패턴(단일) + 4가지 합성 모드(다중 에이전트)를 지원합니다.
triggers:
  - "/thinking"
  - "/think"
  - "구조적 분석"
  - "깊이 생각"
  - "단계별 추론"
  - "structured thinking"
---

# Thinking Skill

Sequential Thinking MCP의 **9가지 사고 전략**과 Task 도구 기반 **4가지 합성 모드**를 오케스트레이션합니다.

## 원칙

- **바벨 전략**: 85% 단일 전략(직접 호출) / 15% 합성 모드(다중 에이전트)
- **자동 라우팅 기본**: 키워드 감지로 최적 전략 자동 선택
- **명시적 오버라이드**: 플래그로 전략/모드 강제 지정
- **직교 관계**: `--think` = 깊이(depth), `/thinking` = 전략(strategy) → 독립 조합

---

## 3단계 모드 결정 트리

사용자 입력을 분석하여 아래 순서로 처리한다. **먼저 매칭되는 단계를 적용**.

### Step 1: 합성 모드 감지
| 플래그 | 모드 | 동작 |
|--------|------|------|
| `--panel` | 병렬 분석 | `modes/panel.md` 읽고 실행 |
| `--adversarial` | 대립 분석 | `modes/adversarial.md` 읽고 실행 |
| `--red-blue` |  대립 분석 | `modes/red-blue.md` 읽고 실행 |
| `--iterative` | 순차 에스컬레이션 | `modes/iterative.md` 읽고 실행 |

→ 매칭 시 해당 모드 파일을 Read하여 **Task 도구 기반 다중 에이전트** 실행

### Step 2: 단일 전략 감지 (명시적 플래그)
| 플래그 | 전략 | 파일 |
|--------|------|------|
| `--cot` | Chain of Thought | `strategies/cot.md` |
| `--tot` | Tree of Thoughts | `strategies/tot.md` |
| `--step-back` | Step-Back Abstraction | `strategies/step-back.md` |
| `--self-ask` | Self-Ask | `strategies/self-ask.md` |
| `--react` | ReAct (Reason + Act) | `strategies/react.md` |
| `--ooda` | OODA Loop | `strategies/ooda.md` |
| `--ulysses` | Ulysses Protocol | `strategies/ulysses.md` |
| `--flow-injection` | Flow Injection Analysis | `strategies/flow-injection.md` |
| `--invariant` | Invariant-based Analysis | `strategies/invariant.md` |

→ 매칭 시 해당 전략 파일을 Read하여 **Sequential Thinking MCP 직접 호출**

### Step 3: 자동 라우팅 (키워드 매칭)
| 순서 | 감지 키워드 | 전략 | 플래그 |
|------|------------|------|--------|
| 1 | "A vs B", "비교", "선택", "트레이드오프" | ToT | `--tot` |
| 2 | "왜", "근본 원인", "반복되는", "막혔" | Step-Back | `--step-back` |
| 3 | "어떻게 동작", "구조", "전체 흐름" | Self-Ask | `--self-ask` |
| 4 | "버그", "디버그", "원인 찾아", "성능 분석" | ReAct | `--react` |
| 5 | "위험", "롤백 불가", "프로덕션", "삭제" | Ulysses | `--ulysses` |
| 6 | "데이터 흐름", "소스 싱크", "입력 추적", "taint" | Flow Injection | `--flow-injection` |
| 7 | "불변 규칙", "비즈니스 로직 취약점", "권한 우회", "race condition" | Invariant | `--invariant` |
| 8 | "빠르게 판단", "상황 변화", "대응", "모니터링" | OODA | `--ooda` |
| 9 | 기본값 | CoT | `--cot` |

→ 매칭된 전략 파일을 Read하여 **Sequential Thinking MCP 직접 호출**

---

## 기존 플래그와의 통합

| 조합 | 깊이 | 전략 | 동작 |
|------|------|------|------|
| `--think` (단독) | 4K | 기본 Sequential | 기존대로 |
| `/thinking` (단독) | 자동 | 자동 라우팅 | 전략만 적용 |
| `--think-hard --tot` | 10K | ToT 고정 | 깊이+전략 |
| `--ultrathink /thinking` | 32K | 자동 라우팅 | 최대 깊이+전략 |

**우선순위**: 합성 모드 > 명시적 전략 플래그 > 자동 라우팅 > 기본값(CoT)

---

## 단일 전략 실행 가이드

1. 결정 트리에서 전략 파일 경로 결정
2. `~/.claude/skills/thinking/strategies/[전략].md` 파일을 Read
3. "호출 패턴" 섹션을 참조하여 Sequential Thinking MCP 직접 호출
4. 결과를 사용자에게 반환

---

## 합성 모드 실행 가이드

1. 결정 트리에서 모드 파일 경로 결정
2. `~/.claude/skills/thinking/modes/[모드].md` 파일을 Read
3. 모드 파일의 "실행 절차"에 따라:
   - 필요한 `strategies/*.md` 파일의 "에이전트 프롬프트" 섹션을 Read
   - Task 도구로 에이전트 호출 (병렬 또는 순차)
   - `subagent_type`은 항상 `"general-purpose"` 사용
4. 모든 Task 결과를 수신한 후 모드 파일의 "합성 템플릿"에 따라 결과 합성
5. 합성 결과를 사용자에게 반환

---

## Fallback

전략/모드 파일 읽기에 실패한 경우, 인라인 CoT로 대체:

```
sequentialthinking(thought="문제: [사용자 질문]. 단계별로 분석한다.",
  thoughtNumber=1, totalThoughts=4, nextThoughtNeeded=true)
→ 순차적으로 진행
→ 마지막 thought에서 결론 도출
```

---

## 파일 구조

```
~/.claude/skills/thinking/
├── SKILL.md                    # ← 현재 파일 (오케스트레이터)
├── strategies/                 # 9개 전략 모듈
│   ├── cot.md                 # Chain of Thought
│   ├── tot.md                 # Tree of Thoughts
│   ├── step-back.md           # Step-Back Abstraction
│   ├── self-ask.md            # Self-Ask
│   ├── react.md               # ReAct (Reason + Act)
│   ├── ooda.md                # OODA Loop
│   ├── ulysses.md             # Ulysses Protocol
│   ├── flow-injection.md      # Flow Injection Analysis
│   └── invariant.md           # Invariant-based Analysis
└── modes/                      # 4개 합성 모드
    ├── panel.md               # 병렬 분석 (Fan-out/Fan-in)
    ├── adversarial.md         # 대립 분석 (Advocate vs Critic)
    ├── red-blue.md            # 대립 분석 (Red vs Blue)
    └── iterative.md           # 순차 에스컬레이션 (Pipeline)
```
