"""bash-guard 대상 분류 기반: 세션 시각·생성 시각·정규화·임시 루트·보호 이름·스위치 값 (spec §3.4, §3.9)."""
from __future__ import annotations

import functools
import json
import math
import os
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace

# subprocess·hashlib·datetime 은 쓰는 함수 안에서 import — 모든 Bash 호출의 기동 지연(약 5ms)을 조회가 필요할 때만 낸다
from guard_mode import (  # noqa: F401 — 재수출(기존 import 경로 유지)
    MODE_RANK,
    repo_root,
    switch_mode,
)
from ledger import (
    KIND_CREATED,
    KIND_PRE_DIRTY,
    KIND_PRE_SESSION,
    KIND_TOUCHED,
    Entry,
    Ledger,
)
from shell_parse import Mount

TYPE_CHECKING = False   # typing import 를 피한다(bash_guard 와 같은 이유)
if TYPE_CHECKING:
    import subprocess

# 벽시계가 뒤로 간다(WSL2 실측 약 30초마다 −0.6초·−0.68초 연속) — 세션 전 항목이 세션 시작 뒤로 찍혀
# '세션이 만든 것'(저장소 통째 삭제 허용)이 되지 않게, 세션 시작 + 여유 안의 시각은 세션 전으로 본다
CLOCK_MARGIN = 2.0
CLOCK_MARGIN_ENV = "HARNESS_BASH_GUARD_CLOCK_MARGIN"


@dataclass
class Ctx:
    environ: Mapping[str, str]
    session_id: str | None
    transcript_path: str | None
    ledger: Ledger
    deadline: float  # time.monotonic() 기준
    clock_margin: float = CLOCK_MARGIN

    @functools.cached_property
    def session_start(self) -> float | None:
        # stat 외부 명령은 세션 시각이 필요한 판정에서만 — 대부분의 명령은 묻지 않는다
        return session_start(self.transcript_path, self.environ)

    def remaining(self) -> float:
        return self.deadline - time.monotonic()


def before_session(t: float, ctx: Ctx) -> bool:
    """t 가 세션 전(또는 세션 시작 근처라 확정 불가)인가. 세션 시작을 모르면 True(보호)."""
    return ctx.session_start is None or t < ctx.session_start + ctx.clock_margin


def _clock_margin(environ: Mapping[str, str]) -> float:
    try:
        v = float(environ.get(CLOCK_MARGIN_ENV, ""))
    except ValueError:
        return CLOCK_MARGIN
    # nan 은 모든 비교가 거짓이라 '세션 전 아님'이 된다 — 유한한 0 이상만 받는다
    return v if math.isfinite(v) and v >= 0 else CLOCK_MARGIN


FIXED_SCRATCH_ROOTS: tuple[str, ...] = ("/tmp", "/var/tmp")
WIN_TEMP_PATTERN = "/mnt/c/Users/*/AppData/Local/Temp"
# '*' 를 한 경로 구성요소로만 맞춘다(fnmatch 의 '*' 는 '/' 도 넘어 임의 깊이 폴더까지 임시로 본다)
_WIN_TEMP_RE = re.compile(re.escape(WIN_TEMP_PATTERN).replace(r"\*", "[^/]+"))
_ENV_EXAMPLES = {".env.example", ".env.sample", ".env.template"}
_LOCAL_SUFFIXES = (".local.json", ".local.yaml", ".local.yml", ".local.toml")
_KEY_PREFIXES = ("id_rsa", "id_ed25519", "id_ecdsa", "credentials")
_SECRET_DIRS = {".ssh", ".gnupg", ".aws"}
_TEXT = {"encoding": "utf-8", "errors": "surrogateescape"}


def make_ctx(payload: dict, environ: Mapping[str, str], budget: float) -> Ctx:
    deadline = time.monotonic() + budget
    return Ctx(environ, payload.get("session_id") or None,
               payload.get("transcript_path"), Ledger(environ), deadline, _clock_margin(environ))


def session_start(transcript_path: str | None, environ: Mapping[str, str]) -> float | None:
    if not transcript_path:
        return None
    import subprocess
    try:
        r = subprocess.run(["stat", "-c", "%.9W", "--", transcript_path], env=dict(environ),
                           capture_output=True, timeout=2.0, check=False, **_TEXT)
        v = float(r.stdout) if r.returncode == 0 else 0.0
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return v or None


def _parse_stat(stdout: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for line in stdout.splitlines():
        num, sep, name = line.partition(" ")
        try:
            v = float(num)
        except ValueError:
            continue
        if sep and v:
            out[name] = v
    return out


def births(paths: list[str], ctx: Ctx) -> dict[str, float]:
    # 줄바꿈 든 경로는 %n 출력 줄이 갈라져 다른 키로 오인될 수 있어 묻지 않는다(키 없음 = 읽을 수 없음, 보호 쪽)
    asked = [p for p in paths if "\n" not in p]
    if not asked:
        return {}
    r = run(["stat", "-c", "%.9W %n", "--", *asked], ctx)
    if r is None:
        return {}
    wanted = set(asked)
    return {k: v for k, v in _parse_stat(r.stdout).items() if k in wanted}


def run(cmd: list[str], ctx: Ctx, cwd: str | None = None, stdin: str | None = None) -> subprocess.CompletedProcess | None:
    left = ctx.remaining()
    if left <= 0:
        return None
    import subprocess
    try:
        return subprocess.run(cmd, cwd=cwd, env=dict(ctx.environ), capture_output=True, input=stdin,
                              timeout=min(2.0, left), check=False, **_TEXT)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def normalize(path: str, trailing_slash: bool) -> str:
    # normpath 로 '..' 를 먼저 지우지 않는다 — 링크 뒤 '..' 는 링크 대상의 부모라서 realpath 로 함께 해소 (spec §3.4 정규화 4)
    head, name = os.path.split(path)
    if trailing_slash or name in ("", ".", ".."):
        return os.path.realpath(path)
    # 대상 자체가 링크면 링크를 본다(rm 은 링크만 지움) — 부모만 해소
    return os.path.join(os.path.realpath(head or "."), name)


def scratch_roots(ctx: Ctx) -> list[str]:
    return list(_scratch_roots(ctx.environ.get("TMPDIR", ""), ctx.environ.get("HOME", "")))


# 경로마다 다시 풀면 /mnt/c 의 lstat(WSL 실측 수백 µs)이 폴더 순회 항목 수만큼 반복돼 예산을 넘는다(2000개 6초 실측)
@functools.lru_cache(maxsize=16)
def _scratch_roots(tmpdir: str, home: str) -> tuple[str, ...]:
    roots = list(FIXED_SCRATCH_ROOTS)
    if tmpdir:
        roots.append(tmpdir)
    if home:
        roots.append(os.path.join(home, ".cache"))
    roots.append("/mnt/c/Windows/Temp")
    # 대상 경로가 realpath 로 정규화되므로 루트도 같은 형태로
    return tuple(dict.fromkeys(os.path.realpath(r) for r in roots))


def is_scratch(path: str, ctx: Ctx) -> bool:
    m = _WIN_TEMP_RE.match(path)
    if m and len(path) > m.end() + 1 and path[m.end()] == "/":
        return True
    return any(r != "/" and path.startswith(r + "/") for r in scratch_roots(ctx))


def is_scratch_root(path: str, ctx: Ctx) -> bool:
    return path in scratch_roots(ctx) or _WIN_TEMP_RE.fullmatch(path) is not None


def protected_name(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    if ".git" in parts or _SECRET_DIRS.intersection(parts):
        return True
    if name == ".env" or (name.startswith(".env.") and name not in _ENV_EXAMPLES):
        return True
    return (name.endswith(_LOCAL_SUFFIXES) or name.endswith((".pem", ".key"))
            or name.startswith(_KEY_PREFIXES) or name == ".netrc")


# ---- 7분류·폴더 규칙·작업 영역·장부 기록 (spec §3.4, §3.7) ----

MISSING, UNRESOLVED, PROTECTED_NAME, GIT_TRACKED, SCRATCH, SESSION_NEW, IGNORED_ARTIFACT, PRESERVED = (
    "MISSING", "UNRESOLVED", "PROTECTED_NAME", "GIT_TRACKED", "SCRATCH", "SESSION_NEW", "IGNORED_ARTIFACT", "PRESERVED")
DIR_ENTRY_CAP = 2000
REGENERABLE_NAMES: frozenset[str] = frozenset(
    ["node_modules", "dist", "build", ".next", ".nuxt", "target", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".tox", ".venv", "venv", "coverage", ".coverage", ".gradle", ".parcel-cache", ".turbo", ".cache"])
REGENERABLE_SUFFIXES = (".pyc", ".pyo", ".o", ".class")
SEVERITY = {MISSING: 0, SCRATCH: 0, SESSION_NEW: 0, IGNORED_ARTIFACT: 0, GIT_TRACKED: 1, PRESERVED: 2, PROTECTED_NAME: 2,
            UNRESOLVED: 3}


@dataclass(frozen=True)
class Cls:
    kind: str
    path: str | None
    detail: str = ""
    worktree_root: str | None = None     # 대상이 linked worktree 최상위면 그 경로
    session_repo: bool = False           # 분류 1b(이번 세션이 만든 저장소 안)


class _Unresolved(Exception):
    pass


def _start_dir(path: str) -> str:
    # 대상이 링크면 링크가 놓인 폴더 기준(링크 대상의 저장소가 아니라)
    return path if os.path.isdir(path) and not os.path.islink(path) else os.path.dirname(path)


def _git_top(path: str, ctx: Ctx) -> str | None:
    d = _start_dir(os.path.abspath(path))
    while not os.path.isdir(d):
        d = os.path.dirname(d)
    r = run(["git", "-C", d, "rev-parse", "--show-toplevel"], ctx)
    if r is None:
        raise _Unresolved("git 조회 실패")
    return r.stdout[:-1] if r.returncode == 0 and r.stdout.endswith("\n") else None


def git_toplevel(path: str, ctx: Ctx) -> str | None:
    try:
        return _git_top(path, ctx)
    except _Unresolved:
        return None


def git_tracked(repo: str, paths: list[str], ctx: Ctx) -> set[str] | None:
    """추적 파일이거나 추적 파일을 품은 폴더인 경로들. 조회 실패면 None."""
    if not paths:
        return set()
    r = run(["git", "--literal-pathspecs", "-C", repo, "ls-files", "-z", "--", *paths], ctx)
    if r is None or r.returncode != 0:
        return None
    names = [n for n in r.stdout.split("\0") if n]
    covered: set[str] = set()
    for n in names:
        while n and n not in covered:
            covered.add(n)
            n = os.path.dirname(n)
    out = set()
    for p in paths:
        rel = os.path.relpath(p, repo)
        if rel in covered or (rel == "." and names):
            out.add(p)
    return out


def git_ignored(repo: str, paths: list[str], ctx: Ctx) -> set[str] | None:
    """ignore 규칙에 걸리는 경로들(상위 폴더가 ignore 여도 포함). 조회 실패면 None."""
    if not paths:
        return set()
    r = run(["git", "-C", repo, "check-ignore", "-z", "--stdin"], ctx, stdin="".join(p + "\0" for p in paths))
    if r is None or r.returncode not in (0, 1):
        return None
    hit = set(r.stdout.split("\0"))
    return {p for p in paths if p in hit}


def is_linked_worktree_root(path: str) -> bool:
    g = os.path.join(path, ".git")
    if os.path.islink(g) or not os.path.isfile(g):
        return False
    try:
        with open(g, encoding="utf-8", errors="replace") as f:
            text = f.read(4096)
    except OSError:
        return False
    # 서브모듈의 .git 파일은 modules/ 를 가리킨다 — worktrees/ 만 linked worktree
    return text.startswith("gitdir:") and "/worktrees/" in text


def _nearest_git(path: str, cache: dict[str, str | None]) -> str | None:
    d = _start_dir(path)
    seen = []
    while d not in cache:
        seen.append(d)
        if os.path.lexists(os.path.join(d, ".git")):
            cache[d] = d
            break
        if d == "/":
            cache[d] = None
            break
        d = os.path.dirname(d)
    for s in seen:
        cache[s] = cache[d]
    return cache[d]


def _session_new(paths: list[str], ctx: Ctx, rows: dict[str, list[Entry]] | None = None) -> set[str]:
    start = ctx.session_start
    if start is None or not paths:
        return set()
    b = births(paths, ctx)
    cand = {p for p in paths if p in b and not before_session(b[p], ctx)}
    if not cand:
        return set()
    # 장부는 묶음당 한 번만 읽는다 — entries() 를 항목마다 부르면 폴더 순회에서 항목 수만큼 파일 전체를 읽는다
    if rows is None:
        rows = ctx.ledger.entries_for(cand)
    sid = ctx.session_id
    return {p for p in cand if not any((e.kind == KIND_PRE_SESSION and e.session_id == sid)
                                       or (e.kind == KIND_CREATED and e.session_id != sid) for e in rows.get(p, ()))}


def _is_session_repo(top: str | None, ctx: Ctx) -> bool:
    if top is None or top == "/":
        return False
    home = ctx.environ.get("HOME")
    if home and os.path.realpath(home) == top:
        return False
    g = os.path.join(top, ".git")
    return os.path.isdir(g) and not os.path.islink(g)


def _classify_many(paths: list[str], ctx: Ctx) -> list[Cls]:
    """존재하는 정규화 경로들을 분류 1b~7 로(폴더 순회 없이). git·stat 은 저장소·묶음마다 한 번."""
    res: dict[str, Cls] = {}
    cache: dict[str, str | None] = {}
    near: dict[str, str | None] = {}
    for p in paths:   # 경로마다 조상 lstat — /mnt/c 에서는 수백 개만으로 수 초(재생 최대 7.5초 실측)
        _budget(ctx)
        near[p] = _nearest_git(p, cache)
    tops = sorted({t for t in near.values() if _is_session_repo(t, ctx)})
    new_tops = _session_new(tops, ctx)
    for p in paths:
        if near[p] in new_tops:
            res[p] = Cls(SCRATCH, p, "세션 저장소", session_repo=True)
        elif protected_name(p):
            res[p] = Cls(PROTECTED_NAME, p)
    groups: dict[str, list[str]] = {}
    for key in sorted({near[p] for p in paths if p not in res and near[p]}):
        top = _git_top(key, ctx)
        if top is None:
            # .git 은 있는데 git 이 저장소로 못 읽는다(손상·소유권) — 저장소 아님으로 떨어뜨리면 추적·변경 판정이 빠진다
            raise _Unresolved(f"git 저장소를 읽을 수 없다: {key}")
        groups.setdefault(top, []).extend(p for p in paths if p not in res and near[p] == key)
    for top, ps in groups.items():
        tracked = git_tracked(top, ps, ctx)
        if tracked is None:
            raise _Unresolved("git 조회 실패")
        for p in tracked:
            res[p] = Cls(GIT_TRACKED, p)
    rest = [p for p in paths if p not in res]
    for p in rest:
        if is_scratch(p, ctx):
            res[p] = Cls(SCRATCH, p)
    rest = [p for p in rest if p not in res]
    _budget(ctx)   # 예산이 다한 뒤의 빈 births() 는 '세션 전'으로 떨어진다 — 시간 초과 사유가 맞다
    for p in _session_new(rest, ctx):
        res[p] = Cls(SESSION_NEW, p)
    for top, ps in groups.items():
        ps = [p for p in ps if p not in res]
        ignored = git_ignored(top, ps, ctx)
        if ignored is None:
            raise _Unresolved("git 조회 실패")
        for p in ignored:
            rel = os.path.relpath(p, top)
            if REGENERABLE_NAMES.intersection(rel.split("/")) or rel.endswith(REGENERABLE_SUFFIXES):
                res[p] = Cls(IGNORED_ARTIFACT, p)
    return [res.get(p) or Cls(PRESERVED, p) for p in paths]


def _unreadable(e: OSError) -> None:
    raise _Unresolved(f"읽을 수 없는 항목: {e.filename}")


def _budget(ctx: Ctx) -> None:
    if ctx.remaining() <= 0:
        raise _Unresolved("판정 시간 초과 — 범위를 좁혀라")


def _entries(d: str, ctx: Ctx) -> list[str]:
    out: list[str] = []
    # followlinks=False: 링크 폴더로 내려가지 않아 순환 링크도 끝난다. 링크 자체는 항목으로 남는다
    for root, dirs, files in os.walk(d, onerror=_unreadable):
        _budget(ctx)
        for n in dirs + files:
            out.append(os.path.join(root, n))
            if len(out) > DIR_ENTRY_CAP:
                raise _Unresolved(f"폴더 항목 {DIR_ENTRY_CAP}개 초과 — 범위를 좁혀라")
    return out


def _protected_inside(d: str, ctx: Ctx) -> str | None:
    """임시 루트 폴더 규칙: 이름만 본다(상한 없음), 이번 세션 저장소 안으로는 내려가지 않는다."""
    rows = None
    for root, dirs, files in os.walk(d, onerror=_unreadable):
        _budget(ctx)
        for n in dirs + files:
            if protected_name(os.path.join(root, n)):
                return os.path.join(root, n)
        repos = [os.path.join(root, x) for x in dirs if _is_session_repo(os.path.join(root, x), ctx)]
        if repos:
            if rows is None:
                rows = ctx.ledger.entries_for()
            new = _session_new(repos, ctx, rows)
            dirs[:] = [x for x in dirs if os.path.join(root, x) not in new]
    return None


def classify(path: str | None, ctx: Ctx, trailing_slash: bool = False) -> Cls:
    if path is None:
        return Cls(UNRESOLVED, None, "대상을 확정할 수 없다")
    p = normalize(path, trailing_slash)
    if not os.path.lexists(p):
        return Cls(MISSING, p)
    if is_scratch_root(p, ctx):
        # 루트 자체는 다른 세션·프로세스의 파일까지 담는다 (spec §3.4 임시 루트 ★)
        return Cls(UNRESOLVED, p, "임시 루트 자체 — 자기 세션 폴더로 범위를 좁혀라")
    if ctx.ledger.moved_in_near(p):
        return Cls(PRESERVED, p, "옮겨진 유일본")
    try:
        me = _classify_many([p], ctx)[0]
        if me.session_repo:
            return me
        if is_linked_worktree_root(p):
            # 추적 파일은 커밋에 있다 — 커밋 안 된 변경·ignore 유일본은 정책이 worktree 규칙으로 본다(spec §3.4)
            return replace(me, worktree_root=p)
        if not os.path.isdir(p) or os.path.islink(p) or me.kind == IGNORED_ARTIFACT:
            return me
        if me.kind == SCRATCH:
            hit = _protected_inside(p, ctx)
            return Cls(PROTECTED_NAME, p, f"보호 이름: {hit}") if hit else me
        worst = me
        for c in _classify_many(_entries(p, ctx), ctx):
            if SEVERITY[c.kind] > SEVERITY[worst.kind]:
                worst = c
        return worst if worst is me else Cls(worst.kind, p, f"{worst.path} {worst.detail}".rstrip())
    except _Unresolved as e:
        return Cls(UNRESOLVED, p, str(e))


def in_workspace(path: str, ctx: Ctx) -> bool:
    p = normalize(path, False)
    if is_scratch(p, ctx):
        return True
    top = git_toplevel(p, ctx)
    if top is None or top == "/":
        return False
    home = ctx.environ.get("HOME")
    if home and os.path.realpath(home) == top:
        return False
    g = os.path.join(top, ".git")
    return p != g and not p.startswith(g + "/")


def note_touch(path: str, ctx: Ctx, tool: str | None) -> None:
    p = normalize(path, False)
    L, sid = ctx.ledger, ctx.session_id
    if not os.path.lexists(p):
        if tool == "Write":
            L.record(p, KIND_CREATED, sid)
    else:
        b = births([p], ctx).get(p)
        if ctx.session_start is not None and b is not None and before_session(b, ctx):
            L.record(p, KIND_PRE_SESSION, sid)
        if _nearest_git(p, {}) and not any(e.kind == KIND_TOUCHED and e.session_id == sid for e in L.entries(p)) \
                and _pre_dirty(p, ctx):
            L.record(p, KIND_PRE_DIRTY, sid)
    # 판정기(tool None)도 touched 를 쓴다 — spec §3.7 기록 주체 2 는 '같은 규칙(created 제외)'
    L.record(p, KIND_TOUCHED, sid)


def _pre_dirty(p: str, ctx: Ctx) -> bool:
    """추적 파일이고 커밋 안 된 수정이 있는가. .git 이 있는데 조회가 실패하면 True(과보호)."""
    try:
        top = _git_top(p, ctx)
        tracked = git_tracked(top, [p], ctx) if top else None
        if tracked is None:
            raise _Unresolved("git 조회 실패")
        if p not in tracked:
            return False
        r = run(["git", "--literal-pathspecs", "-C", top, "status", "--porcelain=v1", "-z", "--", p], ctx)
        if r is None or r.returncode != 0:
            raise _Unresolved("git 조회 실패")
        return bool(r.stdout)
    except _Unresolved:
        return True


# ---- git 상태·브랜치·find 미리보기·docker 조회 (spec §3.5, §3.6, §3.7) — 실패·시간 초과는 None ----

def _git(repo: str, args: list[str], ctx: Ctx, stdin: str | None = None) -> str | None:
    r = run(["git", "-C", repo, *args], ctx, stdin=stdin)
    return r.stdout if r is not None and r.returncode == 0 else None


def _status_paths(out: str) -> list[tuple[str, str]]:
    """`status --porcelain=v1 -z` 를 (XY, 경로) 로. 이름 변경·복사는 다음 칸의 원래 이름도 같은 XY 로."""
    items, res, i = out.split("\0"), [], 0
    while i < len(items):
        e = items[i]
        i += 1
        if len(e) < 4:
            continue
        res.append((e[:2], e[3:]))
        if "R" in e[:2] or "C" in e[:2]:
            res.append((e[:2], items[i]))
            i += 1
    return res


def git_dirty(repo: str, pathspecs: list[str], ctx: Ctx) -> list[str] | None:
    top = git_toplevel(repo, ctx)
    out = _git(repo, ["status", "--porcelain=v1", "-z", "--untracked-files=no", "--", *pathspecs], ctx) if top else None
    if out is None:
        return None
    # porcelain 경로는 cwd 가 아니라 저장소 최상위 기준
    return [os.path.join(top, p) for _, p in _status_paths(out)]


def is_session_change(path: str, ctx: Ctx) -> bool:
    start, sid = ctx.session_start, ctx.session_id
    p = normalize(path, False)
    try:
        mtime = os.lstat(p).st_mtime
    except OSError:
        return False
    if start is None or before_session(mtime, ctx):
        return False
    # 다른 세션의 손길은 여유만큼 앞까지 '이번 세션 중'으로 본다(애매하면 내 변경 아님)
    return not any((e.kind == KIND_PRE_DIRTY and e.session_id == sid)
                   or (e.kind == KIND_TOUCHED and e.session_id != sid and e.ts >= start - ctx.clock_margin)
                   for e in ctx.ledger.entries(p))


def git_default_branch(repo: str, remote: str, ctx: Ctx) -> str | None:
    pre = f"refs/remotes/{remote}/"
    head = (_git(repo, ["symbolic-ref", "-q", pre + "HEAD"], ctx) or "").strip()
    if head.startswith(pre):
        return head[len(pre):]
    names = ("main", "master")
    out = _git(repo, ["for-each-ref", "--format=%(refname)", *(b + n for n in names for b in ("refs/heads/", pre))], ctx)
    have = set((out or "").split("\n"))
    return next((n for n in names if "refs/heads/" + n in have or pre + n in have), None)


def git_remote_names(repo: str, ctx: Ctx) -> list[str] | None:
    # 실패(None)와 원격 없음([])을 구분한다 — 원격 없음만 push 판정 대상이 아니다
    out = _git(repo, ["remote"], ctx)
    return None if out is None else out.split()


def git_upstream_branch(repo: str, ctx: Ctx) -> str | None:
    # 설정에서 읽는다 — `rev-parse --abbrev-ref @{u}` 는 추적 ref 가 없으면 실패하고(실측) 값도 '원격/이름' 이라 기본 브랜치와 비교가 안 된다
    cur = (_git(repo, ["symbolic-ref", "-q", "--short", "HEAD"], ctx) or "").strip()
    merge = (_git(repo, ["config", f"branch.{cur}.merge"], ctx) or "").strip() if cur else ""
    return merge.removeprefix("refs/heads/") or None


def _epoch(text: str | None) -> float | None:
    try:
        return float(text) if text else None
    except ValueError:
        return None


def git_stash_created(repo: str, ref: str, ctx: Ctx) -> float | None:
    return _epoch(_git(repo, ["log", "-1", "--format=%ct", "--end-of-options", ref, "--"], ctx))


_CLEAN_LONG = ("dry-run", "force", "interactive", "quiet", "exclude")


def git_clean_preview(repo: str, clean_args: list[str], ctx: Ctx) -> list[str] | None:
    args: list[str] = []
    opts, value_next = True, False
    for a in clean_args:
        if value_next or not opts or not a.startswith("-") or a == "-":
            value_next = False
        elif a == "--":
            opts = False
        elif a.startswith("--"):
            # git 은 긴 옵션의 모호하지 않은 접두를 받는다(`--q` = quiet, 실측) — 목록 밖·모호하면 확정 불가
            name, eq, _ = a[2:].partition("=")
            hit = [o for o in _CLEAN_LONG if o.startswith(name)] if name else []
            if len(hit) != 1 or hit[0] == "interactive" or (eq and hit[0] != "exclude"):
                return None
            if hit[0] == "quiet":
                continue
            value_next = hit[0] == "exclude" and not eq
        else:
            flags, e, val = a[1:].partition("e")   # -e 뒤는 패턴 값이라 q 를 빼면 안 된다
            if "i" in flags:
                return None
            value_next = bool(e) and not val
            # -q 는 목록 출력을 막는다(빈 목록 = 허용 오판). -f·-ff 는 그대로 — -n 이 함께면 지우지 않고, -ff 라야 중첩 저장소가 목록에 든다
            a = "-" + flags.replace("q", "") + e + val
            if a == "-":
                continue
        args.append(a)
    # 메시지가 번역되면 'Would remove' 를 못 찾는다 — C 로캘 고정
    r = run(["env", "LC_ALL=C", "git", "-C", repo, "-c", "core.quotepath=false", "clean", "-n", *args], ctx)
    if r is None or r.returncode != 0:
        return None
    out = []
    for line in r.stdout.splitlines():
        if line.startswith("Would remove "):
            name = line[len("Would remove "):]
            if name.startswith('"'):
                return None   # 제어 문자가 든 이름은 따옴표로 바뀌어 원래 경로를 확정할 수 없다
            out.append(os.path.join(repo, name.rstrip("/")))
    return out


def git_extra_items(worktree: str, ctx: Ctx) -> list[str] | None:
    out = _git(worktree, ["status", "--porcelain=v1", "-z", "--ignored=matching", "--untracked-files=normal"], ctx)
    if out is None:
        return None
    return [os.path.join(worktree, p.rstrip("/")) for xy, p in _status_paths(out) if xy in ("??", "!!")]


@dataclass(frozen=True)
class BranchInfo:
    has_upstream: bool
    upstream_ref_exists: bool
    ahead: int | None
    reachable_elsewhere: bool
    created_at: float | None
    merged_into_default: bool


def _patch_ids(repo: str, diff: str | None, ctx: Ctx) -> set[str] | None:
    if diff is None:
        return None
    out = _git(repo, ["patch-id", "--stable"], ctx, stdin=diff)
    return None if out is None else {line.split()[0] for line in out.splitlines() if line.strip()}


def _merged(repo: str, tip: str, remote: str, ctx: Ctx) -> bool | None:
    default = git_default_branch(repo, remote, ctx)
    if default is None:
        return False
    base = None
    for ref in (f"refs/remotes/{remote}/{default}", f"refs/heads/{default}"):
        if _git(repo, ["rev-parse", "--verify", "-q", ref], ctx) is not None:
            base = ref
            break
    if base is None:
        return False
    cherry = _git(repo, ["cherry", base, tip], ctx)
    if cherry is None:
        return None
    if not any(line.startswith("+") for line in cherry.splitlines()):
        return True
    mb = (_git(repo, ["merge-base", base, tip], ctx) or "").strip()
    if not mb:
        return False
    plain = ["--no-color", "--no-ext-diff"]
    mine = _patch_ids(repo, _git(repo, ["diff", *plain, mb, tip], ctx), ctx)
    landed = _patch_ids(repo, _git(repo, ["log", "-p", *plain, f"{mb}..{base}"], ctx), ctx)
    if mine is None or landed is None:
        return None
    return bool(mine & landed)   # 스쿼시 병합: 브랜치 전체 diff 가 기본 브랜치의 한 커밋과 같다


def git_branch_info(repo: str, branch: str, ctx: Ctx) -> BranchInfo | None:
    head = f"refs/heads/{branch}"
    tip = (_git(repo, ["rev-parse", "--verify", "-q", head + "^{commit}"], ctx) or "").strip()
    if not tip:
        return None
    remote = (_git(repo, ["config", f"branch.{branch}.remote"], ctx) or "").strip()
    # '<b>@{u}' 는 같은 이름 태그와 모호하고 'refs/heads/<b>@{u}' 는 안 먹는다(실측) — 설정상 추적 ref 이름을 받아 존재를 따로 본다
    up = (_git(repo, ["for-each-ref", "--format=%(upstream)", head], ctx) or "").strip()
    if up and _git(repo, ["rev-parse", "--verify", "-q", up], ctx) is None:
        up = ""
    ahead = None
    if up:
        n = _epoch(_git(repo, ["rev-list", "--count", f"{up}..{tip}"], ctx))
        if n is None:
            return None
        ahead = int(n)
    refs = _git(repo, ["for-each-ref", "--contains", tip, "--format=%(refname)"], ctx)
    reflog = _git(repo, ["reflog", "show", "--date=unix", "--format=%gd", head], ctx)
    merged = _merged(repo, tip, remote or "origin", ctx)
    if refs is None or reflog is None or merged is None:
        return None
    lines = reflog.split()
    # 마지막 줄 = 가장 오래된 reflog 항목 '<b>@{<epoch>}' (%ct 는 가리키는 커밋 시각이라 분기 시각이 아니다)
    created = _epoch(lines[-1].rpartition("@{")[2].rstrip("}")) if lines else None
    return BranchInfo(bool(remote), bool(up), ahead, bool(set(refs.split("\n")) - {"", head, up}), created, merged)


_FIND_VALUE_TESTS = {"-name", "-iname", "-path", "-ipath", "-wholename", "-regex", "-type", "-mtime", "-mmin", "-newer",
                     "-size", "-maxdepth", "-mindepth"}
_FIND_BARE_TESTS = {"-empty", "-prune", "-o", "-or", "-a", "-and", "-not", "!", "(", ")"}
_RM_FLAGS = {"-r", "-f", "-rf", "-fr", "-R"}


def find_preview(args: list[str], cwd: str, ctx: Ctx) -> list[str] | None:
    i = 0
    while i < len(args) and not args[i].startswith("-") and args[i] not in ("!", "(", ")"):
        i += 1
    paths, expr, action = args[:i], [], None
    while i < len(args):
        a = args[i]
        if a in _FIND_VALUE_TESTS and i + 1 < len(args):
            expr += args[i:i + 2]
            i += 2
        elif a in _FIND_BARE_TESTS:
            expr.append(a)
            i += 1
        elif a == "-delete" and action is None:
            action = a
            expr.append("-print0")
            i += 1
        elif a in ("-exec", "-execdir") and action is None and args[i + 1:i + 2] == ["rm"]:
            j = i + 2
            while j < len(args) and args[j] in _RM_FLAGS:
                j += 1
            if args[j:j + 1] != ["{}"] or args[j + 1:j + 2] not in ([";"], ["+"]):
                return None
            action = a
            expr.append("-print0")
            i = j + 2
        else:
            return None
    if action is None:
        return None
    # -delete 는 -depth 를 켜서 -prune 이 듣지 않는다 — 미리보기도 같은 순회로
    r = run(["find", *paths, *(["-depth"] if action == "-delete" else []), *expr], ctx, cwd=cwd)
    if r is None or r.returncode != 0:
        return None
    # normpath 금지 — 링크 뒤 '..' 를 글자로 지우면 다른 경로가 된다. 해소는 classify 의 normalize(realpath) 가 한다
    return [os.path.join(cwd, p) for p in r.stdout.split("\0") if p]


_DESKTOP_BIND = "/run/desktop/mnt/host/wsl/docker-desktop-bind-mounts/"


def _desktop_bind_source(src: str) -> str | None:
    """Docker Desktop(WSL) 변환 경로 → 원본 경로. 해시는 원본 경로의 sha256 이고, 이 배포판의
    /mnt/wsl/docker-desktop-bind-mounts/<배포판>/<해시> 에 원본 폴더가 바인드 마운트돼 있다(실측 2026-10-16)."""
    local = "/mnt/wsl/docker-desktop-bind-mounts/" + src[len(_DESKTOP_BIND):]
    import hashlib
    digest = src.rsplit("/", 1)[1]
    try:
        with open("/proc/self/mountinfo", encoding="utf-8", errors="surrogateescape") as f:
            rows = [[re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), x) for x in line.split()[2:5]] for line in f]
    except OSError:
        return None
    mine = next((r for r in rows if len(r) == 3 and r[2] == local), None)
    if mine is None:
        return None
    for dev, root, point in rows:
        # 같은 장치의 다른 마운트에서 원본 위치를 계산하고, sha256 이 맞는 것만 믿는다
        if dev == mine[0] and point != local and (mine[1] + "/").startswith(root.rstrip("/") + "/"):
            cand = os.path.join(point, mine[1][len(root.rstrip("/")):].lstrip("/")).rstrip("/") or "/"
            if hashlib.sha256(cand.encode("utf-8", "surrogateescape")).hexdigest() == digest:
                return cand
    return None


def docker_container_info(container: str, ctx: Ctx) -> tuple[tuple[Mount, ...], str] | None:
    r = run(["docker", "inspect", "--type", "container", "--format", "{{json .}}", container], ctx)
    if r is None or r.returncode != 0:
        return None
    try:
        info = json.loads(r.stdout)
        host = info.get("HostConfig") or {}
        # 요청한 원본 바인드 경로(목적지별). Docker Desktop(WSL)은 .Mounts 의 Source 를 가끔
        # /run/desktop/mnt/host/wsl/docker-desktop-bind-mounts/… 로 바꿔 보고한다(실측 간헐) — 그 경로로 사상하면 MISSING 으로 읽힌다
        asked = {m["Target"]: m["Source"] for m in host.get("Mounts") or () if m.get("Type") == "bind"}
        for b in host.get("Binds") or ():
            src, _, rest = b.partition(":")
            if src.startswith("/"):
                asked[rest.split(":")[0]] = src
        mounts = []
        for m in info.get("Mounts") or ():
            kind, dst = m.get("Type"), m.get("Destination")
            if kind == "volume":
                mounts.append(Mount(m["Name"], dst, kind))
            elif kind == "bind":
                src = asked.get(dst, m["Source"])
                if src.startswith(_DESKTOP_BIND):
                    src = _desktop_bind_source(src)
                    if src is None:
                        return None   # 호스트 경로를 확정할 수 없다
                mounts.append(Mount(src, dst, kind))
        return tuple(mounts), info["Config"]["WorkingDir"]
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def compose_container_id(service: str, project_dir: str, project: str | None, ctx: Ctx) -> str | None:
    cmd = ["docker", "compose", "--project-directory", project_dir, *(["-p", project] if project else []), "ps", "-q", service]
    # compose 파일은 cwd 에서 찾는다 — --project-directory 만으로는 파일 위치가 바뀌지 않는다
    r = run(cmd, ctx, cwd=project_dir)
    if r is None or r.returncode != 0:
        return None
    return next(iter(r.stdout.split()), None)


def docker_volume_created(name: str, ctx: Ctx) -> float | None:
    r = run(["docker", "volume", "inspect", "--format", "{{.CreatedAt}}", name], ctx)
    if r is None or r.returncode != 0:
        return None
    # 3.10 의 fromisoformat 은 'Z' 와 6자리 아닌 소수를 못 읽는다
    m = re.fullmatch(r"(.+T\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)?", r.stdout.strip())
    if m is None:
        return None
    tz = "+00:00" if m.group(3) in (None, "Z") else m.group(3)
    from datetime import datetime
    try:
        return datetime.fromisoformat(f"{m.group(1)}.{(m.group(2) or '')[:6].ljust(6, '0')}{tz}").timestamp()
    except ValueError:
        return None


def docker_volumes(selector: str, value: str | None, ctx: Ctx) -> list[str] | None:
    if selector == "compose-project" and not value:
        return None   # 프로젝트를 모르면 목록을 확정할 수 없다 — 빈 목록은 허용으로 읽힌다
    flt = {"dangling": "dangling=true", "compose-project": f"label=com.docker.compose.project={value}"}[selector]
    r = run(["docker", "volume", "ls", "-q", "-f", flt], ctx)
    if r is None or r.returncode != 0:
        return None
    return r.stdout.split()
