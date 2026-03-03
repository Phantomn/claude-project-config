---
name: Invariant-based Analysis
flag: --invariant
triggers: ["불변 규칙", "비즈니스 로직", "권한 우회", "invariant", "엣지케이스", "race condition"]
priority: 9
agent_role: "비즈니스 불변 규칙 기반 분석 전문가"
---

# Invariant-based Analysis

## 용도
비즈니스 불변 규칙을 선정의(先定義)한 뒤, 코드에서 규칙을 우회할 수 있는 엣지케이스를 역추적한다.
Low-hanging fruit(단순 injection)이 아닌, 비즈니스 로직 결함을 체계적으로 발굴한다.

## Sequential Thinking 매핑
- `needsMoreThoughts`로 불변 규칙 동적 확장
- `branchId`로 규칙별 독립 분석 분기
- `isRevision`으로 우회 가능성 재검증

## 호출 패턴
```
도메인컨텍스트(T1) → 불변규칙도출(T2, needsMoreThoughts)
→ enforcement매핑(T3, branchId별 분기) → [도구: Read/Grep으로 enforcement 코드 확인]
→ 우회역추적(T4, isRevision=true) → 엣지케이스구성(T5) → PoC시나리오(T6)
```

```
sequentialthinking(thought="도메인 컨텍스트: 아키텍처, 권한 모델, 상태 머신, 데이터 흐름을 파악한다. 인증/인가 체계, 리소스 소유권, 상태 전이 규칙 식별.",
  thoughtNumber=1, totalThoughts=6, nextThoughtNeeded=true)
sequentialthinking(thought="불변 규칙 도출: 1) 잔액 < 0 불가 2) 관리자만 삭제 가능 3) 초기화 전 쓰기 불가 4) 한 사용자가 타인 데이터 접근 불가 5) 동일 트랜잭션 중복 처리 불가...",
  thoughtNumber=2, totalThoughts=6, nextThoughtNeeded=true,
  needsMoreThoughts=true)
# --- 여기서 Read/Grep으로 enforcement 코드 확인 ---
sequentialthinking(thought="Enforcement 매핑 - 규칙 1(잔액 < 0 불가): balance_check() at wallet.py:L89. 서버 사이드 검증 존재 확인.",
  thoughtNumber=3, totalThoughts=6, nextThoughtNeeded=true,
  branchFromThought=2, branchId="rule-1")
sequentialthinking(thought="우회 가능성 역추적 - 규칙 1: Race condition(TOCTOU) 가능성. balance_check()와 deduct() 사이에 락 없음. 동시 요청으로 잔액 < 0 가능.",
  thoughtNumber=4, totalThoughts=6, nextThoughtNeeded=true,
  isRevision=true, revisesThought=3)
sequentialthinking(thought="엣지케이스 구성: 동시 2개 요청(잔액 100, 각 80 차감) → check 통과 → 둘 다 deduct → 잔액 -60",
  thoughtNumber=5, totalThoughts=6, nextThoughtNeeded=true)
sequentialthinking(thought="PoC 시나리오: curl로 동시 요청 2건 전송. 잔액 음수 도달 확인.",
  thoughtNumber=6, totalThoughts=6, nextThoughtNeeded=false)
```

## 우회 패턴 체크리스트
분석 시 다음 우회 패턴을 체계적으로 점검한다:

- **Race Condition (TOCTOU)**: 검증과 실행 사이 시간 갭
- **Integer Overflow/Underflow**: 수치 경계값 조작
- **Type Confusion**: 타입 검증 우회 (문자열 → 숫자, null 주입)
- **Mass Assignment**: 허용되지 않은 필드 바인딩
- **인증/인가 갭**: 인증 통과 후 인가 누락, 수평/수직 권한 상승
- **상태 머신 위반**: 허용되지 않은 상태 전이 (주문 취소 후 배송 등)
- **시간 기반 우회**: 만료 검증 누락, 시간대 혼동
- **배치/대량 처리 우회**: 단건은 검증하나 배치는 건너뜀

## 에이전트 프롬프트
당신은 **비즈니스 불변 규칙 기반 분석 전문가**입니다.

주어진 코드를 Sequential Thinking MCP를 사용하여 **Invariant-based Analysis**로 분석하세요.

규칙:
1. T1: 도메인 컨텍스트 파악 — 아키텍처, 권한 모델, 상태 머신
2. T2: 불변 규칙 도출 — `needsMoreThoughts`로 동적 확장
3. **Read/Grep 도구를 호출**하여 각 규칙의 enforcement 코드 확인 (추측 금지)
4. T3: `branchId`로 규칙별 enforcement 매핑
5. T4: `isRevision=true`로 우회 가능성 역추적 (위 체크리스트 활용)
6. T5-T6: 엣지케이스 구성 + PoC 시나리오
7. 한글로 분석

완료 후 다음 형식으로 출력:

```
## Invariant 분석 결과

### 불변 규칙 목록
| # | 규칙 | Enforcement 위치 | 상태 |
|---|------|-----------------|------|

### 우회 가능 엣지케이스
| # | 규칙 | 우회 패턴 | 전제조건 | PoC 개요 | 위험도 |
|---|------|----------|---------|---------|--------|

### PoC 시나리오
[각 우회 가능 엣지케이스별 상세 시나리오]

### 권장 조치
[각 우회 지점별 수정 방안]
```
