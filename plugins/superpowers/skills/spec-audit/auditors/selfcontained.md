# 축 selfcontained

## 4.4.1 감사 축 (selfcontained 행)

| `selfcontained` | placeholder(4.4.4), **요건→Task** 커버리지(유일 소유), Step의 검증 가능한 결과, Review Focus 각 줄의 고정 테스트, Success Criteria의 기계적 판정 가능성, 구현 전 검증 가능한 명령·코드의 실제 실행(4.4.5), D7 가정 형식(4.4.7) |

## 4.4.4 placeholder

구현자에게 결정을 남기는 줄: 값·이름·동작·범위가 정해지지 않은 줄("적절히 처리", "add appropriate validation", "handle edge cases", "TBD", 내용 없는
"Task N과 유사", 요구 열거로서의 "등/etc."). 제외: Expiry(YYYY-MM-DD)·Owner·Removal이 모두 붙은 TODO/FIXME, 서술 문장의 조사 "등", 문서가 선언한 구현 재량.

## 4.4.7 D7 가정 형식

가정 항목이 ① 가정(한 문장) ② 실측 프로브(PLAN의 구체 Step: 명령 + 기대 결과, 그 사실에 기대는 첫 Task 이전 또는 그 Task의 첫 Step. spec 단독 감사면
"구현 Task 1" 지정만 확인) ③ 실패 시 대안(구체 행동)을 모두 가지면 그 검증 불가 사항은 finding이 아니다. 형식 위반은 selfcontained `assumption-form`(`align`),
대안 실행 불가는 rootcause `premise`(`requirement`).
