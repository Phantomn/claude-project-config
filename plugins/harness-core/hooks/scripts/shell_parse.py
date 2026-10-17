"""bash-guard 어휘 분석기: 셸 명령 문자열 -> 토큰 목록 (spec §3.3-1).

shlex 를 쓰지 않는 이유: 따옴표 종류·리다이렉트 위치·`2>&1` 을 잃어 단위 분해가 틀어진다.
"""
from __future__ import annotations

import glob
import itertools
import os
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, field, replace


class LexError(ValueError):
    pass


class ModelError(LexError):
    """해석기가 모델링하지 못하는 구문(함수 재귀·재정의·갈래 정의 뒤 호출·source/eval 정의·unset -f·함수 안 함수·인라인 상한·break 모양·
    heredoc 슬라이스·목록 밖 docker 옵션·재귀 깊이) — bash 가 돌리는 명령이라 위험 단어와 무관하게 거부한다. 구문 오류(LexError)는 spec §3.8 (가)."""


class CodeUnknown(ModelError):
    """bash 가 돌리지만 정적으로 알 수 없는 셸 코드(변수·치환으로 만든 `-c` 문자열·eval·trap·heredoc·`<<<`) — 최종 묶음 C 항목 7.
    사유가 다르다: 리터럴로 쓰거나 스크립트 파일로 실행하라."""


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
    pos: int = -1  # 단어 시작 위치(원문 인덱스) — for 본문 원문을 잘라낼 때 쓴다


# 단어를 끊는 공백은 공백·탭·개행뿐(bash 실측) — \r·\v·\f·NBSP 등 다른 유니코드 공백은 단어 글자다
_PLAIN = re.compile(r"[^ \t\n;&|()<>'\"\\$`]+")
_DQ_STOP = re.compile(r"[\"\\$`]")
_BLANK = re.compile(r"[ \t]+")
_REDIR_OPS = ("<<<", "<<-", "&>>", ">>", ">|", ">&", "&>", "<<", "<>", "<&", ">", "<")
_OPS = (";;&", ";;", ";&", "&&", "||", "|&", ";", "|", "&", "(", ")")


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
    """s[i] 는 `$` 또는 백틱. `$(…)`·`${…}`·백틱이면 치환 전체를 건너뛴 다음 인덱스, 그 밖의 `$` 면 한 걸음 뒤."""
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
    if nxt == "(":   # 산술 `$((…))` 안의 << 는 시프트다 — heredoc 으로 보면 뒤 명령을 본문으로 건너뛴다
        return _skip_to(s, i + 2, ")", not s.startswith("$((", i))
    if nxt == "{":
        return _skip_to(s, i + 2, "}")
    return i + 1


def _heredoc_end(s: str, i: int, delim: str, strip: bool, sub: bool = False) -> tuple[int, int]:
    """i = 본문 첫 줄 시작. (본문 끝 인덱스, 구분자 줄 다음 인덱스). 구분자 줄이 없으면 LexError.

    sub(`( )` 안): bash 5.2 는 구분자로 시작하고 `)` 가 든 줄에서 heredoc 을 끝낸다(경고만, 실측). `delim)` 은 그대로
    따르고(다음 인덱스 = 그 `)`), 그 밖의 모양(`EOF )`·`EOFX)`)은 모델링하지 않아 해석 실패로 둔다."""
    n, start = len(s), i
    while i < n:
        j = s.find("\n", i)
        end = n if j < 0 else j
        line = s[i:end]
        body = line.lstrip("\t") if strip else line
        if body == delim:
            return (i - 1 if i > start else start), (end + 1 if j >= 0 else n)
        if sub and body.startswith(delim) and ")" in body[len(delim):]:
            if body[len(delim)] != ")":
                raise LexError(f"heredoc 끝 줄을 확정할 수 없음 {line!r}")
            return (i - 1 if i > start else start), end - len(body) + len(delim)
        i = end + 1
    raise LexError(f"끝나지 않은 heredoc {delim!r}")


def _skip_to(s: str, i: int, closer: str, heredoc: bool = True) -> int:
    """중첩·따옴표를 세며 closer 다음 인덱스. i 는 여는 기호 다음. `( )` 안 heredoc 본문은 건너뛴다(heredoc=False 면 산술)."""
    n = len(s)
    pending: list[tuple[str, bool]] = []
    while i < n:
        c = s[i]
        if c == closer:
            # 줄바꿈 전에 닫힌 `<<` 는 산술 시프트이거나 본문 없는 heredoc — 후자는 안쪽 코드를 lex 할 때 오류가 된다
            return i + 1
        if c == "\n" and pending:
            i += 1
            for k, (delim, strip) in enumerate(pending):
                i = _heredoc_end(s, i, delim, strip, True)[1]
                if s[i : i + 1] == ")" and k < len(pending) - 1:
                    raise LexError("`)` 로 닫힌 heredoc 뒤에 남은 heredoc")
            pending.clear()
        elif c == "<" and closer == ")" and heredoc and s.startswith("<<", i) and not s.startswith("<<<", i):
            strip = s.startswith("<<-", i)
            j = i + 2 + strip
            if (m := _BLANK.match(s, j)):
                j = m.end()
            w, i = _read_word(s, j)
            if not w.parts:
                raise LexError("heredoc 구분자 없음")
            pending.append((w.literal(), strip))
        elif c == "'":
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
            i = _skip_to(s, i + 1, ")", heredoc)
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


_ANSI_SIMPLE = {"a": 7, "b": 8, "e": 27, "E": 27, "f": 12, "n": 10, "r": 13, "t": 9, "v": 11, "\\": 92, "'": 39, '"': 34, "?": 63}
_ANSI_ESC = re.compile(r"\\(?:([abeEfnrtv\\'\"?])|([0-7]{1,3})|x([0-9A-Fa-f]{1,2})|u([0-9A-Fa-f]{1,4})|U([0-9A-Fa-f]{1,8})|c(\\\\|[^\\]))")


def _ansi_c(text: str) -> str:
    """`$'…'` 본문을 bash 처럼 푼다(실측): \\nnn·\\xHH 는 바이트, \\u·\\U 는 문자, \\cX 는 제어 문자, NUL 에서 끝, 모르는 \\z 는 그대로."""
    out, i = bytearray(), 0
    for m in _ANSI_ESC.finditer(text):
        out += text[i:m.start()].encode("utf-8", "surrogateescape")
        simple, octal, hx, uni4, uni8, ctl = m.groups()
        if simple:
            out.append(_ANSI_SIMPLE[simple])
        elif octal:
            out.append(int(octal, 8) & 0xFF)
        elif hx:
            out.append(int(hx, 16))
        elif ctl:
            out.append((ord(ctl[-1].upper()) ^ 0x40) & 0xFF)
        elif int(uni4 or uni8, 16) <= 0x10FFFF:
            out += chr(int(uni4 or uni8, 16)).encode("utf-8", "surrogatepass")
        else:
            out += m.group().encode()
        i = m.end()
    out += text[i:].encode("utf-8", "surrogateescape")
    return bytes(out).split(b"\0", 1)[0].decode("utf-8", "surrogateescape")


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
            add(_ansi_c(s[i + 2 : j]), "'")
            i = j + 1
        elif c in "$`":
            j = _skip_sub(s, i)
            add(s[i:j], "")
            i = j
        elif c in "<>" and s[i + 1 : i + 2] == "(":  # 프로세스 치환은 단어의 일부
            j = _skip_to(s, i + 2, ")")
            add(s[i:j], "")
            i = j
        elif c == "(" and parts and parts[-1].quote == "" and parts[-1].text[-1:] in ("!", "@", "+", "*", "?"):
            j = _skip_to(s, i + 1, ")")   # 확장 글롭 `!(…)` 등 — bash(extglob)는 단어로 읽는다(실측)
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
        if len(toks) & 1023 == 0:
            _check_deadline()   # 큰 입력은 토큰화 중에도 마감을 본다
        if c in " \t":
            i = _BLANK.match(s, i).end()
        elif c == "\\" and s[i + 1 : i + 2] == "\n":
            i += 2
        elif c == "\n":
            toks.append(Token("op", op="\n", pos=i))
            i += 1
            for idx, delim, strip in pending:
                start = i
                body_end, i = _heredoc_end(s, i, delim, strip)
                toks[idx] = replace(toks[idx], body=s[start:body_end])
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
                toks.append(Token("op", op=op, pos=i))
                i += len(op)
                continue
            start, (w, i) = i, _read_word(s, i)
            if not w.parts:
                raise LexError(f"해석할 수 없는 문자 {c!r}")
            toks.append(Token("word", word=w, pos=start))
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
    cli: str = "docker"       # 띄운 CLI 이름(docker|podman|docker-compose) — podman 은 데몬이 없다(C3 I2-a)
    daemon_set: bool = False   # 명령이 데몬을 직접 지정(-H/--host/-c/--context/--config, DOCKER_HOST/CONTEXT/CONFIG 할당·해제·env 미확정) — 훅 env 의 소켓 부재는 증거 아님(C3 I2-c, C4 R-D)


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
    log_len: int = 0   # 최상위 해석의 쓰기 로그 길이 — 테스트 계측(test_shell_parse.test_log_is_bounded_by_writes 가 쓴다), 판정은 안 쓴다
    unmodeled: bool = False   # error 가 모델링 불가(ModelError) — bash 는 돌리므로 fail-closed
    dynamic: bool = False     # 그중 정적으로 알 수 없는 코드(CodeUnknown) — 사유 문구가 다르다


_ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\[[^]]*\])?\+?=")
_OP_ASSIGN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*):?=")   # `${f:=값}`·`${f=값}` 는 확장하며 f 에 대입한다
_NAMEREF = "\x00nameref"   # declare -n 이 있었다 — 어느 이름에 대입해도 다른 변수가 바뀔 수 있다
_BOUNDARY = ("\n", ";", ";;", "&&", "||", "|", "|&", "&")
_VAR_DECL = ("export", "declare", "typeset", "local")
# 래퍼 -> 값을 받는 옵션. 값 없는 옵션은 '-' 로 시작하는 단어 하나로 소비한다.
_WRAPPER_VALUE_OPTS: dict[str, tuple[str, ...]] = {
    "command": (),
    "sudo": ("-u", "-g", "-h", "-p", "-C", "-D", "--chdir", "-r", "-t", "-U"),
    "timeout": ("-s", "-k"),
    "nice": ("-n",),
    "ionice": ("-c", "-n", "-p"),
    "stdbuf": ("-i", "-o", "-e"),
    "flock": ("-w", "-E"),
    "time": (),
    "exec": ("-a",),
    "doas": ("-u", "-C"),
    # 최종 리뷰 I6 — 이 호스트의 --help 실측(util-linux setsid/flock/su/runuser, strace 6.8, ltrace 0.7.3, procps watch 4.0.4)
    "setsid": (),
    "strace": ("-e", "-o", "-p", "-s", "-P", "-E", "-u", "-I", "-S", "-O", "-a", "-X", "-b", "-U", "--trace", "--signal", "--status",
               "--trace-fds", "--trace-path", "--output", "--env", "--user", "--attach", "--columns", "--interruptible", "--detach-on",
               "--string-limit", "--abbrev", "--verbose", "--raw", "--read", "--write", "--quiet", "--kvm", "--decode-fds", "--overhead",
               "--summary-sort-by", "--summary-columns"),
    "ltrace": ("-a", "-A", "-D", "-e", "-F", "-l", "-n", "-o", "-p", "-s", "-u", "-x"),
    "watch": ("-n", "--interval", "-q", "--equexit"),
    "runuser": ("-u", "--user", "-g", "--group", "-G", "--supp-group", "-w", "--whitelist-environment", "-s", "--shell"),
}
_WRAPPER_TAIL = {"timeout": 1, "flock": 1}  # 옵션 뒤에 소비할 위치 인자 수
# `-c 코드`(watch 는 인자 전체)를 그 셸이 돌린다 — `sh -c 코드` 로 바꿔 안쪽을 해석한다(su·runuser 는 로그인 셸, flock·watch 는 sh)
_CODE_WRAPPERS = ("su", "runuser", "flock", "watch")
_CODE_OPTS = ("-c", "--command", "--session-command")
_SIMPLE_WRAPPERS = ("builtin", "nohup", "chronic", "busybox")   # busybox <애플릿> …
# 단위 맨 앞에서 벗기는 제어 예약어. `for`/`select` 머리는 명령이 아니라 단위를 내지 않는다.
# `time` 은 예약어라 뒤에 복합 명령(`time if …`)이 올 수 있다 — 래퍼로 벗기면 `if` 가 명령 자리로 보이지 않는다(NB8)
_RESERVED = ("{", "}", "!", "time", "if", "then", "elif", "else", "fi", "while", "until", "do", "done", "esac")
_LOOP_HEAD = ("for", "select")
_LOOPS = ("for", "select", "while", "until")
_CTL_OPEN = ("if", "while", "until")
_CTL = {"then": ("if", ("cond",)), "elif": ("if", ("body",)), "else": ("if", ("body",)), "fi": ("if", ("body", "else")),
        "do": ("loop", ("cond",)), "done": ("loop", ("body", "done"))}   # 예약어 -> (짝 종류, 그 앞에 올 수 있는 mode)
_FOR_CAP = 50   # for 목록 항목 상한 — 넘으면 루프 변수 미확정(본문을 항목마다 해석하는 비용)
_FOR_TOTAL = 500   # 해석 한 번의 반복 총량 — 치환 안 루프 중첩이 곱으로 커지지 않게
_FOR_CHARS = 200_000   # 해석 한 번에 본문을 다시 해석하는 글자 수 총량 — 반복 수만으로는 본문 길이 비용이 안 묶인다
_last_log = [0]   # 최상위 해석의 쓰기 로그 길이(ParseResult.log_len)
fn_stack: list[str] = []   # 인라인 해석 중인 함수 이름들(재귀·깊이 검출) — parse() 마다 비운다
fn_locals: list[set[str]] = []   # 인라인 호출마다 본문이 선언한 local 이름 — 호출 끝에 복원(갈래 합류·중첩 호출과 무관)
fn_args: list[list[Word]] = []   # 인라인 호출마다 인자 단어들 — 본문의 `"$@"` 명령 자리를 인자 단어들로 바꾼다
fn_called: set[str] = set()   # 인라인된 함수 이름 — 그 정의 시점 단위(미확정 인자로 판정)는 결과에서 뺀다
fn_def_segs: list[tuple[str, int, int]] = []   # (이름, 정의 본문 단위의 segments 구간)
_for_runs = [0, 0]   # [반복 수, 재해석 글자 수] — parse() 마다 0 으로. 훅은 한 프로세스에서 한 번씩 해석한다
_deadline: list[float | None] = [None]   # 판정기 마감(time.monotonic) — 지나면 루프를 묶지 않는다


def _late() -> bool:
    return _deadline[0] is not None and time.monotonic() > _deadline[0]


def _check_deadline() -> None:
    """마감 검사는 여기 한 곳 — 토큰마다·해석 입구·합류에서 부른다(단일 단위 안에서도 마감을 본다, 재검토 3 NB4·NB10)."""
    if _late():
        raise LexError("해석 시간 초과")


SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
_MAX_DEPTH = 8
# 셸 호출 옵션(C4 R-A, bash 5.2·dash 0.5.12 실측): 한 글자는 두 셸의 합집합, 그 밖(zsh 전용 등)은 확정 불가
_SH_LETTERS = frozenset("abcefhiklmnprstuvxBCDEHIPTV")
_SH_LONG = frozenset({"--norc", "--noprofile", "--posix", "--login", "--restricted", "--verbose", "--noediting", "--pretty-print"})
_SH_LONG_VALUE = frozenset({"--rcfile", "--init-file"})   # 값 단어를 받는다(`--rcfile=x` 는 bash 가 거부)
_SH_LONG_EXIT = frozenset({"--help", "--version", "--dump-strings", "--dump-po-strings"})   # 코드를 돌리지 않고 끝난다
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_BRACE = re.compile(r"\{([^{}]*,[^{}]*)\}")
_HEREDOC = ("<<", "<<-")
# env 안의 셸 작업 폴더 — 변수 이름이 될 수 없는 키라 사용자 할당(PWD=…)으로 덮이지 않는다. `$(pwd)` 가 읽는다.
SHELL_CWD = "\x00cwd"
_STDIN_OPS = ("<", "<>", "<&", "<<", "<<-", "<<<")   # fd 를 생략하면 stdin 에 거는 연산자
_XARGS_VALUE = ("-a", "-d", "-E", "-I", "-J", "-L", "-n", "-P", "-s", "--arg-file", "--delimiter", "--max-args", "--max-procs",
                "--max-chars", "--max-lines", "--process-slot-var")
_XARGS_MARK = "\x00xargs-input\x00"  # xargs 가 입력으로 바꿔 넣는 자리 — 이 표시가 든 대상은 확정 불가
_SEQ = re.compile(r"(-?\d+|[a-zA-Z])\.\.(-?\d+|[a-zA-Z])(?:\.\.(-?\d+))?")
_BRACE_CAP = 64
_CONTAINER_CLIS = ("docker", "podman", "docker-compose")
# 옵션 표 = (값 옵션, 플래그). 표에 없는 옵션은 값 소비 여부를 몰라 이미지·명령 위치가 틀어지므로 해석 실패로 보낸다.
_DOCKER_GLOBAL = (
    {"-H", "--host", "-c", "--context", "--config", "-l", "--log-level", "--tlscacert", "--tlscert", "--tlskey",
     "--root", "--runroot", "--connection", "--url", "--identity", "--storage-driver", "--storage-opt", "--cgroup-manager",
     "--conmon", "--events-backend", "--hooks-dir", "--network-cmd-path", "--network-config-dir", "--registries-conf",
     "--runtime", "--runtime-flag", "--tmpdir", "--volumepath", "--imagestore", "--module", "--ssh", "--out", "--cdi-spec-dir"},
    {"-D", "--debug", "--tls", "--tlsverify", "-v", "--version", "--help", "-r", "--remote", "--syslog", "--noout"},
)
_EXEC = (
    {"-e", "--env", "--env-file", "-u", "--user", "-w", "--workdir", "--detach-keys"},
    {"-d", "--detach", "-i", "--interactive", "-t", "--tty", "--privileged"},
)
_RUN = (
    _EXEC[0] | {
        "-v", "--volume", "--mount", "--name", "-p", "--publish", "--network", "--net", "--network-alias", "--net-alias",
        "--entrypoint", "-l", "--label", "--label-file", "--platform", "--hostname", "-h", "--domainname", "--add-host",
        "--annotation", "-a", "--attach", "--blkio-weight", "--blkio-weight-device", "--cap-add", "--cap-drop",
        "--cgroup-parent", "--cgroupns", "--cidfile", "--cpu-period", "--cpu-quota", "--cpu-rt-period", "--cpu-rt-runtime",
        "-c", "--cpu-shares", "--cpus", "--cpuset-cpus", "--cpuset-mems", "--device", "--device-cgroup-rule",
        "--device-read-bps", "--device-read-iops", "--device-write-bps", "--device-write-iops", "--dns", "--dns-option",
        "--dns-opt", "--dns-search", "--expose", "--gpus", "--group-add", "--health-cmd", "--health-interval",
        "--health-retries", "--health-start-period", "--health-start-interval", "--health-timeout", "--ip", "--ip6", "--ipc",
        "--isolation", "--kernel-memory", "--link", "--link-local-ip", "--log-driver", "--log-opt", "--mac-address",
        "-m", "--memory", "--memory-reservation", "--memory-swap", "--memory-swappiness", "--oom-score-adj", "--pid",
        "--pids-limit", "--pull", "--restart", "--runtime", "--security-opt", "--shm-size", "--stop-signal",
        "--stop-timeout", "--storage-opt", "--sysctl", "--tmpfs", "--ulimit", "--userns", "--uts", "--volume-driver",
        "--volumes-from"},
    _EXEC[1] | {"--rm", "--init", "--read-only", "-P", "--publish-all", "-q", "--quiet", "--no-healthcheck",
                "--oom-kill-disable", "--disable-content-trust", "--sig-proxy", "--use-api-socket", "--help"},
)
_COMPOSE_GLOBAL = (  # docker compose(v2) 와 docker-compose(v1) 전역 옵션
    {"-f", "--file", "-p", "--project-name", "--project-directory", "--env-file", "--profile", "--ansi", "--parallel",
     "--progress", "--log-level", "-H", "--host", "-c", "--context", "--tlscacert", "--tlscert", "--tlskey"},
    {"--compatibility", "--dry-run", "--all-resources", "--verbose", "--help", "-h", "--no-ansi", "--skip-hostname-check",
     "--tls", "--tlsverify", "-v", "--version"},
)
_COMPOSE_EXEC = (
    {"-e", "--env", "-u", "--user", "-w", "--workdir", "--index"},
    {"-d", "--detach", "-T", "--no-TTY", "--no-tty", "--privileged", "-i", "--interactive", "-t", "--tty"},
)
_COMPOSE_RUN = (
    _COMPOSE_EXEC[0] | {"-v", "--volume", "--name", "-p", "--publish", "--entrypoint", "-l", "--label", "--env-from-file",
                        "--cap-add", "--cap-drop", "--pull"},
    _COMPOSE_EXEC[1] | {"--rm", "--no-deps", "--service-ports", "--use-aliases", "--build", "--quiet-pull",
                        "--remove-orphans"},
)


# ---- 단어 확장 (spec §3.3-4·8, §3.4 정규화 1~3) ----

def _seq(a: str, b: str, step: str | None) -> list[str] | None:
    """`{a..b[..step]}` 수열. 0 채움·숫자/문자 혼합·간격 0·상한 초과는 None."""
    num = a.lstrip("-").isdigit()
    if num != b.lstrip("-").isdigit() or (num and any(re.match(r"-?0\d", g) for g in (a, b))):
        return None
    x, y = (int(a), int(b)) if num else (ord(a), ord(b))
    k = abs(int(step)) if step else 1
    if k == 0 or abs(y - x) // k >= _BRACE_CAP:
        return None
    d = k if y >= x else -k
    return [str(v) if num else chr(v) for v in range(x, y + (1 if d > 0 else -1), d)]


# mktemp 결과 대신 쓰는 이름 — 없는 경로라 분류가 MISSING(허용)이 된다. 프로세스마다 고유
_MKTEMP_NAME = "bash-guard-mktemp-" + os.urandom(6).hex()
_TMPDIR0 = "\x00tmpdir"   # env 안의 호출 시점 TMPDIR — 변수 이름이 될 수 없는 키라 명령 안 할당으로 덮이지 않는다
_MKTEMP_OPT = re.compile(r"-([duqt]*)(?:p(.*))?")


def _mktemp(body: str, env: Mapping[str, str | None]) -> str | None:
    """`$(mktemp …)` 의 결과: 임시 루트(/tmp·/var/tmp·$TMPDIR) 아래 새 경로. 그 밖·모르는 옵션은 None(확정 불가)."""
    try:
        toks = lex(body)
    except LexError:
        return None
    if not toks or any(x.kind == "op" for x in toks) or toks[0].kind != "word" or toks[0].word.literal() != "mktemp":
        return None
    a = [x.word for x in toks if x.kind == "word"]
    tmp = env.get("TMPDIR")
    if tmp != env.get(_TMPDIR0):
        return None   # 이 명령 안에서 바꾼 TMPDIR 는 임시 루트로 믿지 않는다
    default = tmp or "/tmp"
    d: str | None = None
    tmpl, t_flag, i = None, False, 1
    while i < len(a):
        x = a[i].literal()
        if x in ("--directory", "--dry-run", "--quiet"):
            pass
        elif x.startswith(("--tmpdir", "--suffix")):
            k, eq, _ = x.partition("=")
            if k == "--tmpdir":
                d = _text(_drop(a[i], len(k) + 1).parts, env) if eq else default
            elif not eq:
                i += 1
        elif (m := _MKTEMP_OPT.fullmatch(x)) and x != "-":
            t_flag = t_flag or "t" in m.group(1)
            if m.group(2) is not None:
                w = _drop(a[i], len(x) - len(m.group(2))) if m.group(2) else (a[i + 1] if i + 1 < len(a) else None)
                i += 0 if m.group(2) else 1
                d = _text(w.parts, env) if w is not None else None
                if d is None:
                    return None
        elif x.startswith("-") or tmpl is not None:
            return None
        else:
            tmpl = _text(a[i].parts, env)
            if tmpl is None:
                return None
        i += 1
    if d is not None and tmpl is not None and "/" in tmpl:
        return None   # GNU mktemp 는 -p 폴더 뒤 템플릿의 `/`·`..` 로 폴더 밖에 만든다
    if d is None:
        if tmpl is not None and "/" in tmpl:
            if t_flag or not tmpl.startswith("/"):
                return None
            d = os.path.dirname(tmpl)
        elif tmpl is not None and not t_flag:
            return None   # 템플릿만 주면 현재 폴더에 만든다
        else:
            d = default
    d = os.path.normpath(d or default)
    roots = [os.path.normpath(r) for r in ("/tmp", "/var/tmp", tmp) if r]
    if not any(d == r or d.startswith(r + "/") for r in roots) or not os.path.isdir(d) or not os.access(d, os.W_OK | os.X_OK):
        return None   # 폴더가 없거나 쓸 수 없으면 mktemp 가 실패해 결과가 빈 값이 된다
    return os.path.join(d, _MKTEMP_NAME)


# 파이썬 fnmatch 가 bash 와 다르게 읽는 괄호 식 — `[^…]` 부정·`[[:class:]]`·`[=…=]`·`[.….]`(파이썬은 0건 → 리터럴 → 허용이 된다),
# 확장 글롭 `!(…)`·`@(…)`·`+(…)`·`*(…)`·`?(…)`(shopt extglob 여부를 모른다)
_BASH_ONLY_GLOB = re.compile(r"\[[\^!]|\[[:=.]|[!@+*?]\(")


def _bad_glob(ch: list[tuple[str, bool]]) -> bool:
    return any(a and _BASH_ONLY_GLOB.search(t) for t, a in ch)


def _mktemp_tail_unsafe(lit: str, globbing: bool) -> bool:
    """mktemp 결과 자리 뒤의 `..`·글롭 — 결과가 빈 값(실패)이면 `/..`·`/*` 가 된다."""
    return _MKTEMP_NAME in lit and (globbing or ".." in lit.partition(_MKTEMP_NAME)[2].split("/"))


def _dollar(t: str, i: int, env: Mapping[str, str | None]) -> tuple[str | None, int]:
    """t[i] 는 `$` 또는 백틱. (확장값 | None=확정 불가, 다음 인덱스).

    `$PWD` 는 env 의 PWD 변수(사용자가 덮어쓸 수 있음), `$(pwd)` 는 셸 작업 폴더 SHELL_CWD 를 쓴다
    — 둘 다 단위 cwd 와 다를 수 있다(컨테이너 -w, git -C).
    """
    if t[i] == "`" or t.startswith("$(", i):
        j = _skip_sub(t, i)
        body = t[i + 1 : j - 1] if t[i] == "`" else t[i + 2 : j - 1]
        return (env.get(SHELL_CWD) if body.strip() == "pwd" else _mktemp(body, env)), j
    if t.startswith("${", i):
        j = _skip_sub(t, i)
        inner = t[i + 2 : j - 1]
        return (env.get(inner) if _NAME.fullmatch(inner) or inner.isdigit() or inner in ("#", "@", "*") else None), j
    if (m := _NAME.match(t, i + 1)):
        return env.get(m.group()), m.end()
    if t[i + 1 : i + 2] and t[i + 1] in "123456789#@*":   # 위치 매개변수 — 함수 인라인이 묶는다(없으면 미확정)
        return env.get(t[i + 1]), i + 2
    if t[i + 1 : i + 2] and t[i + 1] in "0?$!-":
        return None, i + 2
    return "$", i + 1


HOLE = "\x00hole\x00"
BASE_HOLE = "\x00base\x00"   # `$(basename …)` 자리
_HOLE_VAR = re.compile(r"\$(?:\$|[A-Za-z_][A-Za-z0-9_]*|\{[A-Za-z_][A-Za-z0-9_]*\})")
_HOLE_DATE = re.compile(r"\+(?:[A-Za-z0-9_.:-]|%[YmdHMSsNFTjyuwGVz%])+")   # 공백을 낼 수 없는 형식만(%c·%e 등 제외)


def _hole_mark(x: str, quoted: bool) -> str | None:
    """미확정 확장 x 를 채울 표식 — 한 단어로만 확장되는 형태만(그 밖 None). 배열·`$@`·연산자 확장은 여러 단어나 `..` 를 낸다.
    따옴표 없는 `$NAME` 은 값에 공백이 없다고 가정한다(정직한 실수 모델 §1.5 의 잔여 위험).
    `$(basename …)`(operand 1~2개)는 BASE_HOLE — 한 줄·`/` 없음이라 값이 ""·.·..·/ 뿐이어도 접두의 부모 안에 머문다."""
    if _HOLE_VAR.fullmatch(x):
        return None if x in ("$_", "${_}") else HOLE   # `$_` = 직전 명령의 마지막 인자 — 공백·`/` 가 들어갈 수 있다
    if not x.startswith(("$(", "`")):
        return None
    try:
        a = [t.word.literal() if t.word is not None else None for t in lex(x[2:-1] if x[0] == "$" else x[1:-1])]
    except LexError:
        return HOLE if quoted else None
    if a[:1] == ["basename"]:   # -a·-s·-z·--multiple 은 여러 줄·이름 여럿
        dd = a[1:2] == ["--"]
        ops = a[1 + dd:]
        if 1 <= len(ops) <= 2 and all(y is not None and (dd or not y.startswith("-")) for y in ops):
            return BASE_HOLE
    if quoted:
        return HOLE
    if a[:1] == ["uuidgen"]:   # --help·-V 는 공백 든 여러 줄을 낸다
        return HOLE if all(y in ("-r", "-t", "-x") for y in a[1:]) else None
    ok = len(a) >= 2 and a[0] == "date" and all(y in ("-u", "--utc") for y in a[1:-1]) and \
        a[-1] is not None and _HOLE_DATE.fullmatch(a[-1]) is not None
    return HOLE if ok else None


def _subst(parts: tuple[Part, ...], env: Mapping[str, str | None], split: bool = False,
           hole: bool = False) -> list[tuple[str, bool]] | None:
    """조각 -> (텍스트, 활성) 목록. 활성 = 따옴표 없는 리터럴(중괄호·와일드카드 대상). 확정 불가면 None.
    hole 이면 확정 못 한 변수·치환 자리를 None 대신 표식(HOLE·BASE_HOLE)으로 채운다."""
    out: list[tuple[str, bool]] = []
    for k, p in enumerate(parts):
        if p.quote == "'":
            out.append((p.text, False))
            continue
        t, active, i, start = p.text, p.quote == "", 0, 0
        if k == 0 and active and t.startswith("~"):
            home = env.get("HOME")
            if t.partition("/")[0] != "~" or ("/" not in t and len(parts) > 1) or not home:
                return None  # ~user·~+ 등은 확정 불가
            out.append((home, False))
            i = start = 1
        while i < len(t):
            c = t[i]
            if c == "\\" and not active and t[i + 1 : i + 2] in ("$", "`") and i + 1 < len(t):
                out += [(t[start:i], active), (t[i + 1], False)]
                i = start = i + 2
            elif c in "$`":
                val, j = _dollar(t, i, env)
                if val is None and (not hole or (val := _hole_mark(t[i:j], p.quote == '"')) is None):
                    return None
                if split and active and any(x.isspace() or x in "*?[" for x in val):
                    return None  # 따옴표 없는 값은 단어 분할·glob 되어 한 경로로 확정할 수 없다
                out += [(t[start:i], active), (val, False)]
                i = start = j
            elif active and c in "<>" and t[i + 1 : i + 2] == "(":
                return None  # 프로세스 치환 경로는 실행 시점에만 생긴다
            else:
                i += 1
        out.append((t[start:i], active))
    return out


def _text(parts: tuple[Part, ...], env: Mapping[str, str | None], split: bool = False) -> str | None:
    ch = _subst(parts, env, split)
    return None if ch is None else "".join(t for t, _ in ch)


def _brace_items(items: list[tuple[str, str]], out: list[list[tuple[str, str]]]) -> bool:
    """bash 처럼 변수 확장 전에 중괄호를 전개해 out 에 덧붙인다. 중첩·0 채움 수열·상한 초과면 False."""
    s = "".join(c if q == "" else "\0" for c, q in items)  # 따옴표 안 문자는 전개 기호가 아니다
    i, n = 0, len(s)
    while i < n:
        if s[i] == "`" or (s[i] == "$" and s[i + 1 : i + 2] in ("(", "{")):
            i = _skip_sub(s, i)
            continue
        if s[i] != "{":
            i += 1
            continue
        commas, j = [], i + 1
        while j < n and s[j] != "}":
            if s[j] == "`" or (s[j] == "$" and s[j + 1 : j + 2] in ("(", "{")):
                j = _skip_sub(s, j)
                continue
            if s[j] == "{":
                return False
            if s[j] == ",":
                commas.append(j)
            j += 1
        if j >= n:
            break  # 닫히지 않은 { 는 리터럴
        if commas:
            bounds = [i, *commas, j]
            alts = [items[a + 1 : b] for a, b in itertools.pairwise(bounds)]
        elif (m := _SEQ.fullmatch(s, i + 1, j)):
            if (vals := _seq(*m.groups())) is None:
                return False
            alts = [[(c, "") for c in v] for v in vals]
        elif ".." in s[i + 1 : j]:
            return False  # 지원하지 않는 수열 모양은 리터럴로 확정하지 않는다
        else:
            i = j + 1  # {}·{x} 는 리터럴
            continue
        if len(alts) > _BRACE_CAP:
            return False
        for alt in alts:
            if not _brace_items(items[:i] + alt + items[j + 1:], out) or len(out) > _BRACE_CAP:
                return False
        return True
    out.append(items)
    return True


def _brace_words(parts: tuple[Part, ...]) -> list[tuple[Part, ...]] | None:
    out: list[list[tuple[str, str]]] = []
    if not _brace_items([(c, p.quote) for p in parts for c in p.text], out):
        return None
    words = []
    for items in out:
        merged: list[list[str]] = []
        for c, q in items:
            if merged and merged[-1][1] == q:
                merged[-1][0] += c
            else:
                merged.append([c, q])
        words.append(tuple(Part(t, q) for t, q in merged))
    return words


def _expand(w: Word, env: Mapping[str, str | None], cwd: str | None) -> list[str] | None:
    try:
        return _expand_word(w, env, cwd)
    except LexError:  # 전개 결과가 셸 문법을 깨면(문자 수열이 백틱을 만드는 등) 확정 불가
        return None


def _expand_word(w: Word, env: Mapping[str, str | None], cwd: str | None) -> list[str] | None:
    words = _brace_words(w.parts)
    if words is None:
        return None
    out: list[str] = []
    for parts in words:
        ch = _subst(parts, env, split=True)
        if ch is None:
            return None
        lit = "".join(t for t, _ in ch)
        globbing = any(a and any(x in t for x in "*?[") for t, a in ch)
        if _XARGS_MARK in lit or _mktemp_tail_unsafe(lit, globbing) or _bad_glob(ch):
            return None
        if not lit.startswith("/"):
            if cwd is None:
                return None
            lit = os.path.join(cwd, lit) if lit else cwd
        if globbing:
            pat = "".join(t if a else glob.escape(t) for t, a in ch)
            if not pat.startswith("/"):
                pat = os.path.join(glob.escape(cwd), pat)
            if (hits := sorted(glob.glob(pat))):  # 점 파일은 패턴이 . 로 시작할 때만 — glob 기본이 bash 와 같다
                out += hits
                continue
        out.append(lit)
    return out


_GLOB_DIRS = 1000   # for 목록 글롭이 펼치는 중간 경로 상한


def _glob_list(pat: str, cwd: str | None) -> list[str] | None:
    """`glob.glob(pat, root_dir=cwd)` 를 구성요소마다 한 폴더씩 펼친다 — 폴더를 읽을 때마다 상한·마감을 봐서
    맞는 것 없는 깊은 글롭(`/mnt/c/*/*/*/x` 55초 실측)도 끊긴다. 넘으면 None."""
    rel = not pat.startswith("/")
    pre = (cwd or "").rstrip("/") + "/" if rel else "/"
    bases = [pre]
    for comp in [c for c in pat.split("/") if c]:
        nxt: list[str] = []
        for b in bases:
            if _late():
                return None
            if glob.has_magic(comp):
                nxt += glob.glob(os.path.join(glob.escape(b), comp))
            elif os.path.lexists(p := os.path.join(b, comp)):
                nxt.append(p)
        if len(nxt) > _GLOB_DIRS:
            return None
        bases = nxt
    if pat.endswith("/"):
        bases = [b + "/" for b in bases if os.path.isdir(b)]
    if len(bases) > _FOR_CAP:
        return None
    return sorted(b[len(pre):] if rel else b for b in bases)


def _values(w: Word, env: Mapping[str, str | None], cwd: str | None) -> list[str] | None:
    """for 목록 단어 -> 값들(중괄호·변수·글롭 전개, cwd 로 잇지 않는다). 확정 불가면 None."""
    try:
        words = _brace_words(w.parts)
        if words is None:
            return None
        out: list[str] = []
        for parts in words:
            ch = _subst(parts, env, split=True)
            if ch is None:
                return None
            lit = "".join(t for t, _ in ch)
            globbing = any(a and any(x in t for x in "*?[") for t, a in ch)
            if _XARGS_MARK in lit or _mktemp_tail_unsafe(lit, globbing) or _bad_glob(ch):
                return None
            if globbing:
                pat = "".join(t if a else glob.escape(t) for t, a in ch)
                if cwd is None and not pat.startswith("/"):
                    return None
                if (hits := _glob_list(pat, cwd)) is None:
                    return None
                if hits:
                    out += hits
                    continue
            if lit or any(p.quote for p in parts):   # 따옴표 없는 빈 전개는 단어가 사라진다
                out.append(lit)
        return out
    except LexError:
        return None


def expand_hole(word: Word, seg: Segment) -> str | None:
    """확정 못 한 변수·치환 자리를 HOLE·BASE_HOLE 로 남긴 경로 하나(상대경로는 seg.cwd 기준). 중괄호 여러 갈래·글롭·~user 면 None."""
    try:
        words = _brace_words(word.parts)
        if words is None or len(words) != 1:
            return None
        ch = _subst(words[0], seg.env, split=True, hole=True)
    except LexError:
        return None
    if ch is None or any(a and any(x in t for x in "*?[") for t, a in ch) or _bad_glob(ch):
        return None
    lit = "".join(t for t, _ in ch)
    if _XARGS_MARK in lit or (not lit.startswith("/") and seg.cwd is None):
        return None
    return lit if lit.startswith("/") else os.path.join(seg.cwd, lit)  # type: ignore[arg-type]


def expand(word: Word, seg: Segment) -> list[str] | None:
    """대상 경로 확장. None = 확정 불가. 상대경로는 seg.cwd 기준 절대경로(정규화는 하지 않음)."""
    return _expand(word, seg.env, seg.cwd)


def literal_args(seg: Segment) -> list[str]:
    return [w.literal() for w in seg.argv[1:]]


def _subs(t: str, unquoted: bool) -> list[str]:
    """텍스트 안 명령 치환·백틱·프로세스 치환의 본문들."""
    out: list[str] = []
    i = 0
    while i < len(t):
        c, nxt = t[i], t[i + 1 : i + 2]
        if c == "\\":
            i += 2
        elif c == "`" or (c == "$" and nxt in ("(", "{")):
            j = _skip_sub(t, i)
            if c == "`":
                out.append(t[i + 1 : j - 1])
            elif nxt == "{" or t.startswith("$((", i):
                out += _subs(t[i + 2 : j - 1], True)
            else:
                out.append(t[i + 2 : j - 1])
            i = j
        elif unquoted and c in "<>" and nxt == "(":
            j = _skip_to(t, i + 2, ")")
            out.append(t[i + 2 : j - 1])
            i = j
        else:
            i += 1
    return out


def _word_subs(w: Word) -> list[str]:
    return [x for p in w.parts if p.quote != "'" for x in _subs(p.text, p.quote == "")]


# ---- 단위 분해 ----

def _is_assign(w: Word) -> bool:
    return bool(w.parts) and w.parts[0].quote == "" and bool(_ASSIGN.match(w.parts[0].text))


_EXTGLOB = re.compile(r"[!@+*?]\(")


def _cmd_extglob(w: Word) -> bool:
    """명령 자리 단어에 따옴표 없는 확장 글롭 `!(…)` 등이 있는가 — extglob 꺼진 bash(기본)는 `!(cmd)` 를 부정 서브셸로
    실행하고 `@(…)` 등은 구문 오류라, 단어로 읽으면 안쪽 명령이 판정에서 사라진다(재검토 NB1). 치환 안은 보지 않는다."""
    for p in w.parts:
        if p.quote:
            continue
        i, t = 0, p.text
        while i < len(t):
            if t[i] in "$`":
                i = _skip_sub(t, i)
            elif _EXTGLOB.match(t, i):
                return True
            else:
                i += 1
    return False


def _assign_of(w: Word, env: Mapping[str, str | None]) -> tuple[str, str | None] | None:
    """`NAME=값` 단어면 (이름, 할당 시점에 확장한 값 | None=확정 불가). `NAME+=값`(누적)·`NAME[i]=값`(원소)은 미확정."""
    if not _is_assign(w):
        return None
    m = _ASSIGN.match(w.parts[0].text)
    head, rest = m.group()[:-1], w.parts[0].text[m.end():]   # type: ignore[union-attr]
    if head.endswith(("+", "]")):
        return head.partition("[")[0].rstrip("+"), None
    return head, _text(((Part(rest, ""),) if rest else ()) + w.parts[1:], env)


def _forget(env: dict[str, str | None]) -> None:
    """모든 변수를 미확정으로(어느 변수를 바꿨는지 모르는 source·동적 이름·nameref). 내부 키(\\x00…)는 그대로.
    없던 변수도 생길 수 있다 — 데몬 변수는 키로 남겨 훅 env 의 소켓 부재를 증거로 쓰지 않게 한다(C4 R-D)."""
    for k in env:
        if not k.startswith("\x00"):
            env[k] = None
    for k in _DAEMON_VARS:
        env[k] = None


_READ_VALUE = {"read": "adinNptu", "mapfile": "dnOsuCc", "readarray": "dnOsuCc"}   # 값을 받는 한 글자 옵션


def _clobbered(name: str, w: list[Word]) -> list[str]:
    """변수를 바꾸는 내장 명령이 건드리는 변수 이름 — 새 값은 모델링하지 않는다(미확정으로 둔다)."""
    a = [x.literal() for x in w[1:]]
    if name in ("unset", "readonly"):
        return [x.partition("=")[0] for x in a if not x.startswith("-")]
    if name == "let":
        return [m.group() for x in a if (m := _NAME.match(x))]
    if name == "getopts":
        return a[1:2]
    if name == "printf":
        return ([a[0][2:] or (a[1] if len(a) > 1 else "")] if a and a[0].startswith("-v") else [])
    if name not in _READ_VALUE:
        return []
    out, i = [], 0
    while i < len(a) and a[i].startswith("-") and a[i] != "--":
        x, i = a[i], i + 1
        k = next((n for n, ch in enumerate(x[1:], 1) if ch in _READ_VALUE[name]), None)
        if k is not None:   # 묶음(-rp q)의 값 옵션은 나머지 글자나 다음 단어를 값으로 받는다
            v = x[k + 1:] or (a[i] if i < len(a) else "")
            i += 0 if x[k + 1:] else 1
            if name == "read" and x[k] == "a":
                out.append(v)
    out += a[i + (i < len(a) and a[i] == "--"):] or ["REPLY" if name == "read" else "MAPFILE"]
    return out


_VENV_VARS = ("VIRTUAL_ENV", "VIRTUAL_ENV_PROMPT", "PATH", "PS1", "PYTHONHOME", "_OLD_VIRTUAL_PATH",
              "_OLD_VIRTUAL_PS1", "_OLD_VIRTUAL_PYTHONHOME")   # venv activate 가 대입·해제하는 변수
_SURE_CMDS = (":", "true", "echo", "printf")   # 리다이렉트가 없으면 실패 경로가 사실상 없다(정직한 실수 모델 §1.5)
_NULL_OPS = (">", ">>", ">|", "<", "&>", "&>>", "<>")


def _harmless(r: list[Redirect]) -> bool:
    """실패할 수 없는 리다이렉트뿐인가 — `/dev/null` 로의 입출력과 표준 fd(0·1·2)로의 복제(`2>&1`·`>&2`).
    열려 있지 않은 fd 로의 복제(`>&3`)는 명령이 돌지 않고 실패한다, fd 닫기(`>&-`)·다른 파일도 실패할 수 있다(NB7·재검토 3 NB3)."""
    return all(x.target is not None and ((x.op in _NULL_OPS and x.target.literal() == "/dev/null")
                                         or (x.op in (">&", "<&") and x.target.literal() in ("0", "1", "2"))) for x in r)


def _sure_assign(w: list[Word], env: Mapping[str, str | None]) -> bool:
    """대입 단위가 실패할 수 없는가 — 치환이 모두 mktemp 이고(대입의 종료 상태는 마지막 치환의 상태), 그 mktemp 가
    성공으로 모델링됐다(값 확정). 없는 `-p` 폴더·바뀐 TMPDIR 로 실패하는 mktemp 는 `&&` 우변을 돌리지 않는다(NB4)."""
    for x in w:
        subs = _word_subs(x)
        if any(b.split()[:1] != ["mktemp"] for b in subs):
            return False
        if subs and (a := _assign_of(x, env)) is not None and a[1] is None:
            return False
    return True


def _mktemp_dir(w: Word) -> bool:
    return any((a := b.split())[:1] == ["mktemp"] and any(
        y == "--directory" or ((m := _MKTEMP_OPT.fullmatch(y)) is not None and "d" in m.group(1)) for y in a[1:])
        for b in _word_subs(w))


# env 안의 '이 해석에서 정의한 함수' 표시(OS2·5-6). 값 = 본문 소스 — 호출 지점에서 호출 시점 상태·인자로 다시 해석한다.
# None = 모델링 불가(재정의·중첩 정의·unset -f·source·eval·갈래마다 다른 정의) — 호출하면 해석 실패(fail-closed). 갈래 합류를 따른다
_FN = "\x00fn:"
_INFN = "\x00infn"   # 인라인 해석 중(local·return 이 함수 범위를 갖는다)
_DEAD = "\x00dead"   # 인라인 해석이 보고하는 도달 불가(exit)
_PARAMS = ("1", "2", "3", "4", "5", "6", "7", "8", "9", "#", "@", "*")
_FN_DEPTH = 4   # 함수 호출 깊이 상한
_EXP = "\x00exp:"   # export 된 셸 변수 표시 — 새 셸 프로세스(sh -c 등)는 이것과 접두 할당만 받는다
_MADE = "\x00made:"   # env 안의 '이 해석에서 mkdir·mktemp -d 가 만든 폴더' 표시 — 갈래 합류(_merge)를 함께 따른다


def _made(p: str, env: Mapping[str, str | None]) -> bool:
    """같은 해석에서 앞서 (모든 경로가) 만든 폴더 — `mkdir -p` 가 만든 중간 폴더도 기록되어 있다(env 전체 순회는 변수 수에 비례)."""
    return bool(env.get(_MADE + p))


def _mkdir_sure(w: list[Word], cwd: str | None, env: Mapping[str, str | None]) -> tuple[list[str], bool] | None:
    """`mkdir` 이 실패할 수 없는 모양이면 (만드는 경로들, 들어갈 수 있는가), 아니면 None(대상 미확정·이미 있음·상위가 폴더가 아님).
    `-m`/`--mode` 의 모드에 소유자 실행 비트가 없거나 모드를 읽을 수 없으면 뒤의 cd 는 실패한다(NB5)."""
    parents, out, i, ops, mode = False, [], 1, False, None
    while i < len(w):
        lit = w[i].literal()
        if not ops and lit == "--":
            ops = True
        elif not ops and lit.startswith("--"):
            parents |= lit == "--parents"
            if lit.startswith("--mode"):
                _, eq, val = lit.partition("=")
                mode = val if eq else (w[i + 1].literal() if i + 1 < len(w) else "")
                i += not eq
        elif not ops and lit.startswith("-") and lit != "-":
            head, m, val = lit[1:].partition("m")
            parents |= "p" in head
            if m:
                mode = val or (w[i + 1].literal() if i + 1 < len(w) else "")
                i += not val
        else:
            r = _expand(w[i], env, cwd)
            if not r or len(r) != 1:
                return None
            out.append(os.path.normpath(r[0]))
        i += 1
    made: list[str] = []
    for p in out:
        if os.path.lexists(p):
            if not (parents and os.path.isdir(p)):
                return None
            continue
        made.append(p)
        q = os.path.dirname(p)
        while parents and q != "/" and not os.path.lexists(q) and not _made(q, env):
            made.append(q)   # -p 가 만드는 중간 폴더
            q = os.path.dirname(q)
        if not (_made(q, env) or (os.path.isdir(q) and os.access(q, os.W_OK | os.X_OK))):   # 권한·읽기 전용 FS 는 실패
            return None
    if mode is not None and not (mode and all(c in "01234567" for c in mode)):
        return None   # 비8진·기호·빈 모드 — mkdir 자체가 실패할 수 있다(재검토 3 NB8: `int(mode, 8)` 크래시)
    return (made, mode is None or bool(int(mode, 8) & 0o100)) if out else None


def _resolve_dir(w: Word, cwd: str | None, env: Mapping[str, str | None]) -> str | None:
    if w.literal() == "-":
        return None
    r = _expand(w, env, cwd)
    return os.path.normpath(r[0]) if r and len(r) == 1 else None


def _strip_wrapper(words: list[Word], run_env: dict[str, str | None], env: Mapping[str, str | None]) -> list[Word] | None:
    """맨 앞 래퍼 하나를 벗긴 단어 목록. 래퍼가 아니면 None. `env X=값` 은 env 로 확장해 run_env 에 저장."""
    name = os.path.basename(words[0].literal())
    i = 1

    def chdir(k: int, skip: int) -> None:   # env -C·sudo -D: 명령이 도는 폴더 — 바깥 셸이 확장한 단어(words[k] 의 앞 skip 글자 뒤)
        run_env[_CHDIR] = _text(_drop(words[k], skip).parts, env) if k < len(words) else None

    if name == "env":
        while i < len(words):
            lit = words[i].literal()
            nxt = words[i + 1].literal() if i + 1 < len(words) else ""
            if (a := _assign_of(words[i], env)) is not None:
                run_env[a[0]] = a[1]
            elif lit in ("-", "--ignore-environment"):
                _reset_env(run_env)
            elif lit.startswith("--split-string"):
                raise ModelError(f"env {lit}")   # 단어 분리를 다시 하는 env — bash 는 돌린다
            elif lit.startswith("--chdir"):
                chdir(i, 8) if "=" in lit else chdir(i + 1, 0)
                i += "=" not in lit
            elif lit.startswith("--unset"):
                run_env[lit.partition("=")[2] if "=" in lit else nxt] = None
                i += "=" not in lit
            elif lit.startswith("-") and not lit.startswith("--"):
                for n, c in enumerate(lit[1:], 2):   # 짧은 옵션 묶음(-iv·-uNAME·-u NAME)
                    if c == "i":
                        _reset_env(run_env)
                    elif c in "uCS":
                        if c == "S":
                            raise ModelError(f"env {lit}")
                        if c == "C":
                            chdir(i, n) if lit[n:] else chdir(i + 1, 0)
                        else:
                            run_env[lit[n:] or nxt] = None
                        i += not lit[n:]
                        break
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
    if name in ("su", "runuser"):
        a = words[1:]
        for n, x in enumerate(a):   # 옵션은 사용자 뒤에도 올 수 있다(getopt 순열, 실측 `su - root -c …`)
            lit = x.literal()
            if lit == "--":
                break
            if lit in _CODE_OPTS and n + 1 < len(a):
                return _as_sh(a[n + 1])
            if lit.startswith(("--command=", "--session-command=")):
                return _as_sh(_drop(x, lit.index("=") + 1))
        if name == "su" or not any(x.literal() in ("-u", "--user") or x.literal().startswith("--user=") for x in a):
            return None   # 대화식 셸(su user)·runuser 의 su 호환 모양 — 실행할 명령이 없다
    if name not in _WRAPPER_VALUE_OPTS:
        return None
    reset = name in ("sudo", "doas")   # 기본 env_reset — 안쪽 명령은 바깥 변수를 물려받지 않는다(sudo -E 는 보존)
    while i < len(words) and words[i].literal().startswith("-") and words[i].literal() != "--":
        lit = words[i].literal()
        if name == "sudo":
            if lit.startswith("--chdir"):
                chdir(i, 8) if "=" in lit else chdir(i + 1, 0)
            reset &= not lit.startswith("--preserve-env")
            for n, c in enumerate(lit[1:] if not lit.startswith("--") else "", 2):
                reset &= c != "E"
                if c == "D":
                    chdir(i, n) if lit[n:] else chdir(i + 1, 0)
                if c in "ughpCDrtU":   # 값을 받는 옵션 — 뒤 글자는 값
                    break
        i += 2 if lit in _WRAPPER_VALUE_OPTS[name] else 1
    if reset:
        _reset_env(run_env)
    if i < len(words) and words[i].literal() == "--":
        i += 1
    rest = words[i + _WRAPPER_TAIL.get(name, 0):]
    if name == "flock" and rest and rest[0].literal() in ("-c", "--command"):   # `flock [opts] <file> -c <코드>`
        return _as_sh(rest[1]) if len(rest) > 1 else None
    if name == "watch" and not any(x.literal() in ("-x", "--exec") for x in words[1:i]):
        # watch 는 인자들을 공백으로 이어 `sh -c` 로 돌린다(-x 만 직접 실행) — 이은 한 단어를 코드로
        parts = tuple(p for n, w in enumerate(rest) for p in ((Part(" ", "'"),) if n else ()) + w.parts)
        return _as_sh(Word(parts)) if rest else None
    return rest


def _as_sh(code: Word) -> list[Word]:
    return [Word((Part("sh", "'"),)), Word((Part("-c", "'"),)), code]


_RESET = "\x00reset"   # 래퍼가 환경을 비웠다 — 호출자가 바깥 변수(run_env)도 미확정으로 바꾼다
_CHDIR = "\x00chdir"   # 래퍼(env -C·sudo -D)가 명령 폴더를 바꿨다 — 값 = 확장한 폴더(모르면 None)


def _chdir(cwd: str | None, run_env: dict[str, str | None]) -> str | None:
    """래퍼가 남긴 폴더로 명령 cwd 를 바꾼다(이 셸의 폴더는 그대로). 표시가 없으면 cwd 그대로."""
    if _CHDIR not in run_env:
        return cwd
    d = run_env.pop(_CHDIR)
    if d is None or (cwd is None and not d.startswith("/")):
        return None
    return os.path.normpath(os.path.join(cwd or "/", d))


def _reset_env(run_env: dict[str, str | None]) -> None:
    """env -i·sudo·doas: 앞서 모은 래퍼 할당도 지운다(미확정). 바깥 변수는 _RESET 표시를 본 호출자가 미확정으로."""
    for k in run_env:
        if not k.startswith("\x00"):
            run_env[k] = None
    run_env[_RESET] = "1"


def _strip_all(w: list[Word], run_env: dict[str, str | None], env: Mapping[str, str | None],
               names: list[str] | None = None) -> list[Word]:
    """할당과 래퍼를 반복해 벗긴다. 할당 값은 env(이 줄 단어를 확장하는 env)로 확장해 run_env(명령이 보는 env)에 저장.
    벗긴 래퍼 이름은 names 에 모은다.

    맨 앞 접두 할당(bash 가 왼쪽부터 순차 확장)은 호출자가 먼저 벗긴다 — 여기서는 모두 래퍼 뒤 단어로 본다.
    """
    while w:
        while w and (a := _assign_of(w[0], env)) is not None:
            run_env[a[0]] = a[1]
            w = w[1:]
        if not w or (rest := _strip_wrapper(w, run_env, env)) is None:
            break
        if names is not None:
            names.append(_cmd_name(w))
        w = rest
    return w


def _cmd_name(w: list[Word]) -> str:
    return os.path.basename(w[0].literal()) if w else ""


# ---- 재귀 해석 (spec §3.3-7) ----

def _heredoc_text(r: Redirect, env: Mapping[str, str | None]) -> str | None:
    """heredoc 본문. 구분자에 따옴표가 없으면 바깥 셸이 $VAR·$(…) 를 먼저 확장한다 — 확정할 수 없으면 LexError."""
    if r.body is None or r.target is None or r.target.is_quoted():
        return r.body
    if (t := _text((Part(r.body, '"'),), env)) is None:
        raise CodeUnknown("heredoc 본문을 확정할 수 없음")
    return t


def _pipe_text(prev: Segment) -> str | None:
    """파이프 앞 단위가 셸에 넘기는 리터럴 텍스트. 모르면 None(해석하지 않고 통과)."""
    if prev.name == "cat":   # 피연산자가 있으면 cat 은 stdin 이 아니라 그 파일을 읽는다
        r = _stdin_redirect(prev.redirects)
        if r is None or r.op not in _HEREDOC or any(w.literal() != "-" for w in prev.argv[1:]):
            return None
        return _heredoc_text(r, prev.env)
    if prev.name not in ("echo", "printf"):
        return None
    args = prev.argv[1:]
    if prev.name == "echo":
        while args and re.fullmatch(r"-[neE]+", args[0].literal()):
            args = args[1:]
    vals = [_text(w.parts, prev.env) for w in args]
    if None in vals:
        return None
    s = " ".join(vals)  # type: ignore[arg-type]
    return s.replace("\\n", "\n") if prev.name == "printf" else s


def _shell_code(seg: Segment, pipe_prev: Segment | None, outer: Segment | None = None) -> str | None:
    """셸이 실행할 코드 — 바깥 셸(outer, 기본 seg)이 확장한 뒤의 텍스트. 확장할 수 없으면 LexError(해석 실패).

    옵션은 bash getopt 규칙(bash 5.2·dash 0.5.12 실측, C4 R-A): `-`/`+` 묶음, 묶음 안 o/O 마다 다음 단어가 값,
    -c 는 플래그(코드 = 옵션 뒤 첫 단어), noexec(-n·-D·-o noexec)는 마지막 설정이 이긴다(+n·+o 가 해제). 모르는 옵션은 확정 불가."""
    o = outer or seg
    a = seg.argv
    i, cmd, stdin, noexec = 1, False, False, False
    while i < len(a):
        x = a[i].literal()
        if x in ("-", "--"):   # 옵션 끝 — 다음 단어가 코드·스크립트 파일, 없으면 stdin(C3 D3: `bash -- <(…)`)
            i += 1
            break
        if x.startswith("--"):
            if x in _SH_LONG_EXIT:
                return None
            if x not in _SH_LONG and x not in _SH_LONG_VALUE:
                raise CodeUnknown(f"셸 옵션 {x} 을 해석할 수 없음")
            i += 2 if x in _SH_LONG_VALUE else 1
            continue
        if len(x) < 2 or x[0] not in "-+":
            break
        on, j = x[0] == "-", i + 1
        for c in x[1:]:
            if c in "oO":
                if c == "o" and (not on or (j < len(a) and a[j].literal() == "noexec")):
                    noexec = on   # 값을 모르는 +o 도 해제로 본다(실행 쪽이 안전)
                j += 1
            elif c not in _SH_LETTERS:
                raise CodeUnknown(f"셸 옵션 {x[0]}{c} 을 해석할 수 없음")
            elif c in "nD":
                noexec = on
            elif c == "c":
                cmd = True
            elif c == "s":
                stdin = True
        i = j
    if noexec:
        return None   # 구문 검사만, 실행하지 않는다(C3 O1)
    if cmd:
        if i >= len(a):
            if seg.via_xargs:
                raise CodeUnknown("xargs 가 넣는 -c 코드를 확정할 수 없음")   # `… | xargs -0 sh -c` — 첫 입력 항목이 코드(C3 D5)
            return None
        if (code := _text(a[i].parts, o.env, split=True)) is None:
            raise CodeUnknown("셸 -c 문자열을 확정할 수 없음")
        return code
    if i < len(a) and not stdin:
        lit = a[i].literal()
        if lit.startswith("<("):
            raise CodeUnknown("프로세스 치환으로 넘긴 코드를 확정할 수 없음")   # bash <(curl …)
        if not _stdin_path(a[i], o.env, seg.cwd):
            return None  # 스크립트 파일을 실행하면 stdin 은 코드가 아니다(-s·stdin 장치 경로면 stdin 이 코드)
    return _stdin_code(seg.redirects, o.env, pipe_prev)


# stdin 장치(C4 R-C, bash 실측: //dev/stdin·/dev/./stdin·/proc/thread-self/fd/0·/proc/<pid>/fd/0 실행). /dev/fd/00 은 실측상 없는 경로지만 보수적으로 포함
_STDIN_DEV = re.compile(r"/dev/stdin|/dev/fd/0+|/proc/[^/]+(?:/task/[^/]+)?/fd/0+")


def _stdin_path(w: Word, env: Mapping[str, str | None], cwd: str | None) -> bool:
    """단어가 stdin 장치 경로인가 — 연속 /·.·.. 를 정리한 뒤 판별. 확정할 수 없는 /dev·/proc 경로는 CodeUnknown."""
    s = _text(w.parts, env)
    p = s if s is not None else w.literal()
    if not p.startswith("/") and cwd is not None:
        p = os.path.join(cwd, p)
    p = "/" + os.path.normpath(p).lstrip("/") if p.startswith("/") else p   # normpath 는 앞 '//' 를 남긴다
    if s is None:
        if p.startswith(("/dev/", "/proc/")):
            raise CodeUnknown("표준입력 장치일 수 있는 경로를 확정할 수 없음")
        return False
    return bool(_STDIN_DEV.fullmatch(p))


def _stdin_redirect(redirects: list[Redirect]) -> Redirect | None:
    """표준입력을 정하는 리다이렉트 — fd 0(또는 생략)에 대한 입력 리다이렉트 중 마지막 것(bash 실측: 같은 fd 는 마지막이 이긴다, C4 R-B)."""
    return next((r for r in reversed(redirects) if r.fd == 0 or (r.fd is None and r.op in _STDIN_OPS)), None)


def _stdin_code(redirects: list[Redirect], env: Mapping[str, str | None], pipe_prev: Segment | None) -> str | None:
    """셸이 표준입력에서 읽을 코드: heredoc·`<<<`·리터럴 파이프(echo/printf/cat heredoc)는 텍스트, 파일·명령 파이프는 알 수 없다(C2).
    입력원이 없으면 None(도구의 stdin 은 비어 있다)."""
    if (r := _stdin_redirect(redirects)) is not None:
        if r.op in _HEREDOC:
            return _heredoc_text(r, env)
        if r.op == "<<<" and r.target is not None:
            if (code := _text(r.target.parts, env)) is None:
                raise CodeUnknown("<<< 문자열을 확정할 수 없음")
            return code
        t = r.target.literal() if r.target is not None else None
        if (r.op in ("<", "<>") and t == "/dev/null") or (r.op == "<&" and t == "-"):
            return None   # 빈 코드·닫힌 stdin(C3 O2)
        raise CodeUnknown("표준입력의 코드를 확정할 수 없음")
    if pipe_prev is None:
        return None
    if (code := _pipe_text(pipe_prev)) is None:
        raise CodeUnknown("파이프로 넘긴 코드를 확정할 수 없음")
    return code


def _drop(w: Word, n: int) -> Word:
    """단어 앞 n 글자를 뺀 단어(따옴표 종류 유지)."""
    parts = []
    for p in w.parts:
        if n >= len(p.text):
            n -= len(p.text)
            continue
        parts.append(Part(p.text[n:], p.quote))
        n = 0
    return Word(tuple(parts))


def _opts(a: list[Word], i: int, table: tuple[set[str], set[str]]) -> tuple[int, list[tuple[str, Word]]]:
    """옵션을 건너뛰며 값 옵션을 (이름, 값 단어) 로 모은다. `--opt=값`·`-v값`·`-v=값`·`-it` 묶음 처리, 표에 없으면 LexError."""
    values, flags = table
    got: list[tuple[str, Word]] = []
    while i < len(a):
        x = a[i].literal()
        if x == "--":
            return i + 1, got
        if not x.startswith("-") or x == "-":
            break
        if x.startswith("--"):
            k, eq, _ = x.partition("=")
            if k in values:
                if eq:
                    got.append((k, _drop(a[i], len(k) + 1)))
                elif i + 1 < len(a):
                    got.append((k, a[i + 1]))
                    i += 1
            elif k not in flags:
                raise ModelError(f"알 수 없는 옵션 {k}")
            i += 1
            continue
        for n in range(1, len(x)):
            o = "-" + x[n]
            if o in values:
                rest = x[n + 1:]
                if rest:
                    got.append((o, _drop(a[i], n + 1 + rest.startswith("="))))
                elif i + 1 < len(a):
                    got.append((o, a[i + 1]))
                    i += 1
                break
            if o not in flags:
                raise ModelError(f"알 수 없는 옵션 {o}")
        i += 1
    return i, got


def _mounts(o: list[tuple[str, Word]], seg: Segment) -> tuple[Mount, ...] | None:
    """run 인자의 정적 마운트. 출발지를 확정할 수 없으면 None(조회 대상)."""
    out: list[Mount] = []
    for k, w in o:
        if k not in ("-v", "--volume", "--mount"):
            continue
        s = _text(w.parts, seg.env, split=True)
        if s is None:
            return None
        if k == "--mount":
            kv = dict(x.partition("=")[::2] for x in s.split(","))
            kind = kv.get("type", "volume")
            src = kv.get("source") or kv.get("src") or ""
            dst = kv.get("target") or kv.get("destination") or kv.get("dst") or ""
            if kind not in ("bind", "volume"):
                continue
        else:
            src, _, rest = s.partition(":")
            if not rest:
                src, rest = "", src  # 익명 볼륨
            dst = rest.partition(":")[0]
            kind = "bind" if src.startswith(("/", ".")) else "volume"
        if kind == "bind" and not src.startswith("/"):
            if seg.cwd is None:
                return None
            src = os.path.join(seg.cwd, src)
        out.append(Mount(src, dst, kind))
    return tuple(out)


_DAEMON_VARS = ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG")   # DOCKER_CONFIG: 다른 config 폴더의 currentContext


def _container(seg: Segment, segments: list[Segment], pipe_prev: Segment | None, run_env: Mapping[str, str | None]) -> None:
    """docker/podman [container] exec|run|create, compose exec|run 의 안쪽 명령을 container 문맥 단위로 (spec §3.6).
    `docker container --help` 실측(C3 I2-b): create 는 run 과 같은 인자로 컨테이너를 만들고 start 때 그 명령을 돌린다."""
    a = seg.argv
    compose = seg.name == "docker-compose"
    i = 1
    daemon_set = any(k in run_env or k in seg.env for k in _DAEMON_VARS)   # 접두 할당·export·unset·env -u 는 상태 env 에 키로 남는다
    if not compose:
        i, gd = _opts(a, 1, _DOCKER_GLOBAL)
        daemon_set |= any(k in ("-H", "--host", "-c", "--context", "--config") for k, _ in gd)
        if i < len(a) and a[i].literal() == "compose":
            compose, i = True, i + 1
        elif i < len(a) and a[i].literal() == "container":   # 관리 명령 형태
            i += 1
    g: list[tuple[str, Word]] = []
    if compose:
        i, g = _opts(a, i, _COMPOSE_GLOBAL)
    sub = a[i].literal() if i < len(a) else ""
    if sub not in ("exec", "run") and not (sub == "create" and not compose):
        return
    if sub == "create":
        sub = "run"
    table = (_COMPOSE_RUN if sub == "run" else _COMPOSE_EXEC) if compose else (_RUN if sub == "run" else _EXEC)
    i, o = _opts(a, i + 1, table)
    if i >= len(a):
        return
    proj = [w.literal() for k, w in g if k in ("-p", "--project-name")]
    pdir = [w for k, w in g if k == "--project-directory"]
    files = [w for k, w in g if k in ("-f", "--file")]
    if pdir:
        project_dir = _resolve_dir(pdir[-1], seg.cwd, seg.env)
    elif files:  # compose 는 첫 -f 파일의 폴더를 프로젝트 폴더로 쓴다
        r = _expand(files[0], seg.env, seg.cwd)
        project_dir = os.path.dirname(os.path.normpath(r[0])) if r and len(r) == 1 else None
    else:
        project_dir = seg.cwd
    ctx = Context(   # 컨테이너 이름은 호스트 셸이 확장한 값 — 미확정(None)이면 조회할 수 없다(최종 리뷰 I2)
        "container", _text(a[i].parts, seg.env), ("compose-" if compose else "") + sub,
        _mounts(o, seg) if sub == "run" else None,
        project_dir if compose else None,
        proj[-1] if proj else None,
        seg.name,
        daemon_set,
    )
    wd = [w for k, w in o if k in ("-w", "--workdir")]
    r = _expand(wd[-1], seg.env, None) if wd else None  # 컨테이너 경로라 호스트 cwd 로 잇지 않는다
    cwd = r[0] if r and len(r) == 1 else None
    # 인자는 호스트 셸이 확장한다(seg.env) — 안쪽 단위의 cwd(-w)는 상대경로 기준으로만 쓰인다.
    # 컨테이너 안에서 실행되는 코드의 env 는 호스트 것을 물려받지 않는다(-w 만 셸 작업 폴더로 안다).
    cenv: dict[str, str | None] = {SHELL_CWD: cwd} if cwd else {}
    w = _strip_all(a[i + 1:], cenv, seg.env)
    cenv.pop(_RESET, None)
    if (new := _chdir(cwd, cenv)) != cwd:
        cwd = new
        cenv.pop(SHELL_CWD, None)
        if cwd:
            cenv[SHELL_CWD] = cwd
    if not w:
        return
    stdin = [r] if (r := _stdin_redirect(seg.redirects)) is not None else []  # exec -i 로 넘어가는 표준입력(파일이면 확정 불가)
    inner = Segment(_cmd_name(w), w, stdin, cwd, dict(seg.env), ctx, seg.depth + 1, seg.via_xargs)
    code = _shell_code(inner, pipe_prev, seg) if inner.name in SHELLS else None  # -c·<<< 는 호스트 셸이 먼저 확장
    if code is not None:
        _parse(code, cwd, cenv, ctx, inner.depth, segments, seg.via_xargs)
    else:
        segments.append(inner)
        _descend(inner, segments, pipe_prev, cenv)


def _child_env(seg: Segment, run_env: Mapping[str, str | None]) -> dict[str, str | None]:
    """새 셸 프로세스의 env: export 안 된 셸 변수는 없고(값 미확정 — fail-closed), PWD 는 작업 폴더로 다시 잡힌다(bash·dash 실측)."""
    env = dict(run_env)
    for k, v in run_env.items():
        # 접두 할당(`X=1 sh -c`·env X=1)은 그 명령에 내보내진다 — 실행 env 값이 단어 확장 env 와 다르다
        if not k.startswith("\x00") and not run_env.get(_EXP + k) and (k in seg.env and v == seg.env[k]):
            env[k] = None
    for k in ("PWD", SHELL_CWD):   # 새 셸의 작업 폴더 = 명령 cwd(env -C 등으로 바뀌었을 수 있다)
        if seg.cwd is None:
            env.pop(k, None)
        else:
            env[k] = seg.cwd
    return env


def _descend(seg: Segment, segments: list[Segment], pipe_prev: Segment | None,
             run_env: dict[str, str | None]) -> tuple[str | None, dict[str, str | None]] | None:
    """seg 가 실행하는 안쪽 명령을 seg 바로 뒤에 depth+1 로 넣는다. eval 이면 그 뒤 상태(현재 셸에서 돌므로).

    seg.env 는 seg 단어를 확장한 env, run_env 는 seg 가 실행될 때의 env(접두 할당 포함·컨테이너면 컨테이너 쪽).
    """
    d = seg.depth + 1
    if pipe_prev is not None and seg.argv and _text(seg.argv[0].parts, seg.env) is None:
        raise CodeUnknown("파이프 대상 명령을 확정할 수 없음")   # `… | $SHELL`·`| $(which sh)` — 셸이면 코드를 돌린다(C3 D4)
    if seg.name in SHELLS:
        if (code := _shell_code(seg, pipe_prev)) is not None:
            _parse(code, seg.cwd, _child_env(seg, run_env), seg.context, d, segments, seg.via_xargs)
    elif seg.name == "eval":
        vals = [_text(w.parts, seg.env) for w in seg.argv[1:]]
        if None in vals:
            raise CodeUnknown("eval 인자를 확정할 수 없음")
        return _parse(" ".join(vals), seg.cwd, dict(run_env), seg.context, d, segments, seg.via_xargs)  # type: ignore[arg-type]
    elif seg.name == "trap":
        # `trap [-lp] [--] <코드> <시그널>…` — 코드는 bash 가 나중에 현재 셸에서 돌린다(실측 I4). 인자 하나(`trap EXIT`)·'-'·'' 은 재설정
        a = [w for w in seg.argv[1:]]
        while a and a[0].literal().startswith("-") and a[0].literal() != "-":
            if a[0].literal() == "--":
                a = a[1:]
                break
            if "l" in a[0].literal() or "p" in a[0].literal():
                return None   # 조회
            a = a[1:]
        if len(a) >= 2 and a[0].literal() not in ("-", ""):
            code = _text(a[0].parts, seg.env)
            if code is None:
                raise CodeUnknown("trap 코드를 확정할 수 없음")
            _parse(code, seg.cwd, dict(run_env), seg.context, d, segments, seg.via_xargs)
    elif seg.name == "xargs":
        a, i, repl = seg.argv, 1, None
        while i < len(a) and a[i].literal().startswith("-"):
            x = a[i].literal()
            if x == "--":
                i += 1
                break
            if x in ("-I", "-J") and i + 1 < len(a):
                repl = a[i + 1].literal()
            elif x.startswith(("-I", "-J", "-i")) and len(x) > 2:
                repl = x[2:]
            elif x in ("-i", "--replace"):
                repl = "{}"
            elif x.startswith("--replace="):
                repl = x[len("--replace="):]
            i += 2 if x in _XARGS_VALUE else 1
        cmd = a[i:]
        if repl:  # 치환 문자열 자리는 입력에서 오므로 표시로 바꿔 둔다(-c 문자열 안까지, 명령 이름은 GNU xargs 처럼 제외)
            cmd = cmd[:1] + [Word(tuple(Part(p.text.replace(repl, _XARGS_MARK), p.quote) for p in w.parts)) for w in cmd[1:]]
        env = dict(run_env)  # xargs 가 실행하는 명령의 env — 단어는 이미 seg.env 로 확장됐다
        w = _strip_all(cmd, env, seg.env)
        env.pop(_RESET, None)   # 이 env 는 바깥 변수까지 담아 _reset_env 가 이미 비웠다
        if w:
            inner = Segment(_cmd_name(w), w, [], _chdir(seg.cwd, env), dict(seg.env), seg.context, d, via_xargs=True)
            segments.append(inner)
            _descend(inner, segments, None, env)
    elif seg.name in _CONTAINER_CLIS:
        _container(seg, segments, pipe_prev, run_env)
    return None


def parse(command: str, cwd: str | None, env: Mapping[str, str], context: Context = HOST,
          deadline: float | None = None) -> ParseResult:
    state_env: dict[str, str | None] = {k: env[k] for k in ("HOME", "TMPDIR", "USER") if k in env}
    state_env[_TMPDIR0] = env.get("TMPDIR")
    state_env.update({_EXP + k: "1" for k in ("HOME", "TMPDIR", "USER", "PWD") if k in env or k == "PWD"})   # 환경에서 받은 변수는 export 됨
    if cwd is not None:
        state_env["PWD"] = state_env[SHELL_CWD] = cwd
    segments: list[Segment] = []
    _for_runs[:] = [0, 0]
    fn_stack.clear()
    fn_locals.clear()
    fn_args.clear()
    fn_called.clear()
    fn_def_segs.clear()
    _deadline[0] = deadline
    try:
        _parse(command, cwd, state_env, context, 0, segments)
    except CodeUnknown as e:
        return ParseResult([], str(e), unmodeled=True, dynamic=True)
    except ModelError as e:
        return ParseResult([], str(e), unmodeled=True)
    except LexError as e:
        return ParseResult([], str(e))
    drop = {i for name, a, b in fn_def_segs if name in fn_called for i in range(a, b)}
    return ParseResult([x for i, x in enumerate(segments) if i not in drop], log_len=_last_log[0])


_POS = "\x00pos"   # 스냅샷이 찍힌 쓰기 로그 위치 — 그 뒤에 쓰인 키만 지금 상태와 다를 수 있다(NB9)


class _Env(dict):
    """쓰기 로그를 남기는 env. 불변식: 스냅샷 S(위치 p)와 지금 상태의 차이는 log[p:] 안에 있다 — 합류가 전체 키 대신
    그 조각만 비교한다(변수 수에 대해 이차였던 합류 비용의 근본 원인, 재검토 NB9)."""
    __slots__ = ("_snap", "log")

    def __init__(self, src: Mapping[str, str | None]) -> None:
        super().__init__(src)
        super().pop(_POS, None)   # 다른 해석의 로그 위치
        self.log: list[str] = []
        self._snap: dict[str, str | None] | None = None   # 마지막 스냅샷 — 그 뒤 쓰기가 없으면 복사 없이 다시 쓴다(스냅샷은 불변)

    def __setitem__(self, k: str, v: str | None) -> None:
        self.log.append(k)
        super().__setitem__(k, v)

    def pop(self, k: str, *default):   # type: ignore[override]
        self.log.append(k)
        return super().pop(k, *default)

    def update(self, m: Mapping[str, str | None]) -> None:   # type: ignore[override]
        self.log.extend(m)
        super().update(m)

    def snapshot(self) -> dict[str, str | None]:
        if self._snap is None or self._snap[_POS] != len(self.log):
            super().__setitem__(_POS, len(self.log))
            self._snap = dict(self)
        return self._snap

    def replace(self, e: Mapping[str, str | None]) -> None:
        """상태를 e 로 바꾼다. 다시 적는 키 = e 가 이 로그의 스냅샷이면 그 뒤에 쓰인 키 중 **지금 값과 정말 다른 것**만
        (같은 키를 매번 다시 적으면 case 분기마다 로그가 두 배로 자란다 — 재검토 3 NB1). 스냅샷이 아니면 둘의 모든 키."""
        pos = e.get(_POS)
        if pos is None:   # 다른 해석(for 본문·eval·인라인)의 상태 — 실제로 다른 키만
            changed = [k for k in {*self, *e} if (k in self) != (k in e) or (k in e and self[k] != e[k])]
        else:
            changed = [k for k in dict.fromkeys(self.log[pos:]) if (k in self) != (k in e) or (k in e and self[k] != e[k])]
        super().clear()
        super().update(e)
        self.log.extend(changed)


def _merge(states: list[tuple[str | None, dict[str, str | None]]],
           log: list[str] | None = None) -> tuple[str | None, dict[str, str | None]]:
    """여러 갈래 끝 상태의 합: 모두 같은 값만 남기고 다르면 None(확정 불가). log 가 있고 모두 그 로그의 스냅샷이면
    가장 이른 스냅샷 뒤에 쓰인 키만 비교한다(결과의 위치 = 가장 이른 위치)."""
    cwd = states[0][0] if all(c == states[0][0] for c, _ in states) else None
    pos = [e.get(_POS) for _, e in states]
    if log is None or None in pos:
        keys = {k for _, e in states for k in e} - {_POS}
        return cwd, {k: (vals.pop() if len(vals := {e.get(k) for _, e in states}) == 1 else None) for k in keys}
    envs = sorted((e for _, e in states), key=lambda e: e[_POS])
    if envs[0][_POS] == envs[-1][_POS]:
        return cwd, envs[0]   # 사이에 쓰기가 없었다 — env 가 모두 같다
    # 위치순 인접 쌍은 그 사이 로그 조각에서만 다를 수 있다 — 조각들을 다 합쳐도 로그 길이라 비용이 갈래 수에 선형
    out = dict(envs[0])
    for a, b in itertools.pairwise(envs):
        for k in set(log[a[_POS]:b[_POS]]):
            if k in a and k in b and a[k] == b[k]:
                continue
            if k in a or k in b:
                out[k] = None
            else:
                out.pop(k, None)   # 어느 갈래에도 없는 키
    out[_POS] = envs[0][_POS]
    return cwd, out


def _parse(command: str, cwd: str | None, state_env: dict[str, str | None], context: Context, depth: int,
           segments: list[Segment], via_xargs: bool = False) -> tuple[str | None, dict[str, str | None]]:
    """segments 에 단위를 덧붙이고 끝 상태(cwd, env)를 돌려준다. 오류는 LexError."""
    if depth > _MAX_DEPTH:
        raise ModelError("재귀 깊이 초과")
    _check_deadline()
    toks = lex(command)
    state_env = _Env(state_env)   # 쓰기 로그(합류 비용) — 호출자의 dict 는 그대로 둔다
    st: dict = {"cwd": cwd, "dead": False, "fn": False, "start": True}   # start = 지금 단어들이 모두 예약어(명령 자리)   # fn = 함수 머리 뒤 — 다음 복합 명령이 본문이라 격리한다   # dead = 지금 자리는 도달 불가(모든 경로가 exit·조건이 늘 참/거짓) — 단위는 판정하되 끝 상태를 남기지 않는다
    stack: list[tuple] = []   # (kind, cwd, env, in_pipe, andor, dead, list_snap) — 열 때의 바깥 상태
    words: list[Word] = []
    redirects: list[Redirect] = []
    pipe_prev: Segment | None = None
    # 진행 중인 요소 — n: 단위 수(복합·파이프는 2 이상), sure: 실패 경로 없음, pre: 실패 끝(cd 는 cd 전 상태), exit: 경로 끝.
    # 요소가 끝나면 outcome() 이 (성공 끝들, 실패 끝들)로 바꾸고, 모든 구문이 그 집합을 collect/join 으로 합류한다
    elem: dict = {"n": 0, "sure": False, "pre": None, "exit": False, "neg": False}

    def reset_elem() -> None:
        elem.update(n=0, sure=False, pre=None, exit=False, neg=False)

    def flush() -> Segment | None:
        nonlocal words, redirects
        w, r, words, redirects = words, redirects, [], []
        st["start"] = True
        # 치환은 할당 값·for 머리·리다이렉트 대상에서도 실행된다(컨트롤러 결정)
        subs = [x for wd in w + [rd.target for rd in r if rd.op not in _HEREDOC and rd.target is not None] for x in _word_subs(wd)]
        # 구분자에 따옴표가 없는 heredoc 본문의 치환도 실행된다
        subs += [x for rd in r if rd.op in _HEREDOC and rd.body and rd.target is not None and not rd.target.is_quoted()
                 for x in _subs(rd.body, False)]
        sub_cwd, sub_env = st["cwd"], (dict(state_env) if subs else None)
        seg = unit(w, r)
        for code in subs:
            _parse(code, sub_cwd, dict(sub_env), context, depth + 1, segments, via_xargs)   # type: ignore[arg-type]
        return seg

    def unit(w: list[Word], r: list[Redirect]) -> Segment | None:
        nonlocal last_list
        neg, i = False, 0
        while i < len(w) and not w[i].is_quoted() and (lit := w[i].literal()) in _RESERVED:   # 인덱스로 한 번에(슬라이스 반복은 이차)
            neg ^= lit == "!"   # `! !` 은 원래 값
            i += 2 if lit == "time" and i + 1 < len(w) and w[i + 1].literal() == "-p" else 1
            if i & 1023 == 0:
                _check_deadline()
        w = w[i:]
        if w or r:   # 요소의 단위 수와 '실패 경로 없음' 여부(outcome 이 읽는다)
            elem.update(n=elem["n"] + 1, sure=False, pre=None, exit=False, neg=neg)
            last_end[0] = last_list = None   # 상태가 바뀔 수 있다 — 앞서 만든 끝 상태를 지금 상태로 믿지 않는다
        if _NAMEREF in state_env:
            _forget(state_env)
        for m in _OP_ASSIGN.finditer(" ".join([x.literal() for x in w] + [rd.target.literal() for rd in r if rd.target]
                                              + [rd.body for rd in r if rd.body])):
            state_env[m.group(1)] = None
        if w and all(_is_assign(x) for x in w):  # 할당만 있는 단위는 이후 단위에 반영
            for x in w:
                k, v = _assign_of(x, state_env)  # type: ignore[misc]
                state_env[k] = v
                if v is not None and _mktemp_dir(x):
                    state_env[_MADE + v] = "1"
            elem["sure"] = _harmless(r) and _sure_assign(w, state_env)
            if not r:
                return None
            w = []
        # 같은 줄 단어는 할당 전 env 로 확장되고(seg.env), 접두 할당은 실행되는 안쪽 코드에만 보인다(run_env)
        unit_env = state_env.snapshot()   # Segment.env — 스냅샷처럼 바꾸지 않는다
        run_env = unit_env   # 접두 할당·래퍼 env 가 있을 때만 따로 복사한다
        while w and (a := _assign_of(w[0], run_env)) is not None:  # 맨 앞 할당끼리는 왼쪽부터 순차 확장
            if run_env is unit_env:
                run_env = dict(unit_env)
            run_env[a[0]] = a[1]
            w = w[1:]
        if w and fn_args and len(w[0].parts) == 1 and w[0].parts[0].quote != "'" and w[0].parts[0].text in ("$@", "${@}"):
            w = [*fn_args[-1], *w[1:]]   # `"$@"` 명령 자리 = 호출 인자 단어들(`run() { "$@"; }; run make -j4`)
        if w and any(p.quote != "'" and ("$" in p.text or "`" in p.text) for p in w[0].parts):
            v = _text(w[0].parts, unit_env, split=True)   # 변수로 부르는 명령 — 확정되면 그 이름, 아니면 전부 미확정(간접 호출, fail-closed)
            if v:
                w = [Word((Part(v, ""),))] + w[1:]
            else:
                st["cwd"] = None
                state_env.pop("PWD", None)
                state_env.pop(SHELL_CWD, None)
                _forget(state_env)
        if w and (fx := _FN + w[0].literal()) in state_env:   # 정의된 함수 호출 — 래퍼를 벗기기 전에 본다(래퍼 이름을 가리는 함수도 함수가 우선)
            if not _harmless(r):   # 호출 단위의 리다이렉트가 실패하면 함수가 돌지 않는다 — 호출 전 상태가 실패 끝
                elem["pre"] = now()
            inline_call(w[0].literal(), state_env[fx], w[1:], unit_env, run_env)
            return None
        wrappers: list[str] = []
        extra: dict[str, str | None] = {}
        w = _strip_all(w, extra, unit_env, wrappers)
        unit_cwd = _chdir(st["cwd"], extra)
        if extra.pop(_RESET, None):   # env -i·sudo·doas: 바깥 변수는 안쪽 명령에 없다 — 값을 모른다(fail-closed)
            run_env = {k: (v if k.startswith("\x00") else None) for k, v in run_env.items()}
        if extra:
            run_env = {**run_env, **extra}
        # 래퍼 밑의 명령은 성공 가정을 못 받는다(sudo 는 비밀번호·권한, env·nice 는 PATH 검색) — command·builtin 은 결과를 바꾸지 않는다(NB6)
        plain = _harmless(r) and all(x in ("command", "builtin") for x in wrappers)
        if w and not w[0].is_quoted() and w[0].literal() in _LOOP_HEAD:
            if len(w) > 1:   # 항목마다 묶지 못한 루프 변수는 미확정
                state_env[w[1].literal()] = None
            return None
        name = _cmd_name(w)
        # 내장(cd·true·exit…)은 맨이름으로만 불린다 — `./true`·`/bin/true` 는 외부 프로그램, 래퍼 밑(command·builtin 제외)도 외부 검색
        builtin = bool(w) and "/" not in w[0].literal() and all(x in ("command", "builtin") for x in wrappers)
        if name in ("shift", "set") and builtin and (name == "shift" or any(not x.literal().startswith("-") or x.literal() == "--" for x in w[1:])):
            for k in list(state_env):   # 위치 매개변수 재바인딩 — 전부 미확정
                if k.isdigit() or k in ("#", "@", "*"):
                    state_env[k] = None
        for k in _clobbered(name, w):
            if _NAME.fullmatch(n := k.partition("[")[0]):
                state_env[n] = None
            else:
                _forget(state_env)   # 동적 이름(`read "$v"`) — 어느 변수인지 모른다
        if name == "return" and builtin and state_env.get(_INFN):   # 함수 범위의 return — 호출 끝으로 합류
            returns.append(now())
            elem["exit"] = True
            return None
        if name == "unset" and any(x.literal().startswith("-") and "f" in x.literal() for x in w[1:]):
            for x in w[1:]:
                if not x.literal().startswith("-"):
                    state_env[_FN + x.literal()] = None
        if name in ("source", "."):
            sw = w[2:] if len(w) > 1 and w[1].literal() == "--" else w[1:]
            a = sw[0].literal() if sw else ""
            dev = bool(sw) and _stdin_path(sw[0], unit_env, unit_cwd)
            if dev or a.startswith("<("):   # 읽어 들이는 코드가 stdin·프로세스 치환 — 셸 인터프리터와 같은 규칙(C2, C3 D2, C4 R-C)
                code = _stdin_code(r, unit_env, pipe_prev) if dev else None
                if code is None:
                    raise CodeUnknown("source 의 코드를 확정할 수 없음")
                _parse(code, st["cwd"], dict(state_env), context, depth + 1, segments, via_xargs)
            if "/" in a and a.rpartition("/")[2] in ("activate", "activate.sh"):   # 가상환경 activate 는 자기 변수만 바꾼다
                state_env.update(dict.fromkeys(_VENV_VARS))
            else:   # 읽어 들인 파일은 변수·함수·작업 폴더를 모두 바꿀 수 있다(재검토 3 OOS2)
                _forget(state_env)
                st["cwd"] = None
                state_env.pop("PWD", None)
                state_env.pop(SHELL_CWD, None)
            for k in list(state_env):
                if k.startswith(_FN):
                    state_env[k] = None   # source 가 함수를 다시 정의할 수 있다
        if name == "git":
            while len(w) > 2 and w[1].literal() == "-C":
                unit_cwd = _resolve_dir(w[2], unit_cwd, unit_env)
                w = [w[0]] + w[3:]
        if name in _VAR_DECL:
            flags = "".join(x.literal()[1:] for x in w[1:] if x.literal().startswith("-"))
            # export·declare -x 는 내보내고 export -n 은 해제 — local 은 가리는 변수의 export 속성을 잇는다(bash 실측)
            exported = (name == "export" and "n" not in flags) or (name != "export" and "x" in flags)
            unexported = name == "export" and "n" in flags
            for x in w[1:]:
                lit = x.literal()
                if lit.startswith("-"):
                    if name != "export" and "n" in lit[1:]:   # export -n 은 내보내기 해제
                        state_env[_NAMEREF] = "1"
                    continue
                if exported or unexported:
                    state_env[_EXP + lit.partition("=")[0]] = "1" if exported else None
                if (a := _assign_of(x, state_env)) is not None:
                    state_env[a[0]] = a[1]
                    if a[1] is not None and _mktemp_dir(x):
                        state_env[_MADE + a[1]] = "1"
                elif not _NAME.fullmatch(lit.partition("=")[0].partition("[")[0]):
                    _forget(state_env)   # 동적 이름(`declare "$v"=…`)
            if name in ("local", "declare", "typeset") and fn_locals and state_env.get(_INFN) \
                    and not any(x.literal().startswith("-") and "g" in x.literal()[1:] for x in w[1:]):   # 함수 범위(-g 는 전역) — 호출 끝에 복원
                fn_locals[-1].update(x.literal().partition("=")[0] for x in w[1:] if not x.literal().startswith("-"))
            elem["sure"] = (name not in ("typeset", "local") or bool(state_env.get(_INFN))) and plain and _sure_assign(w, state_env)   # 함수 밖 local 은 늘 실패
            if r:   # `export X=1 > f` 도 f 를 비운다 — 리다이렉트 판정용 단위
                segments.append(Segment(name, w, r, unit_cwd, unit_env, context, depth, via_xargs))
            return None
        if not (w or r):
            return None
        if not w and not _harmless(r):   # 복합 명령 뒤의 리다이렉트 — 실패하면 복합 명령 전체가 돌지 않는다(복합 전 상태가 실패 끝, 재검토 3 OOS6)
            elem.update(n=1, sure=False, pre=snap)
        if plain:
            if (name in _SURE_CMDS or (name == "readonly" and _sure_assign(w, state_env))) and builtin:
                elem["sure"] = True
            elif name == "exit" and builtin:   # 최상위 return 은 오류를 내고 계속 실행된다(bash -c 실측) — 경로 끝이 아니다
                elem["exit"] = True
            elif name == "mkdir" and (mk := _mkdir_sure(w, unit_cwd, unit_env)) is not None:
                if mk[1]:
                    state_env.update(dict.fromkeys([_MADE + x for x in mk[0]], "1"))
                elem["sure"] = True
        if name in ("break", "continue") and builtin:   # 그 시점 상태는 대상 루프의 종료 끝, 뒤는 도달 불가(재검토 3 NB2·OOS1)
            n = w[1].literal() if len(w) > 1 else "1"
            loops = [c for c in ctl if c["loop"]]
            if not n.isdigit() or int(n) < 1 or int(n) > len(loops):
                raise ModelError(f"모델링할 수 없는 {name} {n}")
            target = loops[-int(n)]
            if any(k[0] == "(" for k in stack[target["depth"] + 1:]):
                raise ModelError(f"서브셸 안의 {name}")
            target["ends"].append(now())
            elem["exit"] = True
        seg = Segment(name, w, r, unit_cwd, unit_env, context, depth, via_xargs)
        segments.append(seg)
        if (after := _descend(seg, segments, pipe_prev, run_env)) is not None:
            st["cwd"] = after[0]
            new_fns = [k for k, v in after[1].items() if k.startswith(_FN) and v != state_env.get(k)]
            state_env.replace(after[1])
            for k in new_fns:
                state_env[k] = None   # eval 로 정의·재정의된 함수는 미확정
        if name in ("cd", "pushd", "popd") and not builtin:
            pass   # 래퍼(sudo·env·nice …) 뒤·경로로 부른 cd 는 외부 명령 검색이라 이 셸의 폴더를 바꾸지 않는다
        elif name in ("cd", "pushd"):
            elem["pre"] = now()   # 실패한 cd 는 폴더를 바꾸지 않는다 — 실패 끝은 cd 전 상태
            opts = w[1:]
            while opts and opts[0].literal().startswith("-") and opts[0].literal() not in ("-", "--"):
                opts = opts[1:]
            args = opts[1:] if opts and opts[0].literal() == "--" else opts   # `--` 뒤는 폴더 이름(재검토 3 OOS8)
            st["cwd"] = _resolve_dir(args[0], st["cwd"], unit_env) if args else (
                state_env.get("HOME") if name == "cd" else None)
            if st["cwd"] is not None:
                state_env["PWD"] = state_env[SHELL_CWD] = st["cwd"]
                # 있는 폴더·앞서 만든 폴더로의 cd 만 실패 경로가 없다 — 없는 폴더(`cd build && …`)는 실패 끝을 유지
                elem["sure"] = plain and (_made(st["cwd"], state_env) or (
                    os.path.isdir(st["cwd"]) and os.access(st["cwd"], os.X_OK)))
            else:
                state_env.pop("PWD", None)
                state_env.pop(SHELL_CWD, None)
        elif name == "popd":
            st["cwd"] = None
            state_env.pop("PWD", None)
            state_env.pop(SHELL_CWD, None)
        return seg

    snap = (st["cwd"], state_env.snapshot())   # 파이프라인 시작 상태 — 구성원은 서브셸이라 끝나면 여기로 돌아온다
    list_snap = snap   # 목록 시작 상태 — `A && cd X &` 는 목록 전체가 배경 서브셸이라 끝나면 여기로 돌아온다(OS3)
    in_pipe = False
    # 진행 중인 `&&`·`||` 목록: (성공 끝 상태들, 실패 끝 상태들, 직전 연산자, 지금 요소가 시작부터 도달 불가)
    andor: tuple[list, list, str, bool] | None = None
    last_end: list = [None]   # outcome 이 마지막으로 만든 끝 상태 — 같은 객체 하나로 합류하면 상태를 다시 놓지 않는다
    last_list: tuple[list, list] | None = None   # 방금 `;`·줄바꿈으로 닫은 목록의 (성공 끝들, 실패 끝들) — 조건 자리가 읽는다

    def now() -> tuple[str | None, dict[str, str | None]]:
        return st["cwd"], state_env.snapshot()

    def set_state(s: tuple[str | None, dict[str, str | None]]) -> None:
        st["cwd"], st["dead"], last_end[0] = s[0], False, None
        state_env.replace(s[1])

    def restore() -> None:
        set_state(snap)

    # ---- 경로 집합: 모든 구문(단순 명령·`&&`/`||`·`;`·조건 자리·그룹·갈래)이 같은 세 함수로 끝 상태를 모으고 합친다 ----

    def outcome() -> tuple[list, list]:
        """방금 끝난 요소의 (성공 끝들, 실패 끝들). 도달 불가 자리에서 끝났으면 둘 다 빈 목록.
        단순 명령 하나: 실패 경로 없음(sure)이면 실패 끝 없음, cd 는 실패 끝이 cd 전 상태, exit 은 둘 다 없음, `!` 는 둘을 뒤바꿈.
        복합·파이프는 둘 다 끝 상태."""
        if st["dead"]:
            last_end[0] = None
            return [], []
        e = last_end[0] = now()
        if elem["n"] != 1:
            return [e], [e]
        if elem["exit"]:
            return [], []
        ok, fail = [e], ([] if elem["sure"] else [elem["pre"] or e])
        return (fail, ok) if elem["neg"] else (ok, fail)   # `!` 는 성공·실패 끝을 뒤바꾼다

    def collect() -> tuple[list, list]:
        """진행 중인 목록을 닫고 (성공 끝들, 실패 끝들). 시작부터 도달 불가였던 요소는 목록에 기여하지 않는다."""
        nonlocal andor
        ok, fail = outcome()
        reset_elem()
        if andor is not None:
            pok, pfail, last, dead0 = andor
            if dead0:
                ok, fail = pok, pfail
            elif last == "&&":
                fail = pfail + fail
            else:
                ok = pok + ok
            andor = None
        return ok, fail

    def join(states: list) -> None:
        """끝 상태들의 합을 지금 상태로. 비면 도달 불가. 방금 만든 끝 하나면 그대로 둔다. 마감이 지났으면 해석 실패."""
        _check_deadline()
        if not states:
            st["dead"] = True
        elif not all(s is last_end[0] for s in states):
            set_state(_merge(states, state_env.log))

    def andor_step(op: str | None) -> None:
        # op 가 있으면 다음 요소의 시작(&& 는 성공, || 는 실패 끝들의 합), 없으면 목록 끝(모든 끝의 합)
        nonlocal andor
        ok, fail = collect()
        if op is None:
            join(ok + fail)
        else:
            s = ok if op == "&&" else fail
            andor = (ok, fail, op, not s)
            join(s)

    def end_list() -> None:
        # `;`·줄바꿈·그룹 끝: 목록의 모든 끝을 합친다(`cd missing; …` 도 cd 전·뒤 두 경로). 조건 자리(then·do)가 읽도록 남긴다
        nonlocal last_list
        last_list = collect()
        join(last_list[0] + last_list[1])

    def open_group(kind: str) -> None:
        # 파이프 구성원 판정은 같은 그룹 깊이에서만 하므로 안쪽은 in_pipe·`&&` 목록을 새로 시작한다
        nonlocal snap, list_snap, in_pipe, andor
        if st["fn"]:   # 함수 본문 — 닫을 때 서브셸처럼 되돌리고 본문 소스를 남긴다
            isolated.add(len(stack))
            fn_cur[-1]["depth"] = len(stack)
            st["fn"] = False
        e = now()
        stack.append((kind, *e, in_pipe, andor, st["dead"], list_snap))
        in_pipe, andor = False, None
        snap = list_snap = e

    def close_compound(kind: str, ends: list | None) -> None:
        """복합 명령(그룹·서브셸·if·루프·case)을 닫는다. ends = 갈래 끝들(None 이면 지금 상태 그대로).
        서브셸·파이프 구성원은 안쪽 변화가 밖으로 안 나간다."""
        nonlocal snap, list_snap, in_pipe, andor
        _, cwd0, env0, outer_pipe, andor, dead0, list_snap = stack.pop()
        summary = None
        if fn_cur and fn_cur[-1].get("depth") == len(stack):   # 함수 본문 끝 — 본문 소스(여는 토큰부터 닫는 토큰까지)
            f = fn_cur.pop()
            if not f["unknown"]:   # 모델링 불가(재정의 등) 정의의 본문 판정은 호출돼도 남긴다(trap 으로만 불릴 수 있다)
                fn_def_segs.append((f["name"], f["seg0"], len(segments)))
                t_end = toks[st["idx"]]
                summary = (f["name"], command[toks[f["start"]].pos : t_end.pos + len(t_end.word.literal() if t_end.kind == "word" else t_end.op)])
        if kind == "(" or outer_pipe or len(stack) in isolated:
            isolated.discard(len(stack))
            set_state((cwd0, env0))
            st["dead"] = dead0
        elif ends is not None:
            join(ends)
        if summary is not None and state_env.get(_FN + summary[0], "") is None:
            state_env[_FN + summary[0]] = summary[1]   # 자리표시자(None)였을 때만 — 재정의·갈래 차이는 None 유지
        in_pipe = outer_pipe
        elem.update(n=2, sure=False, pre=None, exit=False, neg=False)   # 복합 명령은 실패 경로를 따로 모델링하지 않는다
        snap = (cwd0, env0)  # 그룹 뒤 `|` 가 오면 그룹 전체를 되돌리는 기준

    def close_group(kind: str) -> None:
        flush()
        if in_pipe:  # 그룹 안 마지막 파이프 구성원
            restore()
        end_list()
        if not stack or stack[-1][0] != kind:
            raise LexError(f"짝 없는 {'}' if kind == '{' else ')'!r}")
        close_compound(kind, None)

    # 열린 case 문(spec 밖 구문 — 재생 군집 P1): mode head(머리)·pat(패턴)·body(분기 본문), pat = 0 단어 기대 /
    # 1 `|`·`)` 기대 / 2 `|` 뒤 단어 기대, ends = 분기 끝 상태들. stack 의 "case" 항목과 짝을 이룬다
    cases: list[dict] = []
    isolated: set[int] = set()   # 함수 본문인 stack 항목의 깊이
    fn_cur: list[dict] = []   # 해석 중인 함수 본문(이름·본문 시작 토큰·미확정 여부)
    returns: list = []   # 인라인 해석 중 만난 return 시점 상태들 — 끝에서 합류

    def define_fn(name: str | None, start: int) -> None:
        if name is None or not _NAME.fullmatch(name):
            raise LexError("함수 이름을 해석할 수 없음")
        unknown = (_FN + name) in state_env or bool(fn_cur)   # 재정의·함수 안 함수는 모델링 불가
        for f in fn_cur:
            f["unknown"] = True
        state_env[_FN + name] = None   # 본문 안 재귀 호출은 자리표시자(None)를 본다
        fn_cur.append({"name": name, "start": start, "unknown": unknown, "seg0": len(segments)})
        st["fn"] = True

    def inline_call(fname: str, body: str | None, args: list[Word], env: Mapping[str, str | None], run_env: Mapping[str, str | None]) -> None:
        """정의된 함수 호출 — 본문을 호출 시점 상태에서 다시 해석한다. 위치 매개변수는 인자 단어(확정이면 값), local·위치
        매개변수는 호출 끝에 복원, return 은 호출 끝으로 합류, exit 은 밖까지 도달 불가. 모델링 불가(None)·재귀·깊이·총량 초과는 해석 실패."""
        if body is None or fname in fn_stack or len(fn_stack) >= _FN_DEPTH:
            raise ModelError(f"모델링할 수 없는 함수 호출 {fname}")
        if _for_runs[1] + len(body) > _FOR_CHARS:
            raise ModelError("함수 인라인 총량 초과")
        _for_runs[1] += len(body)
        vals = [_text(x.parts, env, split=True) for x in args]
        inner: dict[str, str | None] = {k: v for k, v in state_env.items() if not (k.isdigit() or k in ("#", "@", "*"))}
        prefix = {k: v for k, v in run_env.items() if k not in env or env[k] != v}   # 접두 할당(`d=X f`)은 본문에 보이고 호출 뒤 사라진다
        inner.update(prefix)
        inner.update({str(i): v for i, v in enumerate(vals, 1)})
        inner["#"] = str(len(vals))
        inner["@"] = inner["*"] = vals[0] if len(vals) == 1 else None   # 여러 인자는 단어 여럿이라 한 값으로 못 둔다
        inner[_INFN] = "1"
        fn_stack.append(fname)
        fn_locals.append(set())
        fn_args.append(list(args))
        fn_called.add(fname)
        try:
            after_cwd, after_env = _parse(body, st["cwd"], inner, context, depth + 1, segments, via_xargs)
        except LexError as e:   # 정의 시점엔 읽혔는데 본문만 다시 읽으면 깨지는 모양(heredoc 이 `}` 뒤 등) — 모델링 불가
            raise ModelError(f"함수 본문 재해석 실패 {fname}: {e}") from e
        finally:
            fn_stack.pop()
            fn_args.pop()
            locals_ = fn_locals.pop()
        dead = after_env.pop(_DEAD, None) is not None
        for k in {*locals_, *prefix, *(k for k in [*state_env, *after_env] if k.isdigit() or k in ("#", "@", "*"))}:
            if k in state_env:
                after_env[k] = state_env[k]
            else:
                after_env.pop(k, None)
        after_env.pop(_INFN, None)
        st["cwd"] = after_cwd
        state_env.replace(after_env)
        if dead:
            elem["exit"] = True

    def at_start() -> bool:
        return st["start"]

    def add_word(w: Word) -> None:   # words 에 넣으며 명령 자리 플래그를 O(1) 로 유지(예약어 체인이 O(n²) 이었다)
        lit = None if w.is_quoted() else w.literal()
        st["start"] = st["start"] and (lit in _RESERVED or (lit == "-p" and bool(words) and words[-1].literal() == "time"))
        words.append(w)

    def close_case() -> None:
        # 어느 분기가 돌았는지(또는 아무것도 안 돌았는지) 모르므로 상태는 시작과 모든 분기 끝이 같을 때만 유지
        c = cases.pop()
        end_list()
        if c["mode"] == "body" and not st["dead"]:
            c["ends"].append(now())
        close_compound("case", [stack[-1][1:3], *c["ends"]])

    # 열린 if·루프(while/until/for/select): mode cond(조건)·body(본문)·else·done(목록 확정 for — for_loop 가 이미 합쳤다),
    # cond = 조건이 거짓(until 은 참)인 끝 상태들, ends = 갈래 끝 상태들. stack 의 "if"·"loop" 항목과 짝을 이룬다
    ctl: list[dict] = []

    def control(word: str) -> None:
        """if·while·until 을 열고 then·elif·else·fi·do·done 으로 갈래를 넘긴다. 본문은 조건의 성공 끝에서 시작하고,
        거짓 갈래·else 없는 경로·루프 종료는 조건의 실패 끝(cd 실패 = 조건 전 상태)에서 시작·합류한다."""
        nonlocal snap, list_snap
        flush()
        if word in _CTL_OPEN or word in _LOOP_HEAD:   # 앞 `&&` 목록은 그룹처럼 stack 에 맡긴다(복합 명령이 그 요소)
            open_group("if" if word == "if" else "loop")
            ctl.append({"mode": "cond", "ends": [], "until": word == "until", "loop": word != "if", "depth": len(stack) - 1})
            return
        kind, modes = _CTL[word]
        c = ctl[-1] if stack and stack[-1][0] == kind else None
        if c is None or c["mode"] not in modes:
            raise LexError(f"짝 없는 {word}")
        if word in ("then", "do"):
            ok, fail = last_list or collect()
            if c["until"]:
                ok, fail = fail, ok
            c.update(mode="body", cond=fail)
            join(ok)
        else:
            end_list()
            if not st["dead"]:
                c["ends"].append(now())
            if word in ("fi", "done"):
                ctl.pop()
                close_compound(kind, None if c["mode"] == "done" else c["ends"] + ([] if c["mode"] == "else" else c["cond"]))
                return
            join(c["cond"])   # elif·else — 다음 조건·else 본문은 앞 조건이 거짓인 상태에서
            c["mode"] = "cond" if word == "elif" else "else"
        snap = list_snap = last_end[0] or now()   # 상태가 그대로면 방금 만든 끝을 다시 쓴다

    def bare(i: int) -> str | None:
        t = toks[i] if i < len(toks) else None
        return t.word.literal() if t is not None and t.kind == "word" and not t.word.is_quoted() else None

    def for_loop(k: int) -> int | None:
        """toks[k] = for. `for N in 목록; do …; done` 이고 목록이 확정되면 본문을 항목마다 해석하고 done 의 인덱스.
        그 밖(목록 미확정·0개·상한 초과·중첩 루프·in 없음)은 None — 일반 처리(루프 변수 미확정, 본문 한 번)."""
        name = bare(k + 1)
        if name is None or not _NAME.fullmatch(name) or bare(k + 2) != "in":
            return None
        i = k + 3
        while i < len(toks) and toks[i].kind == "word":
            i += 1
        items = [t.word for t in toks[k + 3:i] if t.word is not None]
        if i >= len(toks) or toks[i].op not in (";", "\n"):
            return None
        i += 1
        while i < len(toks) and toks[i].op == "\n":
            i += 1
        if bare(i) != "do":
            return None
        do, j, start, open_loops, nested = i, i + 1, True, 0, False
        while True:   # 명령 자리의 done 이 짝. 명령 자리 = 연산자 뒤·예약어 뒤
            if j >= len(toks):
                raise LexError("짝 없는 do")
            t, lit = toks[j], bare(j)
            if t.kind == "op":
                start = True
            elif t.kind == "word":
                if start and lit in _LOOPS:
                    open_loops, nested = open_loops + 1, True
                elif start and lit in ("break", "continue", "return"):
                    nested = True   # 본문을 항목마다 따로 해석하면 루프 문맥이 없다 — 일반 처리
                elif start and lit == "done":
                    if not open_loops:
                        break
                    open_loops -= 1
                start = start and lit in _RESERVED
            j += 1
        # done 줄에서 시작한 heredoc 은 본문이 done 뒤에 있어 본문 원문만 잘라서는 해석할 수 없다 — 일반 처리
        if nested or any(t.kind == "redir" and t.op in _HEREDOC and not any(x.op == "\n" for x in toks[h + 1 : j])
                         for h, t in enumerate(toks[do + 1 : j], do + 1)):
            return None
        vals: list[str] = []
        for wd in items:
            if (v := _values(wd, state_env, st["cwd"])) is None:
                return None
            vals += v
        body = command[toks[do].pos + 2 : toks[j].pos]
        # 0개 '확정'은 모델링 못 한 변수 변화일 수 있다 — 본문을 버리지 않고 일반 처리(루프 변수 미확정)로 한 번 본다
        if not vals or len(vals) > _FOR_CAP or _for_runs[0] + len(vals) > _FOR_TOTAL \
                or _for_runs[1] + len(vals) * len(body) > _FOR_CHARS or _late():
            return None
        _for_runs[0] += len(vals)
        _for_runs[1] += len(vals) * len(body)
        for wd in items:   # 머리 단어의 치환도 실행된다
            for code in _word_subs(wd):
                _parse(code, st["cwd"], dict(state_env), context, depth + 1, segments, via_xargs)
        state: tuple[str | None, dict[str, str | None]] = (st["cwd"], dict(state_env))
        ends = []
        for v in vals:   # 반복은 앞 반복의 끝 상태에서 이어진다
            state = _parse(body, state[0], {**state[1], name: v}, context, depth, segments, via_xargs)
            ends.append(state)
        set_state(_merge(ends))   # break 등으로 어느 반복에서 끝났는지 모른다
        return j

    skip = 0
    for idx, t in enumerate(toks):
        if idx < skip:
            continue
        _check_deadline()
        st["idx"] = idx
        cur = cases[-1] if stack and stack[-1][0] == "case" else None
        word = t.word.literal() if t.kind == "word" and not t.word.is_quoted() else None
        if cur is not None and cur["mode"] == "head":
            if t.kind == "op" and t.op == "\n":
                continue
            if t.kind != "word" or (cur["n"] and word != "in"):
                raise LexError("case 머리를 해석할 수 없음")
            if cur["n"] == 0:
                for code in _word_subs(t.word):
                    _parse(code, st["cwd"], dict(state_env), context, depth + 1, segments, via_xargs)
            cur["n"] += 1
            cur["mode"] = "pat" if cur["n"] == 2 else "head"
            continue
        if cur is not None and cur["mode"] == "pat":
            if word == "esac" and cur["pat"] == 0 and not cur["paren"]:
                close_case()
                add_word(t.word)   # 예약어로 벗겨지고 뒤 리다이렉트는 case 전체에 붙는다
            elif t.kind == "word" and cur["pat"] in (0, 2):
                if _word_subs(t.word):
                    raise ModelError("case 패턴 안 치환은 지원하지 않음")
                cur["pat"] = 1
            elif t.kind == "op" and t.op == "|" and cur["pat"] == 1:
                cur["pat"] = 2
            elif t.kind == "op" and t.op in ("(", "\n") and cur["pat"] == 0 and not cur["paren"]:
                cur["paren"] = t.op == "("
            elif t.kind == "op" and t.op == ")" and cur["pat"] == 1:
                cur.update(mode="body", pat=0, paren=False)
            else:
                raise LexError("case 패턴을 해석할 수 없음")
            continue
        if (word in _CTL or word in _CTL_OPEN or word in _LOOP_HEAD) and at_start():
            control(word)   # type: ignore[arg-type]
            if word == "for" and (end := for_loop(idx)) is not None:
                ctl[-1]["mode"] = "done"
                skip = end   # done 은 일반 처리 — 예약어로 벗겨지고 뒤 리다이렉트는 루프 전체에 붙는다
                continue
            if word not in ("fi", "done", "for", "select"):   # for·select 머리는 unit 이, fi·done 뒤 리다이렉트는 단위가 받는다
                continue
        if word == "function" and not words and not redirects:   # `function f [()] 본문`
            skip = idx + 2
            if skip + 1 < len(toks) and toks[skip].op == "(" and toks[skip + 1].op == ")":
                skip += 2
            define_fn(bare(idx + 1), skip)
            continue
        if t.kind == "word" and word in ("case", "esac") and at_start():
            if word == "case":
                flush()
                open_group("case")
                cases.append({"mode": "head", "n": 0, "pat": 0, "paren": False, "ends": []})
                continue
            if cur is None:
                raise LexError("짝 없는 esac")
            close_case()
        if t.kind == "op" and t.op in (";;", ";&", ";;&") and cur is not None:
            flush()
            if in_pipe:
                restore()
            end_list()
            in_pipe, pipe_prev = False, None
            ends = [] if st["dead"] else [now()]
            cur["ends"] += ends
            # ;& ·;;& 는 다음 분기 본문이 이 분기 끝 상태에서 이어질 수도 있다
            set_state(_merge([stack[-1][1:3], *([] if t.op == ";;" else ends)], state_env.log))
            snap = now()
            cur["mode"] = "pat"
            list_snap = snap
            continue
        if t.kind == "op" and t.op in (";&", ";;&"):
            raise LexError(f"case 밖의 {t.op}")
        if t.kind == "word":
            w = t.word
            if not w.is_quoted() and ((w.literal() == "{" and at_start()) or (w.literal() == "}" and not words and not redirects)):
                if w.literal() == "{":
                    flush()   # 앞의 `!`·`time` 은 빈 단위로 소비한다
                    open_group("{")
                else:
                    close_group("{")
            else:
                lit = w.literal()
                if at_start() and len(w.parts) == 1 and w.parts[0].quote == "" and lit.startswith("!(") and lit.endswith(")") \
                        and _skip_to(lit, 2, ")") == len(lit):   # extglob 꺼진 bash: `!(cmd)` = `! ( cmd )` — 안쪽은 서브셸
                    flush()
                    _parse(lit[2:-1], st["cwd"], dict(state_env), context, depth + 1, segments, via_xargs)
                    elem.update(n=2, sure=False, pre=None, exit=False, neg=False)
                    last_end[0] = last_list = None
                    continue
                if at_start() and not _is_assign(w) and _cmd_extglob(w):
                    raise LexError(f"명령 자리의 확장 글롭 {lit[:20]!r}")
                if st["fn"]:
                    raise LexError("함수 본문은 복합 명령이어야 함")
                add_word(w)
        elif t.kind == "redir":
            redirects.append(Redirect(t.op, t.fd, t.target, t.body))
            st["start"] = False
        elif t.op in _BOUNDARY:
            seg = flush()
            if in_pipe or t.op in ("|", "|&"):
                restore()   # 파이프 구성원은 서브셸
            if t.op in ("&&", "||"):
                andor_step(t.op)
            elif t.op == "&":   # 목록 전체가 배경 서브셸 — 단위는 판정했고 상태는 목록 시작으로
                andor = None
                reset_elem()
                set_state(list_snap)
            elif t.op not in ("|", "|&"):
                end_list()
            else:
                elem["n"] += 2   # 파이프라인은 단순 명령 하나가 아니다
            in_pipe = t.op in ("|", "|&")
            pipe_prev = seg if in_pipe else None
            snap = last_end[0] or now()
            if not in_pipe and t.op not in ("&&", "||"):
                list_snap = snap
        elif t.op == "(":
            if len(words) == 1 and not redirects and idx + 1 < len(toks) and toks[idx + 1].op == ")" \
                    and not _is_assign(words[0]):   # `f() 본문` — `A=()` 는 빈 배열 대입
                define_fn(None if words[0].is_quoted() else words[0].literal(), idx + 2)
                words, skip, st["start"] = [], idx + 2, True
                continue
            flush()
            open_group("(")
        elif t.op == ")":
            close_group("(")
    flush()
    end_list()
    if stack:
        raise LexError("닫히지 않은 그룹")
    if returns:   # 함수 본문의 return 들 — 끝 상태와 합류(끝이 도달 불가면 return 들만)
        set_state(_merge(returns + ([] if st["dead"] else [now()]), state_env.log))
    if st["dead"] and state_env.get(_INFN):
        state_env[_DEAD] = "1"
    if depth == 0:
        _last_log[0] = len(state_env.log)
    env = dict(state_env)
    env.pop(_POS, None)   # 다른 해석의 로그 위치는 의미가 없다
    return st["cwd"], env
