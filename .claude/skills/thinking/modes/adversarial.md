---
name: Adversarial Analysis
flag: --adversarial
description: "Advocate(찬성) vs Critic(반대) 대립 분석 후 균형 잡힌 결론"
---

# Adversarial 모드 (대립 분석)

## 개요
**Advocate(옹호자)**와 **Critic(비평가)** 2개 에이전트를 병렬 실행하여 대립적 관점을 생성한 뒤, 메인 에이전트가 쟁점을 대조하여 균형 잡힌 결론을 도출한다.

## 역할 정의

### Advocate (옹호자)
- **기반 전략**: CoT
- **관점**: 실행 가능성, 장점, 기대 효과에 집중
- **목표**: 제안이 왜 좋은 선택인지 최대한 설득력 있게 논증

### Critic (비평가)
- **기반 전략**: Step-Back + Ulysses
- **관점**: 리스크, 약점, 숨겨진 가정, 실패 시나리오에 집중
- **목표**: 제안의 문제점을 최대한 날카롭게 지적

## 실행 절차

### 1. 두 에이전트 병렬 호출

**Advocate Task**:
```
Task(subagent_type="general-purpose",
  description="Advocate 분석",
  prompt="당신은 **Advocate(옹호자)**입니다.

주어진 제안/결정에 대해 Sequential Thinking MCP를 사용하여 **찬성 논거**를 구성하세요.

규칙:
1. Chain of Thought 방식으로 순차적 논증
2. 실행 가능성, 장점, 기대 효과에 집중
3. 구체적 근거와 사례를 포함
4. 최대한 설득력 있게 구성
5. 한글로 분석

분석 대상: [사용자 질문]")
```

**Critic Task**:
```
Task(subagent_type="general-purpose",
  description="Critic 분석",
  prompt="당신은 **Critic(비평가)**입니다.

주어진 제안/결정에 대해 Sequential Thinking MCP를 사용하여 **반대 논거**를 구성하세요.

규칙:
1. Step-Back으로 한 단계 추상화하여 숨겨진 가정 식별
2. Ulysses Protocol로 인지 편향 체크 (매몰비용, 확증편향, 낙관편향)
3. 리스크, 약점, 실패 시나리오에 집중
4. 대안이 있다면 제시
5. 한글로 분석

분석 대상: [사용자 질문]")
```

### 2. 결과 대조 및 합성
메인 에이전트가 두 결과를 수신한 후:

```markdown
## 대립 분석 결과

### Advocate (찬성)
[옹호자의 핵심 논거 요약]

### Critic (반대)
[비평가의 핵심 논거 요약]

### 쟁점 대조
| 쟁점 | Advocate | Critic |
|------|----------|--------|
| [쟁점1] | [찬성 논거] | [반대 논거] |
| [쟁점2] | [찬성 논거] | [반대 논거] |

### 균형 잡힌 결론
[양측 논거를 종합한 최종 판단 + 조건부 추천]
```

## 주의사항
- 두 Task는 반드시 **단일 메시지에서 병렬 호출**
- 각 에이전트에 **사용자 질문 원문**을 반드시 포함
- 합성 시 한쪽에 치우치지 않도록 주의
- 최종 결론에는 **조건**(~한다면 A, ~한다면 B)을 포함
