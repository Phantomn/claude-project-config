# harness-core

프로젝트마다 복사돼 갈라지던 하네스 자산의 **단일 저장 위치**. 프로젝트는 사본을 두지 않고
`enabledPlugins` 로 참조한다.

## 왜 이 플러그인이 생겼나

2026-08-24 실측: 같은 개념의 훅이 프로젝트 3벌로 갈라져 있었고(`auto-approve-readonly.sh` —
agent·analysis·bounty, **셋 다 내용 상이**), 하네스 파일 98개 중 2개 이상 프로젝트가 공유하는
8개의 **완전동일본은 0개**였다. 반대로 유일하게 동일했던 2개는 아무도 안 건드린 템플릿 잔재였다.
*실제로 쓰이는 것은 전부 갈라졌고, 갈라지지 않은 것은 아무도 안 쓴 것이다.*

## 담는 기준

**이빨(teeth)이 있는 것만.** 자기검증 없는 자산을 공유하면 결함도 함께 배포된다.
현재:

- `auto-approve-readonly.sh` + `t_auto_approve_rm.py`(20 케이스) — Bash 입구와 기존 판정(OLD).
- **bash-guard**(`bash_guard.py`·`shell_parse.py`·`target_class.py`·`policy.py`·`ledger.py`·`guard_mode.py`·`touch-ledger.py`) —
  대상 성질 기반 파괴적 명령 판정기. 스위치 `HARNESS_BASH_GUARD`(기본 `off`). 설계: `docs/superpowers/specs/2026-10-14-bash-guard-design.md`,
  결정: [DECISIONS.md](DECISIONS.md), 한계: [LIMITS.md](LIMITS.md).
- `bootstrap/` — 새 PC 개발 환경 이식 도구(수동 실행, 훅 아님). `verify` 로 충족 여부를 판정하고 `selftest` 로 자체 시험한다. 사용·결정·한계: [bootstrap/README.md](bootstrap/README.md).
- `code-read-guard.py`·`guard-read-codefile.sh`·`symbol-tools.sh`(코드 읽기 → serena/codegraph), `task-handoff.sh`(/wrap 태스크 인계).

## 프로젝트별 값 (env 노브 — settings.json 의 `env`)

| 노브 | 기본 | 뜻 |
|---|---|---|
| `HARNESS_RM_REPO_DIRS` | `src\|lib\|app\|docs\|scripts\|.claude` | 재귀삭제 시 ask 로 올릴 저장소 추적 트리. 저장소마다 다르다. 기존 판정(OLD) 전용 — **bash-guard `on` 안정화 후 제거 예정** |
| `HARNESS_CODEREAD_GUARD` | `0`(끔) | bash 로 코드 읽기(grep·sed·awk·cat 등에 코드파일 인자, 코드 트리 재귀 검색)를 **첫 시도부터 차단**하고 사유에 serena 대체 호출을 적는다(`code-read-guard.py`). git 저장소 밖·비코드·파이프 입력은 무개입. **serena 가 실제로 붙은 프로젝트에서만 켠다** — 없는 프로젝트에서 켜면 없는 도구를 권하며 막는다 |
| `HARNESS_BASH_GUARD` | `off` | bash-guard 모드 `off`·`shadow`·`on`(그 외 값 = `off`). **프로젝트 `.claude/settings.json`(또는 `settings.local.json`, local 우선)의 `env` 에만** 둔다 — 전역 `~/.claude/settings.json` 금지. 판정은 **대상 저장소 기준**: 세션 env 값, 훅 cwd 저장소 값, 판정 대상 단위의 cwd 저장소 값, 대상 경로들의 저장소 값 중 가장 강한 것(`on` > `shadow` > `off`). 그래서 홈에서 연 세션도 스위치를 켠 저장소를 건드리면 켜진다. 저장소 = 위로 올라가 처음 만나는 `.git` 을 가진 폴더(그 폴더가 `$HOME`·`/` 이면 값 없음) |
| `HARNESS_BASH_GUARD_ALLOW_DELETE` | (없음) | bash-guard 가 '세션 전부터 있던 유일본'(`PRESERVED`)·대상 확정 불가(`UNRESOLVED` — 폴더 항목 상한 초과 등)로 막는 **삭제**를 사용자가 허용하는 목록. `:` 로 구분한 경로 패턴(`*`·`?`·`[…]` 글롭, `*` 는 `/` 도 넘는다), 절대경로 또는 프로젝트 루트 상대. **대상 저장소**의 `.claude/settings.local.json` → `settings.json` 순으로 처음 나오는 값(저장소 밖 대상에는 없음). 목록과 무관하게 안 되는 것: 보호 이름(폴더면 안까지 다시 본다), 추적 파일·추적 파일을 품은 폴더(→ `git rm`), 홈·`/`·프로젝트 루트·임시 루트 자체, 덮어쓰기 등 삭제 아닌 규칙. `/`·홈 아래 전부나 프로젝트 루트 아래 이름 전부(`*`·`**/*`)를 덮는 패턴은 버리고, 설정 파일을 못 읽거나 값이 문자열이 아니면 목록 전체를 버린다 — 둘 다 `settings_errors` 에 남는다. 풀린 삭제는 기록 `allow_delete` 에 남는다. 예: `"HARNESS_BASH_GUARD_ALLOW_DELETE": "android/*/build:tmp-data"` |
| `HARNESS_BASH_GUARD_CLOCK_MARGIN` | `2.0`(초) | 세션 시작 뒤 이 초 안에 생성·수정된 대상은 세션 전 것으로 본다(벽시계 역행 방어, DECISIONS "시각 여유"). 0 이상 실수. 음수·파싱 실패·`nan`·`inf` → 기본값. 운영에서는 바꾸지 않는다(테스트 세계가 작은 값을 쓴다) |

bash-guard 가 그 밖에 읽는 환경 변수(설정 노브가 아니라 실행 환경 값):

| 변수 | 쓰임 |
|---|---|
| `XDG_STATE_HOME` | 상태 폴더 위치. 절대경로가 아니면 `$HOME/.local/state` |
| `HOME` | 상태 폴더 기본값(없으면 장부 비활성 — 세션 생성 판정을 하지 않는 보호 쪽), `~` 확장, 저장소 판정에서 홈 저장소 제외, 임시 루트 `~/.cache`, Docker 컨텍스트 설정 `~/.docker/config.json` |
| `TMPDIR` | 임시 루트 하나(설정 시). 명령 안에서 바꾼 `TMPDIR` 는 `mktemp` 결과 확정에 쓰지 않는다 |
| `COMPOSE_PROJECT_NAME` | `docker compose down -v` 의 대상 볼륨 프로젝트명(명령의 `-p` 가 없을 때) |
| `DOCKER_HOST`·`DOCKER_CONTEXT`·`XDG_RUNTIME_DIR` | 컨테이너 조회가 실패했을 때 데몬 부재의 긍정 증거 판정(소켓 부재만 증거 — `unix://` 소켓, 기본 `/var/run/docker.sock`, rootless `$XDG_RUNTIME_DIR/docker.sock`). 클라이언트가 `PATH` 에 있는지는 보지 않는다. 이 증거는 `docker exec`·`docker container exec`·`docker compose exec` 에만 쓴다 — `podman`(데몬이 없다)·독립 실행 `docker-compose` 와, 명령이 데몬을 직접 지정한 경우(전역 `-H`·`--host`·`-c`·`--context`·`--config`, 또는 명령 안에서 `DOCKER_HOST`·`DOCKER_CONTEXT`·`DOCKER_CONFIG` 를 할당·`export`·`unset`·`env -u`), 그리고 상태 env 를 확정할 수 없는 문장(`source`/`.`·동적 이름 할당 `export $(…)`·`declare -x "$N=…"`·`read "$v"`)이 앞에 있는 경우는 훅 env 의 소켓 부재가 증거가 아니라 확정 불가다(spec §3.5) |

## bash-guard

### 구조

입구 `auto-approve-readonly.sh`(PreToolUse `Bash`, timeout 10초)가 code-read-guard 블록 뒤 기존 판정 OLD 를 만들고
`bash_guard.py --old "$OLD"` 에 넘긴다. 파이썬이 뜨지 않거나 출력이 비면 입구가 OLD 를 그대로 낸다.

```
bash_guard.py  ─ 입력 읽기·모드 결정·시간 예산(5초)·출력·기록
 ├ guard_mode.py   스위치 값(대상 저장소 settings)
 ├ shell_parse.py  명령 문자열 → 명령 단위(Segment) 목록 (자체 어휘 분석기, 제어 흐름·함수 인라인·확장)
 ├ target_class.py 대상 경로 → 분류(7분류 + 세션 저장소·옮겨진 유일본) — git·stat·docker 조회
 ├ policy.py       단위 × 분류 → 거부 사유(Finding) — 정책 표
 └ ledger.py       공유 장부 읽기·쓰기
touch-ledger.py ─ PreToolUse `Write|Edit|NotebookEdit`(timeout 5초) 장부 기록 훅
```

판정 대상이 될 수 없는 단순 명령(`ls`·`git status` 류만으로 된 줄)은 빠른 길(`_TRIVIAL`)로 무거운 모듈을 읽지 않고 허용한다.

### 모드

| 모드 | 출력 | 기록 |
|---|---|---|
| `off`(기본) | OLD 를 바이트 그대로(종료 코드 포함) | 아래 '모드 무관' 만 |
| `shadow` | OLD 를 바이트 그대로(종료 코드 포함) | 새 판정과 OLD 가 다르면 한 줄 + 모드 무관 |
| `on` | 새 판정: `allow` 또는 `deny`+사유. **`ask` 를 내지 않는다** | 거부마다 한 줄 + 모드 무관 |

모드 무관 기록: 판정기 내부 예외(`error`·`fallback`), 그리고 `stats`·`settings_errors`·`allow_delete` 가 있는 판정(허용이어도 — 아래 필드).

스위치와 무관하게 모든 Bash 호출에서 파이썬 판정이 돈다(모드를 정하려면 대상 경로가 필요하다). `on` 에서도 파이썬 기동이
실패하면 입구 폴백으로 OLD(그 `ask` 포함)가 나간다. `on` 에서 판정기 내부 예외가 나면 OLD ∪ 위험 단어로 판정한다(OLD 가 `ask`·`deny` 이거나
원문에 위험 단어가 있으면 거부 — spec §3.8 (다)).

### 장부와 기록 (상태 폴더 `${XDG_STATE_HOME:-$HOME/.local/state}/harness-core/`)

- `ledger.tsv` — 모든 세션이 공유하는 장부. 행 `<realpath>\t<kind>\t<session_id>\t<epoch>`, kind = `pre-session`·`pre-dirty`·`created`·`touched`·`moved-in`.
  `touch-ledger.py` 와 판정기가 **스위치와 무관하게 항상** 기록한다. 5MB 를 넘으면 7일 지난 줄을 뺀다(`moved-in` 은 경로가 있는 동안 유지). 권한 0600.
  판정기는 해석한 Bash 의 생성 목적지(`mkdir` 피연산자·`-p` 의 없는 조상, 리다이렉트 대상, `cp`·`mv`·`install` 목적지 중 지금 없는 것, `/dev/` 제외)도
  `created` 로 남긴다 — `/mnt/c` 처럼 생성 시각을 못 읽는 곳에서 세션 생성의 증거(파일 mtime 이 기록 시각 − 시각 여유 이후일 때만).
- `bash-guard.jsonl` — 판정 기록(위 모드 표). 10MB 를 넘으면 `.1` 로 한 번 순환. 권한 0600.
  **명령 원문이 들어 있다 — 저장소·PR 에 옮기지 않는다.**
- 잠금: 장부·기록 모두 `ledger.lock_file`(비차단 재시도 + 마감) 하나를 쓴다. 못 잠그면 기록을 포기하지 않고 잠금 없이 한 줄 추가한다
  (장부: 판정 예산 마감·`touch-ledger` 3초, 기록: 1초).

`bash-guard.jsonl` 한 줄의 필드:

| 필드 | 뜻 |
|---|---|
| `ts`·`mode`·`session_id`·`agent_id`·`cwd` | 시각(UTC), 정해진 모드, 세션·서브에이전트, 훅 cwd |
| `command` | 명령 원문(최대 2,000자) |
| `decision`·`old_decision` | 새 판정(`allow`·`deny`), OLD(`allow`·`ask`·`deny`) |
| `reasons` | 거부 사유 줄. 해석 단계 사유로 종류를 가른다: "명령을 해석하지 못했다"(구문 오류), "해석 한계"(모델링 불가), "코드를 정적으로 알 수 없다"(변수·치환으로 만든 셸 코드), "판정 시간 초과", "판정기 오류" |
| `ms` | 판정 시간(밀리초) |
| `error`·`fallback` | 내부 예외 메시지(또는 출력 실패), 내부 예외 폴백으로 낸 판정이면 `true` |
| `budget_exhausted` | 사유에 판정 시간 초과가 있으면 `true` |
| `stats` | 판정 중 센 횟수(없으면 null): `container_lookup_none`(컨테이너 마운트 조회 실패·이름 미확정), `compose_project_dir_none`(compose exec 프로젝트 폴더 모름), `container_no_daemon`(데몬 부재 증거로 허용 — `docker` CLI 이고 데몬 직접 지정이 없을 때만), `scratch_hole`(임시 폴더 아래 마지막 이름만 변수인 대상을 허용) |
| `settings_errors` | 스위치 settings 파일을 읽다 난 오류(파일 없음 제외). 있으면 스위치가 조용히 `off` 로 떨어졌을 수 있다. 삭제 허용 목록의 버린 패턴·깨진 값도 여기 |
| `allow_delete` | 삭제 허용 목록(`HARNESS_BASH_GUARD_ALLOW_DELETE`)으로 풀린 삭제가 있을 때만 있는 키 — `대상 ← 패턴 원문` 목록. 모드와 무관하게 기록한다(사유 추적) |
| `ledger_bytes` | 그 시점 장부 크기 |
| `dynamic_kind` | 거부 사유가 "코드를 정적으로 알 수 없다"(`R_DYNAMIC`)일 때만 있는 키 — 해석기의 하위 사유 문구 그대로(목록은 spec §3.8 (가′) 표). 예: `명령 이름을 확정할 수 없음`·`단위 밖에서 오는 표준입력의 코드를 확정할 수 없음`·`표준입력 장치일 수 있는 경로를 확정할 수 없음`·`파이프로 넘긴 코드를 확정할 수 없음`·`셸 -c 문자열을 확정할 수 없음`·`셸 옵션 X 을 해석할 수 없음`(X 는 40자까지)·`이름 붙은 fd 입력 리다이렉트의 번호를 확정할 수 없음`·`fish 코드는 해석하지 않음`. 출력 사유에는 들어가지 않는다. `find -exec 의 명령 이름을 확정할 수 없음` 은 policy 경로에서 "대상을 확정할 수 없다" 로 나타나 이 키가 없다. 함수 호출 인라인 안의 이름 미확정은 "해석 한계"(`R_MODEL`)로 감싸져 이 키가 없다 |

### 배포 절차 (요약 — spec §11)

1. PR 병합 → 운영 clone `git pull --ff-only`. 스위치가 없으므로 출력은 이전과 같다.
2. 사용자 승인 뒤 대상 프로젝트들 `.claude/settings.json` 의 `env` 에 `"HARNESS_BASH_GUARD": "shadow"` 한 줄(orca 작업공간은 브랜치별 파일).
3. 최소 3일·Bash 5,000회 뒤 `bash-guard.jsonl` 의 불일치를 검토 → 판정기 오판은 재구성 테스트를 더해 고친다(새 PR).
   LIMITS.md 의 "shadow 관측 지표" 절이 볼 것을 정한다(아래 표).
4. 사용자 승인 → 같은 프로젝트들 `on`. 2주 무사고 뒤 기존 로직·`t_auto_approve_rm.py`·`HARNESS_RM_REPO_DIRS` 제거 PR.
   `on` 전환 때 사용자가 정할 것(LIMITS): `push --force-with-lease` 를 기본 브랜치에 허용할지, `curl -o` 를 덮어쓰기 표에 넣을지,
   `/mnt/c` 세션 폴더 처리, 세션 저장소의 `filter-repo`.
- 되돌리기: 스위치를 `off` 로(코드 되돌림 불필요). 스위치로 안 되는 결함은 PR revert.

shadow 동안 볼 것과 그 출처(최종 리뷰 권고 목록 기준):

| 볼 것 | 기록되나 | 출처 |
|---|---|---|
| 신·구 불일치 수와 방향 | 예 | `decision`·`old_decision`(shadow 불일치 줄) |
| 거부 사유 종류 분포(확정 불가 비율·사유 상위, 구문 오류·해석 한계·동적 코드) | 예 | `reasons` |
| 동적 코드 거부의 하위 사유별 건수(LIMITS O16·O24~O30) | 예 | `dynamic_kind`(`R_DYNAMIC` 거부 줄에만) |
| 정직한 패턴 과잉 거부 후보 ① — `$(…)` 로 대입한 변수를 따옴표 없이 명령으로(`PY=$(…)/bin/python; $PY …`·`B=$(…); $B/x`, C7 S3, LIMITS O24) | 간접 | `dynamic_kind` = `명령 이름을 확정할 수 없음` 인 줄 중, `command` 의 그 명령 자리 변수를 큰따옴표로 감싸(`"$PY"`·`"$B"/x`) `shell_parse.parse` 로 다시 해석하면 `error` 가 사라지는 줄(재해석) |
| 후보 ② — 여러 줄 배열 리터럴 원소를 명령으로 읽음(`A=( [k]=v … )`·글롭 원소, C7 S4, LIMITS O25) | 간접 | `dynamic_kind` = `명령 이름을 확정할 수 없음` 이고 `command` 에 배열 리터럴 `=(` 가 있는 줄(문자열 검사 — 근사) |
| 후보 ③ — 앞에 파이프·`<` 가 있는 명령의 `bash "$X"`·`source "$X"`(C7 항목 2, LIMITS O26) | 간접 | `dynamic_kind` = `표준입력 장치일 수 있는 경로를 확정할 수 없음` 인 줄 중, 그 셸 단위에 `< /dev/null` 을 붙여 다시 해석하면 `error` 가 사라지는 줄(재해석) |
| 후보 ④ — 원문에 `IFS` 가 있는 명령(`while IFS= read …`)의 따옴표 없는 확장(C7 S1, LIMITS O27) | 간접 | 명령 이름이면 `dynamic_kind` = `명령 이름을 확정할 수 없음`, 대상이면 `reasons` 의 "대상을 확정할 수 없다" — 둘 다 `command` 에 `IFS` 글자가 있는 줄로 거른다. 재생에서는 대부분 대상 쪽이었다(14건 중 12) |
| 판정 시간 p50·p99·최대, 시간 초과 건수 | 예(기록된 줄만) | `ms`·`budget_exhausted` |
| 장부 크기 | 예 | `ledger_bytes` |
| 내부 예외 폴백 건수와 명령 모양 | 예 | `error`·`fallback` |
| 컨테이너 조회 실패·compose 프로젝트 폴더 모름·데몬 부재 허용 | 예 | `stats` |
| 임시 폴더 표식 예외로 허용한 건수 | 예 | `stats.scratch_hole` |
| 스위치 settings 읽기 실패 | 예 | `settings_errors` |
| 플랫폼의 훅 취소(10초 초과) | 아니오 | 세션 기록의 `hook_cancelled`(spec 부록 A) |
| 장부 압축 횟수 | 아니오 | — |
| 판정 대상 밖 모양(목록 밖 래퍼·덮어쓰기 도구)이 든 허용 명령 수 | 아니오 | 허용은 `stats` 가 있을 때만 남는다 — 세션 기록 검색으로 따로 센다 |

동적 코드 거부의 안내 문구는 하나다: "코드를 정적으로 알 수 없다(변수·치환으로 만든 셸 코드) — 리터럴로 쓰거나 스크립트 파일로 실행하라"(`bash_guard.R_DYNAMIC`).
위 후보 ①·③ 의 더 좁은 해결(명령 자리 변수를 `"$PY"` 처럼 따옴표로 감싸기, 셸에 `< /dev/null` 붙이기)은 문구에 없다 — LIMITS O24·O26 에 적었고, 문구에 넣을지는 shadow 빈도를 본 뒤 정한다.

## 자기검증

저장소 루트에서(spec §5):

```bash
for t in shell_parse target_class policy bash_guard touch_ledger bash_guard_fast replay_corpus; do
  python3 "plugins/harness-core/hooks/tests/test_$t.py" || exit 1
done
for t in plugins/harness-core/hooks/tests/test-*.sh; do bash "$t" || exit 1; done
python3 plugins/harness-core/hooks/tests/test_code_read_guard.py
python3 plugins/harness-core/hooks/t_auto_approve_rm.py   # 20 케이스(off 경로)
python3 -m py_compile plugins/harness-core/hooks/scripts/*.py
jq empty plugins/harness-core/hooks/hooks.json
```

Docker 테스트는 Docker 와 `sh -c 'sleep'` 이 도는 로컬 이미지가 없으면 사유를 출력하고 건너뛴다. 전수 재생
(`tests/tools/replay_corpus.py --projects ~/.claude/projects --out <저장소 밖 폴더>`)은 로컬 세션 기록을 쓰는 수동 시험이다 —
결과에 명령 원문이 있으므로 저장소 안 `--out` 은 도구가 거부한다. 거부 종류(`deny_by_kind`)는 사유로 가른다(`MODEL`·`DYNAMIC` 포함).
