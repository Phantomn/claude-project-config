# spec-audit 결정 기록

## 1단계 결정 요약

- 종료 기준은 ❌0 그리고 ⚠️0, 예외 없음(D1).
- 요구 의미를 바꾸지 않는 정합 수정은 리드가 자동 반영하고, 그 밖은 항목별 diff를 보이고 사용자 승인을 받는다(D2).
- writing-plans 핸드오프를 "계획 저장 → spec-audit → 합격 후 실행 방식 선택(승인 1회)"으로 바꾼다(D3).
- 감사 스킬이 루프 전체를 소유한다(D4).
- 라운드 상한은 5이고, 5라운드에서 합격하지 못하면 불합격 보고 후 멈춘다(D5).
- 호출마다 새 감사이고 이전 합격을 재사용하지 않는다(D6).
- 감사 시점에 검증할 수 없는 외부 의존 항목은 "가정 + 구현 첫 Task의 실측 프로브 + 실패 시 대안"으로 해소한다(D7).
- 실행 감사자는 `git archive HEAD` 사본에서 실행하고, 추출 실패나 사본 불일치로 실행이 실패하면 `unverified(tool)`이다(D8).
- 단일 출처 원칙을 리드의 수정에도 적용한다(D9).
- 판정 기준은 결함 유형 8종과 필수 근거이고 필수 근거가 없는 finding은 무효다(D14).
- 라운드 2부터 각 축의 배정 범위는 `scope.json`이다(D15).
- 리드는 stash·커밋·되돌리기를 하지 않고 미커밋 변경은 그대로 감사된다(D17).
- 판정이 문서와 트리 읽기만으로 정해지는 finding에는 재현 명령(check)을 붙여 기계가 누적 재실행한다(D22).
- 감사자 정책 훅, 실행 관문, 문서 잠금은 2단계로 넘긴다.

## D12 예외: feature flag 없음

핸드오프 변경은 flag 없이 기본 적용한다(사용자 규칙 "flags default OFF"의 예외). 스킬 문서 한 문단의 변경이라 켜고 끄는 분기를 둘 대상이 없고, 두 경로를 병존시키면 어느 쪽이 실행되는지 문서만으로 알 수 없다. 끄려면 머지 커밋을 revert하는 PR을 낸다.

## D13 근거: 샤드 크기 1,500줄

감사자 분할 크기는 모든 축 1,500줄이다. 한 감사자가 그 안에서 정밀하게 읽을 수 있는 크기로 잡았다. 그 감사자의 `context` finding으로 빠진 범위는 다음 라운드가 미검토 줄로 다시 나눠 본다.

## D16 근거

장치는 관찰된 결함을 막거나 루프를 닫는 데 필요할 때만 둔다. 감사가 가상 경우마다 장치를 덧붙이자 spec이 계속 커졌고 어느 감사 주기도 ❌0·⚠️0에 닿지 못한 이력이 근거다.

## L22를 판정 기준 대신 LIMITS로 둔 이유

리드 절차 분기의 검증 한계를 판정 기준으로 올리면 문서가 스스로 합격선을 정하게 되어 합격 쪽으로 기우는 편향이 재발한다. 그래서 받아들인 한계로 LIMITS에 둔다.

## 맞교환

- 장치 부재 지적은 실행한 명령의 출력이나 기록된 관찰만 근거로 인정하므로, 설계 단계의 보안·동시성 지적 상당수가 보고 파일의 메모로 내려간다.
- 이미 있는 규칙의 모순을 고치며 규칙이 느는 사슬은 판정 기준으로 막지 않는다(L21).
- D15 N≥2 범위: 라운드 2부터는 바뀐 줄과 직전 지적·미검토 줄 주변만 배정한다. 비용이 줄지만 바뀌지 않은 줄의 결함은 라운드 1 이후 다시 보지 않는다.
- 감사자는 모두 opus로 고정한다. 판정 품질을 비용보다 우선한 것이며, 저장소 규칙 "Agent Teams 비용"의 Sonnet/Haiku 권고에 대한 예외로 그 규칙 원문에 적는다.

## 구현 재량 결정

계약 밖 선택이며 단위 테스트로 고정한다.

| 재량 | 결정 |
|---|---|
| slug 해시 | `sha256("\n".join(sorted(realpath 문자열)))`의 앞 8 hex |
| targets 순서 | plan → spec(realpath 사전순) → other(realpath 사전순). 스냅샷 `<i>-<basename>`의 i는 이 순서(1부터) |
| 줄 단위 | 파일을 bytes로 읽어 `splitlines(keepends=True)` — 줄끝 포함 비교(C7), 마지막 줄 개행 없음도 1줄 |
| 샤드 경계 | 축의 배정 범위를 targets 순서로 이은 줄을 정확히 Z줄마다 자른다(제목 맞춤 없음) |
| 줄 위치 옮기기 | `difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes()`: equal 줄은 대응 줄, replace/delete 줄은 새 쪽 `j1+1`(파일 끝을 넘으면 마지막 줄). 범위 = 옮긴 줄들의 min–max |
| 보고 파싱 | 정규식 ```` ^```(\w+)\n(.*?)^```$ ```` (MULTILINE·DOTALL). `findings`·`coverage`·`resolved` 외 이름의 펜스는 무시 |
| C8 항목 키 | `name`,`axis`,`prompt`,`exec_dir`(X 또는 null),`ranges`(범위 문자열),`recheck`(id) |
| C6 키 | `tree`,`plugin_version`,`targets:[{path,rel,role,sha256,lines,snapshot}]` |
| diff.patch | 대상마다 `difflib.unified_diff`(파일 이름 = rel), 이어 붙임 |
| check 출력 | `run_check`의 출력 = stdout+stderr를 이어 붙인 것의 마지막 2000자(시간 초과면 `"timeout"`). 재삽입 finding의 `evidence`와 C9 `output` = `exit <code>`(시간 초과면 `exit timeout`) 한 줄 + 그 출력 |
| K | C9마다 지우고 새로 만든다 |
| 빈 줄 사본(C3 ②) | `TMPROOT/spec-audit/<slug>/shift/` — check 검증마다 지우고 새로 만든다 |
| SKILL.md 내용 해시(C1) | `skill_hash()`: SKILL.md를 bytes로 읽어 `splitlines(keepends=True)`, `"스킬 버전: "`(UTF-8)로 시작하는 줄을 모두 뺀 나머지를 이어 붙인 bytes의 `sha256().hexdigest()[:12]`(줄끝·인코딩 정규화 없음) |
| C3 retry | assign.json의 `<name>-retry` 항목이 그 범위의 감사자가 된다. retry 보고도 없으면 "보고 파일 없음"이고 retry는 null이다(retry는 한 번만 — C3 행의 "retry 보고가 있으면"을 글자대로 읽으면 같은 retry를 다시 만들어 S2·S3이 반복된다) |
| C2 재검 소유자 | 직전 비context finding 중 재검 소유자가 없는 것(target이 비었거나 oracle 절이 사라지거나 placeholder가 됨)이 있으면 C2가 실패하고 stderr에 id·axis·위치를 나열한다(4.6 "정확히 1명" — 조용히 건너뛰면 J1이 잘못 합격할 수 있다) |
| C3 ③ superseded check | `unresolved`로 대체된 id의 check도 `checks`에 남는다(C3 ③ 글자 그대로). 같은 결함의 재삽입은 결함이 남은 동안에만 일어나고 그때 J1은 어차피 `fix`다 |
| run_check 디코딩 | 출력을 `errors="replace"`로 디코딩한다(UTF-8이 아닌 check 출력이 C3·C9를 중단시키면 안 된다) |
