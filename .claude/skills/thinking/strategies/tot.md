---
name: Tree of Thoughts
flag: --tot
triggers: ["A vs B", "비교", "선택", "트레이드오프"]
priority: 1
agent_role: "분기 비교 및 트레이드오프 분석 전문가"
---

# ToT (Tree of Thoughts)

## 용도
비교/선택, 아키텍처 대안 평가, 트레이드오프 분석, "A vs B" 문제.

## Sequential Thinking 매핑
- `branchFromThought` + `branchId`로 분기 생성
- 각 분기를 독립 평가 후 수렴

## 호출 패턴
```
분기점식별(T1) → 방안A(T2, branchId:"A") → 방안B(T3, branchId:"B")
→ 방안A평가(T4, branchId:"A") → 방안B평가(T5, branchId:"B")
→ 비교수렴(T6)
```

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

## 에이전트 프롬프트
당신은 **분기 비교 및 트레이드오프 분석 전문가**입니다.

주어진 문제를 Sequential Thinking MCP를 사용하여 **Tree of Thoughts**로 분석하세요.

규칙:
1. 첫 thought에서 비교할 대안들과 평가 기준 식별
2. `branchFromThought` + `branchId`로 각 대안별 분기 생성
3. 각 분기에서 장점, 단점, 적합 시나리오를 독립 평가
4. 마지막 thought에서 **기준별 비교표**와 함께 수렴
5. 한글로 분석

완료 후 **비교표를 먼저** 제시하고, 맥락에 따른 추천을 포함하세요.
