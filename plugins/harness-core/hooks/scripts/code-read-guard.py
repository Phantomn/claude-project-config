#!/usr/bin/env python3
"""code-read-guard.py — PreToolUse(Bash): 셸 텍스트 도구로 소스코드를 읽는 호출을 막고 serena·codegraph 로 보낸다.

★왜 (2026-10-01 실측). 30일 세션 582개에서 Bash grep/sed/cat 등으로 코드를 읽은 호출 15,391회 대
  serena 122·codegraph 104회. 원인은 세 겹이다:
  ① 하네스가 Bash 를 1급 경로로 만든다 — 네이티브 빌드는 Grep/Glob 도구를 빼고 셸 grep/find 를
    내장 ugrep/bfs 로 바꾼다(anthropics/claude-code#52121), bypass/auto 모드는 "cat·sed -n·grep 으로
    읽어라" 문구를 붙인다(#90599).
  ② MCP 도구가 지연 로드라 첫 선택지에 없다 → 프로젝트 .mcp.json 의 alwaysLoad 로 따로 해결.
  ③ 이전 게이트(이 파일이 대체한 auto-approve-readonly.sh 의 카운터 게이트)는 3회째부터·.codegraph 가
    있을 때만 deny 했고 안내 도구명(codegraph_node 등)은 codegraph 1.6 에서 기본 비노출이었다 — 사실상 무효.
    → 첫 시도부터 실행 **전** 차단하고, 차단 사유에 그 자리에서 쓸 serena 호출을 구체적으로 적는다.

계약:
  - 막는 것: grep/rg/ugrep/ag/ack/awk/sed/cat/head/tail/nl/less/more/bat/tac 가
    (a) 코드 확장자 파일을 인자로 받거나, (b) 코드가 있는 디렉터리를 재귀 검색(grep -r, rg, git grep,
    find -exec grep)할 때. 단 대상이 현재 git 저장소 안일 때만 — serena(--project-from-cwd)가 그곳만 본다.
  - 통과: 파이프 입력(cmd | grep), 비코드 파일(로그·설정·문서), --include/-g/-t 로 비코드만 지정한 검색,
    sed -i(편집), 저장소 밖 경로, cwd 가 git 저장소가 아닐 때, 명령 해석 실패(fail-open).
호출: auto-approve-readonly.sh 가 HARNESS_CODEREAD_GUARD=1 일 때 stdin 을 넘겨 부른다(단독 등록 안 함 —
  같은 훅 안에서 판정해야 그 훅의 기본 allow 와 순서 경합이 없다).
종료: 항상 0 — 차단은 stdout hookSpecificOutput.permissionDecision=deny 로 낸다.
테스트: python3 hooks/tests/test_code_read_guard.py
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys

CODE_EXTS = {
    "py", "pyi", "pyx", "ts", "tsx", "mts", "cts", "js", "jsx", "mjs", "cjs", "go", "rs", "java",
    "kt", "kts", "scala", "c", "h", "cc", "cpp", "cxx", "hpp", "hh", "hxx", "cs", "rb", "php",
    "swift", "m", "mm", "lua", "dart", "vue", "svelte", "sol", "zig", "ex", "exs", "erl", "hs",
    "ml", "clj", "jl", "nim",
}
# rg -t/--type 이름
CODE_TYPES = {
    "py", "python", "ts", "typescript", "js", "javascript", "go", "rust", "java", "kotlin", "c",
    "cpp", "cs", "csharp", "ruby", "php", "swift", "lua", "dart", "vue", "svelte", "scala", "zig",
    "elixir", "haskell", "objc",
}
READERS = {"grep", "egrep", "fgrep", "rg", "ugrep", "ug", "ag", "ack", "awk", "gawk", "sed",
           "cat", "head", "tail", "nl", "less", "more", "bat", "tac"}
PATTERN_FIRST = {"grep", "egrep", "fgrep", "rg", "ugrep", "ug", "ag", "ack", "sed", "awk", "gawk"}
ALWAYS_RECURSIVE = {"rg", "ag", "ack"}
# 다음 토큰을 값으로 먹는 분리형 플래그 — 프로그램마다 뜻이 다르다(grep -n 은 값 없음, head -n 은 값).
_SEARCH_VALUE = {"-A", "-B", "-C", "-m", "-e", "-f", "--include", "--exclude", "--exclude-dir",
                 "--glob", "--iglob", "--type", "--type-not", "--regexp", "--file", "--max-depth",
                 "--context", "--label"}
VALUE_FLAGS = {
    "grep": _SEARCH_VALUE | {"-d", "-D"}, "egrep": _SEARCH_VALUE | {"-d", "-D"},
    "fgrep": _SEARCH_VALUE | {"-d", "-D"},
    "ugrep": _SEARCH_VALUE | {"-d", "-D", "-O", "-g", "-t"}, "ug": _SEARCH_VALUE | {"-d", "-D", "-O", "-g", "-t"},
    "rg": _SEARCH_VALUE | {"-g", "-t", "-T", "-M", "-j", "-E"},
    "ag": _SEARCH_VALUE | {"-G"}, "ack": _SEARCH_VALUE,
    "sed": {"-e", "-f", "-l", "--expression", "--file"},
    "awk": {"-F", "-v", "-f"}, "gawk": {"-F", "-v", "-f"},
    "head": {"-n", "-c"}, "tail": {"-n", "-c"},
}
# 이 플래그가 있으면 첫 위치인자가 패턴/프로그램이 아니다
PATTERN_GIVEN = {"-e", "-f", "--regexp", "--file", "--expression"}
INCLUDE_FLAGS = {"--include", "-g", "--glob", "--iglob", "-G", "-O"}
TYPE_FLAGS = {"-t", "--type"}
WRAPPERS = {"timeout", "time", "nice", "nohup", "stdbuf", "command", "builtin", "noglob", "exec",
            "sudo", "env", "xargs"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "target",
             ".codegraph", ".serena", ".mypy_cache", ".pytest_cache", ".tox"}
WALK_CAP = 20000  # ponytail: 상한 넘게 커도 코드 못 찾으면 통과(fail-open). 거대 트리에서 오판 시 상향.

_EXT_RE = re.compile(r"\.\{([^}]*)\}|\.([A-Za-z0-9_+]+)(?![A-Za-z0-9_])")
_HEREDOC_RE = re.compile(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?")


def has_code_ext(s: str) -> bool:
    for m in _EXT_RE.finditer(s):
        exts = m.group(1).split(",") if m.group(1) is not None else [m.group(2)]
        if any(e.strip().lower() in CODE_EXTS for e in exts):
            return True
    return False


def strip_heredocs(cmd: str) -> str:
    """heredoc 본문(커밋 메시지·파일 생성 내용)은 명령이 아니므로 제거한다."""
    out, end = [], None
    for line in cmd.split("\n"):
        if end is not None:
            if line.strip() == end:
                end = None
            continue
        out.append(line)
        m = _HEREDOC_RE.search(line)
        if m:
            end = m.group(1)
    return "\n".join(out)


def split_segments(cmd: str):
    """[(tokens, piped_in, redirect_in_files)] — 셸 연산자 기준 단순 명령 단위."""
    cmd = strip_heredocs(cmd).replace("\n", " ; ").replace("`", " ; ")
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    toks = list(lex)
    segs, cur, piped, rin = [], [], False, []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t and set(t) <= set("();<>|&"):
            if t.startswith("<<"):  # heredoc/herestring 구분자는 건너뜀
                i += 2
                continue
            if t.startswith("<"):
                if i + 1 < len(toks):
                    rin.append(toks[i + 1])
                i += 2
                continue
            if t.startswith(">") or t in (">&", "&>"):
                i += 2
                continue
            if cur or rin:
                segs.append((cur, piped, rin))
            piped = t in ("|", "|&")
            cur, rin = [], []
            i += 1
            continue
        cur.append(t)
        i += 1
    if cur or rin:
        segs.append((cur, piped, rin))
    return segs


def unwrap(tokens):
    """env 할당·래퍼(timeout 30, nice -n 5, xargs -n1 …)를 벗겨 실제 프로그램부터 반환. (tokens, via_xargs)"""
    toks, via_xargs = list(tokens), False
    while toks:
        t = toks[0]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t):
            toks.pop(0)
            continue
        base = os.path.basename(t.lstrip("\\"))
        if base not in WRAPPERS:
            break
        via_xargs |= base == "xargs"
        toks.pop(0)
        while toks and (toks[0].startswith("-") or re.match(r"^\d+(\.\d+)?[smhd]?$", toks[0])
                        or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[0])):
            flag = toks.pop(0)
            if flag in ("-n", "-I", "-P", "-d", "-L", "-s", "-k", "-u", "-g", "-i") and toks \
                    and base in ("xargs", "nice", "sudo", "timeout"):
                toks.pop(0)
    return toks, via_xargs


def parse_reader(prog: str, args: list[str]):
    """→ (positional_files, includes, types, recursive, sed_inplace)"""
    files, includes, types = [], [], []
    recursive = prog in ALWAYS_RECURSIVE
    sed_inplace = False
    pattern_pending = prog in PATTERN_FIRST and not any(
        a in PATTERN_GIVEN or a.startswith(("--regexp=", "--file=", "--expression=")) for a in args)
    if prog in ("awk", "gawk") and "-f" in args:
        pattern_pending = False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            files.extend(args[i + 1:])
            break
        if a.startswith("--") and "=" in a:
            k, v = a.split("=", 1)
            if k in INCLUDE_FLAGS:
                includes.append(v)
            elif k in TYPE_FLAGS:
                types.append(v)
            elif k == "--directories" and v == "recurse":
                recursive = True
            i += 1
            continue
        if a.startswith("-") and a != "-":
            if a in ("-r", "-R", "--recursive", "--dereference-recursive"):
                recursive = True
            elif re.match(r"^-[A-Za-z]+$", a) and prog in ("grep", "egrep", "fgrep", "ugrep", "ug") \
                    and ("r" in a or "R" in a):
                recursive = True
            if prog == "sed" and (a.startswith("-i") or a == "--in-place"):
                sed_inplace = True
            if a in VALUE_FLAGS.get(prog, ()) and i + 1 < len(args):
                v = args[i + 1]
                if a in INCLUDE_FLAGS:
                    includes.append(v)
                elif a in TYPE_FLAGS:
                    types.append(v)
                i += 2
                continue
            i += 1
            continue
        if pattern_pending:
            pattern_pending = False
        else:
            files.append(a)
        i += 1
    return files, includes, types, recursive, sed_inplace


def git_root(cwd: str) -> str | None:
    try:
        r = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return os.path.realpath(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None


def resolve(path: str, cwd: str) -> str:
    p = os.path.expandvars(os.path.expanduser(path))
    p = re.split(r"[*?\[{]", p, maxsplit=1)[0] or "."  # 글롭은 고정 접두 디렉터리로
    return os.path.realpath(os.path.join(cwd, p))


def inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root + os.sep)


def dir_has_code(d: str) -> bool:
    n = 0
    for _, dirs, fnames in os.walk(d):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for f in fnames:
            n += 1
            if has_code_ext(f):
                return True
            if n > WALK_CAP:
                return False
    return False


def judge_segment(tokens, piped, rin, cwd, root, whole_cmd):
    """차단 사유가 되는 (명령 문자열, 대상 경로) 또는 None."""
    toks, via_xargs = unwrap(tokens)
    if not toks:
        return None
    prog = os.path.basename(toks[0].lstrip("\\"))
    args = toks[1:]

    if prog in ("bash", "sh", "zsh") and "-c" in args:
        i = args.index("-c")
        if i + 1 < len(args):
            return judge_command(args[i + 1], cwd, root)
        return None

    if prog == "git" and args[:1] == ["grep"]:
        prog, args = "rg", args[1:]  # git grep = 저장소 재귀 검색

    if prog == "find":
        return judge_find(args, cwd, root)

    if prog not in READERS or prog == "rg" and "--files" in args:  # rg --files = 목록만, 내용 안 읽음
        return None

    files, includes, types, recursive, sed_inplace = parse_reader(prog, args)
    if prog == "sed" and sed_inplace:
        return None
    files += rin

    for f in files:
        if has_code_ext(f) and inside(resolve(f, cwd), root):
            return f
    if via_xargs and has_code_ext(whole_cmd):  # find -name '*.py' | xargs grep
        return "(xargs 입력)"
    if not recursive:
        return None
    if piped and not files and prog in ALWAYS_RECURSIVE:
        return None  # cmd | rg pat — stdin 검색
    return judge_recursive(files, includes, types, cwd, root)


def judge_recursive(paths, includes, types, cwd, root):
    if includes or types:
        if any(has_code_ext(g) for g in includes) or any(t.lower() in CODE_TYPES for t in types):
            targets = [resolve(p, cwd) for p in paths] or [os.path.realpath(cwd)]
            return next((p for p in targets if inside(p, root)), None)
        return None  # 비코드만 지정
    targets = [resolve(p, cwd) for p in paths] or [os.path.realpath(cwd)]
    for t in targets:
        if not inside(t, root):
            continue
        if os.path.isdir(t) and dir_has_code(t):
            return t
    return None


def judge_find(args, cwd, root):
    """find … -exec/-execdir <reader> … — 시작 디렉터리를 재귀 검색으로 본다."""
    for flag in ("-exec", "-execdir"):
        if flag in args:
            j = args.index(flag)
            inner = os.path.basename(args[j + 1]) if j + 1 < len(args) else ""
            if inner not in READERS or inner == "sed" and any(a.startswith("-i") for a in args[j:]):
                return None
            pre = args[:j]
            k = next((n for n, a in enumerate(pre) if a.startswith(("-", "(", "!"))), len(pre))
            starts = pre[:k]  # find 의 시작 경로 = 첫 식(expression) 앞의 인자들
            names = [pre[n + 1] for n, a in enumerate(pre[:-1])
                     if a in ("-name", "-iname", "-path", "-ipath", "-regex")]
            return judge_recursive(starts, names, [], cwd, root)
    return None


def judge_command(cmd: str, cwd: str, root: str):
    try:
        segs = split_segments(cmd)
    except ValueError:
        return None  # 해석 실패 → fail-open
    for tokens, piped, rin in segs:
        if tokens[:1] in (["cd"], ["pushd"]):  # 명령 안 cd 로 바뀐 위치 기준으로 판정 — 저장소 밖이면 통과
            cwd = resolve(tokens[1] if len(tokens) > 1 else "~", cwd)
            continue
        hit = judge_segment(tokens, piped, rin, cwd, root, cmd)
        if hit:
            return hit
    return None


def reason(cmd: str, hit: str, root: str) -> str:
    rel = os.path.relpath(hit, root) if os.path.isabs(hit) else hit
    has_cg = os.path.isdir(os.path.join(root, ".codegraph"))
    lines = [
        f"[code-read-guard] 셸 텍스트 도구로 소스코드를 읽는 호출이라 차단됨: `{cmd[:160]}` (대상: {rel})",
        "이 저장소에서 코드는 심볼 도구로 읽는다(grep/sed 는 문자열 일치라 정의·호출 관계를 놓친다):",
    ]
    if has_cg:
        lines.append('- 영역·흐름 파악: mcp__codegraph__codegraph_explore(query="<심볼명 또는 질문>")'
                     ' — 셸이면 `codegraph explore "<질의>"`')
    lines += [
        f'- 파일 구조: mcp__serena__get_symbols_overview(relative_path="{rel}")',
        '- 심볼 본문: mcp__serena__find_symbol(name_path_pattern="<이름>", include_body=true)',
        '- 참조·호출부: mcp__serena__find_referencing_symbols(name_path="<이름>", relative_path="<파일>")',
        '- 문자열·주석 등 정규식 검색: mcp__serena__search_for_pattern(substring_pattern="<정규식>",'
        ' paths_include_glob="**/*.py")',
        "로그·설정·문서 파일, 파이프 입력(cmd | grep), sed -i 편집은 차단 대상이 아니다.",
    ]
    return "\n".join(lines)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return
    if data.get("tool_name") != "Bash":
        return
    cmd = (data.get("tool_input") or {}).get("command") or ""
    cwd = data.get("cwd") or os.getcwd()
    root = git_root(cwd)
    if not cmd or not root:
        return
    hit = judge_command(cmd, cwd, root)
    if not hit:
        return
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason(cmd, hit, root),
    }}, ensure_ascii=False))


if __name__ == "__main__":
    main()
