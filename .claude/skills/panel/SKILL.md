---
name: panel
description: N-Agent Panel 실행 및 합성. 다중 에이전트를 병렬 스폰하여 분석 후 수렴/발산점 합성.
triggers:
  - "/panel"
  - "패널 분석"
  - "N-Agent Panel"
  - "multi-agent analysis"
---

# /panel - N-Agent Panel 스킬

## What
N개(3~7) 에이전트를 병렬 스폰하여 동일 주제를 서로 다른 전략으로 분석한 뒤, 수렴/발산점을 합성하는 캠페인 스킬.

## vs /thinking --panel
| | `/thinking --panel` | `/panel` |
|---|---|---|
| 에이전트 수 | 2-3 | 3-7 |
| 도구 | Sequential Thinking MCP | Team + Task + Agent |
| 수명 | 단일 턴 | 다중 턴 캠페인 |
| 합성 | 메인 에이전트 인라인 | 구조화된 수렴/발산 보고서 |
| 메모리 | 없음 | MEMORY.md 자동 기록 |

## When
- 복잡한 코드 분석 (근본 원인 규명, 아키텍처 결정)
- 3개 이상 관점이 필요한 기술 의사결정
- cross-validate가 필요한 가설 검증
- 대규모 코드베이스 전수 조사
- 취약점 심층 분석 (`--security` 플래그)

## Input Format

사용자가 `/panel` 호출 시 다음 정보를 수집한다:

```yaml
topic: "분석 주제 (한 문장)"
agents: 7                          # 3~7, 기본 7
files:                             # 에이전트가 읽을 파일 목록
  - path: "path/to/target.cpp"
    role: "분석 대상"
  - path: "path/to/reference.py"
    role: "정상 참조"
references:                        # 선행 분석 결과 (선택)
  - path: "memory/prior_analysis.md"
    type: "증거"
questions:                         # 에이전트별 핵심 질문 (선택)
  - agent: CoT
    focus: "Type B 발생 경로 완전 추적"
```

**간편 호출**: `/panel "주제" --files file1,file2 --agents 5`

정보가 불충분하면 AskUserQuestion으로 수집한다.

## Workflow

### 1단계: 설정 (Setup)

1. 사용자 입력에서 `topic`, `files`, `agents` 추출
2. 에이전트 수에 맞는 전략 조합 결정:

| 에이전트 수 | 전략 조합 |
|------------|----------|
| 3 | CoT, ReAct, Step-Back |
| 5 | CoT, ToT, ReAct, Self-Ask, Ulysses |
| 7 | CoT, ToT, Step-Back, Self-Ask, ReAct, OODA, Ulysses |

#### `--security` 모드 전략 조합

| 에이전트 수 | 전략 조합 | 역할 |
|------------|----------|------|
| 3 | Flow-Injection, Invariant, ReAct | 흐름분석+RCA + 규칙분석 + 증거검증 |
| 5 | Flow-Injection, Invariant, ReAct, Step-Back, Ulysses | + 추상화 + 위험평가 |
| 7 | Flow-Injection, Invariant, CoT, ReAct, Step-Back, OODA, Ulysses | 전체 커버리지 |

3. 사용자에게 설정 요약 표시 후 확인

### 2단계: 팀 생성 (Spawn)

```
TeamCreate(team_name="panel-{topic-slug}")
```

각 에이전트에 대해:
```
TaskCreate(subject="[전략명] 분석: {topic}")
Agent(subagent_type="code-analyzer", model="sonnet",
  team_name="panel-{topic-slug}",
  name="{strategy-name}",
  run_in_background=true,
  prompt="""
  당신은 [{전략명}] 전략으로 분석하는 에이전트입니다.

  ## 분석 주제
  {topic}

  ## 핵심 질문
  {question}

  ## 입력 파일
  다음 파일들을 직접 읽어서 분석하세요 (추측 금지):
  {files 목록}

  ## 선행 분석 참조
  {references 목록}

  ## 전략 지침
  {strategies/xxx.md의 에이전트 프롬프트}

  ## 출력 형식
  분석 완료 후 다음 구조로 결과를 반환하세요:

  ### 결론
  [핵심 결론 2-3문장]

  ### 증거
  [파일명:줄번호 + 코드 인용]

  ### 유형 분류 (해당 시)
  [Type X(N건): 설명]

  ### 확신도
  [0-100%] + 근거
  """)
```

### 3단계: 수집 (Collect)

- 각 에이전트 완료 메시지 자동 수신
- 모든 에이전트 완료 대기
- 미완료 에이전트가 있으면 상태 확인 후 추가 대기

### 4단계: 합성 (Synthesize)

모든 결과를 수신한 후 Sequential Thinking MCP로 합성:

```
sequentialthinking(
  thought="Panel 합성: N개 에이전트 결과를 수렴/발산점으로 분류",
  totalThoughts=4
)
```

**합성 구조**:

```markdown
## 수렴점 (N/N 에이전트 동의)
[모든 에이전트가 동의하는 결론]

## 다수 합의 (≥5/7 동의)
[다수결로 확정된 결론]

## 발산점
| 쟁점 | 측 A | 측 B | 해결 | 근거 |
|------|------|------|------|------|

## 유형별 확정
| 유형 | 건수 | 근본 원인 | 확정 에이전트 |
|------|------|----------|-------------|

## 미해결 질문
[추가 분석이 필요한 항목]

#### `--security` 모드 합성 (위 합성 구조에 추가)

## Duplicate 위험도 평가
| 취약점 | CWE | 알려진 패턴? | Duplicate 확률 | 최종 판정 |
|--------|-----|------------|---------------|----------|

## 공격 복잡도 (Attack Complexity)
| 취약점 | 전제조건 | 인증 필요 | 체인 수 | AC 등급 |
|--------|---------|----------|--------|--------|

## 비즈니스 영향 (Business Impact)
| 취약점 | 불변 규칙 위반 | 영향 범위 | 심각도 |
|--------|--------------|----------|--------|

## 근본 원인 패턴 집계
| 근본 원인 패턴 | 해당 취약점 | 발견 에이전트 | 빈도 |
|--------------|-----------|-------------|------|

## 재발 예측 매트릭스
| # | 근본 원인 패턴 | 예상 재발 위치 | 확인 방법 | 우선순위 |
|---|--------------|--------------|----------|---------|

## 과거 분석 참조
[memory/panel-* 이전 분석 참조 → 중복 회피]

## 에이전트별 확신도
| 에이전트 | 전략 | 확신도 | 핵심 기여 |
|----------|------|--------|----------|
```

### 5단계: 기록 (Record)

1. `memory/panel-{topic-slug}.md`에 합성 결과 저장
2. MEMORY.md에 1줄 요약 + 파일 참조 추가
3. 파일 참조 목록에 새 파일 등록

### 6단계: 정리 (Cleanup)

```
각 에이전트에게 SendMessage(type="shutdown_request")
TeamDelete()
```

## Gotchas

- **에이전트가 파일을 추측하면 안 됨**: 프롬프트에 "직접 읽어서 분석 (추측 금지)" 명시
- **전략 분리 필수**: 동일 전략 → 동일 결론. 반드시 다른 전략 할당
- **ReAct(전수 조사) 포함 필수**: 추론 에이전트 "11건" → 전수 조사 "15건" 발견 사례
- **합성에서 depth 우선**: 발산점 해결 시 분석 depth 깊은 쪽 > 얕은 판정
- **비용 주의**: 7 에이전트 = 토큰 ~7배. 사용자에게 예상 비용 안내
- **후처리 추천 금지**: 에이전트가 자체적으로 추천하는 "band-aid" 해결책은 합성에서 제외. 사용자가 요청한 분석 범위만 보고

## Integration

- `/thinking --panel`과 직교: `/panel`은 캠페인, `--panel`은 즉석 분석
- `/wrap`에서 Panel 결과 참조 가능
- `/breakdown`으로 Panel 결과 → 수정 계획 변환 가능

## File Structure

```
.claude/skills/panel/
├── SKILL.md            # 현재 파일
.claude/skills/thinking/
├── strategies/         # 전략 프롬프트 (공유)
│   ├── cot.md
│   ├── tot.md
│   ├── step-back.md
│   ├── self-ask.md
│   ├── react.md
│   ├── ooda.md
│   ├── ulysses.md
│   ├── flow-injection.md  # 보안: Source→Sink 추적
│   └── invariant.md       # 보안: 불변 규칙 우회
└── modes/
    └── panel.md        # 2-3 에이전트 즉석 분석 (별개)
```

## Examples

### 최소 호출
```
/panel "ASTree.cpp return-except indent 근본 원인 분석" --files ASTree.cpp,cdc.py --agents 7
```

### 상세 호출
```
/panel
topic: "ET dedup 로직이 multi-except handler를 누락하는 메커니즘"
agents: 5
files:
  - ASTree.cpp (분석 대상)
  - v274.py (정상 참조)
references:
  - memory/phase4a_bis_rootcause_analysis.md
questions:
  - CoT: "L375 dedup 조건의 정확한 평가 경로"
  - ReAct: "5건 각각의 ET entry 매핑"
```
