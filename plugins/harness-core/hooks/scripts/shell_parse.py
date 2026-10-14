"""bash-guard 어휘 분석기: 셸 명령 문자열 -> 토큰 목록 (spec §3.3-1).

shlex 를 쓰지 않는 이유: 따옴표 종류·리다이렉트 위치·`2>&1` 을 잃어 단위 분해가 틀어진다.
"""
from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace


class LexError(ValueError):
    pass


@dataclass(frozen=True)
class Part:
    text: str
    quote: str  # "" | "'" | '"'


@dataclass(frozen=True)
class Word:
    parts: tuple[Part, ...]

    def literal(self) -> str:
        return "".join(p.text for p in self.parts)

    def is_quoted(self) -> bool:
        return any(p.quote for p in self.parts)


@dataclass(frozen=True)
class Token:
    kind: str  # "word" | "op" | "redir"
    word: Word | None = None
    op: str | None = None
    fd: int | None = None
    target: Word | None = None
    body: str | None = None


_PLAIN = re.compile(r"[^\s;&|()<>'\"\\$`]+")
_DQ_STOP = re.compile(r"[\"\\$`]")
_BLANK = re.compile(r"[ \t]+")
_REDIR_OPS = ("<<<", "<<-", "&>>", ">>", ">|", ">&", "&>", "<<", "<>", "<&", ">", "<")
_OPS = (";;", "&&", "||", "|&", ";", "|", "&", "(", ")")


def _skip_dq(s: str, i: int) -> int:
    """i = 여는 따옴표 다음. 닫는 따옴표 다음 인덱스."""
    n = len(s)
    while i < n:
        m = _DQ_STOP.search(s, i)
        if not m:
            break
        i, c = m.start(), s[m.start()]
        if c == '"':
            return i + 1
        i = _skip_sub(s, i) if c != "\\" else i + 2
    raise LexError("닫히지 않은 큰따옴표")


def _skip_sub(s: str, i: int) -> int:
    """s[i] 는 `$`(뒤에 ( 또는 {)·백틱·`\\` 중 하나가 아닌 경우도 안전하게 한 걸음. 치환 전체를 건너뛴 다음 인덱스."""
    c = s[i]
    if c == "`":
        j = i + 1
        while j < len(s):
            if s[j] == "\\":
                j += 2
            elif s[j] == "`":
                return j + 1
            else:
                j += 1
        raise LexError("닫히지 않은 백틱")
    nxt = s[i + 1 : i + 2]
    if nxt == "(":
        return _skip_to(s, i + 2, ")")
    if nxt == "{":
        return _skip_to(s, i + 2, "}")
    return i + 1


def _skip_to(s: str, i: int, closer: str) -> int:
    """중첩·따옴표를 세며 closer 다음 인덱스. i 는 여는 기호 다음."""
    n = len(s)
    while i < n:
        c = s[i]
        if c == closer:
            return i + 1
        if c == "'":
            j = s.find("'", i + 1)
            if j < 0:
                raise LexError("닫히지 않은 작은따옴표")
            i = j + 1
        elif c == '"':
            i = _skip_dq(s, i + 1)
        elif c == "\\":
            i += 2
        elif c == "`" or (c == "$" and s[i + 1 : i + 2] in ("(", "{")):
            i = _skip_sub(s, i)
        elif c == "(" and closer == ")":
            i = _skip_to(s, i + 1, ")")
        else:
            i += 1
    raise LexError(f"닫히지 않은 {closer!r}")


def _read_dq(s: str, i: int) -> tuple[str, int]:
    """큰따옴표 본문. 평문 구간만 \\" 와 \\\\ 를 해제하고 치환($(..) ${..} 백틱)은 원문 유지(해제하면 안쪽 명령이 가려진다)."""
    out: list[str] = []
    n = len(s)
    while i < n:
        m = _DQ_STOP.search(s, i)
        if not m:
            break
        out.append(s[i : m.start()])
        i, c = m.start(), s[m.start()]
        if c == '"':
            return "".join(out), i + 1
        if c == "\\":
            nxt = s[i + 1 : i + 2]
            out.append(nxt if nxt in ('"', "\\") else s[i : i + 2])
            i += 2
        else:
            j = _skip_sub(s, i)
            out.append(s[i:j])
            i = j
    raise LexError("닫히지 않은 큰따옴표")


def _read_word(s: str, i: int) -> tuple[Word, int]:
    n = len(s)
    parts: list[Part] = []

    def add(text: str, q: str) -> None:
        if q == "" and parts and parts[-1].quote == "":
            parts[-1] = Part(parts[-1].text + text, "")
        else:
            parts.append(Part(text, q))

    while i < n:
        c = s[i]
        m = _PLAIN.match(s, i)
        if m:
            add(m.group(), "")
            i = m.end()
        elif c == "'":
            j = s.find("'", i + 1)
            if j < 0:
                raise LexError("닫히지 않은 작은따옴표")
            add(s[i + 1 : j], "'")
            i = j + 1
        elif c == '"':
            text, i = _read_dq(s, i + 1)
            add(text, '"')
        elif c == "\\":
            if s[i + 1 : i + 2] == "\n":
                i += 2
            elif i + 1 >= n:
                raise LexError("끝의 백슬래시")
            else:
                add(s[i + 1], "'")
                i += 2
        elif c == "$" and s[i + 1 : i + 2] == "'":
            j = i + 2
            while j < n and s[j] != "'":
                j += 2 if s[j] == "\\" else 1
            if j >= n:
                raise LexError("닫히지 않은 $'")
            add(s[i + 2 : j], "'")
            i = j + 1
        elif c in "$`":
            j = _skip_sub(s, i)
            add(s[i:j], "")
            i = j
        elif c in "<>" and s[i + 1 : i + 2] == "(":  # 프로세스 치환은 단어의 일부
            j = _skip_to(s, i + 2, ")")
            add(s[i:j], "")
            i = j
        else:
            break  # 공백·연산자·리다이렉트
    return Word(tuple(parts)), i


def lex(src: str) -> list[Token]:
    s, n = src, len(src)
    toks: list[Token] = []
    pending: list[tuple[int, str, bool]] = []  # (토큰 인덱스, 구분자, <<- 여부)
    i = 0
    last_word_end = -1
    while i < n:
        c = s[i]
        if c in " \t":
            i = _BLANK.match(s, i).end()
        elif c == "\\" and s[i + 1 : i + 2] == "\n":
            i += 2
        elif c == "\n":
            toks.append(Token("op", op="\n"))
            i += 1
            for idx, delim, strip in pending:
                start = i
                while True:
                    if i >= n:
                        raise LexError(f"끝나지 않은 heredoc {delim!r}")
                    j = s.find("\n", i)
                    end = n if j < 0 else j
                    line = s[i:end]
                    if (line.lstrip("\t") if strip else line) == delim:
                        body = s[start : i - 1] if i > start else ""
                        toks[idx] = replace(toks[idx], body=body)
                        i = end + 1 if j >= 0 else n
                        break
                    i = end + 1
            pending.clear()
        elif c == "#":
            j = s.find("\n", i)
            i = n if j < 0 else j
        else:
            op = next((o for o in _REDIR_OPS if s.startswith(o, i) and not s.startswith("<(", i) and not s.startswith(">(", i)), None)
            if op:
                fd = None
                if (
                    toks and toks[-1].kind == "word" and last_word_end == i
                    and len(toks[-1].word.parts) == 1 and toks[-1].word.parts[0].quote == ""
                    and toks[-1].word.literal().isdigit()
                ):
                    fd = int(toks.pop().word.literal())
                i += len(op)
                if (m := _BLANK.match(s, i)):
                    i = m.end()
                target, i = _read_word(s, i)
                if not target.parts:
                    raise LexError(f"리다이렉트 {op} 대상 없음")
                if op in ("<<", "<<-"):
                    pending.append((len(toks), target.literal(), op == "<<-"))
                toks.append(Token("redir", op=op, fd=fd, target=target))
                last_word_end = -1
                continue
            op = next((o for o in _OPS if s.startswith(o, i)), None)
            if op:
                toks.append(Token("op", op=op))
                i += len(op)
                continue
            w, i = _read_word(s, i)
            if not w.parts:
                raise LexError(f"해석할 수 없는 문자 {c!r}")
            toks.append(Token("word", word=w))
            last_word_end = i
    if pending:
        raise LexError(f"끝나지 않은 heredoc {pending[0][1]!r}")
    return toks


@dataclass(frozen=True)
class Mount:
    source: str  # bind: 호스트 절대경로 / volume: 볼륨 이름
    destination: str  # 컨테이너 안 절대경로
    kind: str  # "bind" | "volume"


@dataclass(frozen=True)
class Context:
    kind: str = "host"  # "host" | "container"
    container: str | None = None
    launcher: str | None = None  # "exec" | "run" | "compose-exec" | "compose-run"
    mounts: tuple[Mount, ...] | None = None  # run 계열: 인자에서 / exec 계열: None(조회)
    project_dir: str | None = None
    project: str | None = None


HOST = Context()


@dataclass
class Redirect:
    op: str
    fd: int | None
    target: Word | None
    body: str | None


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
    segments: list[Segment] = field(default_factory=list)
    error: str | None = None


_ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
_BOUNDARY = ("\n", ";", ";;", "&&", "||", "|", "|&", "&")
_SUBSHELL_OPS = ("|", "|&", "&")  # 파이프 구성원·배경 명령은 서브셸이라 cd·변수가 밖으로 안 나간다
_VAR_DECL = ("export", "declare", "typeset", "local")
# 래퍼 -> 값을 받는 옵션. 값 없는 옵션은 '-' 로 시작하는 단어 하나로 소비한다.
_WRAPPER_VALUE_OPTS: dict[str, tuple[str, ...]] = {
    "command": (),
    "sudo": ("-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U"),
    "timeout": ("-s", "-k"),
    "nice": ("-n",),
    "ionice": ("-c", "-n", "-p"),
    "stdbuf": ("-i", "-o", "-e"),
    "flock": ("-w", "-E"),
    "time": (),
    "exec": ("-a",),
    "doas": ("-u", "-C"),
}
_WRAPPER_TAIL = {"timeout": 1, "flock": 1}  # 옵션 뒤에 소비할 위치 인자 수
_SIMPLE_WRAPPERS = ("builtin", "nohup", "chronic")
# 단위 맨 앞에서 벗기는 제어 예약어. `for`/`select` 머리는 명령이 아니라 단위를 내지 않는다.
_RESERVED = ("{", "}", "!", "if", "then", "elif", "else", "fi", "while", "until", "do", "done")
_LOOP_HEAD = ("for", "select")


def _assign_of(w: Word) -> tuple[str, str | None] | None:
    """`NAME=값` 단어면 (이름, 값). 값에 명령 치환이 있으면 None 값 (Task 3 에서 expand 로 교체)."""
    if not w.parts or w.parts[0].quote != "" or not _ASSIGN.match(w.parts[0].text):
        return None
    head, _, rest = w.parts[0].text.partition("=")
    if any(p.quote != "'" and ("$(" in p.text or "`" in p.text) for p in w.parts[1:]) or "$(" in rest or "`" in rest:
        return head, None
    return head, rest + "".join(p.text for p in w.parts[1:])


def _resolve_dir(w: Word, cwd: str | None, env: Mapping[str, str | None]) -> str | None:
    """cd 인자 해석. `~`·`$HOME` 만 풀고 그 외 변수·치환이면 None (Task 3 에서 expand 로 교체)."""
    parts = list(w.parts)
    prefix = ""
    first = parts[0] if parts else Part("", "'")
    for pre in ("~", "${HOME}", "$HOME"):
        if first.quote == "" and first.text.startswith(pre) and first.text[len(pre):len(pre) + 1] in ("", "/"):
            prefix = env.get("HOME") or ""
            if not prefix:
                return None
            parts[0] = Part(first.text[len(pre):], "")
            break
    if any(p.quote != "'" and ("$" in p.text or "`" in p.text) for p in parts):
        return None
    lit = prefix + "".join(p.text for p in parts)
    if lit == "-":
        return None
    if lit.startswith("/"):
        return os.path.normpath(lit)
    return os.path.normpath(os.path.join(cwd, lit)) if cwd is not None else None


def _strip_wrapper(words: list[Word], env: dict[str, str | None]) -> list[Word] | None:
    """맨 앞 래퍼 하나를 벗긴 단어 목록. 래퍼가 아니면 None."""
    name = os.path.basename(words[0].literal())
    i = 1
    if name == "env":
        while i < len(words):
            lit = words[i].literal()
            if (a := _assign_of(words[i])) is not None:
                env[a[0]] = a[1]
            elif lit in ("-u", "-C"):
                i += 1
            elif not lit.startswith("-") or lit == "--":
                if lit == "--":
                    i += 1
                break
            i += 1
        return words[i:]
    if name in _SIMPLE_WRAPPERS:
        return words[1:]
    if name == "command":  # -v/-V 는 실행이 아니라 조회라 벗기지 않는다
        for x in words[1:]:
            lit = x.literal()
            if lit == "--" or not lit.startswith("-"):
                break
            if "v" in lit or "V" in lit:
                return None
    if name not in _WRAPPER_VALUE_OPTS:
        return None
    while i < len(words) and words[i].literal().startswith("-") and words[i].literal() != "--":
        i += 2 if words[i].literal() in _WRAPPER_VALUE_OPTS[name] else 1
    if i < len(words) and words[i].literal() == "--":
        i += 1
    return words[i + _WRAPPER_TAIL.get(name, 0):]


def parse(command: str, cwd: str | None, env: Mapping[str, str], context: Context = HOST) -> ParseResult:
    try:
        toks = lex(command)
    except LexError as e:
        return ParseResult([], str(e))
    state_env: dict[str, str | None] = {k: env[k] for k in ("HOME", "TMPDIR", "USER") if k in env}
    if cwd is not None:
        state_env["PWD"] = cwd
    st = {"cwd": cwd}
    stack: list[tuple[str | None, dict[str, str | None]]] = []
    segments: list[Segment] = []
    words: list[Word] = []
    redirects: list[Redirect] = []

    def flush() -> None:
        nonlocal words, redirects
        w, r, words, redirects = words, redirects, [], []
        unit_env = dict(state_env)
        first = True
        while True:
            while w and not w[0].is_quoted() and w[0].literal() in _RESERVED:
                w = w[1:]
            while w and (a := _assign_of(w[0])) is not None:
                unit_env[a[0]] = a[1]
                w = w[1:]
                if not w and first:  # 할당만 있는 단위는 이후 단위에 반영
                    state_env.update(unit_env)
                    return
            first = False
            rest = _strip_wrapper(w, unit_env) if w else None
            if rest is None:
                break
            w = rest
        if w and not w[0].is_quoted() and w[0].literal() in _LOOP_HEAD:
            return
        unit_cwd = st["cwd"]
        name = os.path.basename(w[0].literal()) if w else ""
        if name == "git":
            while len(w) > 2 and w[1].literal() == "-C":
                unit_cwd = _resolve_dir(w[2], unit_cwd, unit_env)
                w = [w[0]] + w[3:]
        if name in _VAR_DECL:
            for x in w[1:]:
                if (a := _assign_of(x)) is not None:
                    state_env[a[0]] = a[1]
            return
        if w or r:
            segments.append(Segment(name, w, r, unit_cwd, unit_env, context))
        if name in ("cd", "pushd"):
            args = [x for x in w[1:] if x.literal() != "--" and not (x.literal().startswith("-") and x.literal() != "-")]
            st["cwd"] = _resolve_dir(args[0], st["cwd"], unit_env) if args else (
                state_env.get("HOME") if name == "cd" else None)
            if st["cwd"] is not None:
                state_env["PWD"] = st["cwd"]
        elif name == "popd":
            st["cwd"] = None

    snap = (st["cwd"], dict(state_env))
    in_pipe = False

    def restore() -> None:
        st["cwd"] = snap[0]
        state_env.clear()
        state_env.update(snap[1])

    def open_group(kind: str) -> None:
        # 파이프 구성원 판정은 같은 그룹 깊이에서만 하므로 안쪽은 in_pipe 를 새로 시작한다
        nonlocal snap, in_pipe
        stack.append((kind, st["cwd"], dict(state_env), in_pipe))
        in_pipe = False
        snap = (st["cwd"], dict(state_env))

    def close_group(kind: str) -> bool:
        nonlocal snap, in_pipe
        flush()
        if in_pipe:  # 그룹 안 마지막 파이프 구성원
            restore()
        if not stack or stack[-1][0] != kind:
            return False
        _, cwd0, env0, outer_pipe = stack.pop()
        if kind == "(" or outer_pipe:  # 서브셸, 또는 파이프 구성원인 { } 는 안쪽 변화가 밖으로 안 나간다
            st["cwd"] = cwd0
            state_env.clear()
            state_env.update(env0)
        in_pipe = outer_pipe
        snap = (cwd0, env0)  # 그룹 뒤 `|`·`&` 가 오면 그룹 전체를 되돌리는 기준
        return True

    for t in toks:
        if t.kind == "word":
            w = t.word
            if not words and not redirects and not w.is_quoted() and w.literal() in ("{", "}"):
                if w.literal() == "{":
                    open_group("{")
                elif not close_group("{"):
                    return ParseResult([], "짝 없는 '}'")
            else:
                words.append(w)
        elif t.kind == "redir":
            redirects.append(Redirect(t.op, t.fd, t.target, t.body))
        elif t.op in _BOUNDARY:
            flush()
            if in_pipe or t.op in _SUBSHELL_OPS:
                restore()
            in_pipe = t.op in ("|", "|&")
            snap = (st["cwd"], dict(state_env))
        elif t.op == "(":
            flush()
            open_group("(")
        elif t.op == ")":
            if not close_group("("):
                return ParseResult([], "짝 없는 ')'")
    flush()
    if stack:
        return ParseResult([], "닫히지 않은 그룹")
    return ParseResult(segments)
