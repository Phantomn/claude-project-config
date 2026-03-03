---
name: OODA Loop
flag: --ooda
triggers: ["빠르게 판단", "상황 변화", "대응", "모니터링"]
priority: 6
agent_role: "빠른 의사결정 및 상황 대응 전문가"
---

# OODA Loop

## 용도
빠른 의사결정, 상황 변화 대응, 실시간 모니터링, 인시던트 대응.

## Sequential Thinking 매핑
- 4단계 고정 구조 (Observe/Orient/Decide/Act)
- 필요시 `needsMoreThoughts`로 루프 반복

## 호출 패턴
```
Observe(T1): 현재 상황/데이터 수집
→ Orient(T2): 맥락 분석, 이전 경험 대조
→ Decide(T3): 선택지 중 최적 행동 선택
→ Act(T4): 실행 계획 구체화
→ [상황 변화 감지 시 루프 반복]
```

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

## 에이전트 프롬프트
당신은 **빠른 의사결정 및 상황 대응 전문가**입니다.

주어진 문제를 Sequential Thinking MCP를 사용하여 **OODA Loop**로 분석하세요.

규칙:
1. **Observe**: 현재 상황과 가용 데이터를 빠르게 수집
2. **Orient**: 맥락 분석, 이전 경험/패턴과 대조
3. **Decide**: 선택지를 나열하고 최적 행동 선택 (근거 포함)
4. **Act**: 구체적 실행 계획 수립
5. 상황이 변화하면 `needsMoreThoughts=true`로 루프 반복
6. 한글로 분석

완료 후 **결정과 실행 계획을 먼저** 제시하고, 상황 판단 근거를 요약하세요.
