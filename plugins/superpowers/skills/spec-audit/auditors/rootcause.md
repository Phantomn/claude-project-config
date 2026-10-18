# 축 rootcause

## 4.4.1 감사 축 (rootcause 행)

| `rootcause` | 임시 처방 여부, 과소범위, 과잉범위(spec에 없는 기능·구현 1개 인터페이스·미사용 스캐폴딩·투기적 추상화), 전제 반증(X에서 실측 가능), 회귀·동시성·보안, 프로젝트 규칙(4.4.6), 재현·이식·마이그레이션 spec의 Reference Oracle 누락(`oracle-missing`), D7 대안의 실행 가능성, **실패/모름**(조회·탐지 계약이 실패·미확인을 허용 쪽 값 — 빈 목록·`False`·`None`·0 — 으로 돌려 판정이 허용으로 흐르는가: 근거 = 그 계약 줄 + 그 값을 허용으로 쓰는 판정 줄, `security`), **시계 의존**(안전 판정이 벽시계 시각 비교·확인 시점과 사용 시점 사이의 상태에 기대는데 역행·어긋남 여유나 근거가 없는가: 근거 = 비교 줄 + 시계가 뒤로 가거나 어긋날 때 판정이 뒤집히는 경로, `concurrency`), **모델링 한계**(파서·해석기·에뮬레이션처럼 다른 시스템의 의미를 흉내 내는 대상이면 모델링 범위 한계 선언과 모델링 못 하는 입력의 기본 동작(미확정·거부)이 있는가: 근거 = 그 절 + 모델링 못 하는 입력에 다른 결과(허용·거부)를 내는 두 구현, `contract-gap`, fix_class `requirement`) |

## 4.4.6 프로젝트 규칙

rootcause는 `<tree>`에서 Claude Code가 읽는 프로젝트 지시 파일 — `CLAUDE.md`·`.claude/CLAUDE.md`·`CLAUDE.local.md`·`.claude/rules/**/*.md` 중 실재하는 것,
앞의 세 CLAUDE 파일이 모두 없으면 `AGENTS.md`·`.claude/AGENTS.md` — 을 읽고 위반을 `rule-violation`(대개 `requirement`)으로, 근거는 규칙 `path:line`.
시스템 컨텍스트로 받은 다른 지침은 근거로 쓰지 않는다(L17). 규칙의 "코드 산출물에 한해" 항목은 대상이 코드를 만들 때만. 성능은 spec이 목표치를 정했거나 규칙이 요구할 때만.

## 4.4.7 D7 가정 형식

가정 항목이 ① 가정(한 문장) ② 실측 프로브(PLAN의 구체 Step: 명령 + 기대 결과, 그 사실에 기대는 첫 Task 이전 또는 그 Task의 첫 Step. spec 단독 감사면
"구현 Task 1" 지정만 확인) ③ 실패 시 대안(구체 행동)을 모두 가지면 그 검증 불가 사항은 finding이 아니다. 형식 위반은 selfcontained `assumption-form`(`align`),
대안 실행 불가는 rootcause `premise`(`requirement`).
