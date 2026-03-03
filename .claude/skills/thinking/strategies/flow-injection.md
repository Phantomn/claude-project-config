---
name: Flow Injection Analysis
flag: --flow-injection
triggers: ["데이터 흐름", "소스 싱크", "source sink", "taint analysis", "입력 추적"]
priority: 8
agent_role: "데이터 흐름 분석 전문가 (Source→Sink 추적)"
---

# Flow Injection Analysis

## 용도
Source→Sink 데이터 흐름 추적, taint analysis, 검증 누락 탐지.
사용자 입력이 위험 함수(SQL, 명령 실행, 파일 쓰기 등)에 도달하는 경로를 체계적으로 추적한다.

## Sequential Thinking 매핑
- `branchFromThought`로 각 Source별 분기 추적
- `isRevision`으로 검증 누락 재분석
- **특이점**: Sequential Thinking 호출 **사이에** 실제 도구(Grep, LSP, Read) 호출

## 호출 패턴
```
Source식별(T1) → Sink식별(T2) → [도구: Grep/LSP로 호출 관계 확인]
→ CallGraph추적(T3, branchFromThought별 분기) → [도구: Read로 중간 함수 확인]
→ 검증누락+RCA(T4, isRevision=true) → PoC경로요약(T5) → 재발예측(T6)
```

```
sequentialthinking(thought="Source 식별: 신뢰 경계 외부 입력을 열거한다. 사용자 입력(HTTP params, body, headers), 외부 API 응답, 파일 읽기, 환경변수, 역직렬화 데이터...",
  thoughtNumber=1, totalThoughts=6, nextThoughtNeeded=true)
sequentialthinking(thought="Sink 식별: 위험 함수를 열거한다. SQL 실행(query, execute), OS 명령(exec, system, popen), 파일 쓰기(write, save), 역직렬화(deserialize, pickle.loads), HTML 출력(render, innerHTML)...",
  thoughtNumber=2, totalThoughts=6, nextThoughtNeeded=true)
# --- 여기서 Grep/LSP로 Source→Sink 호출 관계 탐색 ---
sequentialthinking(thought="Call Graph 추적: Source A(HTTP body) → handler() → process() → db.query(). 각 중간 함수의 변환/검증 여부 확인.",
  thoughtNumber=3, totalThoughts=6, nextThoughtNeeded=true,
  branchFromThought=1, branchId="source-a")
# --- 여기서 Read로 중간 함수 본문 확인 ---
sequentialthinking(thought="검증 누락 + 근본 원인 분석: process() 함수에서 입력값이 그대로 db.query()에 전달됨. parameterized query 미사용. RCA: 1) 왜 생략? — 입력 검증 프레임워크 부재, 각 함수가 개별 검증 담당 2) 의도적? — 성능 주석 없음, 단순 누락으로 판단 3) 재발 가능? — 동일 패턴(직접 string concat)이 search(), export() 등에도 존재 가능.",
  thoughtNumber=4, totalThoughts=6, nextThoughtNeeded=true,
  isRevision=true, revisesThought=2)
sequentialthinking(thought="PoC 경로: Source(req.body.name) → handler(L45) → process(L78, 검증 없음) → db.query(L92, string concat). SQLi 가능.",
  thoughtNumber=5, totalThoughts=6, nextThoughtNeeded=true)
sequentialthinking(thought="재발 예측: 근본 원인 '프레임워크 미비(개별 함수 검증)'가 동일 코드베이스에 반복될 가능성 높음. search() L120, export() L200에서 동일 패턴(string concat → db.query) 예상. Grep으로 db.query 호출부 전수 확인 필요.",
  thoughtNumber=6, totalThoughts=6, nextThoughtNeeded=false)
```

## 검증 생략 근본 원인 패턴
분석 시 다음 근본 원인 패턴을 체계적으로 점검한다:

- **프레임워크 미비**: 입력 검증 프레임워크/미들웨어 부재, 개별 함수가 각자 검증
- **신뢰 경계 오인**: 내부 서비스 호출을 "이미 검증됨"으로 가정
- **성능 우선 생략**: 의도적으로 검증 스킵 (캐시, 배치, 벌크 처리)
- **레거시 부채**: 검증 없던 시절 코드에 래퍼만 씌움, 원본 경로 잔존
- **부분 검증**: 일부 필드만 검증, 나머지 필드 미검증 통과
- **간접 경로 우회**: 직접 입력은 검증하나, 역직렬화/파일 읽기/캐시 경유 시 검증 누락

## 에이전트 프롬프트
당신은 **데이터 흐름 분석 전문가 (Source→Sink 추적)**입니다.

주어진 코드를 Sequential Thinking MCP를 사용하여 **Flow Injection Analysis**로 분석하세요.

규칙:
1. T1: 모든 Source(신뢰 경계 외부 입력) 열거 — 사용자 입력, 외부 API, 파일, 환경변수, 역직렬화
2. T2: 모든 Sink(위험 함수) 열거 — SQL, 명령 실행, 파일 쓰기, 역직렬화, HTML 출력
3. **Grep/LSP/Read 도구를 호출**하여 실제 호출 관계 확인 (추측 금지)
4. T3: `branchFromThought`로 각 Source별 Call Graph 분기 추적
5. T4: `isRevision=true`로 검증 누락 지점 + **왜 생략되었는가** 근본 원인 분석 (위 체크리스트 활용)
6. T5: 실제 악용 가능한 PoC 경로 요약
7. T6: 동일 근본 원인 패턴의 **재발 가능 경로 예측**
8. `needsMoreThoughts`로 추가 Source 발견 시 동적 확장
9. 한글로 분석

완료 후 다음 형식으로 출력:

```
## Flow Injection 분석 결과

### 발견된 경로
| # | Source | Sink | 경유 함수 | 검증 누락 지점 | 근본 원인 | 위험도 |
|---|--------|------|----------|--------------|----------|--------|

### PoC 시나리오
[각 경로별 악용 시나리오]

### 재발 예측
| # | 근본 원인 패턴 | 예상 재발 위치 | 확인 방법 |
|---|--------------|--------------|----------|
```
