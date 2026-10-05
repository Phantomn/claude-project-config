# 축 selfcontained

## 4.4.1 감사 축 (selfcontained 행)

| `selfcontained` | placeholder(4.4.4), **요건→Task** 커버리지(유일 소유), Step의 검증 가능한 결과, Review Focus 각 줄의 고정 테스트, Success Criteria의 기계적 판정 가능성, 구현 전 검증 가능한 명령·코드의 실제 실행(4.4.5), D7 가정 형식(4.4.7) |

## 4.4.4 placeholder

구현자에게 결정을 남기는 줄: 값·이름·동작·범위가 정해지지 않은 줄("적절히 처리", "add appropriate validation", "handle edge cases", "TBD", 내용 없는
"Task N과 유사", 요구 열거로서의 "등/etc."). 제외: Expiry(YYYY-MM-DD)·Owner·Removal이 모두 붙은 TODO/FIXME, 서술 문장의 조사 "등", 문서가 선언한 구현 재량.

## 4.4.5 구현 전 검증 가능 범위

| 대상 | 할 일 |
|---|---|
| 입력이 HEAD에 모두 있고 git 저장소·서브모듈·LFS 실체가 필요 없는 명령 | `X/head/`에서 실행, 기대 결과와 대조 |
| 실행 파일·하위명령·플래그 존재 | `--help`·`command -v` |
| 그 자체로 완결된 코드 블록 | `X/`에서 실행·컴파일 |
| PLAN Create 합집합에 의존하거나 git 저장소·서브모듈·LFS가 필요한 명령·검증 Step | 실행하지 않고 명령 + 기대 결과(실패 Step은 실패 이유)가 적혔는지만 확인. 없으면 `unverifiable-step`(`align`) |

`X/head/`에는 `.git`이 없다. 비 git 대상이면 `X/head/` 자체가 없다 — 저장소 파일을 입력으로 쓰는 명령(git이면 `X/head/`에서 돌릴 명령)은 실행하지 않고 `unverified(tool)`,
그 자체로 완결된 코드 블록은 X에서 실행한다. 이력 조회는 `git -C <tree>`(읽기 하위명령만). 네트워크 접속·패키지 임의 설치·VCS 쓰기·프로세스 종료·컨테이너·장치 접근이
필요한 검증은 실행하지 않고 `unverified(policy)`(2단계에서 훅으로 강제, 1단계는 감사자 지시). X가 없거나 사본이 원본과 달라 생긴 실행 실패(export 속성·
LFS·서브모듈·git이 무시하는 파일·저장소 밖을 가리키는 링크)는 `exec-fail`이 아니라 `unverified(tool)`(D8).

## 4.4.7 D7 가정 형식

가정 항목이 ① 가정(한 문장) ② 실측 프로브(PLAN의 구체 Step: 명령 + 기대 결과, 그 사실에 기대는 첫 Task 이전 또는 그 Task의 첫 Step. spec 단독 감사면
"구현 Task 1" 지정만 확인) ③ 실패 시 대안(구체 행동)을 모두 가지면 그 검증 불가 사항은 finding이 아니다. 형식 위반은 selfcontained `assumption-form`(`align`),
대안 실행 불가는 rootcause `premise`(`requirement`).
