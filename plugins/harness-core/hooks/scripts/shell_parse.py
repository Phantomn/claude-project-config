"""bash-guard 어휘 분석기: 셸 명령 문자열 -> 토큰 목록 (spec §3.3-1).

shlex 를 쓰지 않는 이유: 따옴표 종류·리다이렉트 위치·`2>&1` 을 잃어 단위 분해가 틀어진다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace


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
            j = _skip_dq(s, i + 1)
            # 큰따옴표 안 \" 와 \\ 만 이스케이프 해제, 나머지(\$ 등)는 원문 유지
            add(re.sub(r'\\(["\\])', r"\1", s[i + 1 : j - 1]), '"')
            i = j
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
