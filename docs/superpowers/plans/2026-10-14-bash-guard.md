# bash-guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** harness-core 의 Bash PreToolUse 판정을 "명령 글자 정규식"에서 "셸 구조 해석 + 대상 성질(출처·복구 가능성)
판정"으로 바꿔, 되돌릴 수 없는 손실만 거부하고 그 외에는 개입하지 않게 한다(`on` 모드 출력에 ask 0).

**Architecture:** 입구 `auto-approve-readonly.sh` 는 기존 로직으로 현행 판정 OLD 를 만든 뒤 `bash_guard.py --old "$OLD"` 에 넘긴다.
`bash_guard.py` 는 자체 어휘 분석기(`shell_parse.py`)로 명령 단위를 만들고, 대상 경로를 git·생성 시각·공유 장부·Docker 마운트로
분류(`target_class.py`)한 뒤 작업 × 분류 정책표(`policy.py`)로 새 판정을 낸다. 모드(off/shadow/on)는 세션 env·cwd·대상 경로가 속한
저장소 settings 중 가장 강한 값이며, `on` 이면 새 판정을, 아니면 OLD 를 그대로 출력한다. Write·Edit 직전 장부 훅(`touch-ledger.py`, 스위치와 무관하게 항상)이 세션 전 파일·다른 세션의 생성·수정을 공유 장부에
기록하고, 판정기는 `mv` 로 옮겨진 보호 대상의 목적지를 `moved-in` 으로 기록한다(spec D14).

**Tech Stack:** Python 3.10+ 호환(실행 3.12.3) 표준 라이브러리만, `unittest`, POSIX sh/bash, git, GNU stat 9.4, docker(있으면).

**Spec:** `docs/superpowers/specs/2026-10-14-bash-guard-design.md` — 모든 정책 값의 정본. 계획과 spec 이 다르면 spec 이 이긴다.
구현 중 spec 이 틀렸다고 판단되면 구현을 멈추고 spec 부터 고친다.

## Global Constraints

- 작업 위치: worktree `~/tools/claude-project-config.wt`, 브랜치 `feat/bash-guard`. 운영 clone(`~/tools/claude-project-config`)은
  절대 수정·브랜치 전환하지 않는다(directory 소스라 그 파일이 곧 모든 세션의 실행 코드).
- Python: `from __future__ import annotations`, 3.10 호환 문법, 표준 라이브러리만, `dataclass`·타입 힌트. `shlex` 사용 금지(spec §3.3-1).
- 출력: `json.dumps` 로만 만든 한 줄 JSON, 종료 코드 0. **`on` 모드 새 판정기 출력의 `permissionDecision` 은 `"allow"`·`"deny"` 뿐.**
  `off`·`shadow` 는 OLD 를 바이트 그대로(OLD 가 비면 출력 없음).
- 거부 사유 형식(spec §3.2): 줄마다 `거부: <작업> <대상> — <분류 설명>. 대안: <대안>`, 첫 줄 앞에 `[bash-guard] `, 마지막 줄
  `이 판정을 우회하지 말 것. 대안이 맞지 않으면 작업을 멈추고 사용자에게 보고하라.`
- 판정기는 읽기 전용. 쓰는 곳은 상태 폴더 `${XDG_STATE_HOME:-$HOME/.local/state}/harness-core/` 아래 `bash-guard.jsonl`(10MB 초과 시
  `.1` 로 한 번 순환)과 공유 장부 `ledger.tsv`(5MB 초과 시 `flock` 후 7일 지난 줄 제거)뿐.
- 시간: 판정기 내부 마감 `BUDGET_SECONDS = 5.0`, 외부 명령마다 `timeout=min(2.0, 남은 시간)`. `hooks.json` Bash timeout 10 유지, touch-ledger timeout 5.
- 폴더 순회 상한 `DIR_ENTRY_CAP = 2000`. 생성 시각은 `stat -c '%.9W %n'`(값 0 = 읽을 수 없음).
- `REGENERABLE_NAMES` = `node_modules dist build .next .nuxt target __pycache__ .pytest_cache .ruff_cache .mypy_cache .tox .venv venv coverage
  .coverage .gradle .parcel-cache .turbo .cache`, 재생성 확장자 `.pyc .pyo .o .class`(spec §3.4).
- 스위치 `HARNESS_BASH_GUARD` 값 `off`(기본)·`shadow`·`on`, 그 외 → `off`. 경로의 저장소 값 = 위로 올라가 처음 만나는 `.git` 을 가진 폴더 R
  (R 이 `$HOME`·`/` 이면 없음)의 `.claude/settings.local.json` → `.claude/settings.json` `env` 값. 명령 모드 = {세션 env, cwd 저장소 값,
  판정 대상 작업의 대상 경로들의 저장소 값} 중 가장 강한 것(spec §3.9).
- **공개 저장소**: 실제 세션 명령 원문·세션 기록·상태 폴더 파일을 픽스처·커밋·PR 에 넣지 않는다. 픽스처 경로는 테스트가 만든 세계의
  자리표시자(`{HOME}` `{REPO}` `{SCRATCH}` `{OUT}` `{WT}`)만 쓴다.
- 테스트: `unittest`, 파일 단독 실행(`python3 <파일>`), 개별 실행 `python3 <파일> -k <이름>`. **대역 금지(spec D13)**: 모듈 패치·가짜
  실행 파일·주입 데이터 없이, 인자(`budget`, `max_bytes`)와 실제 환경(실제 git·docker, `PYTHONHOME=/nonexistent` 로 파이썬 기동 실패,
  `DOCKER_HOST=unix:///nonexistent.sock` 로 docker 데몬 부재)으로 검증. Docker 가 없거나 `sh -c 'sleep 300'` 이 도는 로컬 이미지가
  없으면 해당 테스트는 `skipTest("<사유>")`. 테스트 세계는 `$XDG_RUNTIME_DIR`(없으면 `/dev/shm`) 아래 tmpfs 에 만들고(임시 루트도
  git 저장소도 아님), `HOME`·`TMPDIR=<세계>/scratch`·`XDG_STATE_HOME` 을 세계 값으로 덮은 `environ` 을 넘긴다. 실제 홈·상태 폴더를 건드리지 않는다.
- 커밋: 사용자가 이 계획 실행 중 feature 브랜치의 작업별 커밋을 위임했다(spec D13 — 저장소 규칙 '자동 커밋 금지'의 사용자 결정 예외).
  경로 지정 커밋 `git commit -m "<msg>" -- <Files>`, 메시지 끝에 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. push·PR 은 위임 밖.
- 각 작업 커밋 전 공통 검증: 그 작업 테스트 파일 통과, `python3 -m py_compile <바뀐 .py>`, `ruff check plugins/harness-core/hooks`,
  바뀐 .sh 는 `shellcheck`. PR 전에는 spec §5 전체.

## Review Focus

spec 이 요구하지만 기본 테스트가 직접 겨누지 않아 사용자를 가장 먼저 물 가능성이 큰 입력 다섯 가지. 각 줄의 테스트는 담당 작업에 들어 있다.

1. **거대한 명령**(수백 KB heredoc 으로 파이썬 스크립트를 넘기는 흔한 형태) — 어휘 분석이 선형이라 200KB 도 50ms 안. → Task 1 `test_large_heredoc_is_linear`
2. **공백·한글이 든 경로**(`rm -f "보고서 초안.md"`) — 세션 생성이면 허용, 세션 전이면 거부. → Task 5 `test_unicode_space_path`
3. **원격 HEAD 가 없는 저장소·원격 없는 저장소**의 push — 기본 브랜치를 `main`·`master` 로 대체 판정하고, 원격이 없으면 판정 대상 아님. → Task 8 `test_default_branch_fallback`
4. **서브에이전트·다른 세션이 같은 공유 장부에 동시에 기록** — 줄이 섞이거나 깨지지 않는다. → Task 4 `test_ledger_concurrent_append`
5. **읽을 수 없는 하위 폴더가 있는 폴더 삭제** — 순회 오류는 확정 불가(거부). 순환 심볼릭 링크는 따라가지 않아 순회가 끝난다. → Task 5 `test_unreadable_subdir_is_unresolved`·`test_symlink_loop_terminates`

---

## 파일 구조

| 파일 | 책임 | 작업 |
|---|---|---|
| `plugins/harness-core/hooks/scripts/shell_parse.py` | 어휘 분석·명령 단위 분해·래퍼 제거·cd/변수 추적·단어 확장·재귀·컨테이너 문맥 | 1·2·3 |
| `plugins/harness-core/hooks/scripts/ledger.py` | 공유 장부 저장(읽기·추가·압축) | 4 |
| `plugins/harness-core/hooks/scripts/target_class.py` | 세션 시각·생성 시각·정규화·스위치 값·7분류·작업 영역·git·find 미리보기·docker 조회·장부 기록 규칙 | 4·5·6 |
| `plugins/harness-core/hooks/scripts/policy.py` | 작업 식별과 작업 × 분류 판정표 → `Finding` | 7·8 |
| `plugins/harness-core/hooks/scripts/bash_guard.py` | 진입점: 입력·조립·모드·실패 정책·시간 예산·출력·기록 | 9 |
| `plugins/harness-core/hooks/scripts/touch-ledger.py` | Write/Edit/NotebookEdit 장부 훅(스위치와 무관하게 항상 기록) | 10 |
| `plugins/harness-core/hooks/hooks.json` | touch-ledger 등록 | 10 |
| `plugins/harness-core/hooks/scripts/auto-approve-readonly.sh` | 입구: 기존 로직을 `old_logic` 함수로 감싸고 OLD → bash_guard | 12 |
| `plugins/harness-core/hooks/tests/_world.py` | 테스트 세계 빌더(파일·저장소·장부·실제 docker 자원) | 4(생성)·6·7·8·11(확장) |
| `plugins/harness-core/hooks/tests/test_shell_parse.py` | 해석기 단위 | 1·2·3 |
| `plugins/harness-core/hooks/tests/test_target_class.py` | 장부·분류·조회 단위 | 4·5·6 |
| `plugins/harness-core/hooks/tests/test_policy.py` | 정책 단위 | 7·8 |
| `plugins/harness-core/hooks/tests/test_bash_guard.py` | 종단·합격 묶음·시나리오 | 9·11 |
| `plugins/harness-core/hooks/tests/fixtures/false_positive.json`, `false_negative.json` | 재구성 사례 | 11 |
| `plugins/harness-core/hooks/tests/test_touch_ledger.py` | 장부 훅 | 10 |
| `plugins/harness-core/hooks/tests/test-bash-guard-entry.sh` | 입구 | 12 |
| `plugins/harness-core/hooks/tests/tools/replay_corpus.py` | 로컬 전수 재생 | 13 |
| `plugins/harness-core/README.md`, `DECISIONS.md`, `LIMITS.md`, `.claude-plugin/plugin.json` | 문서·버전 0.2.0 | 14 |
| `~/.claude/check-canon.sh` (저장소 밖) | 죽은 등록 게이트 | 15 (Ask first) |
| 4개 프로젝트 `.claude/settings.json` (다른 저장소) | 죽은 등록 제거 | 16 (Ask first) |

모듈 import: 테스트·진입점은 `sys.path.insert(0, <scripts 폴더>)` 후 `import shell_parse, target_class, policy, ledger`.
의존 방향 `bash_guard → policy → target_class → ledger`, `policy → shell_parse`, `target_class → shell_parse`(타입만). 순환 금지.

---

### Task 1: 어휘 분석기 (`shell_parse.lex`)

**Files:**
- Create: `plugins/harness-core/hooks/scripts/shell_parse.py`
- Test: `plugins/harness-core/hooks/tests/test_shell_parse.py`

**Interfaces:**
- Produces:
  ```python
  class LexError(ValueError): ...
  @dataclass(frozen=True)
  class Part:
      text: str
      quote: str            # "" | "'" | '"'   ($'…' 와 백슬래시 이스케이프는 quote="'" 리터럴 조각)
  @dataclass(frozen=True)
  class Word:
      parts: tuple[Part, ...]
      def literal(self) -> str: ...      # 조각 text 를 이은 것(따옴표 제거)
      def is_quoted(self) -> bool: ...   # quote != "" 인 조각이 하나라도 있으면 True
  @dataclass(frozen=True)
  class Token:
      kind: str                          # "word" | "op" | "redir"
      word: Word | None = None
      op: str | None = None              # op: ";" "&&" "||" "|" "|&" "&" "\n" "(" ")" ";;"
                                         # redir: ">" ">>" ">|" "&>" "&>>" "<" "<>" ">&" "<&" "<<<" "<<" "<<-"
      fd: int | None = None              # redir 왼쪽 숫자(연산자에 공백 없이 붙어 있을 때만)
      target: Word | None = None         # redir 대상 단어(heredoc 은 구분자 단어)
      body: str | None = None            # heredoc 본문
  def lex(src: str) -> list[Token]: ...  # 실패 시 LexError
  ```

- [ ] **Step 1: 실패하는 테스트 작성** — `class LexTest(unittest.TestCase)`:

```python
def words(toks): return [t.word.literal() for t in toks if t.kind == "word"]
def redirs(toks): return [(t.op, t.fd, t.target.literal() if t.target else None) for t in toks if t.kind == "redir"]

def test_single_vs_double_quote(self):
    t = lex("rm -rf '$HOME' \"$HOME\"")
    self.assertEqual(t[2].word.parts, (Part("$HOME", "'"),)); self.assertEqual(t[3].word.parts, (Part("$HOME", '"'),))
def test_redirect_attached(self):
    t = lex("echo a>b 2>/dev/null")
    self.assertEqual(words(t), ["echo", "a"]); self.assertEqual(redirs(t), [(">", None, "b"), (">", 2, "/dev/null")])
def test_fd_needs_adjacency(self):
    t = lex("echo 2 >x"); self.assertEqual(words(t), ["echo", "2"]); self.assertEqual(redirs(t), [(">", None, "x")])
def test_fd_dup_is_not_separator(self):
    t = lex("echo a 2>&1 >out")
    self.assertNotIn("&", [x.op for x in t if x.kind == "op"]); self.assertEqual(redirs(t), [(">&", 2, "1"), (">", None, "out")])
def test_operators(self):
    self.assertEqual([x.op for x in lex("a && b || c; d | e |& f & g") if x.kind == "op"], ["&&", "||", ";", "|", "|&", "&"])
def test_comment(self): self.assertEqual(words(lex("echo x # rm -rf ~")), ["echo", "x"])
def test_substitution_stays_in_word(self):
    self.assertEqual(words(lex('echo "$(rm -rf "a b")" `ls`')), ["echo", '$(rm -rf "a b")', "`ls`"])
def test_heredoc_body(self):
    t = lex("cat <<'EOF' > f\nrm -rf ~\nEOF\necho done")
    hd = [x for x in t if x.kind == "redir" and x.op == "<<"][0]
    self.assertEqual(hd.body, "rm -rf ~"); self.assertTrue(hd.target.is_quoted()); self.assertEqual(words(t), ["cat", "echo", "done"])
def test_heredoc_dash_strips_tabs(self):
    self.assertEqual([x.body for x in lex("cat <<-EOF\n\tx\n\tEOF\n") if x.kind == "redir"], ["\tx"])
def test_unterminated(self):
    for s in ['echo "a', "echo 'a", "echo $(a", "cat <<EOF\nx\n"]:
        with self.assertRaises(LexError): lex(s)
def test_large_heredoc_is_linear(self):           # Review Focus 1
    body = "print('rm -rf /')\n" * 12000
    t0 = time.perf_counter(); lex("python3 - <<'PY'\n" + body + "PY\n"); self.assertLess(time.perf_counter() - t0, 0.05)
```

- [ ] **Step 2: 실패 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_shell_parse.py` · Expected: `ModuleNotFoundError: No module named 'shell_parse'`
- [ ] **Step 3: `lex(src: str) -> list[Token]` 구현** — 인덱스 하나로 한 번 훑는 상태 기계. 단어 안 `$(`·`${`·`$((`·백틱은 깊이 카운터와
  따옴표 상태를 유지하며 닫힐 때까지 같은 조각에 담는다. heredoc 은 `<<` 를 만나면 (구분자, 따옴표 여부, `-` 여부)를 대기 목록에 넣고,
  다음 `\n` 을 지날 때 대기 순서대로 본문 줄을 소비한다. fd 숫자는 직전 단어가 숫자만이고 연산자와 사이에 공백이 없을 때만 fd 로 옮긴다.
- [ ] **Step 4: 통과 확인** — 같은 명령 · Expected: `OK`
- [ ] **Step 5: 커밋(위임 승인 D13)** — `feat(harness-core): bash-guard 어휘 분석기 — 따옴표 종류·리다이렉트·heredoc 보존`

### Task 2: 명령 단위 분해 (`shell_parse.parse` 1부)

**Files:**
- Modify: `plugins/harness-core/hooks/scripts/shell_parse.py`
- Test: `plugins/harness-core/hooks/tests/test_shell_parse.py`

**Interfaces:**
- Consumes: Task 1 `lex`, `Word`, `Token`, `LexError`
- Produces:
  ```python
  @dataclass(frozen=True)
  class Mount:
      source: str           # bind: 호스트 절대경로 / volume: 볼륨 이름
      destination: str      # 컨테이너 안 절대경로
      kind: str             # "bind" | "volume"
  @dataclass(frozen=True)
  class Context:
      kind: str = "host"                       # "host" | "container"
      container: str | None = None             # 컨테이너 이름·ID 또는 compose 서비스 이름
      launcher: str | None = None              # "exec" | "run" | "compose-exec" | "compose-run"
      mounts: tuple[Mount, ...] | None = None  # run 계열: 인자에서 정적으로 / exec 계열: None(Task 6 조회)
      project_dir: str | None = None           # compose 계열: 호스트 cwd
      project: str | None = None               # compose 계열: -p/--project-name 값
  HOST = Context()
  @dataclass
  class Redirect:
      op: str; fd: int | None; target: Word | None; body: str | None
  @dataclass
  class Segment:
      name: str
      argv: list[Word]
      redirects: list[Redirect]
      cwd: str | None
      env: dict[str, str | None]
      context: Context = HOST
      depth: int = 0
      via_xargs: bool = False
  @dataclass
  class ParseResult:
      segments: list[Segment]
      error: str | None = None
  def parse(command: str, cwd: str | None, env: Mapping[str, str], context: Context = HOST) -> ParseResult: ...
  ```
  단위 `env` 초기값 = 호출자 env 의 `HOME`·`TMPDIR`·`USER` 와 `PWD`(= cwd).

- [ ] **Step 1: 실패하는 테스트 작성** — `class ParseTest`:

```python
def segs(cmd, cwd="/w", env={"HOME": "/h"}): return parse(cmd, cwd, env).segments
def names(cmd): return [s.name for s in segs(cmd)]

def test_split_and_cd_tracking(self):
    self.assertEqual([(x.name, x.cwd) for x in segs("cd /a && rm x; cd b; rm y") if x.name == "rm"], [("rm", "/a"), ("rm", "/a/b")])
def test_subshell_restores(self):
    self.assertEqual([x.cwd for x in segs("(cd /a; rm x); rm y") if x.name == "rm"], ["/a", "/w"])
def test_cd_unknown(self):
    self.assertIsNone([x for x in segs("cd -; rm y") if x.name == "rm"][0].cwd)
    self.assertEqual([x for x in segs("cd; rm y") if x.name == "rm"][0].cwd, "/h")
def test_assignments_recorded(self):
    rm = segs('X=/a; export Y=/b; declare -x Z=$(date); rm "$X"')[-1]
    self.assertEqual(rm.env["X"], "/a"); self.assertEqual(rm.env["Y"], "/b"); self.assertIsNone(rm.env["Z"])
def test_wrappers_stripped(self):
    for c in [r"\rm -rf x", "/bin/rm -rf x", "sudo -u root rm -rf x", "env -i A=1 rm -rf x", "command rm x", "timeout 5 rm x",
              "nice -n 5 rm x", "nohup rm x", "time -p rm x", "stdbuf -oL rm x", "flock /tmp/l rm x", "doas rm x", "exec rm x",
              "builtin rm x", "ionice -c3 rm x", "chronic rm x"]:
        self.assertEqual(names(c), ["rm"], c)
def test_git_dash_c(self):
    s = segs("git -C /r reset --hard")[0]
    self.assertEqual((s.name, s.cwd, [w.literal() for w in s.argv]), ("git", "/r", ["git", "reset", "--hard"]))
def test_redirects_removed_from_argv(self):
    s = segs("rm -rf build 2>/dev/null")[0]
    self.assertEqual([w.literal() for w in s.argv], ["rm", "-rf", "build"]); self.assertEqual(s.redirects[0].fd, 2)
def test_parse_error_reported(self): self.assertIsNotNone(parse('rm -rf "x', "/w", {}).error)
```

- [ ] **Step 2: 실패 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_shell_parse.py -k ParseTest` · Expected: `ImportError`/`AttributeError: parse`
- [ ] **Step 3: `parse(...)` 구현(재귀·확장·컨테이너 제외)** — 토큰을 연산자로 끊어 단위를 만들고 `(` 진입 시 (cwd, env) 를 쌓았다가 `)` 에서
  복원. `NAME=값` 만 있는 단위는 env 갱신(이 작업에서는 값을 리터럴로 저장하되 `$(`·백틱이 있으면 None — Task 3 에서 `expand` 로 교체),
  `export|declare|typeset|local` 은 옵션 무시하고 `NAME=값` 반영. `cd`/`pushd` 인자는 `~`·`$HOME` 만 풀고 그 외 변수·치환이면 cwd=None
  (Task 3 에서 `expand` 로 교체). `popd`·`cd -` → None. 래퍼 표(spec §3.3-6): `sudo`(값 옵션 `-u -g -h -p -C -D -r -t -U`),
  `env`(`-i` `-u X` `-C X` `NAME=val`), `timeout`(옵션 `-s X -k X` + DURATION), `nice`(`-n N`), `ionice`(`-c X -n X -p X`),
  `stdbuf`(`-i/-o/-e X`), `flock`(옵션 + 파일), `time`(`-p`), 나머지(`doas command builtin exec nohup chronic`)는 단어 하나.
  `git` 은 `-C DIR`(여러 번 가능)을 cwd 에 반영하고 argv 에서 뺀다.
- [ ] **Step 4: 통과 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_shell_parse.py` · Expected: `OK`
- [ ] **Step 5: 커밋(위임 승인 D13)** — `feat(harness-core): bash-guard 명령 단위 분해 — cd·변수·래퍼 추적`

### Task 3: 단어 확장·재귀·컨테이너 문맥 (`shell_parse` 2부)

**Files:**
- Modify: `plugins/harness-core/hooks/scripts/shell_parse.py`
- Test: `plugins/harness-core/hooks/tests/test_shell_parse.py`

**Interfaces:**
- Consumes: Task 2 `parse`, `Segment`, `Context`, `Mount`
- Produces:
  ```python
  SHELLS = {"bash", "sh", "zsh", "dash"}
  def expand(word: Word, seg: Segment) -> list[str] | None: ...   # None = 확정 불가. 결과는 절대경로(상대는 seg.cwd 기준, cwd None → None)
  def literal_args(seg: Segment) -> list[str]: ...                # 옵션 판별용: 따옴표 제거·확장 없는 리터럴 인자(argv[1:])
  ```
  재귀로 만든 안쪽 단위는 같은 `segments` 목록의 바깥 단위 바로 뒤에 `depth+1` 로 들어간다.

- [ ] **Step 1: 실패하는 테스트 작성** — `class ExpandTest`, `class RecursionTest`, `class ContainerTest`:

```python
def ex(word_src, cwd="/w", env={"HOME": "/h"}):
    s = parse("x " + word_src, cwd, env).segments[0]; return expand(s.argv[1], s)
def test_expand_basic(self):
    self.assertEqual(ex("~/x"), ["/h/x"]); self.assertEqual(ex('"$HOME/x"'), ["/h/x"]); self.assertEqual(ex("'$HOME'"), ["/w/$HOME"])
    self.assertEqual(ex("$(pwd)/x"), ["/w/x"]); self.assertEqual(ex("`pwd`/x"), ["/w/x"]); self.assertEqual(ex("$PWD/x"), ["/w/x"])
    self.assertEqual(ex("{a,b}.txt"), ["/w/a.txt", "/w/b.txt"]); self.assertEqual(ex("a/../b"), ["/w/a/../b"])
def test_expand_unresolved(self):
    for w in ["$(date)", "${X:-a}", "$NOPE/x", "~bob/x", "`hostname`"]: self.assertIsNone(ex(w), w)
    self.assertIsNone(ex("rel", cwd=None))
def test_assignment_value_expanded(self):
    s = parse('x=~/d; y=$HOME/e; rm -rf "$x" "$y"', "/w", {"HOME": "/h"}).segments[-1]
    self.assertEqual([expand(w, s) for w in s.argv[2:]], [["/h/d"], ["/h/e"]])
def test_glob(self):  # 임시 폴더 d 에 a1.log a2.log
    self.assertEqual(ex("*.log", cwd=d), [f"{d}/a1.log", f"{d}/a2.log"]); self.assertEqual(ex("*.none", cwd=d), [f"{d}/*.none"])
    self.assertEqual(ex('"*.log"', cwd=d), [f"{d}/*.log"])

def inner(cmd): return [(s.name, s.depth, s.cwd) for s in parse(cmd, "/w", {"HOME": "/h"}).segments if s.depth > 0]
def test_recursion(self):
    self.assertEqual(inner("bash -lc 'cd /a; rm -rf x'"), [("cd", 1, "/w"), ("rm", 1, "/a")])
    self.assertEqual(inner('eval "rm -rf x"'), [("rm", 1, "/w")]); self.assertEqual(inner("sh <<EOF\nrm -rf x\nEOF"), [("rm", 1, "/w")])
    self.assertEqual(inner("echo 'rm -rf x' | sh"), [("rm", 1, "/w")]); self.assertEqual(inner("printf 'rm -rf x\\n' | bash"), [("rm", 1, "/w")])
    self.assertEqual(inner("echo $(rm -rf x)"), [("rm", 1, "/w")]); self.assertEqual(inner("curl -s u | sh"), [])
    self.assertEqual(inner("python3 -c 'import os'"), [])
def test_xargs(self):
    self.assertEqual([x.name for x in parse("ls | xargs -0 rm -f", "/w", {}).segments if x.via_xargs], ["rm"])

def ctx_of(cmd): return [s for s in parse(cmd, "/w", {"HOME": "/h"}).segments if s.context.kind == "container"]
def test_docker_exec(self):
    s = ctx_of("docker exec -u root c sh -c 'rm -rf /etc/x'")
    self.assertEqual([(x.name, x.context.container, x.context.launcher, x.context.mounts) for x in s], [("rm", "c", "exec", None)])
def test_docker_run_static_mounts(self):
    s = ctx_of('docker run --rm -v "$(pwd)":/app -v data:/var/lib --mount type=bind,source=/s,target=/t img sh -c "rm -rf /app/x"')
    self.assertEqual(s[0].context.mounts, (Mount("/w", "/app", "bind"), Mount("data", "/var/lib", "volume"), Mount("/s", "/t", "bind")))
def test_workdir_and_compose(self):
    self.assertEqual(ctx_of("docker exec -w /app c rm -rf x")[0].cwd, "/app")
    s = ctx_of("docker compose -p proj exec web rm -rf /x")[0]
    self.assertEqual((s.context.launcher, s.context.container, s.context.project_dir, s.context.project), ("compose-exec", "web", "/w", "proj"))
    self.assertEqual(ctx_of("docker-compose exec web rm -rf /x")[0].context.launcher, "compose-exec")
    self.assertEqual(ctx_of("podman exec c rm -rf /x")[0].context.launcher, "exec")
```

- [ ] **Step 2: 실패 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_shell_parse.py` · Expected: FAIL(`expand` 없음 등)
- [ ] **Step 3: 구현** — `expand`: 따옴표 없는 첫 조각의 `~`/`~/` → `HOME`(`~user` → None); 따옴표 없음·`"` 조각의 `$NAME`/`${NAME}` →
  `seg.env`(없거나 None → 전체 None), `$PWD`·`$(pwd)`·`` `pwd` `` → `seg.cwd`, 그 외 `$(`·백틱·`${…연산자…}`·`$((` → None; 따옴표 없는
  조각의 `{a,b}`(쉼표 있고 중첩 없음) 전개; `*?[` 는 `glob.glob`(점 파일은 패턴이 `.` 로 시작할 때만) 정렬 결과, 일치 없으면 리터럴;
  상대경로 → `os.path.join(seg.cwd, …)`(정규화는 Task 4). 할당 값 저장과 `cd` 인자를 `expand` 로 교체(spec §3.3-4: 확장할 수 없으면 None).
  재귀(spec §3.3-7): `-c` 는 `-[a-zA-Z]*c` 옵션 묶음 다음 단어, 셸의 heredoc 본문, 파이프 앞 단위가 `echo`·`printf`(인자 전부 확장 가능한
  리터럴; `printf` 는 `\n` 만 줄바꿈)·`cat`+heredoc 이면 그 텍스트, `eval` 은 인자를 공백으로 이은 문자열, 명령 치환은 단어 조각 안의
  `$(…)`·백틱 내용. docker/podman/docker-compose: 전역 옵션(`-H X`, `--context X`, `-c X`, `--log-level X`) 건너뛰고 `exec|run|compose exec|
  compose run` 처리 — 값 옵션: exec `-e --env --env-file -u --user -w --workdir --detach-keys`, run 위 + `-v --volume --mount --name -p
  --publish --network --entrypoint -l --label --platform --hostname -h --add-host --device --cpus -m --memory`, compose 전역 `-f --file -p
  --project-name --project-directory --env-file --profile`, compose exec/run `-e -u -w --index`. `--opt=값` 은 값 내장, 그 외 `-` 로 시작하면
  값 없는 플래그. `-v SRC:DST[:mode]` 의 SRC 가 `/`·`.`·`~`·`$` 로 시작하면 bind(확장한 절대경로), 아니면 volume. 컨테이너 안 명령이 셸
  `-c` 면 재귀, 아니면 그 argv 자체를 `context=container` 단위로(`-w` 는 그 단위 cwd).
- [ ] **Step 4: 통과 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_shell_parse.py` · Expected: `OK`
- [ ] **Step 5: 커밋(위임 승인 D13)** — `feat(harness-core): bash-guard 단어 확장·재귀 해석·컨테이너 문맥`

### Task 4: 공유 장부·세션 시각·정규화·스위치 값 (`ledger.py`, `target_class.py` 1부)

**Files:**
- Create: `plugins/harness-core/hooks/scripts/ledger.py`, `plugins/harness-core/hooks/scripts/target_class.py`, `plugins/harness-core/hooks/tests/_world.py`
- Test: `plugins/harness-core/hooks/tests/test_target_class.py`

**Interfaces:**
- Produces (`ledger.py`):
  ```python
  KIND_PRE_SESSION = "pre-session"; KIND_PRE_DIRTY = "pre-dirty"; KIND_CREATED = "created"; KIND_TOUCHED = "touched"
  KIND_MOVED_IN = "moved-in"
  PRUNE_SECONDS = 7 * 24 * 3600; COMPACT_BYTES = 5 * 1024 * 1024
  @dataclass(frozen=True)
  class Entry:
      kind: str; session_id: str; ts: float
  def state_dir(environ: Mapping[str, str]) -> Path: ...    # ${XDG_STATE_HOME:-$HOME/.local/state}/harness-core
  class Ledger:
      def __init__(self, environ: Mapping[str, str]) -> None: ...
      def entries(self, path: str) -> list[Entry]: ...
      def moved_in_near(self, path: str) -> str | None: ...   # path 자신·상위·하위(접두 일치) 경로 중 moved-in 기록이 있는 첫 경로
      def record(self, path: str, kind: str, session_id: str | None) -> None: ...
          # session_id None → 아무것도 안 함. (경로, kind, 세션) 중복은 무시(touched 는 매번). 한 줄 = os.write 1회(O_APPEND).
          # 쓰기 전 파일이 COMPACT_BYTES 초과면 fcntl.flock 후 PRUNE_SECONDS 지난 줄을 뺀 내용으로 다시 쓴다.
  ```
- Produces (`target_class.py` 1부):
  ```python
  @dataclass
  class Ctx:
      environ: Mapping[str, str]
      session_id: str | None
      session_start: float | None
      ledger: Ledger
      deadline: float                    # time.monotonic() 기준
      def remaining(self) -> float: ...
  FIXED_SCRATCH_ROOTS: tuple[str, ...] = ("/tmp", "/var/tmp")
  WIN_TEMP_PATTERN = "/mnt/c/Users/*/AppData/Local/Temp"
  def make_ctx(payload: dict, environ: Mapping[str, str], budget: float) -> Ctx: ...
  def session_start(transcript_path: str | None, environ: Mapping[str, str]) -> float | None: ...
  def births(paths: list[str], ctx: Ctx) -> dict[str, float]: ...   # 값 0·실패는 키 없음
  def run(cmd: list[str], ctx: Ctx, cwd: str | None = None) -> subprocess.CompletedProcess | None: ...
      # 남은 시간 ≤ 0 → 실행 안 하고 None. timeout=min(2.0, 남은 시간). env=ctx.environ. 예외·타임아웃 → None
  def normalize(path: str, trailing_slash: bool) -> str: ...
  def scratch_roots(ctx: Ctx) -> list[str]: ...
  def is_scratch(path: str, ctx: Ctx) -> bool: ...       # 루트 '아래'만 True. WIN_TEMP_PATTERN 은 fnmatch 접두 일치(실재 무관)
  def is_scratch_root(path: str, ctx: Ctx) -> bool: ...
  def protected_name(path: str) -> bool: ...
  def repo_root(path: str, environ: Mapping[str, str]) -> str | None: ...   # 위로 첫 .git 보유 폴더. $HOME·/ → None
  def switch_mode(path: str | None, environ: Mapping[str, str]) -> str: ...  # 저장소 settings(local 우선) env 값 → "off"|"shadow"|"on"
  MODE_RANK = {"off": 0, "shadow": 1, "on": 2}
  ```
- Produces (`tests/_world.py`): `class World` — 임시 폴더 아래 세계를 만든다.
  - 구성: `home/`(세계 홈), `home/proj`(git 저장소, 세계 안 bare 저장소를 `origin` 으로, `origin/HEAD → main`), `scratch/`(세계 임시 루트),
    `out/`(저장소 밖·임시 루트 밖 작업 폴더).
  - 생성 순서: 세션 전 파일 → 20ms → `transcript.jsonl`(세션 시작) → 20ms → 세션 파일.
  - 세션 전: `home/data/a.txt`·`home/data/db.sqlite`·`home/data/important.csv`·`home/notes.md`·`home/.ssh/id_ed25519`, 저장소
    `src/main.py`(추적)·`README.md`(추적, 커밋 뒤 수정해 둠 = 세션 전 수정)·`.gitignore`(`build/`, `.env`, `*.sqlite`)·`build/out.o`(재생성 산출물)·
    `local.sqlite`(ignore 대상, 재생성 이름 아님)·`notes_presession.txt`(미추적)·`.env`(`.gitignore` 대상), 세션 전 `stash@{1}`.
  - 세션 파일: `home/proj/src/probe.ts`, `home/proj/out/`, `scratch/s1/x.txt`, 세션 중 `stash@{0}`.
  - 위치: `$XDG_RUNTIME_DIR`(없으면 `/dev/shm`) 아래 `tempfile.mkdtemp` — 임시 루트도 git 저장소도 아닌 tmpfs(생성 시각 지원 실측
    2026-10-14). `close()` 에서 지운다.
  - `environ`: HOME=세계 홈, TMPDIR=`<세계>/scratch`(그래서 `{SCRATCH}` 가 실제 환경 변수로 임시 루트), XDG_STATE_HOME=세계 상태 폴더,
    PATH=실제 PATH, GIT 작성자 값.
  - `World(docker=False)`: `True` 이고 docker 를 쓸 수 있으면 transcript **전에** 실제 docker 자원을 만든다(Task 6 이 채움). 결과는 `w.docker`(없으면 None).
  - 메서드: `fmt(s)`(자리표시자 `{HOME}` `{REPO}` `{SCRATCH}` `{OUT}` `{WT}` 치환), `payload(command, cwd="{REPO}", session_id=None)`,
    `edit_payload(path, tool="Edit")`, `ctx(budget=5.0, transcript=<기본>, session_id=<기본>, environ_extra=None)`(environ_extra = environ 에 덮어쓸 값), `sh(cmd, cwd="{REPO}")`(실제 실행),
    `clean_tree()`, `dirty_before_session(path)`(내용 변경 후 mtime 을 세션 시작 60초 전으로), `touch_modify(path)`(세션 중 내용 변경),
    `checkout(branch, upstream=None)`, `drop_origin_head()`, `remove_remote(name)`, `make_worktree()`(`{WT}` = `out/wt`, 브랜치 `wt-b`),
    `local_branch(name, pushed: bool, before_session: bool)`. 경로 인자는 자리표시자 문자열이며 `fmt` 후 절대경로로 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성** — `class LedgerTest`, `class BasicsTest`, `class SwitchTest`:

```python
def test_ledger_roundtrip_and_dedupe(self):
    L = Ledger(env); L.record("/a b/c", KIND_PRE_SESSION, "s1"); L.record("/a b/c", KIND_PRE_SESSION, "s1")
    self.assertEqual([(e.kind, e.session_id) for e in L.entries("/a b/c")], [(KIND_PRE_SESSION, "s1")])
    L.record("/a b/c", KIND_TOUCHED, "s2"); L.record("/a b/c", KIND_TOUCHED, "s2"); self.assertEqual(len(L.entries("/a b/c")), 3)
    L.record("/x", KIND_CREATED, None); self.assertEqual(L.entries("/x"), [])
def test_ledger_concurrent_append(self):            # Review Focus 4
    # 프로세스 2개가 같은 장부에 서로 다른 경로 500개씩 record → 1000줄, 모든 줄이 탭 4칸이고 경로가 손상 없음
def test_ledger_compaction(self):
    # COMPACT_BYTES 를 넘긴 장부(8일 전 시각 줄 + 최근 줄) 에 record 1회 → 8일 전 줄 사라지고 최근 줄·새 줄 남음
def test_session_start(self):
    self.assertAlmostEqual(session_start(w.transcript, w.environ), stat_birth(w.transcript), places=3)
    self.assertIsNone(session_start(None, w.environ)); self.assertIsNone(session_start("/nope", w.environ))
def test_births_skips_zero(self): self.assertEqual(target_class._parse_stat("0.000000000 /p\n12.5 /q\n"), {"/q": 12.5})
def test_run_respects_deadline(self): self.assertIsNone(run(["true"], w.ctx(budget=0)))
def test_normalize(self):
    self.assertEqual(normalize("/a/b/../c", False), "/a/c")
    # 부모가 심볼릭 링크면 실제 경로로, 대상 자체가 링크면 '/' 없을 때 링크 경로 유지·있을 때 링크 대상
def test_scratch(self):
    ctx = w.ctx()
    self.assertTrue(is_scratch(w.fmt("{SCRATCH}/s1/x.txt"), ctx)); self.assertFalse(is_scratch(w.fmt("{SCRATCH}"), ctx))
    self.assertTrue(is_scratch_root(w.fmt("{SCRATCH}"), ctx)); self.assertTrue(is_scratch(w.fmt("{HOME}/.cache/x"), ctx))
    self.assertTrue(is_scratch("/mnt/c/Users/u/AppData/Local/Temp/x", ctx))      # 패턴 일치(실재 무관)
    self.assertFalse(is_scratch("/mnt/c/Users/u/AppData/Local/Temp", ctx))
def test_protected_name(self):
    for p in ["/r/.git", "/r/.git/config", "/r/.env", "/r/.env.prod", "/r/.claude/settings.local.json", "/r/x.local.yml",
              "/h/.ssh/config", "/h/k.pem", "/h/id_ed25519", "/h/.aws/credentials", "/h/.netrc"]:
        self.assertTrue(protected_name(p), p)
    for p in ["/r/.env.example", "/r/.env.sample", "/r/.env.template", "/r/src/env.py", "/r/.github/x"]:
        self.assertFalse(protected_name(p), p)
def test_switch_mode(self):
    self.assertEqual(switch_mode(w.fmt("{REPO}/src/main.py"), w.environ), "off")
    w.set_repo_switch("shadow"); self.assertEqual(switch_mode(w.fmt("{REPO}/src/main.py"), w.environ), "shadow")
    w.set_repo_switch("on", local=True); self.assertEqual(switch_mode(w.fmt("{REPO}/x"), w.environ), "on")   # local 우선
    self.assertEqual(switch_mode(w.fmt("{HOME}/data/a.txt"), w.environ), "off")                               # 저장소 밖
    self.assertEqual(switch_mode(None, w.environ), "off")
```
  (`set_repo_switch(value, local=False)` 는 저장소 `.claude/settings[.local].json` 의 `env.HARNESS_BASH_GUARD` 를 쓰는 World 메서드 — 이 Step 에서 함께 추가)

- [ ] **Step 2: 실패 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_target_class.py` · Expected: `ModuleNotFoundError`
- [ ] **Step 3: 구현** — `births` 는 한 번의 `stat -c '%.9W %n' -- …`(없는 경로의 오류 줄은 stderr 라 무시), `_parse_stat(stdout) -> dict[str, float]`
  로 파싱(0 제외). 임시 루트 = `FIXED_SCRATCH_ROOTS` + `$TMPDIR`(있으면) + `$HOME/.cache` + `/mnt/c/Windows/Temp`, 그리고 `WIN_TEMP_PATTERN`
  은 `fnmatch(path, WIN_TEMP_PATTERN + "/*")`. `protected_name` 은 spec §3.4 표 2행 그대로. `make_ctx` 는 `payload["transcript_path"]`·
  `payload["session_id"]` 로 `session_start`·`session_id` 를 채우고 `deadline = monotonic() + budget`. `switch_mode`: `repo_root` → `settings.local.json`
  → `settings.json` 순으로 `env.HARNESS_BASH_GUARD` 를 읽어 처음 나온 값(유효하지 않으면 `off`).
- [ ] **Step 4: 통과 확인** — 같은 명령 · Expected: `OK`
- [ ] **Step 5: 커밋(위임 승인 D13)** — `feat(harness-core): bash-guard 공유 장부·세션 시각·정규화·스위치 값`

### Task 5: 대상 7분류·폴더 규칙·작업 영역·장부 기록 규칙 (`target_class` 2부)

**Files:**
- Modify: `plugins/harness-core/hooks/scripts/target_class.py`
- Test: `plugins/harness-core/hooks/tests/test_target_class.py`

**Interfaces:**
- Consumes: Task 4 전부
- Produces:
  ```python
  MISSING, UNRESOLVED, PROTECTED_NAME, GIT_TRACKED, SCRATCH, SESSION_NEW, IGNORED_ARTIFACT, PRESERVED = (
      "MISSING", "UNRESOLVED", "PROTECTED_NAME", "GIT_TRACKED", "SCRATCH", "SESSION_NEW", "IGNORED_ARTIFACT", "PRESERVED")
  DIR_ENTRY_CAP = 2000
  REGENERABLE_NAMES: frozenset[str]   # Global Constraints 값
  REGENERABLE_SUFFIXES = (".pyc", ".pyo", ".o", ".class")
  SEVERITY = {MISSING: 0, SCRATCH: 0, SESSION_NEW: 0, IGNORED_ARTIFACT: 0, GIT_TRACKED: 1, PRESERVED: 2, PROTECTED_NAME: 2, UNRESOLVED: 3}
  @dataclass(frozen=True)
  class Cls:
      kind: str
      path: str | None
      detail: str = ""
      worktree_root: str | None = None     # 대상이 linked worktree 최상위면 그 경로
  def git_toplevel(path: str, ctx: Ctx) -> str | None: ...
  def git_tracked(repo: str, paths: list[str], ctx: Ctx) -> set[str]: ...
  def git_ignored(repo: str, paths: list[str], ctx: Ctx) -> set[str]: ...
  def is_linked_worktree_root(path: str) -> bool: ...
  def classify(path: str | None, ctx: Ctx, trailing_slash: bool = False) -> Cls: ...
  def in_workspace(path: str, ctx: Ctx) -> bool: ...
  def note_touch(path: str, ctx: Ctx, tool: str | None) -> None: ...
      # tool "Write"|"Edit"|"NotebookEdit"(touch-ledger) 또는 None(판정기의 제자리 편집). spec §3.7 기록 규칙
  ```

- [ ] **Step 1: 실패하는 테스트 작성** — `class ClassifyTest`, `class SharedLedgerTest` (World 사용):

```python
def k(p, ctx=None): return classify(w.fmt(p), ctx or w.ctx()).kind
def test_seven_classes(self):
    self.assertEqual(k("{REPO}/nope"), MISSING); self.assertEqual(k("{REPO}/.env"), PROTECTED_NAME)
    self.assertEqual(k("{REPO}/src/main.py"), GIT_TRACKED); self.assertEqual(k("{SCRATCH}/s1/x.txt"), SCRATCH)
    self.assertEqual(k("{REPO}/src/probe.ts"), SESSION_NEW); self.assertEqual(k("{REPO}/build/out.o"), IGNORED_ARTIFACT)
    self.assertEqual(k("{REPO}/local.sqlite"), PRESERVED)                  # ignore 대상이지만 재생성 이름 아님
    self.assertEqual(k("{REPO}/notes_presession.txt"), PRESERVED); self.assertEqual(k("{HOME}/data/a.txt"), PRESERVED)
    self.assertEqual(classify(None, w.ctx()).kind, UNRESOLVED)
def test_ledger_pre_session_overrides_new_birth(self):
    ctx = w.ctx(); note_touch(w.fmt("{HOME}/data/a.txt"), ctx, "Edit"); w.rewrite_atomic("{HOME}/data/a.txt")
    self.assertEqual(k("{HOME}/data/a.txt", ctx), PRESERVED)
def test_note_touch_rules(self):
    ctx = w.ctx(); L = ctx.ledger
    note_touch(w.fmt("{REPO}/new.txt"), ctx, "Write"); self.assertIn(KIND_CREATED, [e.kind for e in L.entries(w.fmt("{REPO}/new.txt"))])
    note_touch(w.fmt("{REPO}/src/probe.ts"), ctx, "Edit"); self.assertEqual([e.kind for e in L.entries(w.fmt("{REPO}/src/probe.ts"))], [KIND_TOUCHED])
    note_touch(w.fmt("{REPO}/README.md"), ctx, "Edit")
    self.assertTrue({KIND_PRE_SESSION, KIND_PRE_DIRTY, KIND_TOUCHED} <= {e.kind for e in L.entries(w.fmt("{REPO}/README.md"))})
def test_other_session_created_is_not_mine(self):          # D12
    a, b = w.ctx(session_id="A"), w.ctx(session_id="B")
    note_touch(w.fmt("{REPO}/made_by_b.txt"), b, "Write"); w.sh("echo x > made_by_b.txt")   # 실제 훅처럼 Write 직전(파일 없음)에 기록 → created
    self.assertEqual(k("{REPO}/made_by_b.txt", a), PRESERVED); self.assertEqual(k("{REPO}/made_by_b.txt", b), SESSION_NEW)
def test_dir_rule(self):
    self.assertEqual(k("{REPO}/out"), SESSION_NEW); self.assertEqual(k("{REPO}/build"), IGNORED_ARTIFACT)
    self.assertEqual(k("{REPO}/src"), GIT_TRACKED); self.assertEqual(k("{HOME}/data"), PRESERVED)
def test_mv_into_session_dir_is_preserved(self):           # 감사 rootcause-s1-003
    w.sh("mv {HOME}/notes.md {REPO}/out/"); self.assertEqual(k("{REPO}/out"), PRESERVED)
def test_moved_in_record_protects(self):                    # D14
    ctx = w.ctx(); ctx.ledger.record(w.fmt("{REPO}/build/a.txt"), KIND_MOVED_IN, ctx.session_id); w.sh("mv {HOME}/data/a.txt {REPO}/build/")
    self.assertEqual(k("{REPO}/build/a.txt", ctx), PRESERVED); self.assertEqual(k("{REPO}/build", ctx), PRESERVED)
def test_dir_cap(self):  # 세션 전 미추적 폴더에 2001개 → UNRESOLVED, detail 에 "2000"
def test_unreadable_subdir_is_unresolved(self):    # Review Focus 5: 세션 폴더 안 chmod 000 하위 폴더 → UNRESOLVED (끝나면 권한 복구)
def test_symlink_loop_terminates(self):           # Review Focus 5: a/loop → a 순환 링크가 있는 세션 폴더 → 1초 안에 끝나고 SESSION_NEW
def test_unicode_space_path(self):                 # Review Focus 2: 세션 '{REPO}/보고서 초안.md' → SESSION_NEW, 세션 전 '{HOME}/보고 서.md' → PRESERVED
def test_worktree_root(self):
    w.make_worktree(); self.assertEqual(classify(w.fmt("{WT}"), w.ctx()).worktree_root, w.fmt("{WT}"))
def test_in_workspace(self):
    ctx = w.ctx()
    self.assertTrue(in_workspace(w.fmt("{REPO}/build/img"), ctx)); self.assertTrue(in_workspace(w.fmt("{SCRATCH}/s1/a"), ctx))
    self.assertFalse(in_workspace(w.fmt("{HOME}/data"), ctx)); self.assertFalse(in_workspace("/dev/sdb", ctx))
    self.assertFalse(in_workspace(w.fmt("{REPO}/.git/x"), ctx))
    w.sh("git init -q {HOME}", cwd="{HOME}"); self.assertFalse(in_workspace(w.fmt("{HOME}/data"), w.ctx()))
def test_session_start_missing_disables_session_new(self):
    self.assertEqual(k("{REPO}/src/probe.ts", w.ctx(transcript=None)), PRESERVED)
```
  (`rewrite_atomic(path)` = 임시 파일 쓰고 `os.replace` — 이 Step 에서 World 에 추가)

- [ ] **Step 2: 실패 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_target_class.py -k ClassifyTest` · Expected: FAIL
- [ ] **Step 3: 구현** — `classify`: `normalize` → `os.path.lexists` 없으면 MISSING → spec §3.4 순서(분류 1a: `ledger.moved_in_near(path)` 가 있으면
  PRESERVED, detail "옮겨진 유일본" — UNRESOLVED 다음, PROTECTED_NAME 보다 먼저). git 조회는 저장소당 한 번
  (`git -C repo ls-files -z -- <경로들>`, `check-ignore -z --stdin`), 생성 시각은 `births` 일괄. SESSION_NEW = `birth >= session_start` ∧
  이 세션의 `pre-session` 없음 ∧ 다른 세션의 `created` 없음. IGNORED_ARTIFACT = ignore ∧ (저장소 상대경로 구성요소 ∩ `REGENERABLE_NAMES` ≠ ∅ ∨
  확장자 ∈ `REGENERABLE_SUFFIXES`), 아니면 PRESERVED. 폴더: IGNORED_ARTIFACT 폴더만 순회 생략. 그 외는 `os.walk(followlinks=False — 순환
  심볼릭 링크를 따라가지 않아 순회가 끝난다, onerror=…)` 로 항목(링크는 `lstat` 기준 링크 자체)을 모아 `DIR_ENTRY_CAP` 초과·onerror 발생 시
  UNRESOLVED, 아니면 각 항목 분류의 `SEVERITY` 최댓값(동률이면 먼저 만난 것). `in_workspace`: 정규화 후 `is_scratch`, 또는 `git_toplevel` 이
  있고 그 값이 `HOME`·`/` 가 아니며 `<top>/.git` 아래가 아님. `note_touch`: spec §3.7 기록 주체 규칙(경로 없음+Write → `created`; 있으면
  birth < start → `pre-session`, 추적이고 이 세션의 `touched` 가 아직 없고 `git status --porcelain=v1 -z -- 경로` 가 비어 있지 않으면
  `pre-dirty`; tool 이 있으면 `touched`).
- [ ] **Step 4: 통과 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_target_class.py` · Expected: `OK`
- [ ] **Step 5: 커밋(위임 승인 D13)** — `feat(harness-core): bash-guard 대상 7분류·폴더 규칙·작업 영역·장부 기록 규칙`

### Task 6: git 상태·find 미리보기·docker 조회 (`target_class` 3부)

**Files:**
- Modify: `plugins/harness-core/hooks/scripts/target_class.py`, `plugins/harness-core/hooks/tests/_world.py`
  (`World(docker=True)` 의 docker 자원: docker 를 쓸 수 있고 `docker run -d <로컬 이미지> sh -c 'sleep 300'` 이 되는 이미지가 있으면,
  transcript 를 만들기 **전에** 이름 볼륨 `bg<id>-db`(라벨 `com.docker.compose.project=bg<id>`)와 컨테이너 `bg<id>-c`(`-v {REPO}:/app
  -v bg<id>-db:/data -w /app`)를 만들고, compose 가 되면 `out/compose.yaml`(서비스 `web` = 같은 이미지·같은 마운트)로
  `docker compose -p bg<id> up -d`. 세션 시작 뒤 `w.docker.make_fresh_volume()` 이 `bg<id>-fresh` 를 만든다. `w.docker` 속성:
  `container`, `volume`, `project`, `image`, `compose: bool`, `fresh_volume`. 안 되면 `w.docker = None`. `close()` 에서 모두 제거)
- Test: `plugins/harness-core/hooks/tests/test_target_class.py`

**Interfaces:**
- Consumes: Task 5
- Test: `plugins/harness-core/hooks/tests/test_target_class.py`

**Interfaces:**
- Consumes: Task 5
- Produces:
  ```python
  def git_dirty(repo: str, pathspecs: list[str], ctx: Ctx) -> list[str] | None: ...   # 추적 파일 index/worktree 변경(절대경로). 실패 None
  def is_session_change(path: str, ctx: Ctx) -> bool: ...    # spec §3.7 '이번 세션 변경'
  def git_default_branch(repo: str, remote: str, ctx: Ctx) -> str | None: ...
  def git_remote_names(repo: str, ctx: Ctx) -> list[str]: ...
  def git_upstream_branch(repo: str, ctx: Ctx) -> str | None: ...
  def git_stash_created(repo: str, ref: str, ctx: Ctx) -> float | None: ...
  def git_clean_preview(repo: str, clean_args: list[str], ctx: Ctx) -> list[str] | None: ...
  @dataclass(frozen=True)
  class BranchInfo:
      has_upstream: bool; upstream_ref_exists: bool; ahead: int | None; reachable_elsewhere: bool; created_at: float | None
      # ahead = `git rev-list --count <upstream>..B` (upstream 추적 ref 가 없으면 None)
  def git_branch_info(repo: str, branch: str, ctx: Ctx) -> BranchInfo | None: ...
  def find_preview(args: list[str], cwd: str, ctx: Ctx) -> list[str] | None: ...
  def docker_container_info(container: str, ctx: Ctx) -> tuple[tuple[Mount, ...], str] | None: ...  # (마운트, WorkingDir)
  def compose_container_id(service: str, project_dir: str, project: str | None, ctx: Ctx) -> str | None: ...
  def docker_volume_created(name: str, ctx: Ctx) -> float | None: ...
  def docker_volumes(selector: str, value: str | None, ctx: Ctx) -> list[str] | None: ...  # "dangling" | "compose-project"
  ```

- [ ] **Step 1: 실패하는 테스트 작성** — `class GitStateTest`, `class FindTest`, `class DockerTest`:

```python
def test_git_dirty_and_session_change(self):
    ctx = w.ctx(); self.assertEqual(git_dirty(w.fmt("{REPO}"), ["."], ctx), [w.fmt("{REPO}/README.md")])
    w.touch_modify("{REPO}/src/main.py"); self.assertTrue(is_session_change(w.fmt("{REPO}/src/main.py"), ctx))
    self.assertFalse(is_session_change(w.fmt("{REPO}/README.md"), ctx))
    ctx.ledger.record(w.fmt("{REPO}/src/main.py"), KIND_PRE_DIRTY, ctx.session_id)
    self.assertFalse(is_session_change(w.fmt("{REPO}/src/main.py"), ctx))
def test_other_session_touched_is_not_mine(self):          # D12
    a = w.ctx(session_id="A"); w.touch_modify("{REPO}/src/main.py")
    a.ledger.record(w.fmt("{REPO}/src/main.py"), KIND_TOUCHED, "B"); self.assertFalse(is_session_change(w.fmt("{REPO}/src/main.py"), a))
def test_default_branch(self):
    ctx = w.ctx(); self.assertEqual(git_default_branch(w.fmt("{REPO}"), "origin", ctx), "main")
    w.drop_origin_head(); self.assertEqual(git_default_branch(w.fmt("{REPO}"), "origin", ctx), "main")
def test_stash_created(self):
    ctx = w.ctx(); self.assertLess(git_stash_created(w.fmt("{REPO}"), "stash@{1}", ctx), ctx.session_start)
    self.assertGreaterEqual(git_stash_created(w.fmt("{REPO}"), "stash@{0}", ctx), ctx.session_start)
def test_clean_preview(self):
    ctx = w.ctx(); self.assertIn(w.fmt("{REPO}/notes_presession.txt"), git_clean_preview(w.fmt("{REPO}"), ["-fd"], ctx))
    self.assertIn(w.fmt("{REPO}/build/out.o"), git_clean_preview(w.fmt("{REPO}"), ["-xffd"], ctx))
def test_branch_info(self):
    ctx = w.ctx(); w.local_branch("pushed", pushed=True, before_session=True); w.local_branch("lonely", pushed=False, before_session=True)
    w.local_branch("mine", pushed=False, before_session=False); w.local_branch("ahead", pushed=True, before_session=True, extra_unpushed=1)
    pi = git_branch_info(w.fmt("{REPO}"), "pushed", ctx); self.assertEqual((pi.has_upstream, pi.ahead), (True, 0))
    self.assertEqual(git_branch_info(w.fmt("{REPO}"), "ahead", ctx).ahead, 1)
    li = git_branch_info(w.fmt("{REPO}"), "lonely", ctx); self.assertFalse(li.has_upstream or li.reachable_elsewhere)
    self.assertGreaterEqual(git_branch_info(w.fmt("{REPO}"), "mine", ctx).created_at, ctx.session_start)
def test_find_preview(self):
    ctx = w.ctx(); r = w.fmt("{REPO}")
    self.assertEqual(sorted(find_preview([r, "-name", "*.o", "-delete"], r, ctx)), [w.fmt("{REPO}/build/out.o")])
    self.assertIsNotNone(find_preview([".", "-name", "*.o", "-exec", "rm", "-f", "{}", "+"], r, ctx))
    self.assertIsNone(find_preview([".", "-name", "x", "-exec", "mv", "{}", "/t", ";"], r, ctx))
    self.assertIsNone(find_preview([".", "-fprint", "/t/x", "-delete"], r, ctx))
def test_docker(self):
    w2 = World(docker=True); self.addCleanup(w2.close); d = w2.docker
    if d is None: self.skipTest("docker 또는 sleep 이 도는 로컬 이미지 없음")
    ctx = w2.ctx(); mounts, wd = docker_container_info(d.container, ctx)
    self.assertIn(Mount(w2.fmt("{REPO}"), "/app", "bind"), mounts); self.assertIn(Mount(d.volume, "/data", "volume"), mounts)
    self.assertEqual(wd, "/app"); self.assertLess(docker_volume_created(d.volume, ctx), ctx.session_start)
    self.assertEqual(docker_volumes("compose-project", d.project, ctx), [d.volume])
    if d.compose: self.assertIsNotNone(compose_container_id("web", w2.fmt("{OUT}"), d.project, ctx))
def test_docker_unavailable(self):
    ctx = w.ctx(environ_extra={"DOCKER_HOST": "unix:///nonexistent.sock"})
    self.assertIsNone(docker_container_info("c", ctx)); self.assertIsNone(docker_volume_created("v", ctx))
```

- [ ] **Step 2: 실패 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_target_class.py` · Expected: FAIL
- [ ] **Step 3: 구현** — `git_dirty`: `git status --porcelain=v1 -z --untracked-files=no -- <pathspecs>`(이름 변경은 두 이름). `is_session_change`:
  `mtime >= session_start` ∧ 이 세션 `pre-dirty` 없음 ∧ `ts >= session_start` 인 다른 세션 `touched` 없음. `git_default_branch`:
  `refs/remotes/<remote>/HEAD` → 없으면 `main` → `master`(로컬 또는 원격 추적 ref 존재) → None. `git_branch_info`: `git config branch.<b>.remote`, upstream 추적 ref 존재(`git rev-parse --verify -q <b>@{u}`)와
  `git rev-list --count <b>@{u}..<b>`(ahead), `git for-each-ref --contains <b끝> --format=%(refname)` 에서 `refs/heads/<b>`·그 upstream 추적 ref 를 뺀 것이 있으면 reachable, `git reflog show --format=%ct
  refs/heads/<b>` 의 마지막 줄(가장 오래된 기록). `find_preview` 허용 토큰: 첫 `-` 전 경로들, `-name -iname -path -ipath -wholename -regex -type
  -mtime -mmin -newer -size -empty -maxdepth -mindepth -prune -o -or -a -and -not ! ( )` 와 값, 동작 정확히 하나(`-delete` 또는 `-exec|-execdir rm
  [-r|-f|-rf|-fr|-R]... {} (;|+)`); 동작을 `-print0` 로 바꿔 실행, 결과는 cwd 기준 절대경로. docker: `docker inspect --format
  '{{json .Mounts}}|{{.Config.WorkingDir}}' <c>`, `docker volume inspect --format '{{.CreatedAt}}' <v>`(RFC3339 → epoch; 3.10 호환 위해 `Z`·
  소수 자릿수 정리 후 `datetime.fromisoformat`), `docker volume ls -q -f dangling=true` / `-f label=com.docker.compose.project=<p>`,
  `docker compose [--project-directory d] [-p p] ps -q <svc>`.
- [ ] **Step 4: 통과 확인** — 같은 명령 · Expected: `OK`(docker 없으면 `skipped` 표시 포함)
- [ ] **Step 5: 커밋(위임 승인 D13)** — `feat(harness-core): bash-guard git 상태·브랜치·find 미리보기·docker 조회`

### Task 7: 정책 — 삭제·덮어쓰기·디스크·시스템·권한 (`policy.py` 1부)

**Files:**
- Create: `plugins/harness-core/hooks/scripts/policy.py`
- Modify: `plugins/harness-core/hooks/tests/_world.py` (헬퍼 `evaluate_all(command, cwd="{REPO}", ctx=None) -> list[Finding]` = parse 후 모든 단위 `evaluate`)
- Test: `plugins/harness-core/hooks/tests/test_policy.py`

**Interfaces:**
- Consumes: Task 3 `Segment`·`expand`·`literal_args`, Task 5 `classify`·`in_workspace`·분류 상수, Task 6 `find_preview`·`git_dirty`·`is_session_change`
- Produces:
  ```python
  KIND_TEXT: dict[str, str]
  @dataclass(frozen=True)
  class Finding:
      op: str          # "삭제" | "덮어쓰기" | "디스크 쓰기" | "시스템 경로 쓰기" | "재귀 권한 변경" | "git <하위명령>" | "docker 볼륨 삭제"
      target: str
      kind: str        # 분류 상수 또는 "DIRTY" "DEFAULT_BRANCH" "REFLOG" "OLD_STASH" "OLD_VOLUME" "SYSTEM" "OUTSIDE_WORKSPACE" "UNPUSHED"
      advice: str
      def reason(self) -> str: ...   # f"거부: {op} {target} — {KIND_TEXT[kind]}. 대안: {advice}"
  def evaluate(seg: Segment, ctx: Ctx) -> list[Finding]: ...
  def is_judged_op(seg: Segment) -> bool: ...
  def judged_targets(seg: Segment) -> list[str]: ...   # 판정 대상 작업의 확정된 대상 경로들(모드 결정용, Task 9)
  SYSTEM_ROOTS = ("/etc", "/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/boot")
  BENIGN_DEVICES = ("/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty", "/dev/fd/")
  ```
  `KIND_TEXT`: `UNRESOLVED`="대상을 확정할 수 없다", `PROTECTED_NAME`="보호 대상 파일(비밀·설정·.git)", `GIT_TRACKED`="git 이 추적하는 파일",
  `PRESERVED`="세션 전부터 있던 유일본", `DIRTY`="커밋 안 된 수정이 있다", `SYSTEM`="호스트 시스템 경로",
  `OUTSIDE_WORKSPACE`="작업 영역(프로젝트·임시 폴더) 밖", `DEFAULT_BRANCH`="기본 브랜치 원격 이력 덮어쓰기", `REFLOG`="reflog 복구 경로 삭제",
  `OLD_STASH`="세션 전 보관본", `OLD_VOLUME`="기존 Docker 볼륨(데이터)", `UNPUSHED`="어디에도 남지 않는 커밋".
  대안 문구는 spec §3.5 문구 그대로(삭제·GIT_TRACKED: "`git rm <경로>` 로 삭제하라(변경 내역에 남아 검토·복구 가능)", PROTECTED_NAME·PRESERVED:
  "세션 전부터 있던 유일본이다. 정말 지워야 하면 사용자에게 요청하라", UNRESOLVED: "대상을 리터럴 경로로, 범위를 좁혀 다시 실행하라",
  xargs rm: "`find … -delete` 나 리터럴 경로를 써라", 임시 루트 와일드카드: "자기 세션 폴더로 범위를 좁혀라", 폴더 상한: "범위를 좁혀라",
  DIRTY(덮어쓰기): "먼저 커밋하거나 `git stash` 하라").
  **판정 대상 작업**(`is_judged_op` True): 처리기 표의 명령(`rm unlink shred find`(동작 있을 때) `xargs`→`rm` `rsync`(`--delete*`) `cp mv install tee
  truncate dd mkfs*`, `-R` 있는 `chmod chown chgrp`), 쓰기 리다이렉트(`>` `>|` `&>`)가 있는 단위, git 하위명령 중 spec §3.5 git 표의 판정 행
  (`reset --hard`, 경로·`.`·`-f` 를 가진 `checkout`, `switch -f|--discard-changes`, 작업 트리 대상 `restore`, `rm -f`, `worktree remove --force`,
  `clean`, `stash drop|clear`, `push`, `branch -D`, `reflog expire|delete`, `gc --prune`, `prune`, `filter-branch`, `filter-repo`), docker 볼륨 삭제
  명령, 그리고 컨테이너 문맥 단위 중 위 처리기 표에 해당하는 것. 그 외(`ls`, `git status`, `docker ps` 등)는 False.

- [ ] **Step 1: 실패하는 테스트 작성** — `class DeleteTest`, `class OverwriteTest`, `class DiskSystemTest`, `class JudgedOpTest`:

```python
def ev(cmd, cwd="{REPO}"): return [(f.op, f.kind) for f in w.evaluate_all(w.fmt(cmd), cwd)]

def test_delete(self):
    self.assertEqual(ev("rm -f src/probe.ts"), []); self.assertEqual(ev("rm -rf build out"), [])
    self.assertEqual(ev("rm -rf /nope 2>/dev/null"), []); self.assertEqual(ev("rmdir emptydir"), [])
    self.assertEqual(ev("rm src/main.py"), [("삭제", GIT_TRACKED)]); self.assertEqual(ev("git rm src/main.py"), [])
    self.assertEqual(ev("rm notes_presession.txt"), [("삭제", PRESERVED)]); self.assertEqual(ev("rm .env"), [("삭제", PROTECTED_NAME)])
    self.assertEqual(ev("rm local.sqlite"), [("삭제", PRESERVED)])
    self.assertEqual(ev('rm -rf "$UNKNOWN/x"'), [("삭제", UNRESOLVED)]); self.assertEqual(ev("rm -rf {SCRATCH}/*"), [("삭제", UNRESOLVED)])
    self.assertEqual(ev("rm -rf {SCRATCH}/s1"), []); self.assertEqual(ev("shred -u {HOME}/data/a.txt"), [("삭제", PRESERVED)])
    self.assertEqual(ev("unlink {HOME}/notes.md"), [("삭제", PRESERVED)])
def test_delete_reason_text(self):
    f = w.evaluate_all(w.fmt("rm src/main.py"), "{REPO}")[0]
    self.assertEqual(f.reason(), f"거부: 삭제 {w.fmt('{REPO}/src/main.py')} — git 이 추적하는 파일. 대안: `git rm <경로>` 로 삭제하라(변경 내역에 남아 검토·복구 가능)")
def test_find_and_xargs(self):
    self.assertEqual(ev("find . -name '*.o' -delete"), []); self.assertEqual(ev("find . -name '*.py' -delete"), [("삭제", GIT_TRACKED)])
    self.assertEqual(ev("find . -name x -exec mv {} /t \\;"), []); self.assertEqual(ev("find . -fprint /t/x -delete"), [("삭제", UNRESOLVED)])
    self.assertEqual(ev("ls | xargs rm -f"), [("삭제", UNRESOLVED)]); self.assertEqual(ev("git ls-files -z | xargs -0 git rm --cached"), [])
def test_overwrite(self):
    self.assertEqual(ev("echo x > src/main.py"), []); self.assertEqual(ev("echo x > README.md"), [("덮어쓰기", "DIRTY")])
    self.assertEqual(ev("echo x >> notes_presession.txt"), []); self.assertEqual(ev("echo x > /dev/null"), [])
    self.assertEqual(ev("echo x > {HOME}/data/important.csv"), [("덮어쓰기", PRESERVED)])
    self.assertEqual(ev("tee -a {HOME}/notes.md"), []); self.assertEqual(ev("tee {HOME}/notes.md"), [("덮어쓰기", PRESERVED)])
    self.assertEqual(ev("cp src/probe.ts notes_presession.txt"), [("덮어쓰기", PRESERVED)])
    self.assertEqual(ev("cp src/probe.ts {HOME}/data/"), []); self.assertEqual(ev("mv {HOME}/notes.md {SCRATCH}/s1/"), [])
    self.assertEqual(ev("truncate -s0 {HOME}/data/db.sqlite"), [("덮어쓰기", PRESERVED)]); self.assertEqual(ev("sed -i s/a/b/ {HOME}/notes.md"), [])
    self.assertEqual(ev("rsync -a --delete src/ {HOME}/data/"), [("삭제", PRESERVED)]); self.assertEqual(ev("rsync -a src/ {SCRATCH}/s1/"), [])
def test_disk_system_chmod(self):
    self.assertEqual(ev("cat img > /dev/sdb"), [("디스크 쓰기", "OUTSIDE_WORKSPACE")])
    self.assertEqual(ev("dd if=/dev/zero of=build/img bs=1M count=1"), []); self.assertEqual(ev("dd if=fw.bin of=rootfs.img bs=1 skip=10"), [])
    self.assertEqual(ev("dd if=/dev/zero of=/dev/sdb"), [("디스크 쓰기", "OUTSIDE_WORKSPACE")])
    self.assertEqual(ev("mkfs.ext4 /dev/sdb1"), [("디스크 쓰기", "OUTSIDE_WORKSPACE")])
    self.assertEqual(ev("echo x > /etc/hosts"), [("시스템 경로 쓰기", "SYSTEM")]); self.assertEqual(ev("sudo rm /usr/bin/x"), [("시스템 경로 쓰기", "SYSTEM")])
    self.assertEqual(ev("chmod -R 777 {HOME}"), [("재귀 권한 변경", "OUTSIDE_WORKSPACE")])
    self.assertEqual(ev("chmod -R 755 build"), []); self.assertEqual(ev("chmod 777 {HOME}/notes.md"), [])
    self.assertEqual(ev("killall node; systemctl --user stop svc; pkill -f x"), [])
def test_is_judged_op(self):
    j = lambda c: [policy.is_judged_op(s) for s in parse(w.fmt(c), w.fmt("{REPO}"), w.environ).segments]
    self.assertEqual(j("ls; git status; docker ps; git log"), [False, False, False, False])
    self.assertEqual(j("rm x; echo a > f; git reset --hard; git push; docker volume rm v"), [True, True, True, True, True])
```

- [ ] **Step 2: 실패 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_policy.py` · Expected: `ModuleNotFoundError: policy`
- [ ] **Step 3: 구현** — `evaluate`: 컨테이너 문맥이면 Task 8 경로(이 작업에서는 빈 목록 자리만). 호스트면 ① 리다이렉트(덮어쓰기·장치·시스템)
  ② 명령 이름별 처리기 표 `HANDLERS: dict[str, Callable[[Segment, Ctx], list[Finding]]]`. 대상 = `expand` 결과(None → UNRESOLVED 하나).
  시스템 경로 검사가 다른 분류보다 먼저. 임시 루트 와일드카드: 원형 단어가 따옴표 없는 글롭이고 디렉터리 부분이 `is_scratch_root` 면 UNRESOLVED.
  덮어쓰기 GIT_TRACKED 는 `git_dirty(repo, [path])` 가 비었거나 `is_session_change(path)` 면 허용, 아니면 DIRTY. 옵션은 `literal_args` 기준
  (`--` 뒤는 모두 피연산자). `cp|mv|install` 목적지 = 마지막 피연산자(`-t DIR` 지원), 존재하는 폴더면 `목적지/원본이름` 들. `rsync --delete*` 는
  목적지 폴더를 삭제 규칙으로. `judged_targets` = 이 단위에서 판정한 경로(확정된 것만).
- [ ] **Step 4: 통과 확인** — 같은 명령 · Expected: `OK`
- [ ] **Step 5: 커밋(위임 승인 D13)** — `feat(harness-core): bash-guard 정책 — 삭제·덮어쓰기·디스크·시스템·권한`

### Task 8: 정책 — git·Docker (`policy.py` 2부)

**Files:**
- Modify: `plugins/harness-core/hooks/scripts/policy.py`
- Test: `plugins/harness-core/hooks/tests/test_policy.py`

**Interfaces:**
- Consumes: Task 6 git/브랜치/docker 조회, Task 7 `Finding`·`evaluate`
- Produces: `evaluate` 가 `git` 과 컨테이너 문맥·docker 볼륨 명령을 처리(새 공개 함수 없음).

- [ ] **Step 1: 실패하는 테스트 작성** — `class GitPolicyTest`, `class DockerPolicyTest`:

```python
def test_discard_ops(self):
    w.clean_tree(); self.assertEqual(ev("git reset --hard"), []); self.assertEqual(ev("git checkout -- ."), [])
    w.touch_modify("{REPO}/src/main.py"); self.assertEqual(ev("git reset --hard HEAD"), [])          # 이번 세션 변경만
    w.make_worktree(); w.dirty_before_session("{REPO}/README.md"); w.dirty_before_session("{WT}/README.md")
    for c in ["git reset --hard", "git checkout .", "git checkout -- README.md", "git restore .", "git switch -f main",
              "git checkout -f main", "git rm -f README.md", "git worktree remove --force {WT}"]:
        self.assertEqual([k for _, k in ev(c)], ["DIRTY"], c)
    self.assertEqual(ev("git restore --staged README.md"), []); self.assertEqual(ev("git rm --cached README.md"), [])
def test_clean(self):
    self.assertEqual(ev("git clean -n"), []); self.assertEqual(ev("git clean -fd"), [("git clean", PRESERVED)])
    self.assertEqual(ev("git clean -fdX"), [("git clean", PROTECTED_NAME)])   # ignore 대상 .env — 재생성 아님
    w.sh("rm .env local.sqlite"); self.assertEqual(ev("git clean -fdX"), [])  # 남은 ignore 는 build/ 뿐
def test_stash(self):
    self.assertEqual(ev("git stash drop stash@{1}"), [("git stash", "OLD_STASH")]); self.assertEqual(ev("git stash drop"), [])
    self.assertEqual(ev("git stash clear"), [("git stash", "OLD_STASH")])
def test_push(self):
    for c in ["git push origin +main", "git push --force origin main", "git push -f origin HEAD:main", "git push origin :main",
              "git push origin --delete main", "git push --mirror"]:
        self.assertEqual([k for _, k in ev(c)], ["DEFAULT_BRANCH"], c)
    for c in ["git push -u origin feat/x", "git push --force origin feat/x", "git push --force-with-lease origin feat/x",
              "git push origin --delete feat/x", "git push -q origin --delete feat/x; git log -1 --format=%h"]:
        self.assertEqual(ev(c), [], c)
    w.checkout("feat/x", upstream="origin/feat/x"); self.assertEqual(ev("git push --force"), [])
    w.checkout("main", upstream="origin/main"); self.assertEqual([k for _, k in ev("git push --force")], ["DEFAULT_BRANCH"])
def test_default_branch_fallback(self):            # Review Focus 3
    w.drop_origin_head(); self.assertEqual([k for _, k in ev("git push --force origin main")], ["DEFAULT_BRANCH"])
    w.remove_remote("origin"); self.assertEqual(ev("git push --force origin main"), [])
def test_branch_delete(self):                      # 감사 rootcause-s1-001·r2-002
    w.local_branch("pushed", pushed=True, before_session=True); w.local_branch("lonely", pushed=False, before_session=True)
    w.local_branch("mine", pushed=False, before_session=False); w.local_branch("ahead", pushed=True, before_session=True, extra_unpushed=1)
    w.local_branch("merged", pushed=True, before_session=True, delete_remote=True)   # 병합 후 원격 삭제(upstream 추적 ref 없음)
    self.assertEqual(ev("git branch -D pushed"), []); self.assertEqual(ev("git branch -D mine"), []); self.assertEqual(ev("git branch -D merged"), [])
    self.assertEqual([k for _, k in ev("git branch -D ahead")], ["UNPUSHED"])
    self.assertEqual([k for _, k in ev("git branch -D lonely")], ["UNPUSHED"]); self.assertEqual(ev("git branch -d lonely"), [])
def test_reflog_destroyers(self):
    for c in ["git reflog expire --expire=now --all", "git gc --prune=now", "git prune", "git filter-branch -- --all", "git filter-repo --force"]:
        self.assertEqual([k for _, k in ev(c)], ["REFLOG"], c)
def test_allowed_history_ops(self):
    for c in ["git rebase origin/main", "git commit --amend -m x", "git worktree add ../wt2 -b y", "git update-ref -d refs/heads/y", "git stash pop"]:
        self.assertEqual(ev(c), [], c)
    w.make_worktree(); self.assertEqual(ev("git worktree remove {WT}"), [])
def test_linked_worktree_rm(self):
    w.make_worktree(); self.assertEqual(ev("rm -rf {WT}"), [])
    w.dirty_before_session("{WT}/README.md"); self.assertEqual([k for _, k in ev("rm -rf {WT}")], ["DIRTY"])

def test_container(self):
    w2 = World(docker=True); self.addCleanup(w2.close); d = w2.docker
    if d is None: self.skipTest("docker 또는 sleep 이 도는 로컬 이미지 없음")
    e = lambda cmd, cwd="{REPO}": [(f.op, f.kind) for f in w2.evaluate_all(w2.fmt(cmd), cwd)]
    c = d.container
    self.assertEqual(e(f"docker exec -u root {c} sh -c 'echo x >> /etc/hosts && rm -rf /var/lib/x'"), [])
    self.assertEqual(e(f"docker exec {c} rm -rf /app/src"), [("삭제", GIT_TRACKED)])                 # main.py 추적 + probe.ts 세션
    self.assertEqual(e(f"docker exec {c} rm -rf src"), [("삭제", GIT_TRACKED)])                      # WorkingDir /app
    self.assertIn(e(f"docker exec {c} sh -c 'rm -rf /app'")[0][1], (PROTECTED_NAME, PRESERVED))         # Destination 자체 = {REPO} 전체
    self.assertEqual(e(f"docker exec {c} rm -rf /data/x"), [("삭제", "OLD_VOLUME")])
    self.assertEqual(e(f'docker run --rm -v "$(pwd)":/app {d.image} rm -f /app/notes_presession.txt'), [("삭제", PRESERVED)])
    if d.compose: self.assertEqual(e(f"docker compose -p {d.project} exec web rm -rf /app/src/probe.ts", cwd="{OUT}"), [])
def test_volume_ops(self):
    w2 = World(docker=True); self.addCleanup(w2.close); d = w2.docker
    if d is None: self.skipTest("docker 또는 sleep 이 도는 로컬 이미지 없음")
    e = lambda cmd: [(f.op, f.kind) for f in w2.evaluate_all(w2.fmt(cmd), "{REPO}")]
    d.make_fresh_volume()
    self.assertEqual(e(f"docker volume rm {d.volume}"), [("docker 볼륨 삭제", "OLD_VOLUME")])
    self.assertEqual(e(f"docker volume rm {d.fresh_volume}"), [])
    self.assertEqual([k for _, k in e(f"docker compose -p {d.project} down -v")], ["OLD_VOLUME"])
    self.assertEqual(e(f"docker rm -f {d.container}; docker compose -p {d.project} down"), [])
def test_docker_unavailable_policy(self):
    ctx = w.ctx(environ_extra={"DOCKER_HOST": "unix:///nonexistent.sock"})
    self.assertEqual([k for _, k in ev("docker volume rm db", ctx=ctx)], [UNRESOLVED])
    self.assertEqual(ev("docker exec c sh -c 'rm -rf /var/lib/x'", ctx=ctx), [])
```
  (이 작업의 `ev` 는 `ev(cmd, cwd="{REPO}", ctx=None)` — Task 7 헬퍼에 `ctx` 인자 추가)

- [ ] **Step 2: 실패 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_policy.py` · Expected: FAIL
- [ ] **Step 3: 구현** — git 하위명령 표(spec §3.5 git 표). 영향 범위: `reset --hard` → 저장소 전체, `checkout|restore` 경로 인자(`.` 이면 전체),
  `switch -f|--discard-changes`·`checkout -f` → 전체, `rm -f|--force` → 인자, `worktree remove --force P` → P 의 작업 트리 전체(P 저장소 기준 조회).
  판정: `git_dirty` 에서 `is_session_change` 아닌 것이 있으면 DIRTY(target = 첫 경로 + "외 N개"), 조회 실패 UNRESOLVED. `clean`(`-n|--dry-run`
  있으면 허용) → `git_clean_preview` 각 경로 `classify`, SEVERITY>0 인 첫 항목 `("git clean", 분류)`. `branch -D B`(`-D`·`--delete --force`·`-df`):
  `git_branch_info` 로 (upstream 이 있고 그 추적 ref 가 없거나 ahead == 0) 또는 reachable_elsewhere 또는 created_at ≥ session_start 면 허용, 아니면 UNPUSHED(대안: "먼저 push 하거나 태그를 남겨라"),
  조회 실패 UNRESOLVED. push: 원격 = 첫 비옵션 인자(없으면 upstream 원격 또는 `origin`), `git_remote_names` 에 없으면 판정 안 함. refspec 목적지 =
  `:` 뒤(없으면 그 자체, `HEAD` → 현재 브랜치), 앞 `+` 는 강제, `refs/heads/` 제거. 강제 = `--force|-f|+refspec`, 삭제 = `--delete|-d|:dst`,
  `--mirror` → DEFAULT_BRANCH. `--force-with-lease`·`--force-if-includes` 는 강제 아님. refspec 없는 push 는 `git_upstream_branch`.
  컨테이너: exec 계열은 `docker_container_info`(compose 는 `compose_container_id(container, project_dir, project)` 먼저)로 마운트·WorkingDir;
  단위 cwd 가 None 이면 WorkingDir. 대상 컨테이너 경로가 마운트 Destination **자체이거나 하위**면 bind → 호스트 경로로 바꿔 Task 7 처리기
  (시스템 경로 규칙 제외), volume → `docker_volume_created` < session_start 면 OLD_VOLUME(조회 실패 UNRESOLVED). 마운트 밖·조회 실패면 판정 없음.
  볼륨 명령: spec §3.5 Docker 표(목록: 인자 / `dangling` / `compose-project`).
- [ ] **Step 4: 통과 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_policy.py` · Expected: `OK`(docker 없으면 skip 표시)
- [ ] **Step 5: 커밋(위임 승인 D13)** — `feat(harness-core): bash-guard 정책 — git·Docker`

### Task 9: 진입점 (`bash_guard.py`)

**Files:**
- Create: `plugins/harness-core/hooks/scripts/bash_guard.py`
- Test: `plugins/harness-core/hooks/tests/test_bash_guard.py`

**Interfaces:**
- Consumes: `shell_parse.parse`, `target_class.make_ctx`·`note_touch`·`classify`·`switch_mode`·`MODE_RANK`, `policy.evaluate`·`is_judged_op`·`judged_targets`, `ledger.KIND_MOVED_IN`
- Produces:
  ```python
  BUDGET_SECONDS = 5.0
  LOG_MAX_BYTES = 10 * 1024 * 1024
  FOOTER = "이 판정을 우회하지 말 것. 대안이 맞지 않으면 작업을 멈추고 사용자에게 보고하라."
  FAIL_WORDS: re.Pattern   # spec §3.8 (가)
  @dataclass
  class Decision:
      allow: bool
      reasons: list[str]
      mode: str                    # 이 명령의 모드
      error: str | None = None
  def judge(payload: dict, environ: Mapping[str, str], budget: float = BUDGET_SECONDS) -> Decision: ...
  def render(d: Decision) -> str: ...
  def log_event(record: dict, environ: Mapping[str, str], max_bytes: int = LOG_MAX_BYTES) -> None: ...
  def final_output(d: Decision, old: str) -> str: ...      # on → render(d) / 그 외 → old(그대로, 빈 문자열 가능)
  def main(argv: list[str] | None = None) -> int: ...      # `--old <JSON 문자열>`. stdin payload → judge → 기록 → final_output 출력 → 0
  ```
  모드 = max(`MODE_RANK`) over {`environ` 의 `HARNESS_BASH_GUARD`, `switch_mode(cwd)`, 판정 대상 단위들의 `judged_targets` 각 `switch_mode`}.
  기록(`log_event`): `on` 의 거부·오류, `shadow` 의 신·구 불일치(old 의 permissionDecision 이 `ask`·`deny` 면 비허용, 그 외 허용)·오류.
  내부 예외 → `main` 이 잡아 old 그대로 출력 + `{error}` 기록(spec §3.8 (다)).

- [ ] **Step 1: 실패하는 테스트 작성** — `class JudgeTest`, `class MainTest`:

```python
ON = {"HARNESS_BASH_GUARD": "on"}
def test_allow_render_exact(self):
    d = judge(w.payload("ls -la"), {**w.environ, **ON}); self.assertTrue(d.allow)
    self.assertEqual(render(d), '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}')
def test_deny_render(self):
    out = json.loads(render(judge(w.payload("rm src/main.py"), {**w.environ, **ON})))["hookSpecificOutput"]
    self.assertEqual(out["permissionDecision"], "deny"); self.assertTrue(out["permissionDecisionReason"].startswith("[bash-guard] 거부: 삭제 "))
    self.assertTrue(out["permissionDecisionReason"].endswith(FOOTER))
def test_multiple_reasons(self):
    self.assertEqual(len(judge(w.payload("rm src/main.py; rm {HOME}/notes.md"), {**w.environ, **ON}).reasons), 2)
def test_mode_resolution(self):
    self.assertEqual(judge(w.payload("rm src/main.py"), w.environ).mode, "off")
    w.set_repo_switch("shadow"); self.assertEqual(judge(w.payload("rm src/main.py"), w.environ).mode, "shadow")
    # 세션 cwd 는 홈(저장소 밖)이고 대상만 스위치 저장소 안 → 대상 저장소 값으로 on
    w.set_repo_switch("on"); self.assertEqual(judge(w.payload("rm {REPO}/src/main.py", cwd="{HOME}"), w.environ).mode, "on")
def test_parse_failure_policy(self):
    self.assertTrue(judge(w.payload('echo "unterminated'), {**w.environ, **ON}).allow)
    d = judge(w.payload('rm -rf "unterminated'), {**w.environ, **ON}); self.assertFalse(d.allow); self.assertIn("해석하지 못했다", d.reasons[0])
def test_budget(self):
    self.assertFalse(judge(w.payload("rm {HOME}/notes.md"), {**w.environ, **ON}, budget=0).allow)
    self.assertIn("판정 시간 초과", judge(w.payload("rm {HOME}/notes.md"), {**w.environ, **ON}, budget=0).reasons[0])
    self.assertTrue(judge(w.payload("ls"), {**w.environ, **ON}, budget=0).allow)
def test_inplace_edit_records_ledger(self):
    judge(w.payload("sed -i s/a/b/ {HOME}/notes.md", session_id=w.session_id), {**w.environ, **ON})
    self.assertIn(KIND_PRE_SESSION, [e.kind for e in Ledger(w.environ).entries(w.fmt("{HOME}/notes.md"))])
def test_mv_records_moved_in(self):                          # D14 — 모드 off 여도 기록
    judge(w.payload("mv {HOME}/notes.md {REPO}/build/", session_id=w.session_id), w.environ)
    self.assertEqual(Ledger(w.environ).moved_in_near(w.fmt("{REPO}/build/notes.md")), w.fmt("{REPO}/build/notes.md"))
    judge(w.payload("mv src/probe.ts {SCRATCH}/s1/", session_id=w.session_id), w.environ)    # 세션 파일 원본 → 기록 없음
    self.assertIsNone(Ledger(w.environ).moved_in_near(w.fmt("{SCRATCH}/s1/probe.ts")))
def test_log_rotation(self):
    for _ in range(5): log_event({"x": "y" * 80}, w.environ, max_bytes=200)
    self.assertTrue((state_dir(w.environ) / "bash-guard.jsonl.1").exists())
def test_main_outputs(self):
    old = '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"x"}}'
    # main 을 subprocess(python3 bash_guard.py --old <old>, stdin=payload, env=…) 로 실행:
    #  off(스위치 없음): stdout == old + "\n", 기록 없음
    #  shadow(세션 env): 'rmdir d' → stdout == old + "\n", 기록 1줄(mode shadow, decision allow, old_decision ask)
    #  shadow: 'rm src/main.py' → 기록 추가 없음(둘 다 비허용)
    #  on: 'rmdir d' → stdout 이 allow JSON
    #  old 가 빈 문자열이고 off → stdout 빈 문자열
def test_internal_error_outputs_old(self):
    # tool_input 이 문자열인 잘못된 payload 를 --old <old> 로 → stdout == old + "\n", 기록에 error 필드 1줄
```

- [ ] **Step 2: 실패 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_bash_guard.py` · Expected: `ModuleNotFoundError`
- [ ] **Step 3: 구현** — `judge`: `tool_name != "Bash"`·명령 없음 → allow(모드는 세션 env·cwd 로만). `ctx = make_ctx(payload, environ, budget)`;
  `parse(command, payload.get("cwd"), environ)`, `error` 있으면 (가). 단위마다 남은 시간 ≤ 0 이면, 지금까지 `is_judged_op` 단위가 있었으면 거부
  ("거부: 판정 시간 초과 — 범위를 좁혀라"), 없으면 허용으로 종료(현재 단위도 판정 대상이면 '있었음'에 포함). `evaluate` 결과를 모으고 사유 중복
  제거. 제자리 편집(`sed -i|--in-place`, `perl -i|-pi`, `git checkout -- P`, `git restore P`) 대상마다 `note_touch(path, ctx, None)`. 모드 계산은
  위 Interfaces. `mv` 단위(모드 무관): 원본을 `classify` 해 `GIT_TRACKED`·`PRESERVED`·`PROTECTED_NAME` 이면 목적지(폴더면 `폴더/원본이름`)를
  `KIND_MOVED_IN` 으로 기록. `log_event` 필드: `ts`(ISO8601), `mode`, `session_id`, `agent_id`, `cwd`, `command`(2000자), `decision`, `old_decision`, `reasons`,
  `ms`, `error`; 쓰기 전 파일이 `max_bytes` 를 넘으면 `.1` 로 교체.
- [ ] **Step 4: 통과 확인** — 같은 명령 · Expected: `OK`
- [ ] **Step 5: 커밋(위임 승인 D13)** — `feat(harness-core): bash-guard 진입점 — 모드·실패 정책·시간 예산·기록`

### Task 10: 장부 훅 (`touch-ledger.py`, `hooks.json`)

**Files:**
- Create: `plugins/harness-core/hooks/scripts/touch-ledger.py`
- Modify: `plugins/harness-core/hooks/hooks.json` (PreToolUse 배열에 항목 추가)
- Test: `plugins/harness-core/hooks/tests/test_touch_ledger.py`

**Interfaces:**
- Consumes: `target_class.make_ctx`·`note_touch`
- Produces: 훅 계약 — stdin JSON, **출력 없음**, 종료 0, **스위치와 무관하게 항상 기록**(spec D14). 대상 = `tool_input.file_path` 또는
  `tool_input.notebook_path`, 도구 = `tool_name`. 모든 예외 무시.
  `hooks.json` 항목: `{"matcher": "Write|Edit|NotebookEdit", "hooks": [{"type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/scripts/touch-ledger.py\"", "timeout": 5}]}`

- [ ] **Step 1: 실패하는 테스트 작성**:

```python
def run_hook(payload_or_text, extra_env=None): # subprocess python3 touch-ledger.py, env={**w.environ, **(extra_env or {})} → (rc, stdout)
def test_records_without_switch(self):          # 스위치 없음(off)에서도 기록
    self.assertEqual(run_hook(w.edit_payload("{HOME}/notes.md")), (0, ""))
    self.assertIn(KIND_PRE_SESSION, [e.kind for e in Ledger(w.environ).entries(w.fmt("{HOME}/notes.md"))])
def test_records_touched_and_pre_dirty(self):
    run_hook(w.edit_payload("{REPO}/README.md"))
    self.assertTrue({KIND_PRE_DIRTY, KIND_TOUCHED} <= {e.kind for e in Ledger(w.environ).entries(w.fmt("{REPO}/README.md"))})
def test_write_new_file_records_created(self):
    run_hook(w.edit_payload("{REPO}/new.txt", tool="Write"))
    self.assertIn(KIND_CREATED, [e.kind for e in Ledger(w.environ).entries(w.fmt("{REPO}/new.txt"))])
def test_malformed_input(self): self.assertEqual(run_hook("not json"), (0, ""))
def test_hooks_json_registration(self):
    h = json.load(open(HOOKS_JSON))["hooks"]["PreToolUse"]
    e = [g for g in h if g.get("matcher") == "Write|Edit|NotebookEdit"][0]["hooks"][0]
    self.assertEqual((e["timeout"], e["command"]), (5, 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/touch-ledger.py"'))
```

- [ ] **Step 2: 실패 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_touch_ledger.py` · Expected: FAIL(파일 없음)
- [ ] **Step 3: 구현** — 위 계약대로. `hooks.json` 은 기존 Bash 항목 뒤에 추가.
- [ ] **Step 4: 통과 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_touch_ledger.py && jq empty plugins/harness-core/hooks/hooks.json` · Expected: `OK`, 종료 0
- [ ] **Step 5: 커밋(위임 승인 D13)** — `feat(harness-core): bash-guard 장부 훅 — Write·Edit 직전 항상 기록`

### Task 11: 합격 묶음 — 오탐 회귀·누락·시나리오

**Files:**
- Create: `plugins/harness-core/hooks/tests/fixtures/false_positive.json`, `plugins/harness-core/hooks/tests/fixtures/false_negative.json`
- Modify: `plugins/harness-core/hooks/tests/test_bash_guard.py`, `plugins/harness-core/hooks/tests/_world.py`
  (`judge_case(case) -> Decision` = setup 적용 후 `fmt` 한 명령을 세션 env `on` 으로 judge, `judge_cmd(cmd, cwd="{REPO}") -> Decision`)
- Test: 같은 파일

**Interfaces:**
- Consumes: `judge`, `World`
- Produces: 픽스처 형식 — JSON 배열, 항목 `{"id": str, "command": str, "cwd": "{REPO}" | "{HOME}" | "{OUT}", "setup": [str], "expect": "allow" | "deny", "why": str}`.
  `setup` 은 World 준비 동작 이름 목록: `"clean_tree"`, `"dirty_before_session:{REPO}/README.md"`, `"make_worktree"`, `"no_env"`(`.gitignore` 대상인 `.env` 와 `local.sqlite` 를 지움). 실제 세션 명령 원문 금지.
  Docker 사례(컨테이너 안 `/etc` 수정, 마운트 경로 삭제, 기존 볼륨 삭제)는 실행마다 자원 이름이 바뀌므로 픽스처에 넣지 않고
  Task 8 `test_container`·`test_volume_ops` 가 담당한다.

- [ ] **Step 1: 픽스처 작성** — `false_positive.json`(기대 allow): spec 부록 C 두 묶음 전 항목 + spec §8 오탐 회귀 행 항목. 최소 id:
  `jq-arg-reset-hard`, `python-heredoc-rm`, `push-delete-then-log-format`, `rm-f-session-file`, `rm-rf-regenerable-abs-path`, `rmdir`,
  `clean-regenerable-only`(setup `no_env`), `push-force-with-lease-feature`, `dd-file-to-file`, `xargs-git-rm-cached`, `checkout-own-change`,
  `quoted-rm-in-echo`, `grep-pattern-rm`, `rm-missing-with-redirect`, `clean-dry-run`, `rm-own-scratch`,
  `systemctl-user-stop`, `killall`, `heredoc-to-cat`, `two-redirects-2>&1`.
  `false_negative.json`(기대 deny): spec 부록 B 전 항목(각 줄 하나씩, 자리표시자 적용. 단 `git stash drop(세션 전 보관본)` 은 World 의 세션 전
  보관본인 `git stash drop stash@{1}` 로, Docker 두 줄은 위 사유로 제외) + `rm -rf ~`, `rm -r {HOME}/data`,
  `git reset --hard HEAD~3`(setup `dirty_before_session:{REPO}/README.md`), `git branch -D lonely`(UNPUSHED). 각 항목 `why` 에 spec 절 번호.
- [ ] **Step 2: 시나리오·픽스처 테스트 작성**:

```python
def test_false_positive_fixtures(self):
    bad = [c["id"] for c in load("false_positive.json") if not w.judge_case(c).allow]; self.assertEqual(bad, [])
def test_false_negative_fixtures(self):
    bad = [c["id"] for c in load("false_negative.json") if w.judge_case(c).allow]; self.assertEqual(bad, [])
def test_never_ask_on(self):     # Task 9 에서 옮김: 두 픽스처 전체를 on 으로 render → "ask" 없음
    for c in load("false_positive.json") + load("false_negative.json"): self.assertNotIn('"ask"', render(w.judge_case(c)), c["id"])
def test_pr_flow_scenario(self):
    steps = ["git worktree add {OUT}/wt2 -b feat/y", "cd {OUT}/wt2 && echo a > f.txt && git add f.txt && git commit -qm a",
             "cd {OUT}/wt2 && git push -u origin feat/y", "cd {OUT}/wt2 && git commit -q --amend -m b && git push --force",
             "git worktree remove {OUT}/wt2", "git branch -D feat/y", "git push origin --delete feat/y"]
    for s in steps: self.assertTrue(w.judge_cmd(s).allow, s); w.sh(s)
def test_self_revert_scenario(self):
    w.clean_tree(); w.touch_modify("{REPO}/src/main.py")
    self.assertTrue(w.judge_cmd("git checkout -- src/main.py").allow); self.assertTrue(w.judge_cmd("git reset --hard").allow)
    w.dirty_before_session("{REPO}/README.md"); self.assertFalse(w.judge_cmd("git reset --hard").allow)
```

- [ ] **Step 3: 실패 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_bash_guard.py` · Expected: 실패한 id 목록이 나오면 그 항목은 Task 1~9 의 결함 →
  해당 작업 파일을 고친다(테스트·픽스처를 바꿔 통과시키지 않는다. 픽스처가 spec 과 어긋난 경우에만 픽스처를 고치고 사유를 커밋 메시지에)
- [ ] **Step 4: 통과 확인** — Run: `for t in shell_parse target_class policy bash_guard touch_ledger; do python3 plugins/harness-core/hooks/tests/test_$t.py || exit 1; done` · Expected: 모두 `OK`
- [ ] **Step 5: 커밋(위임 승인 D13)** — `test(harness-core): bash-guard 합격 묶음 — 오탐 회귀·누락·PR 흐름·자기 되돌리기`

### Task 12: 입구 (`auto-approve-readonly.sh`)

**Files:**
- Modify: `plugins/harness-core/hooks/scripts/auto-approve-readonly.sh:53-179` (rm 가드 ~ 기본 allow 를 `old_logic` 함수로 감싸고 뒤에 흐름 추가)
- Test: `plugins/harness-core/hooks/tests/test-bash-guard-entry.sh` (Create)

**Interfaces:**
- Consumes: `bash_guard.py --old <JSON>` (stdin payload → 최종 출력)
- Produces: 1~51행(입력 읽기, 빈 명령 종료, code-read-guard 블록)은 **그대로**. 그 뒤:

```sh
old_logic() {
    # (기존 53~179행 본문 그대로 — 출력 후 exit 0 하는 구조 유지)
}
OLD=$(old_logic)
OUT=$(printf '%s' "$INPUT" | python3 "$(dirname "$0")/bash_guard.py" --old "$OLD" 2>/dev/null) || OUT=""
if [ -n "$OUT" ]; then printf '%s\n' "$OUT"; elif [ -n "$OLD" ]; then printf '%s\n' "$OLD"; fi
exit 0
```

- [ ] **Step 1: 실패하는 테스트 작성** — `test-bash-guard-entry.sh`(기존 `test-auto-approve-readonly.sh` 의 `mkin`/`run` 관례). 테스트 폴더는 임시 루트 밖에 만든다:
  `T=$(mktemp -d -p "$HERE")`, `trap 'chmod -R u+w "$T"; rm -rf "$T"' EXIT`, `HOME=$T/home`, `XDG_STATE_HOME=$T/state`. `$T/home/data/keep.txt` 를 만든 뒤
  `$T/transcript.jsonl` 을 만들어(payload `transcript_path`) data 가 세션 전 파일이 되게 한다.
  1. **스위치 없음 동일성**: 명령 12개(`ls`, `rm -rf /tmp/x`, `rm -rf ~`, `git reset --hard`, `rmdir d`, `echo 'rm -rf ~'`, `git push -f origin main`,
     `cat a | grep b`, 빈 명령, `dd if=a of=b`, `rm -rf src`, `chmod -R 777 /`)에 대해 `HARNESS_BASH_GUARD` 미설정·`off`·`bogus` 세 경우 stdout 이 같은 바이트이고,
     변경 전 스크립트(`git show "$(git merge-base HEAD origin/main)":plugins/harness-core/hooks/scripts/auto-approve-readonly.sh` 를 임시 파일로)의 stdout 과도 같다.
  2. **on(세션 env)**: `rm -rf ~/data` → `"permissionDecision": "deny"`, `ls` → allow, 출력에 `"ask"` 없음.
  3. **on(대상 저장소 settings)**: `$T/repo`(git init, `.claude/settings.json` 의 `env.HARNESS_BASH_GUARD=on`, 세션 전 미추적 `keep.txt`)에 대해 세션 env 없이
     cwd=`$T/home` 에서 `rm $T/repo/keep.txt` → deny.
  4. **파이썬 기동 실패**: `PYTHONHOME=/nonexistent HARNESS_BASH_GUARD=on` 에서 `rm -rf ~/data`(on 이면 deny 가 나는 명령) → stdout 이 스위치 없을 때의
     같은 명령 출력(OLD)과 같다(deny 가 아님).
  5. **shadow**: `HARNESS_BASH_GUARD=shadow` 에서 `rmdir d` → stdout 이 1번 출력(OLD = ask)과 같고, `$T/state/harness-core/bash-guard.jsonl` 에
     `"mode": "shadow"` 이고 `"old_decision": "ask"` 인 줄 1개.
- [ ] **Step 2: 실패 확인** — Run: `bash plugins/harness-core/hooks/tests/test-bash-guard-entry.sh` · Expected: 2·3·5 FAIL, 1·4 PASS(4 는 구현 전에도 파이썬을 쓰지 않아 OLD 를 낸다 — 구현 후 회귀 방지용)
- [ ] **Step 3: 구현** — 위 Interfaces 대로. `set -euo pipefail` 아래에서 `OLD=$(old_logic)` 이 0 이 아닌 종료를 내지 않게(기존 본문은 항상 exit 0).
- [ ] **Step 4: 통과 확인** — Run: `bash plugins/harness-core/hooks/tests/test-bash-guard-entry.sh && for t in plugins/harness-core/hooks/tests/test-*.sh; do bash "$t" || exit 1; done && python3 plugins/harness-core/hooks/t_auto_approve_rm.py && python3 plugins/harness-core/hooks/tests/test_code_read_guard.py && shellcheck plugins/harness-core/hooks/scripts/auto-approve-readonly.sh` · Expected: 모두 PASS·종료 0
- [ ] **Step 5: 커밋(위임 승인 D13)** — `feat(harness-core): bash-guard 입구 — 현행 판정 OLD 를 bash_guard 로, 스위치 없으면 바이트 동일`

### Task 13: 전수 재생 도구와 검토 (spec SC3)

**Files:**
- Create: `plugins/harness-core/hooks/tests/tools/replay_corpus.py`

**Interfaces:**
- Consumes: `bash_guard.judge`
- Produces: CLI `replay_corpus.py --projects <dir> --out <dir> [--limit N]`. `--out` 이 이 저장소 작업 트리 안이면 거부하고 종료 2.
  재생 문맥(spec §8): payload `{"tool_name":"Bash","tool_input":{"command":c},"cwd":cwd,"session_id":None,"transcript_path":None}`,
  environ = 실제 os.environ 에 `XDG_STATE_HOME=<out>/state`, `HARNESS_BASH_GUARD=on` 덮어씀. 입력: `**/*.jsonl` 의 Bash `tool_use.input.command` 와 레코드
  `cwd`, 명령 문자열 기준 중복 제거. 출력(`--out` 아래만): `summary.json`(`{commands, errors, deny, p50_ms, p99_ms, max_ms}`), `denies.jsonl`
  (`{command(500자), cwd, reasons, context_gap}` — `context_gap` 은 거부 사유가 PRESERVED 이고 대상이 지금 없거나 세션 전/후를 지금 가릴 수 없는 경우 true),
  `errors.jsonl`.

- [ ] **Step 1: 도구 작성** — 위 계약. 1,000개마다 진행 상황을 stderr 로.
- [ ] **Step 2: 실행** — Run: `python3 plugins/harness-core/hooks/tests/tools/replay_corpus.py --projects ~/.claude/projects --out "${XDG_STATE_HOME:-$HOME/.local/state}/harness-core/replay"` · Expected: `summary.json` 의 `errors == 0`, `p99_ms <= 150`
- [ ] **Step 3: 검토** — `denies.jsonl` 을 사유별로 묶어 건수·대표 사례를 **사용자에게** 보여 준다(저장소·PR 에 원문 금지). `context_gap` 은 따로 집계.
  사용자가 부당하다고 한 거부마다 Task 1~9 의 원인 작업에 재구성 실패 테스트를 추가하고 고친 뒤 Step 2 부터 반복. 종료: 사용자 확인 "부당 거부 0건".
- [ ] **Step 4: 커밋(위임 승인 D13)** — `test(harness-core): bash-guard 전수 재생 도구` (도구 파일만. 재생 결과 커밋 금지). PR 본문에는 summary 수치만.

### Task 14: 문서·버전

**Files:**
- Modify: `plugins/harness-core/README.md`, `plugins/harness-core/.claude-plugin/plugin.json`(`"version": "0.2.0"`)
- Create: `plugins/harness-core/DECISIONS.md`, `plugins/harness-core/LIMITS.md`

- [ ] **Step 1: 작성** — README: "담는 기준" 목록에 bash-guard 모듈 추가, env 노브 표에 `HARNESS_BASH_GUARD`(off/shadow/on, 프로젝트 settings 에만, 대상
  저장소 기준 판정) 추가, `HARNESS_RM_REPO_DIRS` 행에 "bash-guard on 안정화 후 제거 예정", 상태 폴더(기록·공유 장부) 위치, 자기검증 명령을 spec §5 로 교체.
  DECISIONS.md = spec §2 표 두 개(D1~D13, 기각 대안)를 옮기고 맨 위에 spec 경로. LIMITS.md = spec §13 목록 + 샌드박스 재검토 조건.
- [ ] **Step 2: 검증** — Run: `jq empty plugins/harness-core/.claude-plugin/plugin.json && test -s plugins/harness-core/DECISIONS.md && test -s plugins/harness-core/LIMITS.md && grep -q D13 plugins/harness-core/DECISIONS.md && grep -q '동시 세션' plugins/harness-core/LIMITS.md && grep -c HARNESS_BASH_GUARD plugins/harness-core/README.md # DECISIONS.md·LIMITS.md 포함 검증` · Expected: 종료 0, 마지막 출력 1 이상
- [ ] **Step 3: 커밋(위임 승인 D13)** — `docs(harness-core): bash-guard README·DECISIONS·LIMITS, 0.2.0`

### Task 15: 죽은 등록 게이트 (`~/.claude/check-canon.sh`) — **실행 전 사용자 승인 필요(Ask first)**

**Files:**
- Modify: `/home/phantom/.claude/check-canon.sh` — 검사 함수 추가(`check_openspec_retired()` 정의 뒤), live 절의 `check_openspec_retired` 호출 다음 줄에 호출,
  `--selftest` 절에 사례 2개(마지막 NEG18 이후 번호)

**Interfaces:**
- Produces: `check_settings_plugin_root()` — `find "$SCAN_ROOT" -mindepth 3 -maxdepth 6 -type f -path '*/.claude/settings*.json' -not -path '*/node_modules/*'`
  각 파일(프로젝트 루트 = `${f%/.claude/*}` 가 `is_ignored` 면 건너뜀)에서 `jq -r '[.hooks // {} | .[] | .[] | .hooks[]? | .command // empty] | .[]'` 결과에
  `${CLAUDE_PLUGIN_ROOT}` 가 있으면 `echo "★ [hooks] 죽은 등록: <파일> — \${CLAUDE_PLUGIN_ROOT} 는 플러그인 hooks.json 에서만 확장된다(이 등록은 항상 실패)"`, `BAD=$((BAD+1))`.

- [ ] **Step 1: 사용자 승인 확인과 백업** — git 저장소 밖 파일이라 `cp ~/.claude/check-canon.sh ~/.claude/check-canon.sh.bak-2026-10-14`.
- [ ] **Step 2: 실패 사례 추가** — selftest 에 `NEG19`(픽스처 `$T/root/p1/.claude/settings.json` 에 해당 command → `run` 1, 출력에 `죽은 등록`)·`NEG19b`
  (`bash .claude/hooks/x.sh` → 0). Run: `~/.claude/check-canon.sh --selftest` · Expected: NEG19 `✗`
- [ ] **Step 3: 구현** — 위 Interfaces. Run: `~/.claude/check-canon.sh --selftest` · Expected: 전 사례 `✓`
- [ ] **Step 4: live 확인** — Run: `~/.claude/check-canon.sh 2>/dev/null | grep '죽은 등록'` · Expected: Task 16 전 4줄(agent, bounty, bounty-agoda, bounty-wordpress)
- [ ] **Step 5: 백업 제거** — Task 16 완료·live 0줄 확인 후 사용자 확인을 받아 `.bak` 삭제(git 밖 파일이라 커밋 없음)

### Task 16: 죽은 등록 제거 4곳 — **실행 전 사용자 승인 필요(Ask first)**

**Files (각각 다른 저장소·브랜치):**
- Modify: `/home/phantom/agent/.claude/settings.json`, `/home/phantom/bounty/.claude/settings.json`,
  `/home/phantom/orca/workspaces/bounty/bounty-agoda/.claude/settings.json`, `/home/phantom/orca/workspaces/bounty/bounty-wordpress/.claude/settings.json`

- [ ] **Step 1: 사용자 승인과 상태 확인** — 각 저장소 `git -C <repo> status --short -- .claude/settings.json` 이 깨끗한지(미커밋 변경이 있으면 멈추고 보고).
- [ ] **Step 2: 제거** — `hooks.PreToolUse[].hooks[]` 중 command 가 `auto-approve-readonly.sh` 를 가리키는 항목만 제거(그룹의 다른 훅 유지, 빈 그룹 제거),
  `json.dump(…, ensure_ascii=False, indent=2)` + 원래 끝 줄바꿈. Run: `jq empty <파일>`
- [ ] **Step 3: 검증** — Run: `~/.claude/check-canon.sh 2>/dev/null | grep -c '죽은 등록'` · Expected: `0`
- [ ] **Step 4: 커밋(사용자 승인 후 저장소마다)** — `git -C <repo> commit -m "chore(settings): 동작하지 않던 auto-approve 등록 제거 — \${CLAUDE_PLUGIN_ROOT} 는 플러그인 훅에서만 확장(harness-core 가 이미 적용)" -- .claude/settings.json`

---

## PR 전 확인과 병합 이후 운영 (spec §9·§11 — 사용자 승인 단계)

0. PR 전: spec §5 의 전체 명령을 worktree 에서 실행해 전부 통과 확인(전수 재생은 Task 13 결과로 갈음).
1. PR(본문: spec 링크, 재생 summary 수치, 원문 없음) → 병합 → `git -C ~/tools/claude-project-config pull --ff-only`. 스위치가 없으므로 출력은 현행과 같다.
2. 사용자와 shadow 대상 프로젝트 목록 확정 → 각 프로젝트 `.claude/settings.json` 의 `env` 에 `"HARNESS_BASH_GUARD": "shadow"`(orca 작업공간은 브랜치별 파일).
3. 최소 3일·Bash 5,000회 후 `bash-guard.jsonl` 의 shadow 불일치 검토 → 판정기 오판은 재구성 테스트 추가 후 수정(새 PR).
4. 사용자 승인 → 같은 프로젝트들 `on`. 2주 무사고 → 기존 로직·`t_auto_approve_rm.py` 제거와 `HARNESS_RM_REPO_DIRS` 정리 PR(기본값 on 여부도 그때 결정).
