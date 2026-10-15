"""bash-guard 어휘 분석기: 셸 명령 문자열 -> 토큰 목록 (spec §3.3-1).

shlex 를 쓰지 않는 이유: 따옴표 종류·리다이렉트 위치·`2>&1` 을 잃어 단위 분해가 틀어진다.
"""
from __future__ import annotations

import glob
import itertools
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


SHELLS = {"bash", "sh", "zsh", "dash"}
_MAX_DEPTH = 8
_SHELL_C = re.compile(r"-[a-zA-Z]*c[a-zA-Z]*")
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_BRACE = re.compile(r"\{([^{}]*,[^{}]*)\}")
_HEREDOC = ("<<", "<<-")
# env 안의 셸 작업 폴더 — 변수 이름이 될 수 없는 키라 사용자 할당(PWD=…)으로 덮이지 않는다. `$(pwd)` 가 읽는다.
SHELL_CWD = "\x00cwd"
_STDIN_CODE = ("<<", "<<-", "<<<")
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


def _dollar(t: str, i: int, env: Mapping[str, str | None]) -> tuple[str | None, int]:
    """t[i] 는 `$` 또는 백틱. (확장값 | None=확정 불가, 다음 인덱스).

    `$PWD` 는 env 의 PWD 변수(사용자가 덮어쓸 수 있음), `$(pwd)` 는 셸 작업 폴더 SHELL_CWD 를 쓴다
    — 둘 다 단위 cwd 와 다를 수 있다(컨테이너 -w, git -C).
    """
    if t[i] == "`" or t.startswith("$(", i):
        j = _skip_sub(t, i)
        body = t[i + 1 : j - 1] if t[i] == "`" else t[i + 2 : j - 1]
        return (env.get(SHELL_CWD) if body.strip() == "pwd" else None), j
    if t.startswith("${", i):
        j = _skip_sub(t, i)
        m = _NAME.fullmatch(t, i + 2, j - 1)
        return (env.get(m.group()) if m else None), j
    if (m := _NAME.match(t, i + 1)):
        return env.get(m.group()), m.end()
    if t[i + 1 : i + 2] and t[i + 1] in "0123456789?#@*$!-":
        return None, i + 2
    return "$", i + 1


def _subst(parts: tuple[Part, ...], env: Mapping[str, str | None], split: bool = False) -> list[tuple[str, bool]] | None:
    """조각 -> (텍스트, 활성) 목록. 활성 = 따옴표 없는 리터럴(중괄호·와일드카드 대상). 확정 불가면 None."""
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
                if val is None:
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
        if _XARGS_MARK in lit:
            return None
        if not lit.startswith("/"):
            if cwd is None:
                return None
            lit = os.path.join(cwd, lit) if lit else cwd
        if any(a and any(x in t for x in "*?[") for t, a in ch):
            pat = "".join(t if a else glob.escape(t) for t, a in ch)
            if not pat.startswith("/"):
                pat = os.path.join(glob.escape(cwd), pat)
            if (hits := sorted(glob.glob(pat))):  # 점 파일은 패턴이 . 로 시작할 때만 — glob 기본이 bash 와 같다
                out += hits
                continue
        out.append(lit)
    return out


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


def _assign_of(w: Word, env: Mapping[str, str | None]) -> tuple[str, str | None] | None:
    """`NAME=값` 단어면 (이름, 할당 시점에 확장한 값 | None=확정 불가)."""
    if not _is_assign(w):
        return None
    head, _, rest = w.parts[0].text.partition("=")
    return head, _text(((Part(rest, ""),) if rest else ()) + w.parts[1:], env)


def _resolve_dir(w: Word, cwd: str | None, env: Mapping[str, str | None]) -> str | None:
    if w.literal() == "-":
        return None
    r = _expand(w, env, cwd)
    return os.path.normpath(r[0]) if r and len(r) == 1 else None


def _strip_wrapper(words: list[Word], env: dict[str, str | None]) -> list[Word] | None:
    """맨 앞 래퍼 하나를 벗긴 단어 목록. 래퍼가 아니면 None."""
    name = os.path.basename(words[0].literal())
    i = 1
    if name == "env":
        while i < len(words):
            lit = words[i].literal()
            if (a := _assign_of(words[i], env)) is not None:
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


def _strip_all(w: list[Word], env: dict[str, str | None]) -> list[Word]:
    """접두 할당(env 에 반영)과 래퍼를 반복해 벗긴다."""
    while w:
        while w and (a := _assign_of(w[0], env)) is not None:
            env[a[0]] = a[1]
            w = w[1:]
        if not w or (rest := _strip_wrapper(w, env)) is None:
            break
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
        raise LexError("heredoc 본문을 확정할 수 없음")
    return t


def _pipe_text(prev: Segment) -> str | None:
    """파이프 앞 단위가 셸에 넘기는 리터럴 텍스트. 모르면 None(해석하지 않고 통과)."""
    if prev.name == "cat":
        return next((_heredoc_text(r, prev.env) for r in prev.redirects if r.op in _HEREDOC), None)
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
    """셸이 실행할 코드 — 바깥 셸(outer, 기본 seg)이 확장한 뒤의 텍스트. 확장할 수 없으면 LexError(해석 실패)."""
    o = outer or seg
    a = seg.argv
    i, stdin = 1, False
    while i < len(a):
        x = a[i].literal()
        if x in ("-o", "+o", "-O", "+O", "--rcfile", "--init-file"):
            i += 2
            continue
        if _SHELL_C.fullmatch(x):
            if i + 1 >= len(a):
                return None
            if (code := _text(a[i + 1].parts, o.env, split=True)) is None:
                raise LexError("셸 -c 문자열을 확정할 수 없음")
            return code
        if not x.startswith(("-", "+")) or x in ("-", "--"):
            break
        stdin = stdin or bool(re.fullmatch(r"-[a-zA-Z]*s[a-zA-Z]*", x))
        i += 1
    if i < len(a) and a[i].literal() not in ("-", "--") and not stdin:
        return None  # 스크립트 파일을 실행하면 stdin 은 코드가 아니다(-s 면 stdin 이 코드)
    for r in seg.redirects:
        if r.op in _HEREDOC:
            return _heredoc_text(r, o.env)
        if r.op == "<<<" and r.target is not None:
            if (code := _text(r.target.parts, o.env)) is None:
                raise LexError("<<< 문자열을 확정할 수 없음")
            return code
    return _pipe_text(pipe_prev) if pipe_prev is not None else None


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
                raise LexError(f"알 수 없는 옵션 {k}")
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
                raise LexError(f"알 수 없는 옵션 {o}")
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


def _container(seg: Segment, segments: list[Segment], pipe_prev: Segment | None) -> None:
    """docker/podman exec|run, compose exec|run 의 안쪽 명령을 container 문맥 단위로 (spec §3.6)."""
    a = seg.argv
    compose = seg.name == "docker-compose"
    i = 1
    if not compose:
        i, _ = _opts(a, 1, _DOCKER_GLOBAL)
        if i < len(a) and a[i].literal() == "compose":
            compose, i = True, i + 1
    g: list[tuple[str, Word]] = []
    if compose:
        i, g = _opts(a, i, _COMPOSE_GLOBAL)
    sub = a[i].literal() if i < len(a) else ""
    if sub not in ("exec", "run"):
        return
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
    ctx = Context(
        "container", a[i].literal(), ("compose-" if compose else "") + sub,
        _mounts(o, seg) if sub == "run" and not compose else None,
        project_dir if compose else None,
        proj[-1] if proj else None,
    )
    wd = [w for k, w in o if k in ("-w", "--workdir")]
    r = _expand(wd[-1], seg.env, None) if wd else None  # 컨테이너 경로라 호스트 cwd 로 잇지 않는다
    cwd = r[0] if r and len(r) == 1 else None
    # 인자는 호스트 셸이 확장한다(seg.env) — 안쪽 단위의 cwd(-w)는 상대경로 기준으로만 쓰인다.
    # 컨테이너 안에서 실행되는 코드의 env 는 호스트 것을 물려받지 않는다(-w 만 셸 작업 폴더로 안다).
    cenv: dict[str, str | None] = {SHELL_CWD: cwd} if cwd else {}
    w = _strip_all(a[i + 1:], cenv)
    if not w:
        return
    stdin = [r for r in seg.redirects if r.op in _STDIN_CODE]  # exec -i 로 넘어가는 표준입력
    inner = Segment(_cmd_name(w), w, stdin, cwd, dict(seg.env), ctx, seg.depth + 1, seg.via_xargs)
    code = _shell_code(inner, pipe_prev, seg) if inner.name in SHELLS else None  # -c·<<< 는 호스트 셸이 먼저 확장
    if code is not None:
        _parse(code, cwd, cenv, ctx, inner.depth, segments, seg.via_xargs)
    else:
        segments.append(inner)
        _descend(inner, segments, pipe_prev, cenv)


def _descend(seg: Segment, segments: list[Segment], pipe_prev: Segment | None,
             run_env: dict[str, str | None]) -> tuple[str | None, dict[str, str | None]] | None:
    """seg 가 실행하는 안쪽 명령을 seg 바로 뒤에 depth+1 로 넣는다. eval 이면 그 뒤 상태(현재 셸에서 돌므로).

    seg.env 는 seg 단어를 확장한 env, run_env 는 seg 가 실행될 때의 env(접두 할당 포함·컨테이너면 컨테이너 쪽).
    """
    d = seg.depth + 1
    if seg.name in SHELLS:
        if (code := _shell_code(seg, pipe_prev)) is not None:
            _parse(code, seg.cwd, dict(run_env), seg.context, d, segments, seg.via_xargs)
    elif seg.name == "eval":
        vals = [_text(w.parts, seg.env) for w in seg.argv[1:]]
        if None in vals:
            raise LexError("eval 인자를 확정할 수 없음")
        return _parse(" ".join(vals), seg.cwd, dict(run_env), seg.context, d, segments, seg.via_xargs)  # type: ignore[arg-type]
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
        if (w := _strip_all(cmd, env)):
            inner = Segment(_cmd_name(w), w, [], seg.cwd, dict(seg.env), seg.context, d, via_xargs=True)
            segments.append(inner)
            _descend(inner, segments, None, env)
    elif seg.name in _CONTAINER_CLIS:
        _container(seg, segments, pipe_prev)
    return None


def parse(command: str, cwd: str | None, env: Mapping[str, str], context: Context = HOST) -> ParseResult:
    state_env: dict[str, str | None] = {k: env[k] for k in ("HOME", "TMPDIR", "USER") if k in env}
    if cwd is not None:
        state_env["PWD"] = state_env[SHELL_CWD] = cwd
    segments: list[Segment] = []
    try:
        _parse(command, cwd, state_env, context, 0, segments)
    except LexError as e:
        return ParseResult([], str(e))
    return ParseResult(segments)


def _parse(command: str, cwd: str | None, state_env: dict[str, str | None], context: Context, depth: int,
           segments: list[Segment], via_xargs: bool = False) -> tuple[str | None, dict[str, str | None]]:
    """segments 에 단위를 덧붙이고 끝 상태(cwd, env)를 돌려준다. 오류는 LexError."""
    if depth > _MAX_DEPTH:
        raise LexError("재귀 깊이 초과")
    toks = lex(command)
    st = {"cwd": cwd}
    stack: list[tuple[str, str | None, dict[str, str | None], bool]] = []
    words: list[Word] = []
    redirects: list[Redirect] = []
    pipe_prev: Segment | None = None

    def flush() -> Segment | None:
        nonlocal words, redirects
        w, r, words, redirects = words, redirects, [], []
        # 치환은 할당 값·for 머리·리다이렉트 대상에서도 실행된다(컨트롤러 결정)
        subs = [x for wd in w + [rd.target for rd in r if rd.op not in _HEREDOC and rd.target is not None] for x in _word_subs(wd)]
        # 구분자에 따옴표가 없는 heredoc 본문의 치환도 실행된다
        subs += [x for rd in r if rd.op in _HEREDOC and rd.body and rd.target is not None and not rd.target.is_quoted()
                 for x in _subs(rd.body, False)]
        sub_cwd, sub_env = st["cwd"], dict(state_env)
        seg = unit(w, r)
        for code in subs:
            _parse(code, sub_cwd, dict(sub_env), context, depth + 1, segments, via_xargs)
        return seg

    def unit(w: list[Word], r: list[Redirect]) -> Segment | None:
        while w and not w[0].is_quoted() and w[0].literal() in _RESERVED:
            w = w[1:]
        if w and all(_is_assign(x) for x in w):  # 할당만 있는 단위는 이후 단위에 반영
            for x in w:
                k, v = _assign_of(x, state_env)  # type: ignore[misc]
                state_env[k] = v
            if not r:
                return None
            w = []
        # 같은 줄 단어는 할당 전 env 로 확장되고(seg.env), 접두 할당은 실행되는 안쪽 코드에만 보인다(run_env)
        unit_env = dict(state_env)
        run_env = dict(state_env)
        w = _strip_all(w, run_env)
        if w and not w[0].is_quoted() and w[0].literal() in _LOOP_HEAD:
            return None
        unit_cwd = st["cwd"]
        name = _cmd_name(w)
        if name == "git":
            while len(w) > 2 and w[1].literal() == "-C":
                unit_cwd = _resolve_dir(w[2], unit_cwd, unit_env)
                w = [w[0]] + w[3:]
        if name in _VAR_DECL:
            for x in w[1:]:
                if (a := _assign_of(x, state_env)) is not None:
                    state_env[a[0]] = a[1]
            return None
        if not (w or r):
            return None
        seg = Segment(name, w, r, unit_cwd, unit_env, context, depth, via_xargs)
        segments.append(seg)
        if (after := _descend(seg, segments, pipe_prev, run_env)) is not None:
            st["cwd"] = after[0]
            state_env.clear()
            state_env.update(after[1])
        if name in ("cd", "pushd"):
            args = [x for x in w[1:] if x.literal() != "--" and not (x.literal().startswith("-") and x.literal() != "-")]
            st["cwd"] = _resolve_dir(args[0], st["cwd"], unit_env) if args else (
                state_env.get("HOME") if name == "cd" else None)
            if st["cwd"] is not None:
                state_env["PWD"] = state_env[SHELL_CWD] = st["cwd"]
            else:
                state_env.pop("PWD", None)
                state_env.pop(SHELL_CWD, None)
        elif name == "popd":
            st["cwd"] = None
            state_env.pop("PWD", None)
            state_env.pop(SHELL_CWD, None)
        return seg

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

    def close_group(kind: str) -> None:
        nonlocal snap, in_pipe
        flush()
        if in_pipe:  # 그룹 안 마지막 파이프 구성원
            restore()
        if not stack or stack[-1][0] != kind:
            raise LexError(f"짝 없는 {'}' if kind == '{' else ')'!r}")
        _, cwd0, env0, outer_pipe = stack.pop()
        if kind == "(" or outer_pipe:  # 서브셸, 또는 파이프 구성원인 { } 는 안쪽 변화가 밖으로 안 나간다
            st["cwd"] = cwd0
            state_env.clear()
            state_env.update(env0)
        in_pipe = outer_pipe
        snap = (cwd0, env0)  # 그룹 뒤 `|`·`&` 가 오면 그룹 전체를 되돌리는 기준

    for t in toks:
        if t.kind == "word":
            w = t.word
            if not words and not redirects and not w.is_quoted() and w.literal() in ("{", "}"):
                if w.literal() == "{":
                    open_group("{")
                else:
                    close_group("{")
            else:
                words.append(w)
        elif t.kind == "redir":
            redirects.append(Redirect(t.op, t.fd, t.target, t.body))
        elif t.op in _BOUNDARY:
            seg = flush()
            if in_pipe or t.op in _SUBSHELL_OPS:
                restore()
            in_pipe = t.op in ("|", "|&")
            pipe_prev = seg if in_pipe else None
            snap = (st["cwd"], dict(state_env))
        elif t.op == "(":
            flush()
            open_group("(")
        elif t.op == ")":
            close_group("(")
    flush()
    if stack:
        raise LexError("닫히지 않은 그룹")
    return st["cwd"], state_env
