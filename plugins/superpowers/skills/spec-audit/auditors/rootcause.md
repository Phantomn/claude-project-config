# 축 rootcause

## 4.4.1 감사 축 (rootcause 행)

| `rootcause` | 임시 처방 여부, 과소범위, 과잉범위(spec에 없는 기능·구현 1개 인터페이스·미사용 스캐폴딩·투기적 추상화), 전제 반증(X에서 실측 가능), 회귀·동시성·보안, 프로젝트 규칙(4.4.6), 재현·이식·마이그레이션 spec의 Reference Oracle 누락(`oracle-missing`), D7 대안의 실행 가능성 |

## 4.4.6 프로젝트 규칙

rootcause는 `<tree>`에서 Claude Code가 읽는 프로젝트 지시 파일 — `CLAUDE.md`·`.claude/CLAUDE.md`·`CLAUDE.local.md`·`.claude/rules/**/*.md` 중 실재하는 것,
앞의 세 CLAUDE 파일이 모두 없으면 `AGENTS.md`·`.claude/AGENTS.md` — 을 읽고 위반을 `rule-violation`(대개 `requirement`)으로, 근거는 규칙 `path:line`.
시스템 컨텍스트로 받은 다른 지침은 근거로 쓰지 않는다(L17). 규칙의 "코드 산출물에 한해" 항목은 대상이 코드를 만들 때만. 성능은 spec이 목표치를 정했거나 규칙이 요구할 때만.

## 4.4.7 D7 가정 형식

가정 항목이 ① 가정(한 문장) ② 실측 프로브(PLAN의 구체 Step: 명령 + 기대 결과, 그 사실에 기대는 첫 Task 이전 또는 그 Task의 첫 Step. spec 단독 감사면
"구현 Task 1" 지정만 확인) ③ 실패 시 대안(구체 행동)을 모두 가지면 그 검증 불가 사항은 finding이 아니다. 형식 위반은 selfcontained `assumption-form`(`align`),
대안 실행 불가는 rootcause `premise`(`requirement`).
