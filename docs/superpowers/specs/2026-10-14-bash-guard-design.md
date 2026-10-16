# Spec: bash-guard — 대상 성질 기반 파괴적 명령 판정기 (harness-core)

| 항목 | 값 |
|---|---|
| 상태 | 초안 — 남은 질문 해소, 최종 승인 대기 |
| 작성 | 2026-10-14 |
| 소유 | Phantomn (harness-core) |
| 대상 저장소 | `Phantomn/claude-project-config` (**공개 저장소**) |
| 대상 플러그인 | `plugins/harness-core` |
| 대체 대상 | `plugins/harness-core/hooks/scripts/auto-approve-readonly.sh` 의 판정 로직 |

이 문서는 **self-contained** 다. 구현자는 이 문서와 저장소만으로 구현·검증할 수 있어야 한다.
수치의 출처는 부록 A(측정 방법)에 있다. 문서 안의 "실측"은 2026-10-14 에 이 환경에서 직접 측정한 값이다.

---

## 1. Objective

### 1.1 한 줄 목표

bypass 모드 무인 실행에서 **되돌릴 수 없는 손실만** 정확히 막고, 그 외 명령에는 **절대 개입하지 않는**
Bash 판정기를 만든다. 판단 근거는 명령의 글자 모양이 아니라 **지워지거나 덮이는 대상의 성질**이다.

### 1.2 배경: 현재 훅이 하는 일

`auto-approve-readonly.sh` 는 모든 Bash 호출 직전(PreToolUse)에 실행되며 다음을 순서대로 한다.

1. 명령에 읽기 도구 이름(grep·cat·sed 등)이 보이면 `code-read-guard.py` 를 호출해 deny 를 받으면 그대로 출력한다.
2. `rm` 에 `-r`·`-f` 류 옵션이 있으면 rm 피연산자를 정규식으로 뽑아 4단 판정한다:
   ①루트·홈·`.git`·`.secrets` → deny, ②`HARNESS_RM_REPO_DIRS`(기본 `src|lib|app|docs|scripts|.claude`)
   이름이 경로에 있으면 → ask, ③`/tmp` 밖 절대경로 → ask, ④그 외 → 통과.
3. 명령 원문 전체에 `DANGEROUS_PATTERNS` 22개 정규식(`rmdir`, `mkfs`, `dd if=`, `dd of=`, `chmod -R 777`,
   `killall`, `systemctl stop|disable`, `git push.*--force`, `git push.*-f`, `git reset --hard`, `git clean -fd`,
   `git checkout -- \.`, `>/etc/`, `>>/etc/`, `>/dev/sd`, `xargs.*rm`, `xargs.*chmod`, `tee\s+/(etc|usr|bin|sbin)/`)을
   대소문자 무시로 걸어 하나라도 맞으면 ask.
4. 어디에도 안 걸리면 allow.

### 1.3 실측된 문제 (2026-07 ~ 2026-10-14 세션 기록 5,209개, 6.2GB)

| 지표 | 값 |
|---|---|
| auto-approve 호출 | 89,034회 (도구 호출 기준 약 94,000건 중 **약 97% 가 `bypassPermissions` 세션**) |
| ask / deny | **471 / 0** |
| ask 중 사용자 거절 | **0건** (471건 모두 승인 후 실행) |
| ask 로 멈춘 시간 | 중앙값 38초. 서브에이전트 198건(중앙값 59초, 최대 약 15.5시간, 10분 초과 35건) · 메인 273건. **합계 약 111시간** |
| 위험 명령 우회 | 조사 때 시험한 27종 중 **22종 allow**. 부록 B 는 이를 정리·확장한 32종(감사 실측: 현행 allow 26 · ask 6) |
| 훅 오류·취소 | 프로젝트 설정의 죽은 등록 오류 91건, 10초 제한 초과 취소 12건(모두 판정 없이 실행됨) |

ask 471건의 원인(절제 실험 — 원인 하나만 바꿔 다시 넣고 판정이 바뀌는지로 확정):

| 유형 | 건수 |
|---|---|
| 재귀가 아닌 `rm -f` 를 재귀 삭제로 판정(`-f` 만 빼면 allow) | 128 |
| 따옴표 안 문자열에 발화 | 56 |
| heredoc 본문·`python -c`·`sh -c` 안쪽 텍스트에 발화 | 36 (+ 이 조사 중 heredoc 본문 때문에 deny 1건) |
| `.*` 가 `;`·`&&` 를 넘어 다른 명령까지 매칭 | 34 |
| `rmdir`(빈 폴더만 지움) | 53 (실행 29) |
| 프로젝트 안 절대경로를 "저장소 밖" 으로 판정(상대경로로 바꾸면 allow) | 44 |
| 경로 이름만으로 "저장소 추적 트리" 판정 — 판별 가능 46건 중 실제 추적 파일 26건, 나머지 20건은 미추적·ignore | 150 중 |
| 패턴 오매칭(점 파일, `push -u`·`--delete`, `git rm --cached`) | 14 |
| 안전한 변형 차단(`--force-with-lease`, `clean -n`·`-X`, 파일 대상 `dd`) | 13 |
| 리다이렉트 토큰을 rm 대상으로 해석 | 4 |
| 정탐성(`reset --hard` 20, `clean -fd` 19, 강제 push 5, `checkout -- .` 1) | 45 — **이것도 전부 승인됨** |

플랫폼 사실(실측·문서):

- 훅의 `allow` 는 확인 창만 건너뛴다. settings 의 deny·ask 규칙은 그대로 적용된다(실측 8/8,
  https://code.claude.com/docs/en/permissions — "PreToolUse hook decisions don't bypass permission rules").
- 루트·홈·작업 디렉터리(와 그 상위) 같은 중요 경로를 대상으로 하는 `rm`·`rmdir`(미할당 변수 아래 glob `$DIR/*` 포함)은
  allow 규칙·훅 allow 로 승인되지 않는다. **bypass 에서는 차단이 아니라 사용자 확인 창**(터미널 2분 제한, 넘기면 거부)으로 간다 —
  무인 실행이면 2분 멈춘 뒤 거부(https://code.claude.com/docs/en/permission-modes, 실측 발동 확인. 판정기가 먼저 deny 하면 이 멈춤도 없다).
- auto 모드에서 훅 `allow` 는 권한 판정 경로를 건너뛴다(headless 통제 실험: 훅 有 12ms "Hook approved … bypassing
  permission prompt" / 훅 無 280ms 권한 판정 진입. 분류기 호출 로그 줄은 없어 강한 정황).
- 훅 `ask` 는 bypass 에서도 확인 창을 띄운다(실측 275건).

### 1.4 근본 원인

증상 37개는 하나의 사슬이다.

```
R0 목적 미정의 ─┬─▶ R3 "의견 없음 = allow" 출력 계약
               ├─▶ R2 판정 축 = 명령 모양(결과 아님) ─▶ R1 원문 정규식(모양 판정의 가장 싼 구현)
               └─▶ R4 맥락 부재(cwd·git 상태·세션 이전 파일 여부를 모름)
R5 되먹임 부재(오탐·누락 측정 없음, 실사례 테스트 없음) ─▶ 증상 패치 5회(08-05 ~ 08-31)로 사슬 유지
R6 배포 위생(설정 검증·타임아웃·운영 clone) — 위 사슬과 독립
```

- **R0**: 이름은 "읽기 전용 자동 승인"이지만 실제로는 일괄 승인기 + 삭제 가드 + 코드 읽기 가드다. 어떤 모드에서
  어떤 손실을 막는지(위협 모델)가 정의된 적이 없어, 사고가 날 때마다 그 글자를 목록에 넣는 것 외에 고칠 방법이 없었다.
- **R1**: 셸 문법(따옴표, 구분자, 접두어, 변수, 인터프리터)을 모르는 원문 정규식 → 실행되지 않는 텍스트엔 발화,
  접두어 하나엔 우회.
- **R2**: "무엇이 사라지는가"가 아니라 "이 글자가 있는가"를 봄 → `rm -f 파일 하나` 와 `rm -rf ~/data` 가 같은 무게.
- **R3**: 판단할 것이 없는 명령에도 allow 를 내어 플랫폼 판정을 덮어씀.
- **R4**: 결과를 판정하려면 현재 폴더, 저장소, git 상태, 파일 출처가 필요한데 쓰지 않음.
- **R5**: 471번 묻고 0번 막힌 사실을 아무도 측정하지 않음.
- **R6**: 프로젝트 settings 의 `${CLAUDE_PLUGIN_ROOT}` 등록은 확장되지 않아 한 번도 동작하지 않았고, 이를 잡는 게이트가 없음.

### 1.5 위협 모델 (이 판정기가 막는 것과 막지 않는 것)

- **막는 것**: 정직하지만 실수하는 에이전트가 **되돌릴 수 없는 손실**을 내는 명령.
  - 세션 시작 전부터 있던, 다른 사본이 없는 데이터의 삭제·덮어쓰기
  - git 추적 파일의 무심코 하는 삭제(`git rm` 으로 명시하게 유도)
  - 커밋되지 않은 변경의 파괴, 기본 브랜치 원격 이력 덮어쓰기, reflog 파괴
  - 호스트 시스템 경로 쓰기, 작업 영역 밖 장치·권한 조작
  - 컨테이너가 마운트한 호스트 경로·기존 Docker 볼륨의 파괴
- **막지 않는 것(알고 받아들이는 구멍, §13)**: 의도적 난독화·악의적 우회(base64 → sh 등), 스크립트 파일·`python -c`·
  `make`·`npm run` 내부의 간접 삭제, 내용을 알 수 없는 `curl … | sh`.
- **이 판정기는 사고 방지 장치이지 보안 경계가 아니다.** (cc-safety-net SECURITY.md, Cursor 의 denylist 폐기 등 조사한
  모든 선행 사례가 같은 입장 — 부록 D)

### 1.6 운용 조건 (사용자 확인)

- 세션은 거의 항상 `bypassPermissions`. auto 모드는 멈춤이 더 잦아 쓰지 않는다.
- 장시간 작업과 서브에이전트 대량 실행이 많다 → **사람을 부르는 판정(ask)은 금지**.
- worktree·브랜치에서 작업하고 push 하는 PR 흐름에서는 **판정기가 발동하면 안 된다**.
- Docker 컨테이너 안 작업(`/etc` 수정 등)이 잦다.
- 환경: WSL2(커널 6.18, ext4 홈), `/mnt/c` 는 9p(생성 시각 읽기 불가), Python 3.12.3(구현은 3.10 호환),
  GNU coreutils 9.4, Claude Code 2.1.299.

---

## 2. 확정 결정과 기각한 대안

| ID | 결정 | 근거 |
|---|---|---|
| D1 | 운용 모드는 bypass 고정. 플랫폼(auto 분류기)에 역할을 넘기지 않는다 | §1.6. auto 는 멈춤이 더 잦음 |
| D2 | **`on` 모드의 새 판정기는 ask 를 출력하지 않는다.** 보호 대상은 즉시 deny + 사유 + 대안(off·shadow 는 현행 출력 그대로) | ask 471건 거절 0건, 멈춤 111시간. deny 는 Claude 가 경로를 바꿔 작업을 이어감 |
| D3 | 판정 대상이 아닌 명령에는 지금처럼 **allow** 를 낸다 | 사용자 선택(b). bypass 에선 체감 차이 없음. auto 모드 분류기 우회는 알고 받아들이는 위험(§13) |
| D4 | 삭제 대상은 이름이 아니라 **출처(세션이 만들었나) × 복구 가능성** 7분류로 판정. git ignore 대상은 **재생성 산출물 이름 안쪽일 때만** 산출물로 본다 | "임시·테스트 데이터는 발동 금지, 설정·기본 파일은 보호"(사용자). 이름 목록은 블랙리스트 재발 — 단 데이터·로컬 설정도 흔히 ignore 되므로 'ignore = 재생성 가능'은 거짓(감사 rootcause-s1-004). 허용 쪽의 좁은 이름 목록(§3.4 `REGENERABLE_NAMES`)만 둔다 |
| D5 | git 추적 파일은 일반 `rm` 거부, `git rm` 허용 | 사용자 선택(a). 삭제가 git 변경으로 명시·검토·복구 가능 |
| D6 | git 은 "커밋 안 된 변경", "기본 브랜치 원격 덮어쓰기", reflog 파괴, **어디에도 남지 않는 커밋을 가진 브랜치 삭제**만 보호. reset·rebase·기능 브랜치 강제 push 는 통과. `branch -D` 는 push 해 둔 상태(upstream 추적 ref 가 있고 로컬에 앞선 커밋이 없음)이거나, 내용이 기본 브랜치에 들어갔거나(병합·리베이스·스쿼시 — 병합 후 원격 브랜치를 지운 정리 포함), 다른 ref 에서 도달 가능하거나, 이번 세션에 만든 브랜치면 통과 | reset·rebase 는 reflog 로 복구 가능. 단 linked worktree 에서 만든 미푸시 커밋은 worktree 제거 후 reflog 에 남지 않아 `branch -D` 로 사라진다(감사 rootcause-s1-001). PR 흐름 무발동 요구 — PR 브랜치는 push 로 upstream 이 남는다. 추적 ref 부재만으로 허용하면 병합 뒤 로컬에 더한 커밋이 사라지므로 내용 포함 여부로 판정한다(재감사 rootcause-r1-s1-003) |
| D7 | 디스크 직접 쓰기·재귀 권한 변경은 작업 영역 안에서만 허용. 시스템 경로 쓰기 거부. `killall`·`systemctl stop/disable`·`rmdir` 허용 | 사용자 지정 |
| D8 | 컨테이너 안 명령의 경로는 컨테이너 기준으로 보고 허용. **호스트 마운트·이름 볼륨만** 호스트 규칙 | 사용자 지정. 컨테이너 안 `/etc` 에 발동하던 것이 실제 문제였음 |
| D9 | 구현은 파이썬 표준 라이브러리만. 셸 문법의 필요한 부분집합을 다루는 **자체 어휘 분석기**. shlex·외부 파서 미도입 | shlex 는 따옴표 종류·리다이렉트 위치·`2>&1` 을 잃어 단위 분해가 틀어짐(§3.3-1 실측). 외부 파서는 bashlex(GPL·정체)·tree-sitter(별도 휠) 이득 작음. 시제품 해석 p99 0.5ms 로 성능 여유 확인 |
| D10 | 기능 스위치 `HARNESS_BASH_GUARD=off|shadow|on`, 기본 `off`. **스위치는 프로젝트 settings 에만** 두고, **대상 저장소 기준으로 판정**한다(§3.9) | 단계적 전환·즉시 되돌림. 정의는 플러그인 한 벌, 스위치는 프로젝트. 세션 env 로만 판정하면 홈에서 연 세션이 스위치 켠 저장소를 건드릴 때 꺼진다 — 코드읽기 가드가 2026-10-04 에 같은 결함으로 대상 저장소 기준이 됐다(감사 rootcause-s1-005, 사용자 결정 2026-10-14) |
| D12 | 장부는 세션별이 아니라 **공유 장부** 하나. 다른 세션이 Write 로 만든 파일·고친 파일은 이 세션 것으로 보지 않는다 | 같은 저장소를 여러 세션이 동시에 쓰는 운용(감사 rootcause-s1-002, 사용자 결정 2026-10-14). 다른 세션이 Bash 로 만든 파일은 못 가림(§13) |
| D14 | 공유 장부는 **스위치와 무관하게 항상 기록**한다. 판정기는 `mv` 의 원본이 유일본·보호 이름이거나 이번 세션 것이 아닌 커밋 안 된 수정이 있는 추적 파일이면 목적지를 `moved-in` 으로 기록하고(깨끗한 추적 파일의 이름 변경은 HEAD 에 사본이 있어 기록 안 함), 분류 때 그 기록을 가장 먼저 본다 | 기록 시점에 꺼져 있던 파일을 나중에 켜진 판정이 오분류하는 경로, `mv` 로 재생성·임시 폴더에 옮겨 지우는 세탁 경로를 막는다(감사 라운드 2 rootcause-r2-001·004, 사용자 결정 2026-10-14). 비용: Write·Edit 마다 파이썬 약 35ms |
| D13 | 구현 중 feature 브랜치의 작업별 커밋은 사용자가 위임했다. 테스트는 대역(모듈 패치·가짜 실행 파일·주입 데이터) 없이 인자(예산·기록 상한)와 실제 환경(실제 docker — 없으면 skip 과 사유 출력, `PYTHONHOME=/nonexistent` 로 파이썬 기동 실패)으로 검증한다 | 저장소 규칙 '자동 커밋 금지'·'Mocking 금지'(`.claude/CLAUDE.md`)와의 충돌을 사용자가 결정(2026-10-14, 감사 rootcause-s1-007·008·s2-005) |
| D11 | 실패 정책 3종 분리(§3.8) | Codex·Gemini·cc-safety-net 모두 셋을 구분 |

기각한 대안:

| 대안 | 기각 이유 |
|---|---|
| auto 모드로 전환해 분류기에 위임 | 사용자 운용과 충돌(멈춤 증가) |
| Claude Code 샌드박스(bubblewrap) 혼합 | Docker 비호환(샌드박스 안에서 안 돌아 `excludedCommands` 로 빼야 하고, 뺀 명령은 전체 권한으로 실행 — 공식 문서. 그 예외 목록이 적용되지 않는 보고 #95813), WSL2 에서 조용히 꺼지는 결함(#84563), `/mnt/c` 9p 지연, 기본 네트워크 차단(부록 D). **재검토 조건**: Docker 호환 해결 또는 WSL2 결함 수정 또는 간접 삭제 사고 1건 발생 |
| 명령을 복구 가능한 형태로 자동 변환(rm → 휴지통) | 셸 재작성 오류가 새 사고가 됨. deny+대안으로 같은 효과 |
| ask 를 유지하되 대상만 좁힘 | 무인 실행 정지 비용 그대로, 신호 붕괴 그대로 |
| 정규식 보강 | R1 을 남기는 증상 처방. Cursor 가 우회 보고 뒤 1.3 에서 폐기한 방식(부록 D) |
| 외부 파서(bashlex, tree-sitter-bash, mvdan/sh) | D9 |

---

## 3. 동작 명세

### 3.1 입력 계약 (실측)

PreToolUse 훅 stdin JSON. 판정기가 쓰는 필드:

| 필드 | 쓰임 |
|---|---|
| `tool_name` | `Bash` 일 때만 판정. `Write`·`Edit`·`NotebookEdit` 는 장부 훅(§3.7) |
| `tool_input.command` | 판정할 명령 |
| `tool_input.file_path` | 장부 훅 대상 |
| `cwd` | 명령의 시작 폴더 |
| `session_id` | 장부 키. **서브에이전트도 부모와 같은 값**(실측) |
| `transcript_path` | 세션 시작 시각 = 이 파일의 생성 시각. **서브에이전트도 부모 파일 경로**(실측) |
| `agent_id`, `agent_type` | 서브에이전트일 때만 존재. 기록용 |
| `permission_mode` | 기록용(판정에 쓰지 않음, D3) |

같은 Bash 매처에 훅이 여럿이어도 각 훅이 온전한 입력을 받는다(실측으로 재현 안 됨. 반대 보고 anthropics/claude-code#42702 는 재현·수정 없이 비활성으로 자동 종료).

### 3.2 출력 계약

- 허용: `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}`
- 거부: `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"<사유>"}}`
- **`on` 모드의 새 판정기는 `ask` 를 출력하지 않는다.** `off`·`shadow` 는 현행 판정(`ask` 포함)을 바이트 그대로 낸다(§3.9).
- 출력은 반드시 `json.dumps` 로 만든다(문자열 연결 금지 — 2026-08-30 `\s` 이스케이프로 JSON 이 깨져 게이트가 증발한 전례).
- 종료 코드는 항상 0.
- 사유 형식(거부 근거가 여럿이면 줄마다 하나):

```
[bash-guard] 거부: <작업> <대상 경로> — <분류 설명>. 대안: <구체적 대안>
…
이 판정을 우회하지 말 것. 대안이 맞지 않으면 작업을 멈추고 사용자에게 보고하라.
```

### 3.3 해석기 (`shell_parse.py`)

입력 문자열 → **명령 단위(Segment) 목록**. 각 단위:

```python
@dataclass
class Segment:
    name: str                      # 래퍼 제거 후 명령 이름(basename, 앞 \ 제거). 단어가 없으면 ""
    argv: list[Word]               # argv[0] = 명령 단어. Word = 따옴표 종류를 보존한 조각 목록(단계 1)
    redirects: list[Redirect]      # (op, fd, 대상 Word, heredoc 본문)
    cwd: str | None                # 이 단위 실행 시점의 현재 폴더(cd 추적, 모르면 None)
    env: dict[str, str | None]     # 확정 변수(None = 값 미확정). 초기값: 호출자 환경의 HOME·TMPDIR·USER 와 PWD(= cwd)
    context: Context = HOST        # host | container(이름, 종류 exec|run|compose-exec|compose-run, 마운트, compose 프로젝트명)
    depth: int = 0                 # 재귀 깊이(0 = 최상위)
    via_xargs: bool = False        # xargs 가 실행하는 명령(대상은 입력에서 옴)
```
파이프로 셸에 넘기는 리터럴 코드(단계 7)는 별도 필드 없이 안쪽 단위(`depth+1`)로 펼쳐 같은 목록에 넣는다.
정확한 타입 정의는 구현 계획 Task 1~3 의 Interfaces 가 정본이다.

처리 순서와 규칙:

1. **어휘 분석(자체 구현, 표준 라이브러리만)**: 한 번의 선형 스캔으로 토큰을 만든다. `shlex` 는 쓰지 않는다
   (계획 단계 실측: ① `'$HOME'` 과 `"$HOME"` 을 구분 못 함, ② `a>b`·`2>/dev/null` 이 단어에 붙음, ③ `<>` 를 구분자로 주면
   `2` 가 인자로 분리됨, ④ `2>&1` 의 `&` 를 명령 구분자로 잘라 **단위 분해 자체가 틀어짐** — 시제품의 실패율 0.04% 는 예외만
   센 값이라 이 조용한 오분해를 포함하지 않는다).
   - 단어는 조각(Part) 목록이다. 조각마다 따옴표 종류(없음 / `'` / `"`)를 보존한다. 백슬래시 이스케이프, `$'…'` 는 리터럴 조각.
   - 단어 안의 `$(…)`·`` `…` ``·`${…}`·`$((…))` 는 중첩 괄호·따옴표를 세어 단어의 일부로 유지한다.
   - 연산자: `;` `&&` `||` `|` `|&` `&` 줄바꿈 `(` `)` `;;`. 단어 맨 앞의 `#` 부터 줄 끝은 주석.
   - 리다이렉트: `[n]>` `[n]>>` `[n]>|` `&>` `&>>` `[n]<` `[n]<>` `[n]>&m` `[n]<&m` `<<<`, 그리고 heredoc `<<`·`<<-`.
     숫자 fd 는 **연산자에 공백 없이 붙어 있을 때만** fd 로 본다(`2>` 는 fd, `2 >` 는 인자 2).
   - heredoc: 구분자 단어(따옴표 여부 기록)를 읽고, 그 줄이 끝난 다음 줄부터 구분자만 있는 줄(`<<-` 는 앞 탭 허용)까지를
     본문으로 잘라 리다이렉트에 붙인다. 본문은 판정 대상이 아니다. 단 heredoc 을 받는 명령이 셸이면 본문을 재귀 해석한다.
   - 닫히지 않은 따옴표·괄호, 끝나지 않은 heredoc → 해석 실패(§3.8 (가)).
2. **단위 분해**: 연산자에서 단위를 자른다. `(`…`)` 서브셸 안의 `cd`·변수 변화는 `)` 이후 원복한다.
3. **리다이렉트 분리**: 리다이렉트 토큰과 대상 단어를 `redirects` 로 보내고 인자에서 뺀다(기존 결함: `2>/dev/null` 을 rm 대상으로 해석).
   `>&m`·`<&m`(fd 복제)은 파일 대상이 아니다.
4. **할당·환경 추적**: 단위 맨 앞 `VAR=val` 만 있는 단위는 이후 단위의 `env` 에 반영. `export`·`declare`·`typeset`·`local`
   (`-x` 등 옵션 무시)의 `VAR=val` 도 반영. `VAR=val cmd` 접두는 그 단위에만 적용. 값은 할당 시점에 확장해 저장한다
   (bash 와 같게: 앞 `~`·확정 변수·`$(pwd)` 확장). 확장할 수 없는 요소(명령 치환 등)가 있으면 미확정(None).
5. **cd 추적**: `cd DIR`·`pushd DIR` → cwd 갱신(상대경로는 이전 cwd 기준, `~`·변수 확장). `cd`(인자 없음) → `$HOME`.
   `cd -`·`popd`·확장 실패 → cwd `None`(이후 상대경로 대상은 미확정).
   `git -C DIR`, `make -C DIR`(git 만 판정) 는 해당 명령의 cwd 로 반영.
6. **래퍼 벗기기**(반복 적용): 맨 앞 `\` 제거(`\rm` → `rm`), 절대경로 명령은 basename(`/bin/rm` → `rm`),
   `sudo`(옵션 `-u X` `-g X` `-E` `-H` `-n` 등 값 소비 포함), `doas`, `env`(`-i` `-u X` `VAR=val` 소비),
   `command`, `builtin`, `exec`, `nice`(`-n N`), `nohup`, `time`(`-p`), `timeout`(옵션 + DURATION), `stdbuf`(옵션),
   `ionice`(옵션), `chronic`, `flock`(옵션 + 파일).
7. **재귀 해석**(같은 cwd·env 상속):
   - `bash|sh|zsh|dash` 의 `-c STR`(옵션 묶음 `-lc` `-ec` 포함) → STR
   - `eval STR…` → 인자 연결 문자열
   - 셸에 heredoc 입력 → 본문
   - `… | bash|sh|zsh|dash`: 파이프 앞 단위가 `echo`·`printf`(리터럴 인자)·`cat <<EOF`(본문)면 그 텍스트를 해석.
     그 외(curl, base64 -d 등)는 **해석하지 않고 통과**(§13 구멍).
   - `xargs [옵션] CMD …` → CMD 를 단위로 만들되 대상은 **미확정**(입력을 모름).
   - `find … -exec CMD … {} [;+]` / `-execdir` / `-delete` → §3.5 find 규칙.
   - `docker exec|run`, `docker compose exec|run`, `podman` 동일 → 뒤 명령을 `context=container` 로 해석(§3.6).
8. **명령 치환·백틱**: `$(…)`·`` `…` `` 는 안쪽을 별도 단위로 재귀 해석(안쪽의 파괴 작업도 판정). 치환 결과가 들어간
   인자는 미확정. 단 `$(pwd)`·`` `pwd` ``·`$PWD` 는 그 단위의 cwd 로 확정한다(Docker `-v "$(pwd)":/app` 처럼 흔함).
   큰따옴표 토큰 안의 `$(`·백틱도 같은 규칙으로 안쪽을 해석한다.
9. **해석 실패**(`ValueError`: 닫히지 않은 따옴표 등): §3.8 (가) 규칙.

`python -c`, `node -e`, `perl -e`, `ruby -e`, 스크립트 파일 실행, `make`, `npm|pnpm|yarn run` 의 내부는 해석하지 않는다(§13).

### 3.4 대상 분류 (`target_class.py`)

#### 정규화

1. 원형 인자에 미확정 요소(미확정 변수, 명령 치환, `~user`, 미확정 cwd 의 상대경로)가 있으면 → **확정 불가**.
2. `~` → `$HOME`, 변수 → env 값, 중괄호 확장 `{a,b}` 전개, 상대경로 → 단위 cwd 기준 절대경로.
3. 와일드카드(`*` `?` `[`)는 `glob.glob`(숨김 파일 규칙은 bash 기본과 같게)으로 전개. **일치 없음 → 리터럴 경로 그대로**
   (bash 기본 동작: 리터럴이 전달되어 없는 파일).
4. **부모 폴더는 `realpath` 로 `..` 와 심볼릭 링크를 함께 해소**한다(`normpath` 로 `..` 를 글자만 먼저 지우지 않는다 —
   링크 뒤의 `..` 는 링크 대상의 부모이지 링크의 부모가 아니라서, 먼저 지우면 실제와 다른 경로를 판정하게 된다.
   구현 중 발견: 임시 폴더 안 링크 `lnk → 저장소/src` 에 대해 `lnk/../README.md` 가 임시 폴더 파일로 분류됨). 대상 이름(마지막 구성요소)이
   `.`·`..` 이거나 비면 전체를 `realpath`. 대상 자체가 심볼릭 링크이고
   끝에 `/` 가 없으면 링크 자체를 대상으로 본다(rm 은 링크만 지움). `/` 가 있으면 링크 대상 폴더로 본다.
5. **존재하지 않는 경로** → 잃을 것이 없으므로 **허용**(삭제·덮어쓰기 모두. 덮어쓰기는 새 파일 생성).

#### 7분류 (위에서부터 먼저 맞는 것 하나)

| 순서 | 분류 | 조건 | 기본 판정 |
|---|---|---|---|
| 1 | `UNRESOLVED` 확정 불가 | 정규화 1 | 보호 |
| 1a | `PRESERVED`(옮겨진 유일본) | 공유 장부(§3.7)에 경로 자신, 그 상위 경로, 또는 (폴더면) 그 하위 경로의 `moved-in` 기록이 있음 | 보호 |
| 1b | `SCRATCH` 세션 저장소 | 주 작업 트리(`.git` 이 폴더) 안이고 그 최상위가 분류 5 의 조건(이번 세션 생성)을 만족 — 세션이 만든 clone·`git init` 실험 저장소(임시 루트 안이든 밖이든). 최상위 = 경로 자신부터 위로 올라가 처음 만나는, `.git` 폴더를 가진 폴더(`.git` 내부 경로는 그 `.git` 의 부모. `rev-parse --show-toplevel` 은 `.git` 안에서 실패하고 중첩 저장소의 바깥 폴더에서는 바깥 저장소를 돌려주므로 쓰지 않는다 — 실측). 분류 2·3 과 폴더 순회·상한을 적용하지 않는다(`.git`·추적 파일까지 저장소째 세션 데이터 — 재감사 rootcause-r1-s1-001·r2-s1-002, D4). linked worktree 는 제외(아래 워크트리 최상위 규칙) | 허용 |
| 2 | `PROTECTED_NAME` 보호 이름 | 경로 구성요소에 `.git`(폴더·파일), 파일명이 `.env` 또는 `.env.*`(단 `.env.example`·`.env.sample`·`.env.template` 제외 — 공개용 견본), `*.local.json`·`*.local.yaml`·`*.local.yml`·`*.local.toml`, `*.pem`·`*.key`·`id_rsa*`·`id_ed25519*`·`id_ecdsa*`, `.netrc`, `credentials*`, 경로에 `.ssh/`·`.gnupg/`·`.aws/` | 보호 |
| 3 | `GIT_TRACKED` git 추적 | 가장 가까운 git 작업 트리(`git -C <부모> rev-parse --show-toplevel`) 안이고 `git ls-files --error-unmatch -- <경로>` 성공 | 작업별(§3.5) |
| 4 | `SCRATCH` 임시 폴더 | 아래 임시 루트의 **하위**(루트 자체 아님). 폴더면 아래 '임시 루트 폴더 규칙' | 허용 |
| 5 | `SESSION_NEW` 세션 생성 | 생성 시각 ≥ 세션 시작 **그리고** 공유 장부(§3.7)에 이 세션의 `pre-session` 기록이 없고 **다른 세션의 `created` 기록도 없음** | 허용 |
| 6 | `IGNORED_ARTIFACT` 재생성 산출물 | git 작업 트리 안이고 `git check-ignore -q -- <경로>` 성공이며, **저장소 안 경로 구성요소 중 하나가 `REGENERABLE_NAMES` 이거나 확장자가 `.pyc` `.pyo` `.o` `.class`** | 허용 |
| 7 | `PRESERVED` 보호 | 그 외 전부: 추적·무시 어느 쪽도 아닌 세션 전 파일, **재생성 이름이 아닌 ignore 대상**(데이터·로컬 설정), 저장소 밖 세션 전 파일, 생성 시각을 못 읽는 경로(`/mnt/c` 등 — 값 0) | 보호 |

`REGENERABLE_NAMES` = `node_modules` `dist` `build` `.next` `.nuxt` `target` `__pycache__` `.pytest_cache` `.ruff_cache` `.mypy_cache`
`.tox` `.venv` `venv` `coverage` `.coverage` `.gradle` `.parcel-cache` `.turbo` `.cache`(허용 쪽 목록 — 빠진 이름은 보호로 떨어진다).

- **임시 루트**: `/tmp`, `/var/tmp`, `$TMPDIR`(설정 시), `~/.cache`, `/mnt/c/Windows/Temp`, 그리고 경로 패턴
  `/mnt/c/Users/*/AppData/Local/Temp`(패턴 일치로 판정 — 그 사용자 폴더의 실재 여부와 무관).
  ★ 임시 루트 **자체**나 루트 바로 아래 와일드카드(`rm -rf /tmp/*`)는 다른 세션·프로세스의 파일까지 지우므로
  `SCRATCH` 가 아니라 확정 불가로 본다(대안: "자기 세션 폴더로 범위를 좁혀라").
- **세션 시작**: `stat -c %.9W <transcript_path>`. 값을 못 얻으면(0·오류) `SESSION_NEW` 는 어떤 경로에도 적용하지 않는다(보수적).
  `--resume` 으로 새 기록 파일이 생기면 그 시점부터가 세션이다(이전 대화에서 만든 파일은 보호 쪽 — 보수적, §13).
- **생성 시각**: `stat -c '%.9W %n' p1 p2 …` 를 한 번에 호출(파이썬 3.10~3.12 는 Linux 생성 시각 API 가 없다).
  커널 시각 해상도가 수 ms 라 연속 생성 파일이 같은 값을 받는다 → 비교는 `>=`.
- **폴더 규칙**: 대상이 폴더면 안의 항목을 `os.walk`(심볼릭 링크 따라가지 않음)로 최대 **2,000개**까지 분류하고,
  **가장 보호 쪽 분류**를 폴더의 분류로 한다(보호 > 추적 > 허용). 상한 초과 → 확정 불가("범위를 좁혀라").
  폴더 자체가 `SESSION_NEW` 여도 **순회한다** — `mv` 는 생성 시각을 유지하므로 세션 전 유일본을 세션 폴더로 옮겨 넣고
  폴더째 지우는 경로를 막는다(감사 rootcause-s1-003). 순회 생략은 폴더가 분류 1b(세션 저장소)이거나 `IGNORED_ARTIFACT`(재생성 이름 안쪽)일 때뿐이며 그때도 분류 1a 를 먼저 본다.
  **임시 루트 폴더 규칙**: 임시 루트 하위 폴더는 항목을 이름으로만 본다 — `os.walk` 로 내려가며(상한 없음, 시간 예산 안) 이번 세션 저장소(1b)
  안으로는 내려가지 않고, 보호 이름(분류 2)이 있으면 `PROTECTED_NAME`, 없으면 `SCRATCH`. 2,000개 넘는 세션 임시 폴더도 허용하면서 다른 세션의
  키·`.env`·`.git` 은 보호한다(재감사 rootcause-r2-s1-001: 임시 폴더 아래 다른 세션의 TLS 개인키 실측).
  심볼릭 링크는 따라가지 않으므로 순환 링크도 순회가 끝나며, 링크 항목은 링크 자체(`lstat`)로 분류한다. 순회 중 읽기 오류 →
  확정 불가. 폴더 아래 추적 파일 존재 여부는 `git ls-files -- <폴더>` 한 번으로 확인. 순회를 생략하는 재생성 산출물 폴더도
  분류 1a(장부의 `moved-in` 접두 일치)는 먼저 확인하므로, `mv` 로 옮겨 넣은 유일본은 보호된다(D14).
- **워크트리 최상위 규칙**: 대상 폴더가 git 작업 트리의 최상위이고 `.git` 이 파일(linked worktree)이면, 추적 파일은 커밋에 있어
  개별 분류하지 않는다. 대신 ① 커밋 안 된 변경(§3.5 git 규칙)과 ② 미추적·ignore 항목(`git -C <wt> status --porcelain=v1 -z --ignored=matching
  --untracked-files=normal` — 미추적·ignore 폴더는 폴더 하나로 나온다)을 위 7분류(폴더 규칙 포함)로 분류해, ①이 있거나 ②에 보호 분류가 있으면
  거부한다. `.env`·로컬 데이터 같은 ignore 유일본이 worktree 와 함께 사라지는 경로를 막는다(D4, 재감사 rootcause-r1-s1-002).
  같은 규칙을 `git worktree remove [--force]` 에도 쓴다.
- **작업 영역**(디스크·권한 규칙용): 임시 루트 하위, 또는 어떤 git 작업 트리 안(`.git` 내부 제외).
  단 작업 트리 최상위가 `$HOME` 이나 `/` 이면 작업 영역으로 보지 않는다(dotfiles 저장소가 홈 전체를 작업 영역으로 만드는 것 방지.
  2026-10-14 현재 홈은 저장소가 아님).

### 3.5 작업별 판정 (`policy.py` — 정책은 이 파일의 데이터 표 하나에)

#### 삭제

대상 명령: `rm`(옵션 유무 무관), `unlink`, `shred`, `find … -delete`, `find … -exec|-execdir rm … {}`, `rsync --delete*` 의 대상 폴더,
`git clean`(git 규칙). **`rmdir` 은 판정 안 함(허용).**

| 분류 | 판정 | 대안 문구 |
|---|---|---|
| `SCRATCH` `SESSION_NEW` `IGNORED_ARTIFACT` / 없는 경로 | 허용 | — |
| `GIT_TRACKED` | 거부 | "`git rm <경로>` 로 삭제하라(변경 내역에 남아 검토·복구 가능)" |
| `PROTECTED_NAME` `PRESERVED` | 거부 | "세션 전부터 있던 유일본이다. 정말 지워야 하면 사용자에게 요청하라" |
| `UNRESOLVED` | 거부 | "대상을 리터럴 경로로, 범위를 좁혀 다시 실행하라" |

- `git rm`(`-f`·`--force` 없음)은 허용. `git rm -f|--force` 는 git 표의 커밋 안 된 변경 판정을 따른다.
- **find 미리보기**: 표현식이 검사 조건(`-name` `-iname` `-path` `-type` `-mtime` `-newer` `-size` `-maxdepth` `-mindepth`
  `-prune` `-o` `-a` `!` `(` `)` 등)과 `-delete` 또는 `-exec rm [-rf] {} [;+]` 하나로만 이뤄졌으면, 그 동작을 `-print0` 로
  바꾼 읽기 전용 find 를 시간 예산 안에서 실행해 실제 대상 목록을 얻고 각각 분류한다. 그 외 형태 → 확정 불가.
- `xargs rm` → 확정 불가(대안: "`find … -delete` 나 리터럴 경로를 써라").

#### 덮어쓰기

대상: 리다이렉트 `>` `>|` `&>`(`>>` 은 추가라 제외), `tee`(`-a` 제외)의 파일 인자, `truncate`, `cp`·`mv`·`install`·`rsync`
의 기존 목적지 파일(목적지가 폴더면 `폴더/원본이름`), `dd of=X`(X 가 장치 경로가 아닐 때).
`/dev/null` `/dev/stdout` `/dev/stderr` `/dev/tty` `/dev/fd/*` 는 제외(허용). 장치 경로 대상은 아래 디스크 규칙만 따른다.

| 분류 | 판정 |
|---|---|
| 없는 경로, `SCRATCH`, `SESSION_NEW`, `IGNORED_ARTIFACT` | 허용 |
| `GIT_TRACKED` 이고 커밋 후 수정 없음 | 허용(git 으로 복구) |
| `GIT_TRACKED` 이고 커밋 안 된 수정 있음, 단 그 수정이 **이번 세션 것**(§git 규칙의 세션 변경 판정) | 허용 |
| 그 외 `GIT_TRACKED` | 거부 — "커밋 안 된 수정이 있다. 먼저 커밋하거나 `git stash` 하라" |
| `PROTECTED_NAME` `PRESERVED` `UNRESOLVED` | 거부 |

`sed -i`·`perl -pi` 등 제자리 편집은 판정하지 않는다(편집은 손실이 아님). 단 장부 기록(§3.7).
`mv` 의 원본은 손실이 아니다(옮겨질 뿐).

#### 디스크·시스템·권한

| 작업 | 판정 |
|---|---|
| 장치 쓰기: 덮어쓰기 대상 전부 — 쓰기 리다이렉트, `tee`, `truncate`, `cp`·`mv`·`install`·`rsync` 목적지, `dd of=` — 의 X 가 **장치 경로**(`/dev/` 아래이고 `/dev/null` `/dev/stdout` `/dev/stderr` `/dev/tty` `/dev/fd/*` `/dev/shm/*` 로 시작하지 않음) | 거부(장치는 작업 영역 밖) |
| `mkfs* X` | X 가 작업 영역 안(이미지 파일)이면 허용, 아니면 거부 |
| 호스트의 `/etc` `/usr` `/bin` `/sbin` `/lib` `/lib32` `/lib64` `/boot` 하위에 대한 삭제·덮어쓰기·`chmod`·`chown`·`chgrp`(재귀 여부·옵션 무관) | 항상 거부 |
| `chmod -R`·`chown -R`·`chgrp -R` | 대상이 작업 영역 안이면 허용, 아니면 거부(시스템 경로 밖의 재귀 아닌 `chmod 777 x` 는 판정 안 함) |
| `killall`, `pkill`, `systemctl stop|disable|restart`, `rmdir` | 판정 안 함(허용) |

#### git

판정은 해당 명령의 저장소(`-C`·cwd)에서 git 을 조회해 한다.

**세션 변경 판정**(커밋 안 된 수정이 이번 세션 것인가): §3.7 '이번 세션 변경' 정의 그대로 — 수정 시각(`%Y`) ≥ 세션 시작,
이 세션의 `pre-dirty` 없음, 세션 시작 이후 다른 세션의 `touched` 없음.

| 명령 | 판정 |
|---|---|
| `branch -d`, `reset`(`--hard` 아님), `rebase`, `commit --amend`, `update-ref -d`, `switch`/`checkout <브랜치>`(강제 아님 — 덮일 변경이 있으면 git 이 스스로 거부), `worktree add`, `stash pop|apply|push`, `rm`(`-f` 없음 — 수정된 파일은 git 이 거부), `restore --staged`만 | 허용 |
| `branch -D B` | B 가 push 해 둔 상태(upstream `branch.B.remote` 가 있고 그 추적 ref 가 있으며 `git rev-list --count <upstream>..B` = 0)이거나, B 의 내용이 기본 브랜치에 들어갔거나(아래 '병합 판정'), B 끝 커밋이 B 외 다른 ref 에서 도달 가능하거나(`git for-each-ref --contains`), B 가 이번 세션에 만들어졌으면(`git reflog show --date=unix --format=%gd refs/heads/B` 의 마지막 줄 `B@{<epoch>}` = 가장 오래된 reflog 항목 시각 ≥ 세션 시작. `%ct` 는 그 항목이 가리키는 커밋 시각이라 쓰지 않는다) 허용. 아니면 거부 — "어디에도 남지 않는 커밋이 있다. 먼저 push 하거나 태그를 남겨라. 병합된 브랜치면 `git fetch` 뒤 다시 실행하라" |
| `push`(아래 예외 외 전부: 기능 브랜치 강제 push, `+ref`, `--delete`, `--force-with-lease` 포함) | 허용 |
| `push` 의 대상 ref 가 **기본 브랜치**이면서 `--force`·`-f`·`+ref`·`--delete`·`:ref`, 또는 `--mirror` | 거부 — "기본 브랜치 원격 이력 덮어쓰기. 기능 브랜치로 push 하고 PR 을 열어라" |
| `reset --hard`, `checkout [--] <경로|.>`, `checkout -f`, `switch -f|--discard-changes`, `restore <경로>`(작업 트리 대상), `rm -f|--force <경로>`, `worktree remove [--force]`, linked worktree 최상위 폴더의 `rm -r` | 영향 범위의 커밋 안 된 변경(`git status --porcelain=v1 -z --untracked-files=no -- <범위>`)이 없거나 전부 이번 세션 변경이면 허용, 아니면 거부 — "먼저 `git stash push -u` 하거나 커밋하라". worktree 세 형태는 추가로 §3.4 워크트리 최상위 규칙 ②에 보호 분류가 있으면 거부 — "worktree 안에 유일본이 있다. 옮기거나 사용자에게 요청하라" |
| `clean`(`-n`·`--dry-run` 이면 허용) | 같은 옵션에 `-n` 을 **더해**(`-f`·`-ff` 는 그대로 둔다 — `-ff` 를 `-f` 로 줄이면 중첩 저장소가 목록에서 빠지고, `-n` 은 `-f` 와 함께여도 지우지 않는다) 지워질 목록을 얻는다. 목록 출력을 막는 `-q`·`--quiet` 는 뺀다(빈 목록 = 허용으로 읽히는 오판). 각 항목(git 이 낸 대로, 폴더는 폴더 하나)을 삭제 규칙으로 분류 |
| `stash drop|clear` | 해당 보관본 생성 시각(`git log -g --format=%ct refs/stash`) ≥ 세션 시작이면 허용, 아니면 거부 |
| `reflog expire|delete`, `gc --prune=now|all`, `prune`, `filter-branch`, `filter-repo` | 거부 — reflog 복구 경로를 없애므로(D6 전제 보호) |

- **기본 브랜치**: `git symbolic-ref --short refs/remotes/<원격>/HEAD` 의 브랜치명. 없으면 `main`·`master`.
- push 의 대상 ref: 인자 refspec 의 목적지. refspec 이 없으면 현재 브랜치의 upstream 이름(`git rev-parse --abbrev-ref @{u}`),
  그것도 없으면 현재 브랜치명. `push --all`·`--branches` 는 모든 로컬 브랜치(로컬에 기본 브랜치가 있으면 그것 포함)를, 글롭 refspec(`*` 포함)은
  목적지 패턴이 `refs/heads/<기본 브랜치>` 와 `fnmatch` 로 맞으면 기본 브랜치를 대상에 넣는다 — 강제(`--force`·`-f`·`+`)와 함께면 거부(재감사 rootcause-r1-s1-004).
- **병합 판정**(`branch -D`): 기준 D = `refs/remotes/<B 의 upstream 원격, 없으면 origin>/<기본 브랜치>`(없으면 로컬 기본 브랜치).
  `git cherry D B` 에 `+` 줄이 없으면(병합·리베이스 병합), 또는 `git diff <merge-base D B> B | git patch-id --stable` 의 id 가
  `git log -p <merge-base>..D | git patch-id --stable` 의 id 중 하나와 같으면(스쿼시 병합 — 실측 2026-10-14: 병합 뒤 커밋을 더하면 불일치) 들어간 것으로 본다.
  쓰기 없는 조회만 쓴다(fetch 하지 않는다). D 가 오래됐는지는 조회만으로 알 수 없으므로 `branch -D` 거부 대안에는 늘
  "병합된 브랜치면 `git fetch` 뒤 다시 실행하라"를 덧붙인다.

#### Docker

| 명령 | 판정 |
|---|---|
| 컨테이너 안 단위(§3.6)의 대상 | 컨테이너 내부 경로 → 허용. 호스트 바인드 마운트 경로 → 호스트 경로로 바꿔 위 규칙 전부 적용. 이름 볼륨 경로 → 볼륨 규칙 |
| `docker volume rm V…`, `docker volume prune`, `docker system prune --volumes`, `docker compose down -v|--volumes` | 각 볼륨의 `CreatedAt` ≥ 세션 시작이면 허용, 아니면 거부 — "기존 볼륨(데이터)이다. 사용자에게 요청하라" |
| 그 외 docker 명령(`rm`, `stop`, `build`, `compose up/down`(볼륨 없이) 등) | 허용 |

- 대상 볼륨 목록: `volume rm` 은 인자, `volume prune`·`system prune --volumes` 는 `docker volume ls -q -f dangling=true`, `compose down -v` 는
  `docker volume ls -q -f label=com.docker.compose.project=<프로젝트명>`(프로젝트명은 `-p` 인자 또는 compose 파일 폴더명).
- Docker 조회 실패(데몬 없음 등) → 볼륨 삭제는 확정 불가(거부), 컨테이너 안 경로는 허용.

### 3.6 컨테이너 문맥

- `docker exec [옵션] 컨테이너 명령…` / `docker compose exec [옵션] 서비스 명령…` → 컨테이너 이름(또는
  `docker compose ps -q 서비스`의 ID)으로 `docker inspect --format '{{json .Mounts}}'` 를 **한 번** 조회해 마운트 표를 얻는다.
- `docker run|compose run` → 마운트는 `-v/--volume SRC:DST`, `--mount type=bind|volume,source=…,target=…` 인자에서 정적으로 얻는다.
- 안쪽 명령은 §3.3 으로 해석(`sh -c` 재귀 포함). 대상의 컨테이너 경로가 마운트 `Destination` 자체이거나 그 하위면 `Source`(bind) 또는
  볼륨 이름(volume)으로 사상한다(`rm -rf /app` 처럼 Destination 자체를 지우면 Source 폴더의 내용 전체가 대상). 마운트 밖이면 컨테이너 내부 경로 → 허용.
- compose 계열은 `-p/--project-name` 값을 컨테이너 조회(`docker compose -p <p> ps -q <서비스>`)에 쓴다.
- 시스템 경로 거부 규칙은 **호스트 경로에만** 적용된다.
- 세션 자체가 컨테이너 안에서 도는 경우(devcontainer)는 범위 밖(§13).

### 3.7 공유 장부 (`touch-ledger` 와 판정기 공용)

문제 ①: Edit 도구·`sed -i`·`git checkout` 은 파일을 바꿔치기해 생성 시각이 갱신된다(실측) → 세션 전 파일을 한 번 고치면 `SESSION_NEW` 로 오분류된다.
문제 ②: 같은 저장소를 동시에 쓰는 다른 세션이 만든·고친 파일도 "세션 시작 뒤"라 이 세션 것으로 보인다(D12).

- 위치: `${XDG_STATE_HOME:-$HOME/.local/state}/harness-core/ledger.tsv` — **모든 세션이 공유하는 파일 하나**.
- 행: `<realpath>\t<kind>\t<session_id>\t<epoch>`. `kind`:
  - `pre-session`: 기록한 세션이 처음 손대기 직전, 생성 시각이 그 세션 시작보다 앞이던 파일
  - `pre-dirty`: 기록한 세션이 처음 손대기 전부터 커밋 안 된 수정이 있던 추적 파일
  - `created`: 기록한 세션이 Write 로 새로 만든 파일
  - `touched`: 기록한 세션이 Write·Edit·NotebookEdit 로 고친 파일(매번, 시각 포함)
  - `moved-in`: 판정기가 해석한 `mv` 의 원본이 `PRESERVED`·`PROTECTED_NAME` 이거나, 커밋 안 된 수정이 있고 그 수정이 이번 세션 것이 아닌 `GIT_TRACKED` 일 때 그 목적지 경로(목적지가 폴더면 `폴더/원본이름`). 깨끗한 추적 파일의 이름 변경은 HEAD 에 사본이 있어 기록하지 않는다(PR 흐름 무발동, 재감사 rootcause-r1-s2-001)
- 쓰기: 추가도 압축도 같은 잠금(flock, `LOCK_EX`)을 장부 파일에 잡고 한다 — 추가는 잠금 안에서 한 줄 = `os.write` 1회(`O_APPEND`).
  같은 (경로, kind, 세션) 은 다시 쓰지 않는다(`touched` 는 매번). 파일이 5MB 를 넘으면 같은 잠금 안에서 7일 지난 줄을 뺀 내용으로 다시 쓴다.
  단 `moved-in` 줄은 기간으로 빼지 않고 그 경로가 더 이상 없을 때만 뺀다(보호 근거가 기간으로 사라지면 세탁 경로가 다시 열린다 — 재감사 rootcause-r1-s1-005).
  잠금 없는 추가는 압축의 읽기와 다시 쓰기 사이에 끼어든 줄을 잃는다(재감사 rootcause-r1-s1-006).
- 기록 주체:
  1. `touch-ledger`(PreToolUse 매처 `Write|Edit|NotebookEdit`, 대상 = `tool_input.file_path` 또는 `notebook_path`): 경로가 없으면 `created`.
     있으면 생성 시각 < 세션 시작이면 `pre-session`, 추적 파일이고 이 세션의 `touched` 가 아직 없는데 이미 수정 상태면 `pre-dirty`.
     그리고 `touched`. 항상 출력 없음, 종료 0. **스위치와 무관하게 항상 기록**한다(D14) — 기록 시점에 꺼져 있던 파일도 나중에 켜진 판정이 정확히 본다.
  2. 판정기: 해석한 단위가 아래 닫힌 목록의 제자리 수정이면 그 대상에 같은 규칙(`created` 제외)을 적용해 장부에 기록한다 — 쓰기·추가 리다이렉트(`>` `>|` `&>` `>>` `&>>`) 대상, `tee`(`-a` 포함)의 파일 인자, `sed -i|--in-place`, `perl -i|-pi`, `truncate`, `cp`·`mv`·`install`·`rsync`·`dd of=` 의 기존 목적지 파일, `git checkout [--] <경로>`, `git restore <경로>`. 목록 밖(`patch`, `git apply`, 스크립트 내부)은 기록하지 않는다(§13).
     `mv` 단위는 원본을 분류해 위 `moved-in` 조건이면 목적지를 `moved-in` 으로 기록한다. 판정기도 모드와 무관하게 기록한다.
- 조회(세션 S 기준):
  - `SESSION_NEW` = 생성 시각 ≥ S 시작 ∧ S 의 `pre-session` 없음 ∧ 다른 세션의 `created` 없음
  - 이번 세션 변경 = 수정 시각 ≥ S 시작 ∧ S 의 `pre-dirty` 없음 ∧ S 시작 이후 다른 세션의 `touched` 없음
- 조회 추가: 분류 1a — 경로 자신·상위·(폴더면) 하위 경로에 `moved-in` 이 있으면 보호.
- 한계: 다른 세션이 Bash 로 만든·고친 파일, 임의 스크립트가 바꿔치기한 세션 전 파일, `patch`·`git apply` 로 고친 파일, 스크립트 안의 `mv` 는 기록되지 않는다(§13).

### 3.8 실패 정책과 시간 예산

| 상황 | 판정 |
|---|---|
| (가) 해석 실패 | 원문에 삭제·덮어쓰기·git 파괴 관련 단어(`rm` `unlink` `shred` `truncate` `dd` `mkfs*`(`mkfs.ext4` 등 포함) `-delete` `reset` `clean` `restore` `checkout` `push` `volume` `prune` `>`)가 **단어 경계로**(앞뒤 글자가 영숫자·`_`·`-`·`.` 가 아님. `>` 는 위치 무관) 있으면 거부("명령을 해석하지 못했다. 단순한 형태로 나눠 실행하라"), 없으면 허용 |
| (나) 대상 확정 불가 | 해당 작업의 `UNRESOLVED` 규칙(거부 + 대안) |
| (다) 판정기 내부 예외 | 오류 기록(§3.9, 모드와 무관). 출력: 세션 env 값과 cwd 저장소 값 중 강한 모드(계산 실패 시 `off`)가 `on` 이면 `on` 모드의 내부 예외 폴백도 ask 를 내지 않도록 (가) 규칙을 원문에 적용해 거부("판정기 오류 — 단순한 형태로 나눠 실행하라") 또는 허용, `off`·`shadow` 면 OLD 그대로(재감사 rootcause-r1-s2-003). 입구 스크립트는 파이썬이 뜨지 않거나 출력이 비면 OLD 를 출력한다(이때만 `on` 에서도 OLD 의 ask 가 나올 수 있다 — §13) |
| 시간 예산 초과(내부 마감 5초) | 그때까지 **판정 대상 작업**(§3.5 표에서 판정 행에 해당하는 단위: 삭제·덮어쓰기·디스크·시스템·재귀 권한, git 의 판정 행 하위명령, docker 볼륨 삭제, 컨테이너 문맥 단위)을 만났으면 거부("판정 시간 초과 — 범위를 좁혀라"), 아니면 허용. 외부 명령(git·stat·docker·find)은 개별 `timeout=2`초 |

플랫폼 제한 10초(`hooks.json` timeout)는 유지한다. 실측 지연: 파이썬 기동+import 35ms, 해석 p99 0.5ms,
git 조회 1.5~8ms(1.3만 파일 저장소 전체 status 최대 70ms), `stat` 1ms, `docker inspect` 33~68ms.

### 3.9 기능 스위치와 기록

- 스위치 `HARNESS_BASH_GUARD`: `off`(기본) | `shadow` | `on`. 그 외 값 → `off`. **대상 저장소 기준으로 판정한다**(D10).
  - 경로의 저장소 값: 경로에서 위로 올라가 처음 만나는 `.git`(폴더·파일)을 가진 폴더 R 의 `R/.claude/settings.local.json`·
    `R/.claude/settings.json` 의 `env.HARNESS_BASH_GUARD`(local 우선). R 이 없거나 `$HOME`·`/` 이면 값 없음.
  - 명령의 모드 = {세션 env 값, 훅 입력 cwd 의 저장소 값, 판정 대상 단위마다 그 단위 cwd(cd 추적 결과, 미확정이면 생략)의 저장소 값, 판정 대상 작업의 모든 대상 경로(컨테이너 문맥은 바인드 마운트를 호스트 경로로 바꾼 것)의 저장소 값} 중 가장 강한 것(`on` > `shadow` > `off`). 홈에서 연 세션이 `cd` 로 스위치 저장소에 들어가 대상을 확정할 수 없는 명령을 내도 켜진다(재감사 rootcause-r1-s2-005·s1-007).
  - `off`: 현행 판정 그대로. `shadow`: 현행 판정 출력 + 새 판정과 다르면 기록. `on`: 새 판정 출력.
- 입구 흐름: 기존 로직이 먼저 현행 판정 OLD 를 만든다 → `bash_guard.py --old "$OLD"` 가 새 판정과 모드를 정해 최종 출력을 낸다
  (`off`·`shadow` 는 OLD 를 바이트 그대로, OLD 가 비면 출력 없음). 파이썬이 뜨지 않거나 출력이 비면 입구가 OLD 를 출력한다.
  비용: 스위치와 무관하게 모든 Bash 호출에서 파이썬 판정이 돈다(기동 약 35ms — 사용자 수용 2026-10-14).
- 기록 파일: `${XDG_STATE_HOME:-$HOME/.local/state}/harness-core/bash-guard.jsonl`. 한 줄 JSON:
  `{ts, mode, session_id, agent_id, cwd, command(최대 2000자), decision, old_decision(shadow), reasons[], ms, error}`.
  기록 대상: `on` 의 거부, `shadow` 의 신·구 불일치, 그리고 판정기 내부 예외(모드와 무관 — `off`·모드 미정 포함). 10MB 초과 시 `.1` 로 한 번 순환.
- **기록은 로컬 전용**이다. 저장소에 넣지 않는다(명령 원문에 경로·비밀이 섞일 수 있음).

---

## 4. Tech Stack

- Python 3.10+ 호환 문법(실행은 시스템 `python3`, 현재 3.12.3). `from __future__ import annotations`, 타입 힌트,
  `dataclass`, `pathlib`. **표준 라이브러리만**(json, re, glob, subprocess, os, time, dataclasses, unittest). shlex 는 쓰지 않는다(§3.3-1).
- 외부 명령: `git`, GNU `stat`(%.9W), `docker`(있을 때만), `find`.
- POSIX `sh` 입구 스크립트(기존 `auto-approve-readonly.sh` 는 bash — `off`/`shadow` 경로 보존을 위해 bash 유지).

## 5. Commands

저장소 루트(`~/tools/claude-project-config` 의 worktree)에서:

```bash
# 단위·회귀·누락·시나리오 테스트 (pytest 미사용 — 표준 unittest, 파일 단독 실행. `-k 이름` 으로 개별 실행)
for t in shell_parse target_class policy bash_guard touch_ledger; do
  python3 "plugins/harness-core/hooks/tests/test_$t.py" || exit 1
done
bash plugins/harness-core/hooks/tests/test-bash-guard-entry.sh

# 기존 테스트(off 경로 회귀)
for t in plugins/harness-core/hooks/tests/test-*.sh; do bash "$t" || exit 1; done
python3 plugins/harness-core/hooks/tests/test_code_read_guard.py
python3 plugins/harness-core/hooks/t_auto_approve_rm.py

# 정적 검증
shellcheck -S warning plugins/harness-core/hooks/scripts/*.sh plugins/harness-core/hooks/tests/test-bash-guard-entry.sh   # 기존 파일의 note 3건은 범위 밖(2026-10-14 실측)
python3 -m py_compile plugins/harness-core/hooks/scripts/*.py
# ruff 는 이 변경이 만든 파일만 — 기존 파일의 기존 위반 6건은 범위 밖(2026-10-14 실측)
ruff check plugins/harness-core/hooks/scripts/{shell_parse,ledger,target_class,policy,bash_guard,touch-ledger}.py \
  plugins/harness-core/hooks/tests/{_world,test_shell_parse,test_target_class,test_policy,test_bash_guard,test_touch_ledger}.py \
  plugins/harness-core/hooks/tests/tools/replay_corpus.py
jq empty plugins/harness-core/hooks/hooks.json

# 전수 재생(로컬 세션 기록 사용, 결과는 저장소 밖에만 씀)
python3 plugins/harness-core/hooks/tests/tools/replay_corpus.py \
  --projects ~/.claude/projects \
  --out "${XDG_STATE_HOME:-$HOME/.local/state}/harness-core/replay"
```

## 6. Project Structure

```
plugins/harness-core/
├── README.md                      # 갱신: 구조·스위치·기록 위치
├── DECISIONS.md                   # 신규: §2 결정·기각 대안·재검토 조건
├── LIMITS.md                      # 신규: §13
└── hooks/
    ├── hooks.json                 # 변경: PreToolUse 매처 Write|Edit|NotebookEdit 에 touch-ledger 등록(timeout 5). Bash 등록은 그대로(timeout 10)
    ├── t_auto_approve_rm.py       # 유지(off 경로 회귀). on 안정화 후 기존 로직과 함께 제거
    ├── scripts/
    │   ├── auto-approve-readonly.sh   # 변경: 스위치 분기 입구. off 경로 = 기존 로직 그대로
    │   ├── bash_guard.py              # 신규: 진입점(main) — 입력 읽기·조립·출력·기록·시간 예산
    │   ├── shell_parse.py             # 신규: §3.3
    │   ├── target_class.py            # 신규: §3.4 (+ 장부 조회)
    │   ├── policy.py                  # 신규: §3.5·§3.6 (정책 데이터 표)
    │   ├── ledger.py                  # 신규: §3.7 읽기·쓰기 공용
    │   ├── touch-ledger.py            # 신규: Write|Edit 장부 훅(스위치와 무관하게 항상 기록)
    │   └── code-read-guard.py         # 유지(이번 범위에서 호출 방식 변경 없음 — §12)
    └── tests/
        ├── test_shell_parse.py        # 신규: 해석기 단위
        ├── test_target_class.py       # 신규: 분류기·git·docker 조회 단위(임시 저장소, 실제 docker — 없으면 skip)
        ├── test_policy.py             # 신규: 작업 × 분류 판정 단위
        ├── test_bash_guard.py         # 신규: 입출력 종단 + 오탐 회귀 + 누락 + 시나리오(§8)
        ├── test_touch_ledger.py       # 신규
        ├── test-bash-guard-entry.sh   # 신규: 입구 스위치(off 동일성·shadow·on·파이썬 기동 실패 시 OLD)
        ├── _world.py                  # 신규: 테스트용 세계(홈·저장소·bare 원격·세션 전/후 파일·실제 docker 자원) 빌더
        ├── fixtures/                  # 신규: 재구성 사례(JSON). 실제 세션 명령 원문 금지
        └── tools/replay_corpus.py     # 신규: 로컬 전수 재생 도구(결과는 저장소 밖)
```

입구 스크립트 흐름(개념):

```sh
INPUT=$(cat)
# (기존) code-read-guard 블록 — 지금 위치·동작 그대로. deny 가 나오면 출력하고 종료.
OLD=$(printf '%s' "$INPUT" | old_logic)          # 현행 rm 가드 + 위험 패턴 + 기본 allow (현행과 같은 출력)
OUT=$(printf '%s' "$INPUT" | python3 "$(dirname "$0")/bash_guard.py" --old "$OLD" 2>/dev/null) || OUT=""
if [ -n "$OUT" ]; then printf '%s\n' "$OUT"; elif [ -n "$OLD" ]; then printf '%s\n' "$OLD"; fi
```

(`bash_guard.py` 는 모드가 `off`·`shadow` 면 OLD 를 그대로 출력한다. 모든 스위치가 꺼진 상태의 출력은 현행과 바이트 단위로 같아야 한다.)

## 7. Code Style

기존 `code-read-guard.py` 관례를 따른다: 모듈 docstring 에 **왜(실측 근거)·계약·호출·종료·테스트**를 쓰고,
주석은 코드가 보여 주지 못하는 이유만 한 줄로. 정책은 코드 분기가 아니라 데이터 표로 둔다.

```python
#!/usr/bin/env python3
"""policy.py — 명령 단위 × 대상 분류 → 거부 사유(Finding) 목록.

★왜: 명령 모양이 아니라 '무엇이 사라지는가'로 판정한다(spec 2026-10-14-bash-guard-design §3.5).
계약: evaluate(seg, ctx) -> list[Finding]. 빈 목록 = 이 단위는 허용(판정 대상 밖 포함).
테스트: python3 hooks/tests/test_policy.py
"""
from __future__ import annotations

from dataclasses import dataclass

KIND_TEXT = {"GIT_TRACKED": "git 이 추적하는 파일", "PRESERVED": "세션 전부터 있던 유일본"}  # 전체 표는 구현 계획 Task 7


@dataclass(frozen=True)
class Finding:
    op: str
    target: str
    kind: str
    advice: str

    def reason(self) -> str:
        return f"거부: {self.op} {self.target} — {KIND_TEXT[self.kind]}. 대안: {self.advice}"
```

## 8. Testing Strategy

원칙: **훅의 입력·출력 JSON 만으로 검증**한다(정책 표나 내부 함수 이름에 테스트를 묶지 않음 — 기존 테스트가 소스의
패턴 목록을 추출하다 목록 변경 시 깨진 전례). 단위 테스트만 모듈 함수를 직접 부른다.

| 묶음 | 내용 | 기대 |
|---|---|---|
| 단위: 해석기 | 구분자·서브셸 원복·리다이렉트 분리·할당/export·cd/pushd/cd -·래퍼 6종 이상·재귀(`bash -c`, `eval`, heredoc→sh, 리터럴 `echo … \| sh`, `$( )`, 백틱)·docker 문맥·해석 실패 | 기대 Segment |
| 단위: 분류기 | 임시 git 저장소를 만들고 세션 시작 파일(테스트용 transcript 파일)을 기준으로 7분류 각각 + 폴더 규칙(혼합 내용, 2,000 상한) + 워크트리 최상위 + 심볼릭 링크 + 없는 경로 + `/tmp/*` 루트 와일드카드 | 기대 분류 |
| 단위: 정책 | 작업 × 분류 조합 전수 | 기대 판정 |
| 오탐 회귀 (`fixtures/false_positive.json`) | §1.3 유형별 **재구성** 사례: 따옴표 안 `'rm -rf ~'`, heredoc 본문, `python -c "…rm -rf /…"`, `git push -q origin --delete feat/x; git log -1 --format=%h`, 세션 생성 파일 `rm -f src/probe.ts`, 프로젝트 안 절대경로의 ignore 산출물, `rmdir`, `git clean -n`, `--force-with-lease`, 파일 대상 `dd`, `xargs -0 git rm --cached`(xargs 뒤가 rm 이 아니라 git rm), 컨테이너 안 `/etc` 수정, `2>/dev/null`, 임시 폴더에 세션이 만든 git clone 의 `rm -rf`, 2,000개 넘는 세션 임시 폴더 삭제 | 전부 allow |
| 누락 (`fixtures/false_negative.json`) | 부록 B 의 정직한 실수 형태 전부(난독화 제외) | 전부 deny |
| PR 흐름 시나리오 | worktree add → 파일 생성·커밋 → 추적 파일 `mv` 이름 변경·커밋 → 그 파일 덮어쓰기·커밋 → push -u → rebase 후 `push --force` → `worktree remove` → `branch -D` → `push --delete` | 전부 allow |
| 자기 변경 되돌리기 | 세션 중 추적 파일 수정 후 `git checkout -- f`·`reset --hard` | allow. 세션 전부터 수정돼 있던 파일(장부 pre-dirty) 포함 시 deny(그 파일에 `>>` 로 덧붙인 뒤에도) |
| Docker | 실제 Docker 로 로컬 이미지 컨테이너·볼륨을 만들어: 마운트 안 된 경로 `rm -rf /var/lib/x` allow, 바인드 마운트된 프로젝트 경로 삭제 deny, 이름 볼륨(세션 전) 삭제 deny. Docker 가 없거나 `sh -c 'sleep'` 이 도는 로컬 이미지가 없으면 그 테스트는 skip 하고 사유를 출력(대역 금지, D13) | 기대 판정 |
| 출력 계약 | `on` 모드 새 판정기 출력이 모든 사례에서 유효 JSON, `ask` 없음, 종료 0. off·shadow 는 현행과 바이트 동일 | — |
| 전수 재생 (로컬, 수동) | `replay_corpus.py` 로 실제 명령 전부 판정 | 오류 0, p99 ≤ 150ms, 거부 목록 사람 검토 |

픽스처 규칙:

- **공개 저장소이므로 실제 세션 명령 원문을 픽스처·커밋·PR 본문에 넣지 않는다.** 유형을 재현하는 최소 사례를 새로 쓴다.
  경로는 임시 폴더와 가상 이름(`/home/u/proj`)만 쓴다.
- 생성 시각 의존 테스트는 "세션 전 파일 생성 → 20ms 대기 → transcript 생성 → 20ms 대기 → 세션 파일 생성" 순으로
  **양쪽 경계에 대기**를 둔다(커널 시각 해상도가 수 ms 라 연속 생성 파일은 같은 값을 받는다).
- 테스트 세계는 임시 루트도 git 저장소도 아닌 tmpfs(`$XDG_RUNTIME_DIR`, 없으면 `/dev/shm` — 생성 시각 지원 실측)에 만들고,
  `TMPDIR=<세계>/scratch` 실제 환경 변수로 세계의 임시 루트를 지정한다(모듈 패치 없음, D13).
- **전수 재생 문맥**: transcript_path·session_id 없이 판정한다(세션 시작 미상 → `SESSION_NEW` 미적용, 보수적).
  장부·기록은 재생 출력 폴더 아래 `XDG_STATE_HOME` 으로 돌려 실제 상태 폴더를 건드리지 않는다. 판정은 **현재 파일 상태** 기준이다.
  SC3 의 거부 검토에서 '대상이 지금 없거나 당시 세션이 만든 것이었을 수 있어 생긴 거부'(세션 문맥 부재 때문)는
  부당 거부로 세지 않고 따로 집계한다.

## 9. Boundaries

- **Always**
  - worktree(`git -C ~/tools/claude-project-config worktree add …`)에서 개발. 운영 clone 은 `main` 고정(directory 소스라
    운영 clone 의 파일이 곧 모든 세션의 실행 코드).
  - 각 작업 커밋 전 그 작업의 테스트·정적 검증 통과. PR 전 §5 전체(전수 재생은 계획 Task 13 결과) 통과.
  - 출력 JSON 은 `json.dumps`, 종료 0, `on` 모드 새 판정기 출력에 `ask` 없음.
  - feature 브랜치의 작업별 커밋은 위임됨(D13). push·PR·병합은 Ask first.
  - 기능 스위치 기본값 `off` 유지.
- **Ask first**
  - `HARNESS_BASH_GUARD` 를 어떤 프로젝트에서든 `shadow`·`on` 으로 켜는 것.
  - 기존 판정 로직(`off` 경로)·`t_auto_approve_rm.py` 삭제.
  - `hooks.json` 의 timeout 변경, 다른 플러그인·`~/.claude/settings.json` 수정.
  - agent·bounty 등 다른 저장소 커밋(§12).
- **Never**
  - 세션 기록·명령 원문·기록 파일을 저장소에 커밋하거나 PR 에 붙이기(공개 저장소).
  - 외부 패키지 의존성 추가.
  - 훅에서 대상 파일을 실제로 지우거나 고치는 동작(판정기는 읽기 전용. find 미리보기도 `-print0` 만).
  - `on` 모드 새 판정기의 `ask` 출력.
  - 테스트 대역(모듈 패치·가짜 실행 파일·주입 데이터) — D13.
  - 운영 clone 에서 직접 수정·브랜치 전환.

## 10. Success Criteria

1. `on` 모드 새 판정기 출력이 모든 테스트 묶음(§8)에서 유효 JSON 이고 `ask` 0건(판정기 내부 예외 폴백 포함. 파이썬 기동 실패만 예외 — §13). off·shadow 출력은 현행과 바이트 동일.
2. 오탐 회귀 묶음 100% allow, 누락 묶음 100% deny, PR 흐름·자기 변경 되돌리기 시나리오 기대대로.
3. 전수 재생: 판정기 내부 오류 0건, 판정 시간 p99 ≤ 150ms, 거부된 명령 목록을 사람이 전부 검토해 부당 거부 0건
   (재생 문맥은 §8 '전수 재생 문맥'. 검토 결과는 로컬에만 기록하고 요약 수치만 PR 에 적는다).
4. `off` 모드에서 기존 테스트(`test-auto-approve-readonly.sh`, `t_auto_approve_rm.py`, `test_code_read_guard.py`) 전부 통과
   — 동작 불변.
5. `shadow` 운용 후(§11) 신·구 불일치 기록을 검토해, 신 판정기 쪽이 틀린 사례 0건이면 `on` 전환.
6. `check-canon.sh` 에 추가한 검사가 현재 죽은 등록 4곳(§12 E1)을 위반으로 보고하고(정리 전), 정리 후 0건.

## 11. Rollout & Rollback

1. 구현·테스트 → PR → 병합 → 운영 clone `git pull --ff-only`(스위치 `off` 라 동작 불변).
2. 사용자 승인 후 **프로젝트별** settings(`<프로젝트>/.claude/settings.json` 의 `env`)에 `HARNESS_BASH_GUARD=shadow`
   1줄 → 최소 3일·Bash 호출 5,000회 이상 수집. 전역(`~/.claude/settings.json`)에는 두지 않는다(사용자 규칙: 모든 폴더에서
   걸리는 동작의 스위치는 프로젝트에 — 2026-10-14 재확인). 대상 목록은 전환 시점에 사용자와 확정한다. 후보(ask 발생 상위):
   money, math, orca 작업공간(브랜치별 settings 파일이 따로 있음), phantomn.github.io, quant, bounty, tools, .agents.
   홈(`~`)에서 연 세션도 스위치를 켠 저장소의 대상을 건드리면 그 저장소 값으로 판정된다(D10). 홈 자체의 파일은 대상 밖.
3. 불일치 검토 → 판정기 수정 반복 → 기준 충족 시 사용자 승인 후 같은 프로젝트들에서 `on`.
4. `on` 2주 무사고 후 사용자 승인으로 기존 로직·`t_auto_approve_rm.py` 제거와 각 프로젝트 settings 의 `HARNESS_RM_REPO_DIRS` 정리(별도 PR — 이번 변경 범위 밖). 이후
   `HARNESS_BASH_GUARD` 가 없는 프로젝트의 기본값을 `on` 으로 바꿀지는 그 PR 에서 결정한다.
- **되돌리기**: 스위치를 `off` 로(코드 되돌림 불필요). 스위치로 해결 안 되는 결함은 PR revert.

## 12. 운영 위생 작업 (이번 변경에 포함)

| 항목 | 조치 |
|---|---|
| E1 죽은 등록 | `${CLAUDE_PLUGIN_ROOT}/hooks/scripts/auto-approve-readonly.sh` 를 등록한 프로젝트 settings 4곳에서 그 항목 제거: `~/agent`, `~/bounty`, `~/orca/workspaces/bounty/bounty-agoda`, `~/orca/workspaces/bounty/bounty-wordpress` 의 `.claude/settings.json`(2026-10-14 전수조사 기준. 각 저장소·브랜치 별도 커밋, Ask first). 근거: 이 변수는 플러그인 hooks.json 에서만 확장되어 91건 전부 "Hook command references ${CLAUDE_PLUGIN_ROOT} but the hook is not associated with a plugin" 오류 |
| E2 게이트 | `~/.claude/check-canon.sh`(git 저장소 아닌 일반 파일 — Ask first)에 검사 함수 추가: `$SCAN_ROOT` 아래 depth 3~6 의 `*/.claude/settings*.json`(**orca 작업공간 포함** — 기존 `projects_for` 는 작업공간을 제외하지만 죽은 등록 오류가 작업공간에서도 났다. `node_modules` 제외, `is_ignored` 존중)에서 `hooks.*[].hooks[].command` 에 `${CLAUDE_PLUGIN_ROOT}` 가 있으면 위반(`BAD` 증가). 자체 시험에 음성·양성 사례 각 1개 |
| 코드 읽기 가드 | 이번 범위에서 호출 방식 유지. 별도 등록 분리는 후속(#42702 의 입력 경합은 실측으로 재현 안 됨 — 분리 시 장애 요인 없음) |
| 문서 | `README.md` 갱신, `DECISIONS.md`(§2)·`LIMITS.md`(§13) 신규 |

## 13. 알려진 한계 (LIMITS.md 로 옮김)

- 간접 실행 내부는 보지 않는다: 스크립트 파일, `python -c`·`node -e`·`perl -e`, `make`, `npm|pnpm|yarn run`,
  내용을 모르는 `… | sh`(`curl | sh`, `base64 -d | sh`). 의도적 난독화는 위협 모델 밖.
- 장부는 Write·Edit·NotebookEdit 와 해석 가능한 제자리 편집만 기록한다. 임의 스크립트가 바꿔치기한 세션 전 파일은
  `SESSION_NEW` 로 오분류될 수 있다. 세션 전부터 수정돼 있던 추적 파일을 스크립트(포매터 등)가 다시 고치면
  "이번 세션 변경"으로 오분류될 수 있다.
- 생성 시각을 못 읽는 파일시스템(`/mnt/c` 9p)은 모두 보호 쪽으로 분류된다(임시 루트 제외).
- `--resume` 으로 새 기록 파일이 생기면 이전 대화에서 만든 파일은 세션 전 파일로 취급된다(보수적).
- 판정 시점과 실행 시점 사이의 파일 상태 변화(TOCTOU)는 다루지 않는다.
- D3(allow 유지)로 인해 auto 모드에서는 분류기 판정이 건너뛰어진다(강한 정황). auto 모드를 쓰게 되면 D3 재검토.
- devcontainer 등 세션 자체가 컨테이너 안에서 도는 경우의 시스템 경로 규칙은 다루지 않는다.
- 훅 자체가 플랫폼 10초 제한에 걸려 취소되면 플랫폼이 판정 없이 실행한다(과부하 시 12건 실측). 내부 5초 마감으로 완화만 한다.
- 동시 세션: 다른 세션이 Bash 로 만든·고친 파일은 장부에 없어 이 세션 것으로 보일 수 있다(D12 의 남는 구멍).
- 스위치가 대상 저장소 기준이라 모든 Bash 호출에서 파이썬 판정이 돈다(약 35ms, 꺼진 곳 포함). 장부 훅도 스위치와 무관하게
  모든 Write·Edit 에서 돈다(약 35ms, D14).
- 스크립트·`make`·`npm run` 안의 `mv` 로 옮긴 유일본은 장부에 `moved-in` 이 없어, 재생성 산출물 폴더·임시 폴더로 옮겨진 뒤 지워지면 막지 못한다.
- `patch`·`git apply` 로 고친 세션 전 수정 파일은 장부에 pre-dirty 가 남지 않아, 이후 `git checkout`·`reset --hard` 가 '이번 세션 변경'으로 허용될 수 있다.
- `on` 모드에서도 파이썬이 뜨지 않으면(입구 폴백) 현행 판정 OLD 가 나가 ask 가 나올 수 있다.
- 세션 저장소(분류 1b)는 이번 세션에 만든 주 작업 트리 전체를, 임시 루트 폴더는 보호 이름이 없으면 전체를 허용한다 — 그 안에 손으로 옮겨 넣은 유일본은 장부 `moved-in` 이 있을 때만 보호된다.

## 14. Reference Oracle

- **현행 동작**: `plugins/harness-core/hooks/scripts/auto-approve-readonly.sh`(main `1e7ee8a` 기준). `off`·`shadow` 의
  기준 판정이며 `off` 에서 바이트 단위로 같은 출력이어야 한다.
- **실사용 분포**: 로컬 `~/.claude/projects/**/*.jsonl`(부록 A 방법으로 재현). 저장소에 넣지 않는다.

## 15. Open Questions

없음. 해소 기록(2026-10-14 사용자 결정):

1. `shadow` 를 켤 위치 → **프로젝트별**(§11-2). 홈에서 연 세션도 스위치를 켠 저장소를 건드리면 그 값으로 수집된다(D10).
2. `on` 후 기존 로직 제거 시점 → **2주 무사고 후**(§11-4) 동의.
3. 스위치 판정 → **대상 저장소 settings 기준**(D10, spec-audit 라운드 1).
4. 동시 세션 → **공유 장부로 부분 반영**(D12).
5. 저장소 규칙 충돌 → **작업별 커밋 위임 + 테스트 대역 최소화**(D13).
6. 장부 기록 → **스위치와 무관하게 항상 기록**(D14, spec-audit 라운드 2).
7. `mv` 세탁 → **목적지를 장부 `moved-in` 으로 보호**(D14).

---

## 부록 A. 측정 방법 (재현용)

- **발화 사례**: 세션 기록에서 `attachment.type=="hook_success"`·`hookEvent=="PreToolUse"`·`hookName=="PreToolUse:Bash"` 레코드의
  `stdout` JSON `hookSpecificOutput.permissionDecision` 을 집계하고, `toolUseID` 로 같은 파일의 `tool_use.input.command` 와 결합.
  오류는 `hook_non_blocking_error`, 취소는 `hook_cancelled` 레코드.
- **사용자 응답**: 같은 `tool_use_id` 의 `tool_result` 에 "doesn't want to proceed" 가 있으면 거절. 471건 중 0건
  (같은 파일들에 거절 문자열 183건 존재 → 탐지 정상).
- **멈춘 시간**: `tool_use` 레코드와 `tool_result` 레코드의 timestamp 차(명령 실행 시간 포함 → 상한 추정).
- **권한 모드**: 메인 세션은 레코드의 `permissionMode`, 서브에이전트(`…/subagents/*.jsonl`, 모드 미기록)는 부모 세션 파일의 최빈 모드로 귀속.
- **원인 절제**: 명령에서 원인 후보 하나(따옴표 내용, 명령 경계, `-f`, 절대→상대경로, 리다이렉트)만 바꿔 현행 훅에 다시 넣고
  ask→allow 로 바뀌면 그 원인으로 확정. 프로젝트별 `HARNESS_RM_REPO_DIRS` 를 넣어야 재현되는 19건 중 18건 재현.
- **해석기 시제품(shlex — 이후 기각, §3.3-1)**: 고유 명령 88,625종(총 91,085회)에 shlex 토큰화 적용 → 실패 32종(0.04%, 모두 heredoc 경계 미검출에 따른
  닫히지 않은 따옴표), 해석 p50 0.11ms·p99 0.5ms·최대 3.4ms.
- **생성 시각 동작**: ext4 에서 `mv` 는 유지, `cp`·임시 파일 바꿔치기·Edit 도구·`sed -i`·`git checkout` 은 갱신. 9p(`/mnt/c`)는 0.
- **훅 입력**: headless `claude -p --permission-mode bypassPermissions --settings <덤프 훅>` 로 메인 Bash·서브에이전트 Bash·Write 입력 덤프.

## 부록 B. 누락 사례 (새 판정기 deny 기대 — 정직한 실수 형태)

감사 실측(2026-10-14) 기준 32종 중 현행 allow 26, 현행 ask 6(`sudo rm -rf ~/data`, `ls ~/data | xargs rm`, `rm -rf ~/.ssh`,
`git push --force origin main`, `dd if=/dev/zero of=/dev/sdb`, `chmod -R 777 ~`).

`HOME` 아래 세션 전 데이터 폴더 `~/data`(가상), 세션 전 추적 파일이 있는 저장소를 전제로:

```
\rm -rf ~/data            command rm -rf ~/data        /bin/rm -rf ~/data          env rm -rf ~/data
sudo rm -rf ~/data        rm -rf "$HOME/data"          x=~/data; rm -rf "$x"       cd ~ && rm -rf data
bash -c 'rm -rf ~/data'   sh -c "rm -rf ~/data"        echo 'rm -rf ~/data' | sh   eval "rm -rf ~/data"
find ~/data -delete       find ~ -name '*.md' -exec rm {} +   ls ~/data | xargs rm
rm -rf ~/.ssh             shred -u ~/data/a.txt        truncate -s0 ~/data/db.sqlite   : > ~/data/important.csv
git push origin +main     git push --force origin main  git clean -xffd(세션 전 미추적 파일 존재)
git checkout .(세션 전 수정 존재)   git restore .(세션 전 수정 존재)   git stash drop(세션 전 보관본)
git reflog expire --expire=now --all    rm src/main.py(추적 파일 — git rm 안내)
docker exec c sh -c 'rm -rf /app'(/app ← 프로젝트 바인드 마운트)   docker volume rm 기존볼륨
dd if=/dev/zero of=/dev/sdb    chmod -R 777 ~             echo x > /etc/hosts
```

(현행에서 deny 였던 `rm -rf ~` 와 ask 였던 `rm -r ~/obsidian`, `rm -R /home/u/quant`, `git reset --hard HEAD~3` 도 포함)

## 부록 C. 오탐 유형별 재구성 사례 (새 판정기 allow 기대)

현행이 ask 또는 deny 를 내는 사례(오탐 재현). heredoc 본문은 줄 맨 앞에 올 때만 현행이 발화한다(따옴표 안이면 현행도 allow — 2026-10-14 실측):

```
jq -n --arg c "git reset --hard" '{c:$c}'        cat > notes.md <<'EOF'(본문 줄이 'rm -rf ~ …' 로 시작) EOF
git push -q origin --delete feat/x; git log -1 --format=%h
rm -f src/probe.ts(세션 생성)                     rm -rf /home/u/proj/.next(재생성 산출물, 절대경로)
rmdir empty-dir                                  git clean -fdX(재생성 산출물만)
git push --force-with-lease origin feat/x        dd if=fw.bin of=rootfs.img bs=1 skip=10
xargs -0 git rm --cached                         git checkout -- .serena/project.yml(이번 세션 수정)
docker exec c sh -c 'echo x >> /etc/hosts && rm -rf /var/lib/x'(마운트 아님)
```

현행도 allow 하는 사례(회귀 보호용 — 새 판정기도 allow 를 유지해야 함):

```
echo 'cleanup: rm -rf ~'                         grep -rn 'rm -rf' docs/
rm -rf build 2>/dev/null(없는 폴더)               git clean -n
rm -rf /tmp/claude-1000/<세션>/scratchpad/out     systemctl --user stop svc
```

## 부록 D. 선행 사례 조사 요약 (2026-10-14, Exa)

| 사례 | 판정 방식 | 우리와의 관계 |
|---|---|---|
| cc-safety-net (kenryu42, 별 약 1.6K) https://github.com/kenryu42/claude-code-safety-net | `bash -c`·`python -c` 안쪽까지 검사, 래퍼 기본명 비교, cwd·임시 루트 허용(README·릴리스 노트) | 가장 가까움. 세션 출처·git 추적 판정은 없음. `TMPDIR` 오버라이드로 임시 루트를 벗어나는 경로 순회 우회를 고친 이력(v0.8.0) → §3.4 정규화 4 |
| dcg (Dicklesworthstone) https://github.com/Dicklesworthstone/destructive_command_guard | Rust, 정규식 트리거 → 추출 → tree-sitter/ast-grep AST 매칭으로 heredoc·인라인 스크립트 | 데이터 문맥 통과 개념 일치 |
| Codex CLI https://github.com/openai/codex (`codex-rs/shell-command/src/bash.rs`) | tree-sitter-bash 로 파싱하고 단어만 있는 단순 명령 열(`&&` `\|\|` `;` `\|`)만 안전 판정 대상. 그 밖의 구문·파싱 오류는 결과가 없어 자동 허용 경로에서 빠진다(소스 해석). execpolicy 는 별개의 prefix_rule 엔진 | 해석 실패 정책(§3.8) 근거 |
| Gemini CLI PolicyEngine https://github.com/google-gemini/gemini-cli (`packages/core/src/policy/policy-engine.ts`) | web-tree-sitter(WASM) 파싱, 파싱 실패 시 기본 결정(대화형 ASK_USER, 비대화형 DENY — 소스 해석) | 실패 정책 근거 |
| Cursor (Backslash 보고 https://www.backslash.security/blog/cursor-ai-security-flaw-autorun-denylist , The Register 2025-07-21) | 문자열 denylist → 난독화(base64)·서브셸·스크립트 파일 등 우회 보고(4종 표기는 2차 출처) 뒤 1.3 에서 폐기 발표 | 정규식 방식 기각 근거 |
| Claude Code 샌드박스 https://code.claude.com/docs/en/sandboxing | Linux·WSL2 는 bubblewrap, macOS 는 Seatbelt OS 격리. docker 는 `excludedCommands` 로 빼야 하고 뺀 명령은 전체 권한 | 기각(§2). 이슈: `excludedCommands` 미적용 #95813(macOS 보고), WSL2 마운트 실패 시 `allowUnsandboxedCommands: true` 면 조용히 비격리 실행 #84563 |
| anthropics/claude-code#101339 | bypassPermissions 에서 백그라운드 서브에이전트가 복합 Bash 명령의 권한 확인 창에서 멈춤(종료됨) | D2(ask 금지)·§1 무인 실행 멈춤의 외부 사례 |
| 파서 비교 | 조사는 shlex 유지 권고(bashlex GPL·정체, tree-sitter 별도 휠, mvdan/sh Go). 계획 단계 실측으로 shlex 결함 확인 → 자체 어휘 분석기 | D9 |
| "세션이 만든 파일만 삭제 허용" | **선행 도구 없음** | 이 설계의 새 부분 → 테스트 비중 큼 |
