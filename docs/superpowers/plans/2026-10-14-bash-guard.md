# bash-guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** harness-core 의 Bash PreToolUse 판정을 "명령 글자 정규식"에서 "셸 구조 해석 + 대상 성질(출처·복구 가능성)
판정"으로 바꿔, 되돌릴 수 없는 손실만 거부하고 그 외에는 개입하지 않게 한다(ask 출력 0).

**Architecture:** 입구 `auto-approve-readonly.sh` 가 스위치 `HARNESS_BASH_GUARD`(off/shadow/on)로 기존 로직과 새 판정기
`bash_guard.py` 를 고른다. 새 판정기는 자체 어휘 분석기(`shell_parse.py`)로 명령 단위를 만들고, 대상 경로를
git·생성 시각·세션 장부·Docker 마운트로 분류(`target_class.py`)한 뒤, 작업 × 분류 정책표(`policy.py`)로 판정한다.
Write·Edit 직전 장부 훅(`touch-ledger.py`)이 "세션 전 파일"을 기록해 생성 시각 허점을 막는다.

**Tech Stack:** Python 3.10+ 호환(실행 3.12.3) 표준 라이브러리만, `unittest`, POSIX sh/bash, git, GNU stat 9.4, (선택) docker.

**Spec:** `docs/superpowers/specs/2026-10-14-bash-guard-design.md` — 이 계획의 모든 정책 값의 정본. 계획과 spec 이
다르면 spec 이 이긴다. 구현 중 spec 이 틀렸다고 판단되면 구현을 멈추고 spec 부터 고친다.

## Global Constraints

- 작업 위치: worktree `~/tools/claude-project-config.wt`, 브랜치 `feat/bash-guard`. 운영 clone(`~/tools/claude-project-config`)은
  절대 수정·브랜치 전환하지 않는다(directory 소스라 그 파일이 곧 모든 세션의 실행 코드).
- Python: `from __future__ import annotations`, 3.10 호환 문법(3.12 전용 문법 금지), 표준 라이브러리만, `dataclass`·타입 힌트.
  `shlex` 사용 금지(spec §3.3-1).
- 출력: `json.dumps` 로만 만든 한 줄 JSON, 종료 코드 0, `permissionDecision` 은 `"allow"` 또는 `"deny"` 뿐(**`"ask"` 금지**).
- 거부 사유 형식(spec §3.2): 줄마다 `[bash-guard] 거부: <작업> <대상> — <분류 설명>. 대안: <대안>`, 마지막 줄
  `이 판정을 우회하지 말 것. 대안이 맞지 않으면 작업을 멈추고 사용자에게 보고하라.` 첫 줄에만 `[bash-guard] ` 접두.
- 판정기는 읽기 전용. 쓰는 곳은 상태 폴더 `${XDG_STATE_HOME:-$HOME/.local/state}/harness-core/` 아래 `bash-guard.jsonl`(10MB 초과 시
  `.1` 로 한 번 순환)과 `ledger/<session_id>.tsv`(수정 7일 지난 장부 삭제)뿐.
- 시간: 판정기 내부 마감 `BUDGET_SECONDS = 5.0`, 외부 명령마다 `timeout=min(2.0, 남은 시간)`. `hooks.json` Bash timeout 10 유지,
  touch-ledger timeout 5.
- 폴더 순회 상한 `DIR_ENTRY_CAP = 2000`. 생성 시각은 `stat -c '%.9W %n'`(값 0 = 읽을 수 없음).
- 스위치 `HARNESS_BASH_GUARD` 값: `off`(기본)·`shadow`·`on`, 그 외 값은 `off`. 스위치는 프로젝트 settings 에만 둔다(전역 금지).
- **공개 저장소**: 실제 세션 명령 원문·세션 기록·상태 폴더 파일을 픽스처·커밋·PR 에 넣지 않는다. 픽스처 경로는 테스트가 만든
  가상 세계(`{HOME}`·`{REPO}` 등 자리표시자)만 쓴다.
- 테스트: `unittest`, 파일 단독 실행(`python3 <파일>`), 개별 실행 `python3 <파일> -k <이름>`. 테스트는 `HOME`·`TMPDIR`·`PATH`·
  `XDG_STATE_HOME` 을 가상 세계 값으로 덮은 `environ` 을 넘기고, 실제 홈·상태 폴더를 건드리지 않는다.
- 커밋: 경로 지정 커밋 `git commit -m "<msg>" -- <Files>`. 메시지 끝에 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- 각 작업 끝 공통 검증: `python3 -m py_compile <바뀐 .py>`, `ruff check plugins/harness-core/hooks`, 바뀐 .sh 는 `shellcheck`.

## Review Focus

spec 이 요구하지만 어느 작업의 기본 테스트도 직접 겨누지 않아 사용자를 가장 먼저 물 가능성이 큰 입력 다섯 가지. 각 줄의
테스트는 담당 작업에 추가돼 있다.

1. **거대한 명령**(수백 KB heredoc 으로 파이썬 스크립트를 넘기는 흔한 형태) — 어휘 분석이 선형이어서 200KB 도 50ms 안에 끝나야
   한다. → Task 1 `test_large_heredoc_is_linear`
2. **공백·한글이 든 경로**(`rm -f "보고서 초안.md"`) — 세션 생성이면 허용, 세션 전이면 거부. → Task 5 `test_unicode_space_path`
3. **원격 HEAD 가 없는 저장소·원격 없는 저장소**의 push — 기본 브랜치를 `main`·`master` 로 대체 판정하고, 원격이 없으면 push 는
   판정 대상이 아님. → Task 8 `test_default_branch_fallback`
4. **서브에이전트 여러 개가 같은 장부에 동시에 기록** — 줄이 섞이거나 깨지지 않아야 한다. → Task 4 `test_ledger_concurrent_append`
5. **읽을 수 없는 하위 폴더·심볼릭 링크 순환이 있는 폴더 삭제** — 순회 오류는 확정 불가(거부)로, 무한 순회 없이. → Task 5
   `test_unreadable_subdir_is_unresolved`

---

## 파일 구조

| 파일 | 책임 | 작업 |
|---|---|---|
| `plugins/harness-core/hooks/scripts/shell_parse.py` | 어휘 분석·명령 단위 분해·래퍼 제거·cd/변수 추적·단어 확장·재귀·컨테이너 문맥 | 1·2·3 |
| `plugins/harness-core/hooks/scripts/ledger.py` | 세션 장부 저장(읽기·추가·정리) | 4 |
| `plugins/harness-core/hooks/scripts/target_class.py` | 대상 성질 조회: 세션 시작·생성 시각·정규화·7분류·작업 영역·git·find 미리보기·docker 조회·장부 기록 규칙 | 4·5·6 |
| `plugins/harness-core/hooks/scripts/policy.py` | 작업 식별과 작업 × 분류 판정표 → `Finding` | 7·8 |
| `plugins/harness-core/hooks/scripts/bash_guard.py` | 진입점: 입력·조립·실패 정책·시간 예산·출력·기록·shadow | 9 |
| `plugins/harness-core/hooks/scripts/touch-ledger.py` | Write/Edit/NotebookEdit 장부 훅 | 10 |
| `plugins/harness-core/hooks/hooks.json` | touch-ledger 등록 | 10 |
| `plugins/harness-core/hooks/scripts/auto-approve-readonly.sh` | 스위치 분기(기존 로직을 `old_logic` 함수로) | 12 |
| `plugins/harness-core/hooks/tests/_world.py` | 테스트용 가상 세계 빌더·가짜 docker | 4(생성)·5~11(확장) |
| `plugins/harness-core/hooks/tests/test_shell_parse.py` | 해석기 단위 | 1·2·3 |
| `plugins/harness-core/hooks/tests/test_target_class.py` | 장부·분류·조회 단위 | 4·5·6 |
| `plugins/harness-core/hooks/tests/test_policy.py` | 정책 단위 | 7·8 |
| `plugins/harness-core/hooks/tests/test_bash_guard.py` | 종단·합격 묶음·시나리오 | 9·11 |
| `plugins/harness-core/hooks/tests/fixtures/false_positive.json`, `false_negative.json` | 재구성 사례 | 11 |
| `plugins/harness-core/hooks/tests/test_touch_ledger.py` | 장부 훅 | 10 |
| `plugins/harness-core/hooks/tests/test-bash-guard-entry.sh` | 입구 스위치 | 12 |
| `plugins/harness-core/hooks/tests/tools/replay_corpus.py` | 로컬 전수 재생 | 13 |
| `plugins/harness-core/README.md`, `DECISIONS.md`, `LIMITS.md`, `.claude-plugin/plugin.json` | 문서·버전 0.2.0 | 14 |
| `~/.claude/check-canon.sh` (저장소 밖) | 죽은 등록 게이트 | 15 (Ask first) |
| 4개 프로젝트 `.claude/settings.json` (다른 저장소) | 죽은 등록 제거 | 16 (Ask first) |

모듈 간 import: 테스트와 진입점은 `sys.path.insert(0, <scripts 폴더>)` 후 `import shell_parse, target_class, policy, ledger`.
의존 방향 `bash_guard → policy → target_class → ledger`, `policy → shell_parse`, `target_class → shell_parse`(데이터 타입만). 순환 금지.

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
      def is_quoted(self) -> bool: ...   # 조각 중 quote != "" 가 하나라도 있으면 True
  @dataclass(frozen=True)
  class Token:
      kind: str                          # "word" | "op" | "redir"
      word: Word | None = None           # kind == "word"
      op: str | None = None              # kind == "op": ";" "&&" "||" "|" "|&" "&" "\n" "(" ")" ";;"
                                         # kind == "redir": ">" ">>" ">|" "&>" "&>>" "<" "<>" ">&" "<&" "<<<" "<<" "<<-"
      fd: int | None = None              # redir 의 왼쪽 숫자(연산자에 붙어 있을 때만)
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
    self.assertEqual(t[2].word.parts, (Part("$HOME", "'"),))
    self.assertEqual(t[3].word.parts, (Part("$HOME", '"'),))
def test_redirect_attached(self):
    t = lex("echo a>b 2>/dev/null")
    self.assertEqual(words(t), ["echo", "a"])
    self.assertEqual(redirs(t), [(">", None, "b"), (">", 2, "/dev/null")])
def test_fd_needs_adjacency(self):
    t = lex("echo 2 >x")
    self.assertEqual(words(t), ["echo", "2"]); self.assertEqual(redirs(t), [(">", None, "x")])
def test_fd_dup_is_not_separator(self):
    t = lex("echo a 2>&1 >out")
    self.assertNotIn("&", [x.op for x in t if x.kind == "op"])
    self.assertEqual(redirs(t), [(">&", 2, "1"), (">", None, "out")])
def test_operators(self):
    t = lex("a && b || c; d | e |& f & g")
    self.assertEqual([x.op for x in t if x.kind == "op"], ["&&", "||", ";", "|", "|&", "&"])
def test_comment(self):
    self.assertEqual(words(lex("echo x # rm -rf ~")), ["echo", "x"])
def test_substitution_stays_in_word(self):
    t = lex('echo "$(rm -rf "a b")" `ls`')
    self.assertEqual(words(t), ["echo", '$(rm -rf "a b")', "`ls`"])
def test_heredoc_body(self):
    t = lex("cat <<'EOF' > f\nrm -rf ~\nEOF\necho done")
    hd = [x for x in t if x.kind == "redir" and x.op == "<<"][0]
    self.assertEqual(hd.body, "rm -rf ~"); self.assertTrue(hd.target.is_quoted())
    self.assertEqual(words(t), ["cat", "echo", "done"])
def test_heredoc_dash_strips_tabs(self):
    t = lex("cat <<-EOF\n\tx\n\tEOF\n")
    self.assertEqual([x.body for x in t if x.kind == "redir"], ["\tx"])
def test_unterminated(self):
    for s in ['echo "a', "echo 'a", "echo $(a", "cat <<EOF\nx\n"]:
        with self.assertRaises(LexError): lex(s)
def test_large_heredoc_is_linear(self):           # Review Focus 1
    body = "print('rm -rf /')\n" * 12000          # 약 200KB
    t0 = time.perf_counter(); lex("python3 - <<'PY'\n" + body + "PY\n")
    self.assertLess(time.perf_counter() - t0, 0.05)
```

- [ ] **Step 2: 실패 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_shell_parse.py` · Expected: `ModuleNotFoundError: No module named 'shell_parse'`
- [ ] **Step 3: `lex(src: str) -> list[Token]` 구현** — 문자 인덱스 하나로 한 번 훑는 상태 기계. 단어 안 `$(`·`${`·`$((`·백틱은
  깊이 카운터와 따옴표 상태를 유지하며 닫힐 때까지 같은 조각에 담는다. heredoc 은 `<<` 를 만나면 (구분자, 따옴표 여부, `-` 여부)를
  대기 목록에 넣고, 다음 `\n` 을 지날 때 대기 목록 순서대로 본문 줄을 소비한다. fd 숫자는 직전 단어가 숫자만이고 연산자와 사이에
  공백이 없을 때만 fd 로 옮긴다.
- [ ] **Step 4: 통과 확인** — 같은 명령 · Expected: `OK`
- [ ] **Step 5: 커밋** — `feat(harness-core): bash-guard 어휘 분석기 — 따옴표 종류·리다이렉트·heredoc 보존`

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
      kind: str = "host"                     # "host" | "container"
      container: str | None = None           # 컨테이너 이름·ID 또는 compose 서비스 이름
      launcher: str | None = None            # "exec" | "run" | "compose-exec" | "compose-run"
      mounts: tuple[Mount, ...] | None = None  # run 계열은 인자에서 정적으로, exec 계열은 None(Task 6 조회)
      project_dir: str | None = None         # compose 계열: 호스트 cwd
  HOST = Context()
  @dataclass
  class Redirect:
      op: str; fd: int | None; target: Word | None; body: str | None
  @dataclass
  class Segment:
      name: str                      # 래퍼 제거 후 명령 이름(basename, 앞 \ 제거). 단어가 없으면 ""
      argv: list[Word]               # argv[0] = 명령 단어
      redirects: list[Redirect]
      cwd: str | None                # 이 단위 실행 시점 현재 폴더(모르면 None)
      env: dict[str, str | None]     # 확정 변수(None = 값 미확정)
      context: Context = HOST
      depth: int = 0                 # 재귀 깊이(0 = 최상위)
      via_xargs: bool = False        # xargs 가 실행하는 명령(대상은 입력에서 옴)
  @dataclass
  class ParseResult:
      segments: list[Segment]
      error: str | None = None
  def parse(command: str, cwd: str | None, env: Mapping[str, str], context: Context = HOST) -> ParseResult: ...
  ```
  `env` 인자는 호출자 환경(os.environ 류). 단위의 `env` 초기값은 그중 `HOME`·`TMPDIR`·`USER` 와 `PWD`(= cwd).

- [ ] **Step 1: 실패하는 테스트 작성** — `class ParseTest`:

```python
def segs(cmd, cwd="/w", env={"HOME": "/h"}): return parse(cmd, cwd, env).segments
def names(cmd): return [s.name for s in segs(cmd)]

def test_split_and_cd_tracking(self):
    s = segs("cd /a && rm x; cd b; rm y")
    self.assertEqual([(x.name, x.cwd) for x in s if x.name == "rm"], [("rm", "/a"), ("rm", "/a/b")])
def test_subshell_restores(self):
    s = segs("(cd /a; rm x); rm y")
    self.assertEqual([x.cwd for x in s if x.name == "rm"], ["/a", "/w"])
def test_cd_unknown(self):
    self.assertIsNone([x for x in segs("cd -; rm y") if x.name == "rm"][0].cwd)
    self.assertEqual([x for x in segs("cd; rm y") if x.name == "rm"][0].cwd, "/h")
def test_assignments(self):
    s = segs('X=/a; export Y=/b; declare -x Z=$(date); rm "$X"')
    rm = s[-1]; self.assertEqual(rm.env["X"], "/a"); self.assertEqual(rm.env["Y"], "/b"); self.assertIsNone(rm.env["Z"])
def test_wrappers_stripped(self):
    for c in [r"\rm -rf x", "/bin/rm -rf x", "sudo -u root rm -rf x", "env -i A=1 rm -rf x", "command rm x",
              "timeout 5 rm x", "nice -n 5 rm x", "nohup rm x", "time -p rm x", "stdbuf -oL rm x",
              "flock /tmp/l rm x", "doas rm x", "exec rm x", "builtin rm x", "ionice -c3 rm x", "chronic rm x"]:
        self.assertEqual(names(c), ["rm"], c)
def test_git_dash_c(self):
    s = segs("git -C /r reset --hard")[0]
    self.assertEqual((s.name, s.cwd, [w.literal() for w in s.argv]), ("git", "/r", ["git", "reset", "--hard"]))
def test_redirects_removed_from_argv(self):
    s = segs("rm -rf build 2>/dev/null")[0]
    self.assertEqual([w.literal() for w in s.argv], ["rm", "-rf", "build"]); self.assertEqual(s.redirects[0].fd, 2)
def test_parse_error_reported(self):
    self.assertIsNotNone(parse('rm -rf "x', "/w", {}).error)
```

- [ ] **Step 2: 실패 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_shell_parse.py -k ParseTest` · Expected: `ImportError`/`AttributeError: parse`
- [ ] **Step 3: `parse(...)` 구현(재귀·확장·컨테이너 제외)** — 토큰을 연산자로 끊어 단위를 만들고, `(` 진입 시 (cwd, env) 스택을
  밀고 `)` 에서 복원. 단위 맨 앞 `NAME=값` 만 있는 단위는 env 갱신(값에 `$(`·백틱이 있으면 None), `export|declare|typeset|local`
  은 옵션 무시하고 `NAME=값` 반영. `cd`/`pushd` 는 인자를 Task 3 `expand` 없이 리터럴로 처리하되 `~`·`$HOME` 만 env 로 풀고
  나머지 변수·치환이 있으면 cwd=None(Task 3 에서 `expand` 로 교체). `popd`·`cd -` → None. 래퍼 표(spec §3.3-6)를 반복 적용:
  `sudo`(값 옵션 `-u -g -h -p -C -D -r -t -U`), `env`(`-i` `-u X` `-C X` `NAME=val`), `timeout`(옵션 `-s X -k X` + DURATION),
  `nice`(`-n N`), `ionice`(`-c X -n X -p X`), `stdbuf`(`-i/-o/-e X`), `flock`(옵션 + 파일), `time`(`-p`), 나머지는 단어 하나.
  `git` 은 `-C DIR`(여러 번 가능)을 cwd 에 반영하고 argv 에서 뺀다.
- [ ] **Step 4: 통과 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_shell_parse.py` · Expected: `OK`
- [ ] **Step 5: 커밋** — `feat(harness-core): bash-guard 명령 단위 분해 — cd·변수·래퍼 추적`

### Task 3: 단어 확장·재귀·컨테이너 문맥 (`shell_parse` 2부)

**Files:**
- Modify: `plugins/harness-core/hooks/scripts/shell_parse.py`
- Test: `plugins/harness-core/hooks/tests/test_shell_parse.py`

**Interfaces:**
- Consumes: Task 2 `parse`, `Segment`, `Context`, `Mount`
- Produces:
  ```python
  SHELLS = {"bash", "sh", "zsh", "dash"}
  def expand(word: Word, seg: Segment) -> list[str] | None: ...
      # None = 확정 불가. 반환 경로는 절대경로(상대경로는 seg.cwd 기준; cwd None 이면 None).
  def literal_args(seg: Segment) -> list[str] | None: ...   # 옵션 판별용: 따옴표 제거·확장 없는 리터럴 인자 목록
  ```
  `parse` 가 재귀로 만든 안쪽 단위는 같은 `segments` 목록에 `depth+1` 로 추가된다(바깥 단위 바로 뒤).

- [ ] **Step 1: 실패하는 테스트 작성** — `class ExpandTest`, `class RecursionTest`, `class ContainerTest`:

```python
def ex(word_src, cwd="/w", env={"HOME": "/h"}):
    s = parse("x " + word_src, cwd, env).segments[0]; return expand(s.argv[1], s)

def test_expand_basic(self):
    self.assertEqual(ex("~/x"), ["/h/x"]); self.assertEqual(ex('"$HOME/x"'), ["/h/x"])
    self.assertEqual(ex("'$HOME'"), ["/w/$HOME"]); self.assertEqual(ex("$(pwd)/x"), ["/w/x"])
    self.assertEqual(ex("`pwd`/x"), ["/w/x"]); self.assertEqual(ex("$PWD/x"), ["/w/x"])
    self.assertEqual(ex("{a,b}.txt"), ["/w/a.txt", "/w/b.txt"]); self.assertEqual(ex("a/../b"), ["/w/a/../b"])
def test_expand_unresolved(self):
    for w in ["$(date)", "${X:-a}", "$NOPE/x", "~bob/x", "`hostname`"]:
        self.assertIsNone(ex(w), w)
    self.assertIsNone(ex("rel", cwd=None))
def test_glob(self):  # 임시 폴더에 a1.log a2.log 생성 후
    self.assertEqual(ex("*.log", cwd=d), [f"{d}/a1.log", f"{d}/a2.log"])
    self.assertEqual(ex("*.none", cwd=d), [f"{d}/*.none"])          # 일치 없음 → 리터럴
    self.assertEqual(ex('"*.log"', cwd=d), [f"{d}/*.log"])           # 따옴표 안은 전개 안 함

def inner(cmd): return [(s.name, s.depth, s.cwd) for s in parse(cmd, "/w", {"HOME": "/h"}).segments if s.depth > 0]
def test_recursion(self):
    self.assertEqual(inner("bash -lc 'cd /a; rm -rf x'"), [("cd", 1, "/w"), ("rm", 1, "/a")])
    self.assertEqual(inner('eval "rm -rf x"'), [("rm", 1, "/w")])
    self.assertEqual(inner("sh <<EOF\nrm -rf x\nEOF"), [("rm", 1, "/w")])
    self.assertEqual(inner("echo 'rm -rf x' | sh"), [("rm", 1, "/w")])
    self.assertEqual(inner("printf 'rm -rf x\\n' | bash"), [("rm", 1, "/w")])
    self.assertEqual(inner("echo $(rm -rf x)"), [("rm", 1, "/w")])
    self.assertEqual(inner("curl -s u | sh"), [])                        # 내용 모름 → 해석 안 함(spec §13)
    self.assertEqual(inner("python3 -c 'import os'"), [])
def test_xargs(self):
    s = [x for x in parse("ls | xargs -0 rm -f", "/w", {}).segments if x.via_xargs][0]
    self.assertEqual(s.name, "rm")

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
    self.assertEqual((s.context.launcher, s.context.container, s.context.project_dir), ("compose-exec", "web", "/w"))
    self.assertEqual(ctx_of("docker-compose exec web rm -rf /x")[0].context.launcher, "compose-exec")
    self.assertEqual(ctx_of("podman exec c rm -rf /x")[0].context.launcher, "exec")
```

- [ ] **Step 2: 실패 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_shell_parse.py` · Expected: `ImportError: expand` 등 FAIL
- [ ] **Step 3: 구현** — `expand`: 조각별로 처리. 따옴표 없는 첫 조각의 `~`/`~/` → `HOME`(`~user` → None). 따옴표 없음·`"` 조각의
  `$NAME`/`${NAME}` → `seg.env`(없거나 None → 전체 None), `$PWD`·`$(pwd)`·`` `pwd` `` → `seg.cwd`, 그 외 `$(`·백틱·`${…연산자…}`·
  `$((` → None. 따옴표 없는 조각의 `{a,b}`(쉼표 있고 중첩 없는 것만) 전개, `*?[` 는 `glob.glob`(점 파일은 패턴이 `.` 로 시작할 때만)
  정렬 결과, 일치 없으면 리터럴. 상대경로는 `os.path.join(seg.cwd, …)`(정규화는 Task 4 의 몫이라 여기선 하지 않음).
  Task 2 의 cd 임시 처리를 `expand` 로 교체. 재귀: spec §3.3-7 그대로(`-c` 는 `-[a-zA-Z]*c` 옵션 묶음의 다음 단어,
  heredoc 은 셸 명령의 `<<` body, 파이프 앞 단위가 `echo`·`printf`(인자 전부 확장 가능한 리터럴)·`cat`+heredoc 이면 그 텍스트;
  `printf` 는 `\n` 만 줄바꿈으로 해석). 명령 치환은 단어 조각 안의 `$(…)`·백틱 내용을 재귀 parse. docker/podman/docker-compose:
  전역 옵션(`-H X`, `--context X`, `-c X`, `--log-level X`) 건너뛰고 하위명령 `exec|run|compose exec|compose run` 의 옵션을 표로
  처리 — 값 옵션: exec `-e --env --env-file -u --user -w --workdir --detach-keys`, run 위 + `-v --volume --mount --name -p --publish
  --network --entrypoint -l --label --platform --hostname -h --add-host --device --cpus -m --memory --user --workdir`, compose 전역
  `-f --file -p --project-name --project-directory --env-file --profile`, compose exec/run `-e -u -w --index`. `--opt=값` 형태는
  값 내장. 그 외 `-`로 시작하는 것은 값 없는 플래그. `-v SRC:DST[:mode]` 에서 SRC 가 `/`·`.`·`~`·`$` 로 시작하면 bind(확장 결과
  절대경로), 아니면 volume. 컨테이너 안 명령이 셸 `-c` 면 재귀, 아니면 그 argv 자체를 `context=container` 단위로.
- [ ] **Step 4: 통과 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_shell_parse.py` · Expected: `OK`
- [ ] **Step 5: 커밋** — `feat(harness-core): bash-guard 단어 확장·재귀 해석·컨테이너 문맥`

### Task 4: 장부·세션 시각·경로 정규화 (`ledger.py`, `target_class.py` 1부)

**Files:**
- Create: `plugins/harness-core/hooks/scripts/ledger.py`, `plugins/harness-core/hooks/scripts/target_class.py`,
  `plugins/harness-core/hooks/tests/_world.py`
- Test: `plugins/harness-core/hooks/tests/test_target_class.py`

**Interfaces:**
- Produces (`ledger.py`):
  ```python
  KIND_PRE_SESSION = "pre-session"; KIND_PRE_DIRTY = "pre-dirty"
  PRUNE_SECONDS = 7 * 24 * 3600
  def state_dir(environ: Mapping[str, str]) -> Path: ...   # ${XDG_STATE_HOME:-$HOME/.local/state}/harness-core
  class Ledger:
      def __init__(self, session_id: str | None, environ: Mapping[str, str]) -> None: ...
      def kinds(self, path: str) -> set[str]: ...          # session_id None → 빈 집합
      def record(self, path: str, kind: str) -> None: ...  # 이미 있으면 무시. 한 줄 = os.write 1회(O_APPEND). 첫 기록 때 7일 지난 장부 삭제
  ```
- Produces (`target_class.py` 1부):
  ```python
  @dataclass
  class Ctx:
      environ: Mapping[str, str]
      session_start: float | None
      ledger: Ledger
      deadline: float                    # time.monotonic() 기준
      def remaining(self) -> float: ...
  FIXED_SCRATCH_ROOTS: tuple[str, ...] = ("/tmp", "/var/tmp")   # 테스트가 덮어쓸 수 있는 모듈 상수
  def make_ctx(payload: dict, environ: Mapping[str, str], budget: float) -> Ctx: ...
  def session_start(transcript_path: str | None, environ: Mapping[str, str]) -> float | None: ...
  def births(paths: list[str], ctx: Ctx) -> dict[str, float]: ...   # 값 0·실패 경로는 키 없음
  def run(cmd: list[str], ctx: Ctx, cwd: str | None = None) -> subprocess.CompletedProcess | None: ...
      # 남은 시간 ≤ 0 이면 실행하지 않고 None. timeout=min(2.0, 남은 시간). env=ctx.environ. 예외·타임아웃 → None
  def normalize(path: str, trailing_slash: bool) -> str: ...
  def scratch_roots(ctx: Ctx) -> list[str]: ...
  def is_scratch(path: str, ctx: Ctx) -> bool: ...     # 루트 '아래'만 True(루트 자체 False)
  def is_scratch_root(path: str, ctx: Ctx) -> bool: ...
  def protected_name(path: str) -> bool: ...
  ```
- Produces (`tests/_world.py`): `class World` — `tempfile` 아래 `home/`, `home/proj`(git 저장소, 로컬 bare 원격 `origin`,
  `origin/HEAD → main`), 세션 전 파일들, `transcript.jsonl`(세션 시작), 세션 파일들을 만들고 `environ`(HOME·TMPDIR 제거·PATH·
  XDG_STATE_HOME·GIT_* 작성자 값)과 `payload(command, cwd=None)`·`edit_payload(path)`·`ctx(budget=5.0, transcript=<기본>)` 를 돌려준다.
  `fmt(s)` 는 자리표시자 `{HOME}`(세계 홈) `{REPO}`(저장소) `{SCRATCH}`(세계 임시 루트) `{OUT}`(저장소 밖·임시 루트 밖 작업 폴더)
  `{WT}`(Task 8 이 만드는 linked worktree)를 치환. 세계를 만들 때 `target_class.FIXED_SCRATCH_ROOTS` 를 `(<세계>/scratch,)` 로 바꾸고 `close()` 에서 복원한다
  (세계가 실제 `/tmp` 아래 있어도 전부 임시 폴더로 분류되지 않게). 파일 생성 순서: 세션 전 파일 → 20ms → transcript → 20ms → 세션 파일.
  세계 목록(이후 작업이 쓰는 이름): 세션 전 `home/data/a.txt`·`home/data/db.sqlite`·`home/data/important.csv`·`home/notes.md`·
  `home/.ssh/id_ed25519`, 저장소 `src/main.py`(추적)·`README.md`(추적)·`.gitignore`(`build/`)·`build/out.o`(무시)·
  `notes_presession.txt`(미추적)·`.env`; 세션 파일 `home/proj/src/probe.ts`·`home/proj/out/`·`home/scratch/s1/x.txt`.

- [ ] **Step 1: 실패하는 테스트 작성** — `class LedgerTest`, `class BasicsTest`:

```python
def test_ledger_roundtrip_and_dedupe(self):
    L = Ledger("s1", env); L.record("/a b/c", KIND_PRE_SESSION); L.record("/a b/c", KIND_PRE_SESSION)
    self.assertEqual(L.kinds("/a b/c"), {KIND_PRE_SESSION}); self.assertEqual(len(ledger_file.read_text().splitlines()), 1)
def test_ledger_concurrent_append(self):            # Review Focus 4
    # 두 프로세스가 같은 session_id 로 서로 다른 경로 500개씩 record → 1000줄, 모든 줄이 '경로\t종류\t시각' 3칸
def test_ledger_prune(self):  # 수정 시각 8일 전으로 만든 다른 장부 파일이 첫 record 뒤 사라짐
def test_session_start(self):
    self.assertAlmostEqual(session_start(w.transcript, w.environ), stat_birth(w.transcript), places=3)
    self.assertIsNone(session_start(None, w.environ)); self.assertIsNone(session_start("/nope", w.environ))
def test_births_skips_zero(self):
    self.assertEqual(target_class._parse_stat("0.000000000 /p\n12.5 /q\n"), {"/q": 12.5})
def test_run_respects_deadline(self):
    ctx = w.ctx(budget=0); self.assertIsNone(run(["true"], ctx))
def test_normalize(self):
    self.assertEqual(normalize("/a/b/../c", False), "/a/c")
    # 부모가 심볼릭 링크면 실제 경로로, 대상 자체가 링크면 '/' 없을 때 링크 경로 유지·있을 때 링크 대상
def test_scratch(self):
    self.assertTrue(is_scratch(f"{w.scratch}/s1/x.txt", ctx)); self.assertFalse(is_scratch(w.scratch, ctx))
    self.assertTrue(is_scratch_root(w.scratch, ctx)); self.assertTrue(is_scratch(f"{w.home}/.cache/x", ctx))
    self.assertTrue(is_scratch("/mnt/c/Users/u/AppData/Local/Temp/x", ctx))
def test_protected_name(self):
    for p in ["/r/.git", "/r/.git/config", "/r/.env", "/r/.env.prod", "/r/.claude/settings.local.json",
              "/h/.ssh/config", "/h/k.pem", "/h/id_ed25519", "/h/.aws/credentials", "/h/.netrc"]:
        self.assertTrue(protected_name(p), p)
    for p in ["/r/.env.example", "/r/.env.sample", "/r/.env.template", "/r/src/env.py", "/r/.github/x"]:
        self.assertFalse(protected_name(p), p)
```

- [ ] **Step 2: 실패 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_target_class.py` · Expected: `ModuleNotFoundError`
- [ ] **Step 3: 구현** — `births` 는 경로 목록을 한 번의 `stat -c '%.9W %n' -- …` 로(없는 경로는 stat 이 오류 줄을 내므로 stderr 무시,
  `_parse_stat(stdout) -> dict[str, float]` 로 파싱, 0 은 제외). 임시 루트 = `FIXED_SCRATCH_ROOTS` + `$TMPDIR`(있으면) +
  `$HOME/.cache` + `glob('/mnt/c/Users/*/AppData/Local/Temp')` + `/mnt/c/Windows/Temp`. `protected_name` 은 spec §3.4 표 2행 그대로.
  `make_ctx` 는 `payload["transcript_path"]`·`payload["session_id"]` 로 `session_start`·`Ledger` 를 만들고 `deadline = monotonic() + budget`.
- [ ] **Step 4: 통과 확인** — 같은 명령 · Expected: `OK`
- [ ] **Step 5: 커밋** — `feat(harness-core): bash-guard 장부·세션 시각·경로 정규화`

### Task 5: 대상 7분류·폴더 규칙·작업 영역 (`target_class` 2부)

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
  SEVERITY = {MISSING: 0, SCRATCH: 0, SESSION_NEW: 0, IGNORED_ARTIFACT: 0, GIT_TRACKED: 1, PRESERVED: 2, PROTECTED_NAME: 2, UNRESOLVED: 3}
  @dataclass(frozen=True)
  class Cls:
      kind: str
      path: str | None
      detail: str = ""                     # 폴더 규칙에서 결정한 항목 경로 등
      worktree_root: str | None = None     # 대상이 linked worktree 최상위면 그 경로
  def git_toplevel(path: str, ctx: Ctx) -> str | None: ...
  def git_tracked(repo: str, paths: list[str], ctx: Ctx) -> set[str]: ...
  def git_ignored(repo: str, paths: list[str], ctx: Ctx) -> set[str]: ...
  def is_linked_worktree_root(path: str) -> bool: ...    # path/.git 가 파일
  def classify(path: str | None, ctx: Ctx, trailing_slash: bool = False) -> Cls: ...   # path None → UNRESOLVED
  def in_workspace(path: str, ctx: Ctx) -> bool: ...
  def note_touch(path: str, ctx: Ctx) -> None: ...      # 장부 기록 규칙(spec §3.7)
  ```

- [ ] **Step 1: 실패하는 테스트 작성** — `class ClassifyTest` (World 사용):

```python
def k(p): return classify(w.fmt(p), ctx).kind
def test_seven_classes(self):
    self.assertEqual(k("{REPO}/nope"), MISSING); self.assertEqual(k("{REPO}/.env"), PROTECTED_NAME)
    self.assertEqual(k("{REPO}/src/main.py"), GIT_TRACKED); self.assertEqual(k("{SCRATCH}/s1/x.txt"), SCRATCH)
    self.assertEqual(k("{REPO}/src/probe.ts"), SESSION_NEW); self.assertEqual(k("{REPO}/build/out.o"), IGNORED_ARTIFACT)
    self.assertEqual(k("{REPO}/notes_presession.txt"), PRESERVED); self.assertEqual(k("{HOME}/data/a.txt"), PRESERVED)
    self.assertEqual(classify(None, ctx).kind, UNRESOLVED)
def test_ledger_overrides_new_birth(self):   # 세션 전 파일을 바꿔치기(새 birth) — 장부에 pre-session 이면 PRESERVED
    note_touch(w.fmt("{HOME}/data/a.txt"), ctx); rewrite_atomic(w.fmt("{HOME}/data/a.txt"))
    self.assertEqual(k("{HOME}/data/a.txt"), PRESERVED)
def test_note_touch_rules(self):
    note_touch(w.fmt("{REPO}/src/probe.ts"), ctx); self.assertEqual(ledger.kinds(w.fmt("{REPO}/src/probe.ts")), set())
    dirty_before_session = w.fmt("{REPO}/README.md")   # World 가 세션 전에 수정해 둔 추적 파일
    note_touch(dirty_before_session, ctx); self.assertIn(KIND_PRE_DIRTY, ledger.kinds(dirty_before_session))
def test_dir_rule(self):
    self.assertEqual(k("{REPO}/out"), SESSION_NEW)                 # 빠른 경로
    self.assertEqual(k("{REPO}/build"), IGNORED_ARTIFACT)          # 빠른 경로
    self.assertEqual(k("{REPO}/src"), GIT_TRACKED)                 # 세션 파일 + 추적 파일 혼합 → 더 보호 쪽
    self.assertEqual(k("{HOME}/data"), PRESERVED)
def test_dir_cap(self):  # 세션 전 미추적 폴더에 2001개 → UNRESOLVED, detail 에 '2000'
def test_unreadable_subdir_is_unresolved(self):    # Review Focus 5: chmod 000 하위 폴더, 그리고 순환 심볼릭 링크 폴더
def test_unicode_space_path(self):                  # Review Focus 2
    # 세션 파일 '{REPO}/보고서 초안.md' → SESSION_NEW, 세션 전 '{HOME}/보고 서.md' → PRESERVED
def test_worktree_root(self):  # git worktree add {TMPWT} 후 classify(TMPWT).worktree_root == TMPWT
def test_in_workspace(self):
    self.assertTrue(in_workspace(w.fmt("{REPO}/build/img"), ctx)); self.assertTrue(in_workspace(w.fmt("{SCRATCH}/s1/a"), ctx))
    self.assertFalse(in_workspace(w.fmt("{HOME}/data"), ctx)); self.assertFalse(in_workspace("/dev/sdb", ctx))
    self.assertFalse(in_workspace(w.fmt("{REPO}/.git/x"), ctx))
    # HOME 자체를 git init 한 세계에서 in_workspace({HOME}/data) → False
def test_session_start_missing_disables_session_new(self):
    ctx0 = w.ctx(transcript=None); self.assertEqual(classify(w.fmt("{REPO}/src/probe.ts"), ctx0).kind, PRESERVED)
```

- [ ] **Step 2: 실패 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_target_class.py -k ClassifyTest` · Expected: FAIL
- [ ] **Step 3: 구현** — `classify`: `normalize` → 존재 확인(`os.path.lexists`, 없으면 MISSING) → spec §3.4 순서. 파일 판정에 필요한
  git 조회는 저장소당 한 번(`git -C repo ls-files -z -- <경로들>`, `check-ignore -z --stdin`), 생성 시각은 `births` 일괄.
  SESSION_NEW 조건 = `birth >= session_start` 이고 `KIND_PRE_SESSION not in ledger.kinds(path)`. 폴더: 빠른 경로 2개(폴더 자체가
  SESSION_NEW / ignore) → 아니면 `git ls-files -- 폴더` 가 비어 있지 않으면 GIT_TRACKED(그래도 순회는 PRESERVED·PROTECTED 확인을
  위해 계속) → `os.walk(followlinks=False, onerror=…)` 로 항목을 모아 cap 초과·onerror 발생 시 UNRESOLVED, 아니면 각 항목 분류의
  `SEVERITY` 최댓값(동률이면 먼저 만난 것). `in_workspace`: 정규화 후 `is_scratch` 이거나, `git_toplevel` 이 있고 그 값이 `HOME`·`/`
  가 아니며 경로가 `<top>/.git` 아래가 아님. `note_touch`: 경로가 존재하고 birth < session_start 이면 `pre-session`; 추적 파일이고
  `git status --porcelain=v1 -z -- 경로` 가 비어 있지 않으면 `pre-dirty`.
- [ ] **Step 4: 통과 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_target_class.py` · Expected: `OK`
- [ ] **Step 5: 커밋** — `feat(harness-core): bash-guard 대상 7분류·폴더 규칙·작업 영역`

### Task 6: git 상태·find 미리보기·docker 조회 (`target_class` 3부)

**Files:**
- Modify: `plugins/harness-core/hooks/scripts/target_class.py`, `plugins/harness-core/hooks/tests/_world.py`(가짜 docker)
- Test: `plugins/harness-core/hooks/tests/test_target_class.py`

**Interfaces:**
- Consumes: Task 5
- Produces:
  ```python
  def git_dirty(repo: str, pathspecs: list[str], ctx: Ctx) -> list[str] | None: ...   # 추적 파일 중 index/worktree 변경(절대경로). 조회 실패 None
  def is_session_change(path: str, ctx: Ctx) -> bool: ...   # mtime >= session_start 이고 장부에 pre-dirty 아님
  def git_default_branch(repo: str, remote: str, ctx: Ctx) -> str | None: ...  # refs/remotes/<remote>/HEAD → 없으면 main → master → None
  def git_remote_names(repo: str, ctx: Ctx) -> list[str]: ...
  def git_upstream_branch(repo: str, ctx: Ctx) -> str | None: ...   # @{u} 의 브랜치 이름, 없으면 현재 브랜치 이름
  def git_stash_created(repo: str, ref: str, ctx: Ctx) -> float | None: ...   # 'stash@{0}' 등. git log -g -1 --format=%ct <ref>
  def git_clean_preview(repo: str, clean_args: list[str], ctx: Ctx) -> list[str] | None: ...  # -f/-i 제거·-n 추가 실행 결과(절대경로)
  def find_preview(args: list[str], cwd: str, ctx: Ctx) -> list[str] | None: ...   # 허용 표현식만, -delete/-exec rm → -print0
  def docker_container_info(container: str, ctx: Ctx) -> tuple[tuple[Mount, ...], str] | None: ...  # (마운트, WorkingDir)
  def compose_container_id(service: str, project_dir: str, project: str | None, ctx: Ctx) -> str | None: ...
  def docker_volume_created(name: str, ctx: Ctx) -> float | None: ...
  def docker_volumes(selector: str, value: str | None, ctx: Ctx) -> list[str] | None: ...  # "dangling" | "compose-project"
  ```
  가짜 docker(`_world.World.fake_docker(spec: dict)`): 세계의 `bin/docker` 스크립트가 `spec` JSON 을 읽어 `inspect --format …`,
  `volume inspect --format {{.CreatedAt}}`, `volume ls -q -f …`, `compose ps -q <svc>` 에 응답. `spec=None` 이면 종료코드 1.

- [ ] **Step 1: 실패하는 테스트 작성** — `class GitStateTest`, `class FindTest`, `class DockerTest`:

```python
def test_git_dirty_and_session_change(self):
    self.assertEqual(git_dirty(w.repo, ["."], ctx), [w.fmt("{REPO}/README.md")])   # 세션 전 수정
    touch_modify(w.fmt("{REPO}/src/main.py"))                                    # 세션 중 수정
    self.assertTrue(is_session_change(w.fmt("{REPO}/src/main.py"), ctx))
    self.assertFalse(is_session_change(w.fmt("{REPO}/README.md"), ctx))
    ledger.record(w.fmt("{REPO}/src/main.py"), KIND_PRE_DIRTY)
    self.assertFalse(is_session_change(w.fmt("{REPO}/src/main.py"), ctx))
def test_default_branch(self):
    self.assertEqual(git_default_branch(w.repo, "origin", ctx), "main")
    # origin/HEAD 삭제 후에도 "main"; main 이 없고 master 만 있으면 "master"; 둘 다 없으면 None
def test_stash_created(self):  # 세션 전 stash@{1}, 세션 중 stash@{0} → 각각 start 전/후
def test_clean_preview(self):
    self.assertIn(w.fmt("{REPO}/notes_presession.txt"), git_clean_preview(w.repo, ["-fd"], ctx))
    self.assertIn(w.fmt("{REPO}/build/out.o"), git_clean_preview(w.repo, ["-xffd"], ctx))
def test_find_preview(self):
    self.assertEqual(sorted(find_preview([w.repo, "-name", "*.o", "-delete"], w.repo, ctx)), [w.fmt("{REPO}/build/out.o")])
    self.assertIsNotNone(find_preview([".", "-name", "*.o", "-exec", "rm", "-f", "{}", "+"], w.repo, ctx))
    self.assertIsNone(find_preview([".", "-name", "x", "-exec", "mv", "{}", "/t", ";"], w.repo, ctx))
    self.assertIsNone(find_preview([".", "-fprint", "/t/x", "-delete"], w.repo, ctx))
def test_docker(self):
    w.fake_docker({"containers": {"c": {"Mounts": [{"Type": "bind", "Source": w.repo, "Destination": "/app"},
                                                   {"Type": "volume", "Name": "db", "Destination": "/data"}],
                                        "WorkingDir": "/app"}},
                   "volumes": {"db": {"CreatedAt": "<세션 전 RFC3339>", "Labels": {}}},
                   "compose": {"web": "c"}})
    mounts, wd = docker_container_info("c", ctx)
    self.assertEqual((mounts, wd), ((Mount(w.repo, "/app", "bind"), Mount("db", "/data", "volume")), "/app"))
    self.assertLess(docker_volume_created("db", ctx), ctx.session_start)
    self.assertEqual(compose_container_id("web", w.repo, None, ctx), "c")
    w.fake_docker(None); self.assertIsNone(docker_container_info("c", ctx))
```

- [ ] **Step 2: 실패 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_target_class.py` · Expected: FAIL
- [ ] **Step 3: 구현** — `git_dirty`: `git status --porcelain=v1 -z --untracked-files=no -- <pathspecs>` 각 항목(이름 변경은 원래·새 이름 둘 다).
  `find_preview` 허용 토큰: 경로 인자(첫 `-` 전), `-name -iname -path -ipath -wholename -regex -type -mtime -mmin -newer -size
  -empty -maxdepth -mindepth -prune -o -or -a -and -not ! ( )` 와 그 값, 그리고 동작 정확히 하나(`-delete` 또는 `-exec|-execdir rm
  [-r|-f|-rf|-fr|-R]... {} (;|+)`). 실행: `find <같은 인자, 동작 → -print0>` (`-delete` 는 깊이 우선이므로 `-depth` 추가 불필요 —
  목록만 필요). 결과 경로는 cwd 기준 절대경로. docker inspect 는
  `docker inspect --format '{{json .Mounts}}|{{.Config.WorkingDir}}' <c>`, 볼륨 생성 시각은 `docker volume inspect --format
  '{{.CreatedAt}}' <v>`(RFC3339 → epoch, `datetime.fromisoformat` 3.10 호환 위해 `Z`·소수 9자리 정리), 목록은
  `docker volume ls -q -f dangling=true` / `-f label=com.docker.compose.project=<p>`, compose 는 `docker compose
  [--project-directory d] [-p p] ps -q <svc>`.
- [ ] **Step 4: 통과 확인** — 같은 명령 · Expected: `OK`
- [ ] **Step 5: 커밋** — `feat(harness-core): bash-guard git 상태·find 미리보기·docker 조회`

### Task 7: 정책 — 삭제·덮어쓰기·디스크·시스템·권한 (`policy.py` 1부)

**Files:**
- Create: `plugins/harness-core/hooks/scripts/policy.py`
- Modify: `plugins/harness-core/hooks/tests/_world.py` (테스트 헬퍼 `evaluate_all(command, cwd) -> list[Finding]` = parse 후 모든 단위 `evaluate` 를 이음)
- Test: `plugins/harness-core/hooks/tests/test_policy.py`

**Interfaces:**
- Consumes: Task 3 `Segment`·`expand`·`literal_args`, Task 5 `classify`·`in_workspace`·분류 상수, Task 6 `find_preview`·`git_dirty`·`is_session_change`
- Produces:
  ```python
  KIND_TEXT: dict[str, str]   # 분류 설명 문구(아래 고정)
  @dataclass(frozen=True)
  class Finding:
      op: str          # "삭제" | "덮어쓰기" | "디스크 쓰기" | "시스템 경로 쓰기" | "재귀 권한 변경" | "git <하위명령>" | "docker 볼륨 삭제"
      target: str      # 경로·브랜치·볼륨 표시 문자열
      kind: str        # 분류 상수 또는 "DIRTY" | "DEFAULT_BRANCH" | "REFLOG" | "OLD_STASH" | "OLD_VOLUME" | "SYSTEM" | "OUTSIDE_WORKSPACE"
      advice: str
      def reason(self) -> str: ...   # f"거부: {op} {target} — {KIND_TEXT[kind]}. 대안: {advice}"
  def evaluate(seg: Segment, ctx: Ctx) -> list[Finding]: ...
  def is_judged_op(seg: Segment) -> bool: ...   # 이 단위가 판정 대상 작업인가(시간 예산 폴백용)
  SYSTEM_ROOTS = ("/etc", "/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/boot")
  BENIGN_DEVICES = ("/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty", "/dev/fd/")
  ```
  `KIND_TEXT` 고정 문구:
  `UNRESOLVED`="대상을 확정할 수 없다", `PROTECTED_NAME`="보호 대상 파일(비밀·설정·.git)", `GIT_TRACKED`="git 이 추적하는 파일",
  `PRESERVED`="세션 전부터 있던 유일본", `DIRTY`="커밋 안 된 수정이 있다", `SYSTEM`="호스트 시스템 경로",
  `OUTSIDE_WORKSPACE`="작업 영역(프로젝트·임시 폴더) 밖", `DEFAULT_BRANCH`="기본 브랜치 원격 이력 덮어쓰기",
  `REFLOG`="reflog 복구 경로 삭제", `OLD_STASH`="세션 전 보관본", `OLD_VOLUME`="기존 Docker 볼륨(데이터)".
  대안 문구는 spec §3.5 표의 문구를 그대로 쓴다(삭제·GIT_TRACKED: "`git rm <경로>` 로 삭제하라(변경 내역에 남아 검토·복구 가능)",
  PROTECTED_NAME·PRESERVED: "세션 전부터 있던 유일본이다. 정말 지워야 하면 사용자에게 요청하라", UNRESOLVED: "대상을 리터럴 경로로,
  범위를 좁혀 다시 실행하라", xargs rm: "`find … -delete` 나 리터럴 경로를 써라", 임시 루트 와일드카드: "자기 세션 폴더로 범위를
  좁혀라", 폴더 상한: "범위를 좁혀라", DIRTY(덮어쓰기): "먼저 커밋하거나 `git stash` 하라").

- [ ] **Step 1: 실패하는 테스트 작성** — `class DeleteTest`, `class OverwriteTest`, `class DiskSystemTest`:

```python
def ev(cmd, cwd="{REPO}"): return [(f.op, f.kind) for f in evaluate_all(w.fmt(cmd), w.fmt(cwd))]
# evaluate_all: parse → 모든 단위 evaluate 를 이은 테스트 헬퍼(_world.py)

def test_delete(self):
    self.assertEqual(ev("rm -f src/probe.ts"), []); self.assertEqual(ev("rm -rf build out"), [])
    self.assertEqual(ev("rm -rf /nope 2>/dev/null"), []); self.assertEqual(ev("rmdir emptydir"), [])
    self.assertEqual(ev("rm src/main.py"), [("삭제", GIT_TRACKED)]); self.assertEqual(ev("git rm src/main.py"), [])
    self.assertEqual(ev("rm notes_presession.txt"), [("삭제", PRESERVED)]); self.assertEqual(ev("rm .env"), [("삭제", PROTECTED_NAME)])
    self.assertEqual(ev('rm -rf "$UNKNOWN/x"'), [("삭제", UNRESOLVED)]); self.assertEqual(ev("rm -rf {SCRATCH}/*"), [("삭제", UNRESOLVED)])
    self.assertEqual(ev("rm -rf {SCRATCH}/s1"), []); self.assertEqual(ev("shred -u {HOME}/data/a.txt"), [("삭제", PRESERVED)])
    self.assertEqual(ev("unlink {HOME}/notes.md"), [("삭제", PRESERVED)])
def test_delete_reason_text(self):
    f = evaluate_all(w.fmt("rm src/main.py"), w.repo)[0]
    self.assertEqual(f.reason(), f"거부: 삭제 {w.fmt('{REPO}/src/main.py')} — git 이 추적하는 파일. 대안: `git rm <경로>` 로 삭제하라(변경 내역에 남아 검토·복구 가능)")
def test_find_and_xargs(self):
    self.assertEqual(ev("find . -name '*.o' -delete"), []); self.assertEqual(ev("find . -name '*.py' -delete"), [("삭제", GIT_TRACKED)])
    self.assertEqual(ev("find . -name x -exec mv {} /t \\;"), []);   # rm 아님 → 판정 대상 아님
    self.assertEqual(ev("find . -fprint /t/x -delete"), [("삭제", UNRESOLVED)])
    self.assertEqual(ev("ls | xargs rm -f"), [("삭제", UNRESOLVED)]); self.assertEqual(ev("git ls-files -z | xargs -0 git rm --cached"), [])
def test_overwrite(self):
    self.assertEqual(ev("echo x > src/main.py"), [])                        # 커밋 후 수정 없음
    self.assertEqual(ev("echo x > README.md"), [("덮어쓰기", "DIRTY")])      # 세션 전 수정 있음
    self.assertEqual(ev("echo x >> notes_presession.txt"), []); self.assertEqual(ev("echo x > /dev/null"), [])
    self.assertEqual(ev("echo x > {HOME}/data/important.csv"), [("덮어쓰기", PRESERVED)])
    self.assertEqual(ev("tee -a {HOME}/notes.md"), []); self.assertEqual(ev("tee {HOME}/notes.md"), [("덮어쓰기", PRESERVED)])
    self.assertEqual(ev("cp src/probe.ts notes_presession.txt"), [("덮어쓰기", PRESERVED)])
    self.assertEqual(ev("cp src/probe.ts {HOME}/data/"), []); self.assertEqual(ev("mv {HOME}/notes.md {SCRATCH}/s1/"), [])
    self.assertEqual(ev("truncate -s0 {HOME}/data/db.sqlite"), [("덮어쓰기", PRESERVED)])
    self.assertEqual(ev("sed -i s/a/b/ {HOME}/notes.md"), [])
    self.assertEqual(ev("rsync -a --delete src/ {HOME}/data/"), [("삭제", PRESERVED)])
    self.assertEqual(ev("rsync -a src/ {SCRATCH}/s1/"), [])
def test_disk_system_chmod(self):
    self.assertEqual(ev("cat img > /dev/sdb"), [("디스크 쓰기", "OUTSIDE_WORKSPACE")])
    self.assertEqual(ev("dd if=/dev/zero of=build/img bs=1M count=1"), []); self.assertEqual(ev("dd if=fw.bin of=rootfs.img bs=1 skip=10"), [])
    self.assertEqual(ev("dd if=/dev/zero of=/dev/sdb"), [("디스크 쓰기", "OUTSIDE_WORKSPACE")])
    self.assertEqual(ev("mkfs.ext4 /dev/sdb1"), [("디스크 쓰기", "OUTSIDE_WORKSPACE")])
    self.assertEqual(ev("echo x > /etc/hosts"), [("시스템 경로 쓰기", "SYSTEM")]); self.assertEqual(ev("sudo rm /usr/bin/x"), [("시스템 경로 쓰기", "SYSTEM")])
    self.assertEqual(ev("chmod -R 777 {HOME}"), [("재귀 권한 변경", "OUTSIDE_WORKSPACE")])
    self.assertEqual(ev("chmod -R 755 build"), []); self.assertEqual(ev("chmod 777 {HOME}/notes.md"), [])
    self.assertEqual(ev("killall node; systemctl --user stop svc; pkill -f x"), [])
```

- [ ] **Step 2: 실패 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_policy.py` · Expected: `ModuleNotFoundError: policy`
- [ ] **Step 3: 구현** — `evaluate` 는 `seg.context.kind == "container"` 면 Task 8 경로로(여기서는 빈 목록 반환 자리만), 호스트면
  ① 리다이렉트(덮어쓰기·장치·시스템) ② 명령 이름별 처리기 표 `HANDLERS: dict[str, Callable[[Segment, Ctx], list[Finding]]]`
  (`rm unlink shred find xargs-rm rsync cp mv install tee truncate dd mkfs* chmod chown chgrp`)를 적용. 대상 경로 = `expand` 결과
  (None → UNRESOLVED 하나). 시스템 경로 검사는 다른 분류보다 먼저(대상이 `SYSTEM_ROOTS` 하위면 SYSTEM). 임시 루트 와일드카드:
  원형 단어가 따옴표 없는 글롭이고 그 글롭의 디렉터리 부분이 `is_scratch_root` 면 UNRESOLVED. 덮어쓰기 GIT_TRACKED 는
  `git_dirty(repo, [path])` 가 비었거나 `is_session_change(path)` 면 허용, 아니면 DIRTY. rm·cp·mv·rsync 옵션 해석은 `literal_args`
  기준(`--` 이후는 모두 피연산자). `cp|mv|install` 의 목적지 = 마지막 피연산자(`-t DIR` 지원), 목적지가 존재하는 폴더면
  `목적지/원본이름` 들. `rsync --delete*` 는 목적지 폴더를 삭제 규칙으로. `is_judged_op` 는 처리기 표 이름이거나 쓰기 리다이렉트가
  있거나 `git`·`docker`·`podman`·`docker-compose` 면 True.
- [ ] **Step 4: 통과 확인** — 같은 명령 · Expected: `OK`
- [ ] **Step 5: 커밋** — `feat(harness-core): bash-guard 정책 — 삭제·덮어쓰기·디스크·시스템·권한`

### Task 8: 정책 — git·Docker (`policy.py` 2부)

**Files:**
- Modify: `plugins/harness-core/hooks/scripts/policy.py`
- Modify: `plugins/harness-core/hooks/tests/_world.py` (세계 조작: `clean_tree()`, `dirty_before_session(rel)` = 내용 변경 후 mtime 을 세션 시작 60초 전으로,
  `touch_modify(rel)` = 세션 중 내용 변경, `checkout(branch, upstream)`, `drop_origin_head()`, `remove_remote(name)`, `add_volume(name, created="before"|"after")`,
  세션 전 `stash@{1}`·세션 중 `stash@{0}`, linked worktree `{WT}` 생성, docker spec 의 compose 라벨 `com.docker.compose.project=proj` 를 단 `db`)
- Test: `plugins/harness-core/hooks/tests/test_policy.py`

**Interfaces:**
- Consumes: Task 6 git/docker 조회, Task 7 `Finding`·`evaluate`
- Produces: `evaluate` 가 `name == "git"` 과 컨테이너 문맥·docker 볼륨 명령을 처리(새 공개 함수 없음).

- [ ] **Step 1: 실패하는 테스트 작성** — `class GitPolicyTest`, `class DockerPolicyTest` (World 의 저장소는 세션 전 수정 `README.md` 를 가진 상태와
  깨끗한 상태 두 가지를 `w.clean_tree()` 로 전환):

```python
def test_discard_ops(self):
    w.clean_tree(); self.assertEqual(ev("git reset --hard"), []); self.assertEqual(ev("git checkout -- ."), [])
    touch_modify("{REPO}/src/main.py"); self.assertEqual(ev("git reset --hard HEAD"), [])        # 이번 세션 변경만
    w.dirty_before_session("{REPO}/README.md")
    for c in ["git reset --hard", "git checkout .", "git checkout -- README.md", "git restore .", "git switch -f main",
              "git checkout -f main", "git rm -f README.md", "git worktree remove --force {WT}"]:
        self.assertEqual([k for _, k in ev(c)], ["DIRTY"], c)
    self.assertEqual(ev("git restore --staged README.md"), []); self.assertEqual(ev("git rm --cached README.md"), [])
def test_clean(self):
    self.assertEqual(ev("git clean -n"), []); self.assertEqual(ev("git clean -fdX"), [])               # ignore 산출물만
    self.assertEqual(ev("git clean -fd"), [("git clean", PRESERVED)])                                 # notes_presession.txt
def test_stash(self):
    self.assertEqual(ev("git stash drop stash@{1}"), [("git stash", "OLD_STASH")])   # 세션 전 보관본
    self.assertEqual(ev("git stash drop"), [])                                        # stash@{0} = 세션 중
    self.assertEqual(ev("git stash clear"), [("git stash", "OLD_STASH")])
def test_push(self):
    for c in ["git push origin +main", "git push --force origin main", "git push -f origin HEAD:main",
              "git push origin :main", "git push origin --delete main", "git push --mirror"]:
        self.assertEqual([k for _, k in ev(c)], ["DEFAULT_BRANCH"], c)
    for c in ["git push -u origin feat/x", "git push --force origin feat/x", "git push --force-with-lease origin feat/x",
              "git push origin --delete feat/x", "git push -q origin --delete feat/x; git log -1 --format=%h"]:
        self.assertEqual(ev(c), [], c)
    w.checkout("feat/x", upstream="origin/feat/x"); self.assertEqual(ev("git push --force"), [])
    w.checkout("main", upstream="origin/main"); self.assertEqual([k for _, k in ev("git push --force")], ["DEFAULT_BRANCH"])
def test_default_branch_fallback(self):            # Review Focus 3
    w.drop_origin_head(); self.assertEqual([k for _, k in ev("git push --force origin main")], ["DEFAULT_BRANCH"])
    w.remove_remote("origin"); self.assertEqual(ev("git push --force origin main"), [])   # 원격 없음 → 판정 대상 아님
def test_reflog_destroyers(self):
    for c in ["git reflog expire --expire=now --all", "git gc --prune=now", "git prune", "git filter-branch -- --all", "git filter-repo --force"]:
        self.assertEqual([k for _, k in ev(c)], ["REFLOG"], c)
def test_allowed_history_ops(self):
    for c in ["git branch -D feat/x", "git rebase origin/main", "git commit --amend -m x", "git worktree add ../wt -b y",
              "git worktree remove {WT}", "git update-ref -d refs/heads/y", "git stash pop"]:
        self.assertEqual(ev(c), [], c)
def test_linked_worktree_rm(self):
    self.assertEqual(ev("rm -rf {WT}"), [])                    # 깨끗한 linked worktree 최상위
    w.dirty_before_session("{WT}/README.md"); self.assertEqual([k for _, k in ev("rm -rf {WT}")], ["DIRTY"])

def test_container(self):
    w.fake_docker(<Task 6 의 spec: c 에 /app=REPO bind, /data=db volume(세션 전), WorkingDir=/app>)
    self.assertEqual(ev("docker exec -u root c sh -c 'echo x >> /etc/hosts && rm -rf /var/lib/x'"), [])
    self.assertEqual(ev("docker exec c rm -rf /app/src"), [("삭제", GIT_TRACKED)])
    self.assertEqual(ev("docker exec c rm -rf src"), [("삭제", GIT_TRACKED)])               # WorkingDir /app
    self.assertEqual(ev("docker exec c rm -rf /data/x"), [("삭제", "OLD_VOLUME")])
    self.assertEqual(ev('docker run --rm -v "$(pwd)":/app img rm -f /app/notes_presession.txt'), [("삭제", PRESERVED)])
    self.assertEqual(ev("docker compose exec web rm -rf /app/src/probe.ts"), [])
def test_volume_ops(self):
    self.assertEqual(ev("docker volume rm db"), [("docker 볼륨 삭제", "OLD_VOLUME")])
    w.add_volume("fresh", created="after"); self.assertEqual(ev("docker volume rm fresh"), [])
    self.assertEqual([k for _, k in ev("docker compose down -v")], ["OLD_VOLUME"])          # 라벨 project=proj 인 db
    self.assertEqual(ev("docker rm -f c; docker compose down"), [])
    w.fake_docker(None)
    self.assertEqual([k for _, k in ev("docker volume rm db")], [UNRESOLVED])
    self.assertEqual(ev("docker exec c sh -c 'rm -rf /var/lib/x'"), [])                    # 조회 실패라도 내부 경로는 허용
```

- [ ] **Step 2: 실패 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_policy.py` · Expected: FAIL
- [ ] **Step 3: 구현** — git 하위명령 표(spec §3.5 git 표). 영향 범위: `reset --hard` → 저장소 전체(`["."]`), `checkout|restore`
  경로 인자(없고 `.` 이면 전체), `switch -f|--discard-changes`·`checkout -f` → 전체, `rm -f|--force` → 인자, `worktree remove --force P`
  → P 저장소 전체. 판정: `git_dirty` 결과에서 `is_session_change` 아닌 것이 있으면 `DIRTY`(target = 첫 경로 + "외 N개"), 조회 실패면
  UNRESOLVED. `clean`(인자에 `-n|--dry-run` 있으면 허용) → `git_clean_preview` 목록 각 경로를 `classify` 하고 SEVERITY>0 인 첫 항목을
  `("git clean", 그 분류)`. push: 원격 이름 = 첫 비옵션 인자(없으면 upstream 원격 또는 `origin`), `git_remote_names` 에 없으면 판정 안 함.
  refspec 목적지 = `:` 뒤(없으면 그 자체, `HEAD` → 현재 브랜치), 앞 `+` 는 강제, `refs/heads/` 접두 제거. 강제 = `--force|-f|+refspec`,
  삭제 = `--delete|-d|:dst`, `--mirror` → 무조건 DEFAULT_BRANCH. `--force-with-lease`·`--force-if-includes` 는 강제로 보지 않음.
  refspec 없는 push 는 `git_upstream_branch`. 컨테이너: exec 계열은 `docker_container_info`(compose 는 `compose_container_id` 먼저)로
  마운트·WorkingDir 를 얻어 단위 cwd 가 None 이면 WorkingDir 로, 대상 컨테이너 경로가 마운트 Destination 하위면 bind → 호스트 경로로
  바꿔 Task 7 처리기(시스템 경로 규칙 제외)로, volume → `docker_volume_created` < session_start(또는 None)이면 OLD_VOLUME(조회 실패
  UNRESOLVED), 마운트 밖이면 판정 없음. 조회 실패(None)면 컨테이너 안 판정 없음. 볼륨 명령: spec §3.5 Docker 표.
- [ ] **Step 4: 통과 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_policy.py` · Expected: `OK`
- [ ] **Step 5: 커밋** — `feat(harness-core): bash-guard 정책 — git·Docker`

### Task 9: 진입점 (`bash_guard.py`)

**Files:**
- Create: `plugins/harness-core/hooks/scripts/bash_guard.py`
- Test: `plugins/harness-core/hooks/tests/test_bash_guard.py`

**Interfaces:**
- Consumes: `shell_parse.parse`, `target_class.make_ctx`·`note_touch`, `policy.evaluate`·`is_judged_op`
- Produces:
  ```python
  BUDGET_SECONDS = 5.0
  LOG_MAX_BYTES = 10 * 1024 * 1024
  FOOTER = "이 판정을 우회하지 말 것. 대안이 맞지 않으면 작업을 멈추고 사용자에게 보고하라."
  FAIL_WORDS: re.Pattern   # spec §3.8 (가): rm unlink shred truncate dd mkfs* -delete reset clean restore checkout push volume prune 와 '>'
  @dataclass
  class Decision:
      allow: bool
      reasons: list[str]
      error: str | None = None
  def judge(payload: dict, environ: Mapping[str, str]) -> Decision: ...
  def render(d: Decision) -> str: ...        # 허용: 고정 allow JSON / 거부: deny JSON, 사유 = "[bash-guard] " + "\n".join(reasons + [FOOTER])
  def log_event(record: dict, environ: Mapping[str, str]) -> None: ...   # 상태 폴더 bash-guard.jsonl, 10MB 초과 시 .1 로 교체
  def main(argv: list[str] | None = None) -> int: ...   # stdin → judge → (shadow 아니면) print(render) ; 항상 0
  ```
  `main --shadow-old <JSON>`: 출력하지 않는다. old 의 `permissionDecision`(`ask`·`deny` → 비허용, 그 외 허용)과 새 판정이 다르면
  `{mode:"shadow", decision, old_decision, …}` 기록.

- [ ] **Step 1: 실패하는 테스트 작성** — `class JudgeTest`, `class MainTest`:

```python
def test_allow_render_exact(self):
    d = judge(w.payload("ls -la"), w.environ); self.assertTrue(d.allow)
    self.assertEqual(render(d), '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}')
def test_deny_render(self):
    out = json.loads(render(judge(w.payload("rm src/main.py"), w.environ)))["hookSpecificOutput"]
    self.assertEqual(out["permissionDecision"], "deny")
    self.assertTrue(out["permissionDecisionReason"].startswith("[bash-guard] 거부: 삭제 "))
    self.assertTrue(out["permissionDecisionReason"].endswith(FOOTER))
def test_multiple_reasons(self):  # "rm src/main.py; rm {HOME}/notes.md" → reasons 2개
def test_parse_failure_policy(self):
    self.assertTrue(judge(w.payload('echo "unterminated'), w.environ).allow)
    d = judge(w.payload('rm -rf "unterminated'), w.environ); self.assertFalse(d.allow); self.assertIn("해석하지 못했다", d.reasons[0])
def test_internal_error_allows_and_logs(self):   # policy.evaluate 를 예외 던지게 패치 → allow, 로그 1줄 error 필드
def test_budget(self):
    # target_class.run 을 time.sleep 으로 마감을 넘기게 패치: 'rm {HOME}/notes.md' → deny "판정 시간 초과"; 'ls' → allow
def test_inplace_edit_records_ledger(self):
    judge(w.payload("sed -i s/a/b/ {HOME}/notes.md"), w.environ)
    self.assertIn(KIND_PRE_SESSION, Ledger(w.session_id, w.environ).kinds(w.fmt("{HOME}/notes.md")))
def test_never_ask(self):   # fixtures 두 파일 전체 + 이 파일 사례를 render → "ask" 문자열 없음
def test_log_rotation(self):  # LOG_MAX_BYTES 를 200 으로 패치, 거부 5번 → bash-guard.jsonl.1 존재, 본 파일 < 200B
def test_shadow_logs_only_mismatch(self):
    # main(["--shadow-old", '{"hookSpecificOutput":{"permissionDecision":"ask"}}']) with 'rm -rf build' → stdout 빈 문자열, 로그 1줄(decision allow, old ask)
    # 같은 old 로 'rm src/main.py' → 로그 추가 없음(둘 다 비허용)
def test_e2e_subprocess(self):
    # python3 bash_guard.py 에 payload 를 stdin 으로, env=w.environ → 종료코드 0, stdout 한 줄 유효 JSON
```

- [ ] **Step 2: 실패 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_bash_guard.py` · Expected: `ModuleNotFoundError`
- [ ] **Step 3: 구현** — `judge`: `tool_name != "Bash"` 또는 명령 없음 → allow. `ctx = make_ctx(payload, environ, BUDGET_SECONDS)`.
  `parse(command, payload.get("cwd"), environ)`; `error` 있으면 (가). 단위마다: 남은 시간 ≤ 0 이면 지금까지 `is_judged_op` 인 단위가
  있었으면 deny("거부: 판정 시간 초과 — 범위를 좁혀라"), 없으면 allow 로 종료. `evaluate` 결과를 모은다. 제자리 편집(`sed -i|--in-place`,
  `perl -i|-pi`, `git checkout -- P`, `git restore P`)의 대상 경로마다 `note_touch`. 모든 예외는 `main` 에서 잡아 allow + `log_event(error)`.
  거부 사유 중복(같은 문자열) 제거. `log_event` 기록 필드: `ts`(ISO8601), `mode`(`on`|`shadow`), `session_id`, `agent_id`, `cwd`,
  `command`(2000자 자름), `decision`, `old_decision`, `reasons`, `ms`, `error`. 기록 대상: on 의 거부·오류, shadow 의 불일치·오류.
- [ ] **Step 4: 통과 확인** — 같은 명령 · Expected: `OK`
- [ ] **Step 5: 커밋** — `feat(harness-core): bash-guard 진입점 — 조립·실패 정책·시간 예산·기록·shadow`

### Task 10: 장부 훅 (`touch-ledger.py`, `hooks.json`)

**Files:**
- Create: `plugins/harness-core/hooks/scripts/touch-ledger.py`
- Modify: `plugins/harness-core/hooks/hooks.json` (PreToolUse 배열에 항목 추가)
- Test: `plugins/harness-core/hooks/tests/test_touch_ledger.py`

**Interfaces:**
- Consumes: `target_class.make_ctx`·`note_touch`
- Produces: 훅 계약 — stdin JSON, **출력 없음**, 종료 0. `HARNESS_BASH_GUARD` 가 `shadow`·`on` 이 아니면 즉시 종료(꺼진 프로젝트 비용 0).
  대상 경로 = `tool_input.file_path` 또는 `tool_input.notebook_path`.
  `hooks.json` 추가 항목: `{"matcher": "Write|Edit|NotebookEdit", "hooks": [{"type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/scripts/touch-ledger.py\"", "timeout": 5}]}`

- [ ] **Step 1: 실패하는 테스트 작성**:

```python
def run_hook(payload, mode): # subprocess python3 touch-ledger.py, env=w.environ + HARNESS_BASH_GUARD=mode → (rc, stdout)
def test_off_does_nothing(self):
    self.assertEqual(run_hook(w.edit_payload("{HOME}/notes.md"), "off"), (0, "")); self.assertFalse(ledger_file.exists())
def test_records_pre_session(self):
    for mode in ("shadow", "on"):
        self.assertEqual(run_hook(w.edit_payload("{HOME}/notes.md"), mode), (0, ""))
    self.assertEqual(Ledger(w.session_id, w.environ).kinds(w.fmt("{HOME}/notes.md")), {KIND_PRE_SESSION})
def test_new_file_and_session_file_not_recorded(self):  # Write 새 경로, 세션 파일 Edit → 장부 없음
def test_malformed_input(self): self.assertEqual(run_hook_raw("not json", "on"), (0, ""))
def test_hooks_json_registration(self):
    h = json.load(open(HOOKS_JSON))["hooks"]["PreToolUse"]
    e = [g for g in h if g.get("matcher") == "Write|Edit|NotebookEdit"][0]["hooks"][0]
    self.assertEqual((e["timeout"], e["command"].endswith('touch-ledger.py"')), (5, True))
```

- [ ] **Step 2: 실패 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_touch_ledger.py` · Expected: FAIL(파일 없음)
- [ ] **Step 3: 구현** — 위 계약대로. 모든 예외 무시. `hooks.json` 은 기존 Bash 항목 뒤에 추가하고 `jq empty` 로 검증.
- [ ] **Step 4: 통과 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_touch_ledger.py && jq empty plugins/harness-core/hooks/hooks.json` · Expected: `OK`, 종료 0
- [ ] **Step 5: 커밋** — `feat(harness-core): bash-guard 장부 훅 — Write·Edit 직전 세션 전 파일 기록`

### Task 11: 합격 묶음 — 오탐 회귀·누락·시나리오

**Files:**
- Create: `plugins/harness-core/hooks/tests/fixtures/false_positive.json`, `plugins/harness-core/hooks/tests/fixtures/false_negative.json`
- Modify: `plugins/harness-core/hooks/tests/test_bash_guard.py`, `plugins/harness-core/hooks/tests/_world.py`
  (`judge_case(case) -> Decision` = setup 적용 후 fmt 한 명령을 judge, `judge_cmd(cmd, cwd="{REPO}") -> Decision`, `sh(cmd, cwd="{REPO}")` = 실제 실행,
  저장소 `origin` 은 세계 안 bare 저장소라 push 가 실제로 동작)
- Test: 같은 파일

**Interfaces:**
- Consumes: `judge`, `World`
- Produces: 픽스처 형식 — JSON 배열, 항목 `{"id": str, "command": str, "cwd": "{REPO}" | "{HOME}" | …, "setup": [str], "expect": "allow" | "deny", "why": str}`.
  `setup` 은 `World` 의 이름 있는 준비 동작 목록(`"dirty_before_session:README.md"`, `"old_stash"`, `"fake_docker:default"`,
  `"presession_untracked"` 등 — `_world.py` 에 정의한 것만). 실제 세션 명령 원문 금지.

- [ ] **Step 1: 픽스처 작성** — `false_positive.json`(기대 allow): spec 부록 C 전 항목 + spec §8 오탐 회귀 행의 항목. 최소 다음 id 를 포함:
  `quoted-rm-in-echo`, `jq-arg-reset-hard`, `grep-pattern-rm`, `python-heredoc-rm`, `push-delete-then-log-format`,
  `rm-f-session-file`, `rm-rf-ignored-abs-path`, `rm-missing-with-redirect`, `rmdir`, `clean-dry-run`, `clean-ignored-only`,
  `push-force-with-lease-feature`, `dd-file-to-file`, `xargs-git-rm-cached`, `checkout-own-change`, `container-etc-edit`,
  `rm-own-scratch`, `killall`, `systemctl-user-stop`, `heredoc-to-cat`, `two-redirects-2>&1`.
  `false_negative.json`(기대 deny): spec 부록 B 전 항목(각 줄 하나씩, 자리표시자 적용) + `rm -rf ~`, `rm -r {HOME}/data`,
  `git reset --hard HEAD~3`(세션 전 수정 있음). 각 항목 `why` 에 spec 절 번호.
- [ ] **Step 2: 시나리오·픽스처 테스트 작성**:

```python
def test_false_positive_fixtures(self):
    bad = [c["id"] for c in load("false_positive.json") if not w.judge_case(c).allow]
    self.assertEqual(bad, [])
def test_false_negative_fixtures(self):
    bad = [c["id"] for c in load("false_negative.json") if w.judge_case(c).allow]
    self.assertEqual(bad, [])
def test_pr_flow_scenario(self):
    # 각 명령을 judge → allow 확인 → 실제 실행(subprocess, cwd 반영) 을 순서대로:
    steps = ["git worktree add {OUT}/wt -b feat/y", "cd {OUT}/wt && echo a > f.txt && git add f.txt && git commit -qm a",
             "cd {OUT}/wt && git push -u origin feat/y", "cd {OUT}/wt && git commit -q --amend -m b && git push --force",
             "git worktree remove {OUT}/wt", "git branch -D feat/y", "git push origin --delete feat/y"]
    for s in steps: self.assertTrue(w.judge_cmd(s).allow, s); w.sh(s)
def test_self_revert_scenario(self):
    w.clean_tree(); w.sh("echo x >> src/main.py")
    self.assertTrue(w.judge_cmd("git checkout -- src/main.py").allow); self.assertTrue(w.judge_cmd("git reset --hard").allow)
    w.dirty_before_session("README.md"); self.assertFalse(w.judge_cmd("git reset --hard").allow)
```

- [ ] **Step 3: 실패 확인** — Run: `python3 plugins/harness-core/hooks/tests/test_bash_guard.py` · Expected: 픽스처 id 목록이 실패 메시지에 나오면 그 항목이 Task 1~9 의 결함 →
  해당 작업 파일을 고친다(테스트·픽스처를 바꿔 통과시키지 않는다. 픽스처가 spec 과 어긋난 경우에만 픽스처 수정, 그 사유를 커밋 메시지에)
- [ ] **Step 4: 통과 확인** — Run: `for t in shell_parse target_class policy bash_guard touch_ledger; do python3 plugins/harness-core/hooks/tests/test_$t.py || exit 1; done` · Expected: 모두 `OK`
- [ ] **Step 5: 커밋** — `test(harness-core): bash-guard 합격 묶음 — 오탐 회귀·누락·PR 흐름·자기 되돌리기`

### Task 12: 입구 스위치 (`auto-approve-readonly.sh`)

**Files:**
- Modify: `plugins/harness-core/hooks/scripts/auto-approve-readonly.sh:53-179` (rm 가드 ~ 기본 allow 를 `old_logic` 함수로 감싸고 분기 추가)
- Test: `plugins/harness-core/hooks/tests/test-bash-guard-entry.sh` (Create)

**Interfaces:**
- Consumes: `bash_guard.py` CLI(`stdin` → 한 줄 JSON / `--shadow-old <JSON>` → 출력 없음)
- Produces: 입구 동작 — 1~51행(입력 읽기, 빈 명령 종료, code-read-guard 블록)은 **그대로**. 그 뒤:

```sh
old_logic() {
    # (기존 53~179행 본문 그대로 — 출력 후 exit 0 하는 구조 유지)
}
case "${HARNESS_BASH_GUARD:-off}" in
    on)
        OUT=$(printf '%s' "$INPUT" | python3 "$(dirname "$0")/bash_guard.py" 2>/dev/null) || OUT=""
        if [ -n "$OUT" ]; then printf '%s\n' "$OUT"; else
            printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}\n'; fi
        exit 0 ;;
    shadow)
        OLD=$(old_logic)
        printf '%s' "$INPUT" | python3 "$(dirname "$0")/bash_guard.py" --shadow-old "$OLD" >/dev/null 2>&1 || :
        printf '%s\n' "$OLD"
        exit 0 ;;
esac
old_logic
```

- [ ] **Step 1: 실패하는 테스트 작성** — `test-bash-guard-entry.sh`(기존 `test-auto-approve-readonly.sh` 의 `mkin`/`run` 관례, `XDG_STATE_HOME`·`HOME` 은 `mktemp -d`):
  1. **off 동일성**: 명령 12개(`ls`, `rm -rf /tmp/x`, `rm -rf ~`, `git reset --hard`, `rmdir d`, `echo 'rm -rf ~'`, `git push -f origin main`,
     `cat a | grep b`, 빈 명령, `dd if=a of=b`, `rm -rf src`, `chmod -R 777 /`)에 대해 `HARNESS_BASH_GUARD` 미설정·`off`·`bogus` 세 경우 stdout 이
     **같은 바이트**이고, 변경 전 스크립트(`git show "$(git merge-base HEAD origin/main)":plugins/harness-core/hooks/scripts/auto-approve-readonly.sh`
     를 임시 파일로 — 커밋 뒤에도 기준이 바뀌지 않게 분기점 기준)의 stdout 과도 같다.
  2. **on**: `rm -rf ~/data`(테스트 HOME 에 미리 만든 폴더) → `"permissionDecision": "deny"`; `ls` → allow; 출력에 `"ask"` 없음.
  3. **on + 파이썬 실패**: `PATH` 앞에 `exit 1` 하는 가짜 `python3` → stdout 이 allow JSON.
  4. **shadow**: `echo 'rm -rf ~'` → stdout 이 off 와 같은 바이트, 상태 폴더 `bash-guard.jsonl` 에 `"mode": "shadow"` 줄 1개(old ask, 새 allow).
- [ ] **Step 2: 실패 확인** — Run: `bash plugins/harness-core/hooks/tests/test-bash-guard-entry.sh` · Expected: 2~4 FAIL(스위치 없음), 1 PASS
- [ ] **Step 3: 구현** — 위 Interfaces 블록대로. `set -euo pipefail` 아래에서 `OLD=$(old_logic)` 이 0 이 아닌 종료를 내지 않게(기존 본문은 항상 exit 0).
- [ ] **Step 4: 통과 확인** — Run: `bash plugins/harness-core/hooks/tests/test-bash-guard-entry.sh && for t in plugins/harness-core/hooks/tests/test-*.sh; do bash "$t" || exit 1; done && python3 plugins/harness-core/hooks/t_auto_approve_rm.py && python3 plugins/harness-core/hooks/tests/test_code_read_guard.py && shellcheck plugins/harness-core/hooks/scripts/auto-approve-readonly.sh` · Expected: 모두 PASS·종료 0
- [ ] **Step 5: 커밋** — `feat(harness-core): bash-guard 입구 스위치 off/shadow/on — off 는 기존과 바이트 동일`

### Task 13: 전수 재생 도구와 검토 (합격 기준 3)

**Files:**
- Create: `plugins/harness-core/hooks/tests/tools/replay_corpus.py`

**Interfaces:**
- Consumes: `bash_guard.judge`
- Produces: CLI `replay_corpus.py --projects <dir> --out <dir> [--limit N]`. `--out` 이 이 저장소 작업 트리 안이면 거부하고 종료 2.
  출력(`--out` 아래만): `summary.json`(`{commands, errors, deny, p50_ms, p99_ms, max_ms}`), `denies.jsonl`(`{command(500자), cwd, reasons}`),
  `errors.jsonl`. 입력: `**/*.jsonl` 의 Bash `tool_use.input.command` 와 레코드 `cwd`, 명령 문자열 기준 중복 제거.
  판정 payload: `{"tool_name":"Bash","tool_input":{"command":c},"cwd":cwd,"session_id":"replay","transcript_path":None}`
  (세션 시작 없음 → SESSION_NEW 미적용, 보수적), environ 은 실제 os.environ.

- [ ] **Step 1: 도구 작성** — 위 계약. 1,000개마다 진행 상황을 stderr 로.
- [ ] **Step 2: 실행** — Run: `python3 plugins/harness-core/hooks/tests/tools/replay_corpus.py --projects ~/.claude/projects --out "${XDG_STATE_HOME:-$HOME/.local/state}/harness-core/replay"` · Expected: `summary.json` 의 `errors == 0`, `p99_ms <= 150`
- [ ] **Step 3: 검토** — `denies.jsonl` 을 거부 사유별로 묶어 건수와 대표 사례를 **사용자에게** 보여 준다(저장소·PR 에 원문 금지).
  사용자가 부당하다고 판정한 거부마다 Task 1~9 중 원인 작업에 실패 테스트(재구성 사례)를 추가하고 고친 뒤 Step 2 부터 반복.
  종료 조건: 사용자 확인 "부당 거부 0건".
- [ ] **Step 4: 커밋** — `test(harness-core): bash-guard 전수 재생 도구` (도구 파일만. 재생 결과는 커밋 금지). PR 본문에는 summary 수치만.

### Task 14: 문서·버전

**Files:**
- Modify: `plugins/harness-core/README.md`, `plugins/harness-core/.claude-plugin/plugin.json`(`"version": "0.2.0"`)
- Create: `plugins/harness-core/DECISIONS.md`, `plugins/harness-core/LIMITS.md`

- [ ] **Step 1: 작성** — README: "담는 기준"의 현재 목록에 bash-guard 모듈들 추가, env 노브 표에 `HARNESS_BASH_GUARD`(off/shadow/on, 프로젝트 settings 에만)
  추가하고 `HARNESS_RM_REPO_DIRS` 행에 "bash-guard on 안정화 후 제거 예정" 표기, 상태 폴더 위치(기록·장부), 자기검증 명령을 spec §5 로 교체.
  DECISIONS.md = spec §2 표 두 개를 옮기고 맨 위에 spec 경로. LIMITS.md = spec §13 목록 그대로 + 샌드박스 재검토 조건.
- [ ] **Step 2: 검증** — Run: `jq empty plugins/harness-core/.claude-plugin/plugin.json && grep -c HARNESS_BASH_GUARD plugins/harness-core/README.md` · Expected: 종료 0, 1 이상
- [ ] **Step 3: 커밋** — `docs(harness-core): bash-guard README·DECISIONS·LIMITS, 0.2.0`

### Task 15: 죽은 등록 게이트 (`~/.claude/check-canon.sh`) — **실행 전 사용자 승인 필요(Ask first)**

**Files:**
- Modify: `/home/phantom/.claude/check-canon.sh` — 검사 함수 추가(기존 `check_openspec_retired()` 정의 뒤), live 절(현재 `check_openspec_retired` 호출 다음 줄)에 호출 추가,
  `--selftest` 절에 사례 2개 추가(마지막 NEG18 이후 빈 번호)

**Interfaces:**
- Produces: `check_settings_plugin_root()` — `find "$SCAN_ROOT" -mindepth 3 -maxdepth 6 -type f -path '*/.claude/settings*.json' -not -path '*/node_modules/*'`
  각 파일(그 프로젝트 루트 = `${f%/.claude/*}` 가 `is_ignored` 면 건너뜀)에서
  `jq -r '[.hooks // {} | .[] | .[] | .hooks[]? | .command // empty] | .[]'` 결과에 `${CLAUDE_PLUGIN_ROOT}` 가 있으면
  `echo "★ [hooks] 죽은 등록: <파일> — \${CLAUDE_PLUGIN_ROOT} 는 플러그인 hooks.json 에서만 확장된다(이 등록은 항상 실패)"`, `BAD=$((BAD+1))`.

- [ ] **Step 1: 사용자 승인 확인** — 이 파일은 git 저장소 밖이므로 수정 전 `cp ~/.claude/check-canon.sh ~/.claude/check-canon.sh.bak-2026-10-14`.
- [ ] **Step 2: 실패 사례 추가** — selftest 에 `NEG19 settings 의 ${CLAUDE_PLUGIN_ROOT} 등록 검출`(픽스처 `$T/root/p1/.claude/settings.json` 에 해당 command → `run` 이 1, 출력에 `죽은 등록`)·
  `NEG19b 플러그인 경로 없는 settings 훅은 통과`(`bash .claude/hooks/x.sh` → 0). Run: `~/.claude/check-canon.sh --selftest` · Expected: NEG19 `✗`
- [ ] **Step 3: 구현** — 위 Interfaces. Run: `~/.claude/check-canon.sh --selftest` · Expected: 전 사례 `✓`
- [ ] **Step 4: live 확인** — Run: `~/.claude/check-canon.sh 2>/dev/null | grep '죽은 등록'` · Expected: Task 16 전에는 4줄(agent, bounty, bounty-agoda, bounty-wordpress)
- [ ] **Step 5: 백업 제거** — Task 16 완료·live 0줄 확인 후 사용자 확인을 받아 `.bak` 삭제. (git 밖 파일이라 커밋 없음)

### Task 16: 죽은 등록 제거 4곳 — **실행 전 사용자 승인 필요(Ask first)**

**Files (각각 다른 저장소·브랜치):**
- Modify: `/home/phantom/agent/.claude/settings.json`, `/home/phantom/bounty/.claude/settings.json`,
  `/home/phantom/orca/workspaces/bounty/bounty-agoda/.claude/settings.json`, `/home/phantom/orca/workspaces/bounty/bounty-wordpress/.claude/settings.json`

- [ ] **Step 1: 사용자 승인과 상태 확인** — 각 저장소에서 `git -C <repo> status --short -- .claude/settings.json` 이 깨끗한지(미커밋 변경이 있으면 멈추고 보고).
- [ ] **Step 2: 제거** — 각 파일의 `hooks.PreToolUse[].hooks[]` 중 command 가 `auto-approve-readonly.sh` 를 가리키는 항목만 제거(그 그룹의 다른 훅은 유지,
  그룹이 비면 그룹 제거). JSON 형식 보존을 위해 들여쓰기 2칸 `json.dump(…, ensure_ascii=False, indent=2)` 후 원래 끝 줄바꿈 유지. Run: `jq empty <파일>`
- [ ] **Step 3: 검증** — Run: `~/.claude/check-canon.sh 2>/dev/null | grep -c '죽은 등록'` · Expected: `0`
- [ ] **Step 4: 커밋(저장소마다)** — `git -C <repo> commit -m "chore(settings): 동작하지 않던 auto-approve 등록 제거 — \${CLAUDE_PLUGIN_ROOT} 는 플러그인 훅에서만 확장(harness-core 가 이미 적용)" -- .claude/settings.json`

---

## 병합 이후 운영 (계획 범위 밖 — 사용자 승인 단계, spec §11)

1. PR(본문: spec 링크, 재생 summary 수치, 원문 없음) → 병합 → `git -C ~/tools/claude-project-config pull --ff-only`. 스위치 off 라 동작 불변.
2. 사용자와 shadow 대상 프로젝트 목록 확정 → 각 프로젝트 `.claude/settings.json` 의 `env` 에 `"HARNESS_BASH_GUARD": "shadow"`(orca 작업공간은 브랜치별 파일).
3. 최소 3일·Bash 5,000회 후 `bash-guard.jsonl` 의 shadow 불일치를 검토 → 판정기 쪽 오판은 재구성 테스트 추가 후 수정(새 PR).
4. 사용자 승인 → 같은 프로젝트들 `on`. 2주 무사고 → 기존 로직·`HARNESS_RM_REPO_DIRS`·`t_auto_approve_rm.py` 제거 PR(기본값 on 여부도 그때 결정).
