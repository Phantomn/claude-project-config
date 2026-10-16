"""bash-guard 대상 분류 기반: 세션 시각·생성 시각·정규화·임시 루트·보호 이름·스위치 값 (spec §3.4, §3.9)."""
from __future__ import annotations

import functools
import json
import os
import re
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace

from ledger import (
    KIND_CREATED,
    KIND_PRE_DIRTY,
    KIND_PRE_SESSION,
    KIND_TOUCHED,
    Entry,
    Ledger,
)


@dataclass
class Ctx:
    environ: Mapping[str, str]
    session_id: str | None
    session_start: float | None
    ledger: Ledger
    deadline: float  # time.monotonic() 기준

    def remaining(self) -> float:
        return self.deadline - time.monotonic()


FIXED_SCRATCH_ROOTS: tuple[str, ...] = ("/tmp", "/var/tmp")
WIN_TEMP_PATTERN = "/mnt/c/Users/*/AppData/Local/Temp"
# '*' 를 한 경로 구성요소로만 맞춘다(fnmatch 의 '*' 는 '/' 도 넘어 임의 깊이 폴더까지 임시로 본다)
_WIN_TEMP_RE = re.compile(re.escape(WIN_TEMP_PATTERN).replace(r"\*", "[^/]+"))
MODE_RANK = {"off": 0, "shadow": 1, "on": 2}
_ENV_EXAMPLES = {".env.example", ".env.sample", ".env.template"}
_LOCAL_SUFFIXES = (".local.json", ".local.yaml", ".local.yml", ".local.toml")
_KEY_PREFIXES = ("id_rsa", "id_ed25519", "id_ecdsa", "credentials")
_SECRET_DIRS = {".ssh", ".gnupg", ".aws"}
_TEXT = {"encoding": "utf-8", "errors": "surrogateescape"}


def make_ctx(payload: dict, environ: Mapping[str, str], budget: float) -> Ctx:
    deadline = time.monotonic() + budget
    return Ctx(environ, payload.get("session_id") or None,
               session_start(payload.get("transcript_path"), environ), Ledger(environ), deadline)


def session_start(transcript_path: str | None, environ: Mapping[str, str]) -> float | None:
    if not transcript_path:
        return None
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


def repo_root(path: str, environ: Mapping[str, str]) -> str | None:
    p = os.path.abspath(path)
    while True:
        if os.path.lexists(os.path.join(p, ".git")):
            break
        if p == "/":
            return None
        p = os.path.dirname(p)
    home = environ.get("HOME")
    if p == "/" or (home and os.path.realpath(home) == os.path.realpath(p)):
        return None
    return p


def switch_mode(path: str | None, environ: Mapping[str, str]) -> str:
    root = repo_root(path, environ) if path else None
    if root is None:
        return "off"
    for name in ("settings.local.json", "settings.json"):
        try:
            with open(os.path.join(root, ".claude", name), encoding="utf-8") as f:
                env = json.load(f).get("env")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(env, dict) and "HARNESS_BASH_GUARD" in env:
            v = env["HARNESS_BASH_GUARD"]
            return v if isinstance(v, str) and v in MODE_RANK else "off"
    return "off"


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
    cand = {p for p in paths if b.get(p, 0.0) >= start}
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
    near = {p: _nearest_git(p, cache) for p in paths}
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
        start, b = ctx.session_start, births([p], ctx).get(p)
        if start is not None and b is not None and b < start:
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
