"""bash-guard 정책: 명령 단위마다 거부 사유(Finding)를 낸다 (spec §3.5). 1부 — 삭제·덮어쓰기·디스크·시스템·권한."""
from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, replace

from shell_parse import (
    _COMPOSE_GLOBAL,
    _DOCKER_GLOBAL,
    LexError,
    Segment,
    Word,
    _drop,
    _opts,
    expand,
    literal_args,
)
from target_class import (
    GIT_TRACKED,
    IGNORED_ARTIFACT,
    MISSING,
    PRESERVED,
    PROTECTED_NAME,
    SCRATCH,
    SESSION_NEW,
    UNRESOLVED,
    Ctx,
    classify,
    find_preview,
    git_dirty,
    in_workspace,
    is_scratch_root,
    is_session_change,
    normalize,
)

SYSTEM_ROOTS = ("/etc", "/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/boot")
BENIGN_DEVICES = ("/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty", "/dev/fd/")
DEVICE_EXEMPT = BENIGN_DEVICES + ("/dev/shm/",)

KIND_TEXT: dict[str, str] = {
    UNRESOLVED: "대상을 확정할 수 없다",
    PROTECTED_NAME: "보호 대상 파일(비밀·설정·.git)",
    GIT_TRACKED: "git 이 추적하는 파일",
    PRESERVED: "세션 전부터 있던 유일본",
    "DIRTY": "커밋 안 된 수정이 있다",
    "SYSTEM": "호스트 시스템 경로",
    "OUTSIDE_WORKSPACE": "작업 영역(프로젝트·임시 폴더) 밖",
    "DEFAULT_BRANCH": "기본 브랜치 원격 이력 덮어쓰기",
    "REFLOG": "reflog 복구 경로 삭제",
    "OLD_STASH": "세션 전 보관본",
    "OLD_VOLUME": "기존 Docker 볼륨(데이터)",
    "UNPUSHED": "어디에도 남지 않는 커밋",
}

ADV_GIT_RM = "`git rm <경로>` 로 삭제하라(변경 내역에 남아 검토·복구 가능)"
ADV_PRESERVED = "세션 전부터 있던 유일본이다. 정말 지워야 하면 사용자에게 요청하라"
ADV_UNRESOLVED = "대상을 리터럴 경로로, 범위를 좁혀 다시 실행하라"
ADV_XARGS = "`find … -delete` 나 리터럴 경로를 써라"
ADV_SCRATCH_ROOT = "자기 세션 폴더로 범위를 좁혀라"
ADV_DIRTY = "먼저 커밋하거나 `git stash` 하라"
# spec §3.5 디스크·시스템·권한 표에는 대안 문구가 없다 — 아래 셋은 이 구현의 문구
ADV_SYSTEM = "호스트 시스템 경로다. 필요하면 사용자에게 요청하라"
ADV_DISK = "장치에 쓰지 말고 작업 영역 안의 이미지 파일을 써라. 필요하면 사용자에게 요청하라"
ADV_WORKSPACE = "작업 영역(프로젝트·임시 폴더) 안으로 범위를 좁혀라"

OP_DELETE, OP_OVERWRITE, OP_DISK, OP_SYSTEM, OP_RPERM = "삭제", "덮어쓰기", "디스크 쓰기", "시스템 경로 쓰기", "재귀 권한 변경"
DELETE, OVERWRITE, MKFS, PERM, RPERM = "delete", "overwrite", "mkfs", "perm", "rperm"
_ALLOWED = {MISSING, SCRATCH, SESSION_NEW, IGNORED_ARTIFACT}
_XARGS_LABEL = "(xargs 입력)"


@dataclass(frozen=True)
class Finding:
    op: str
    target: str
    kind: str
    advice: str

    def reason(self) -> str:
        return f"거부: {self.op} {self.target} — {KIND_TEXT[self.kind]}. 대안: {self.advice}"


@dataclass(frozen=True)
class Job:
    """판정할 작업 하나: 규칙과 확정된 대상 경로들(None = 확정 불가)."""
    op: str
    rule: str
    label: str                 # 확정 못 할 때 사유에 쓰는 원문
    paths: list[str] | None
    trailing: bool = False     # 원문 끝 '/' — 링크면 링크 대상 폴더(spec §3.4 정규화 4)
    advice: str = ADV_UNRESOLVED


# ---- 인자 해석 ----

def _args(seg: Segment, values: frozenset[str] = frozenset()) -> tuple[set[str], dict[str, Word], list[Word]]:
    """GNU 식 옵션(어디에 있어도 옵션, `--` 뒤는 모두 피연산자). (플래그, 값 옵션, 피연산자)."""
    flags: set[str] = set()
    vals: dict[str, Word] = {}
    ops: list[Word] = []
    a, i, opts = seg.argv[1:], 0, True
    while i < len(a):
        w, s = a[i], a[i].literal()
        i += 1
        if not opts or s == "-" or not s.startswith("-"):
            ops.append(w)
        elif s == "--":
            opts = False
        elif s.startswith("--"):
            k, eq, _ = s.partition("=")
            flags.add(k)
            if k in values:
                if eq:
                    vals[k] = _drop(w, len(k) + 1)
                elif i < len(a):
                    vals[k], i = a[i], i + 1
        else:
            for n in range(1, len(s)):
                o = "-" + s[n]
                flags.add(o)
                if o in values:
                    if n + 1 < len(s):
                        vals[o] = _drop(w, n + 1)
                    elif i < len(a):
                        vals[o], i = a[i], i + 1
                    break
    return flags, vals, ops


def _scratch_glob(word: Word, paths: list[str], ctx: Ctx) -> bool:
    # 임시 루트 바로 아래 와일드카드는 다른 세션·프로세스 파일까지 지운다(spec §3.4 임시 루트 ★)
    return any(not p.quote and any(c in p.text for c in "*?[") for p in word.parts) and \
        any(is_scratch_root(os.path.realpath(os.path.dirname(x)), ctx) for x in paths)


def _job(op: str, rule: str, word: Word, seg: Segment, ctx: Ctx | None, advice: str = ADV_UNRESOLVED) -> Job:
    paths = expand(word, seg)
    if paths and ctx is not None and _scratch_glob(word, paths, ctx):
        paths, advice = None, ADV_SCRATCH_ROOT
    return Job(op, rule, word.literal(), paths, word.literal().endswith("/"), advice)


def _xargs(op: str, rule: str, advice: str = ADV_UNRESOLVED) -> Job:
    return Job(op, rule, _XARGS_LABEL, None, advice=advice)


# ---- 처리기: 명령 이름 → 판정할 작업들 (ctx None = 판정 대상 여부만, 조회 없음) ----

def _delete(values: frozenset[str] = frozenset()) -> Callable[[Segment, Ctx | None], list[Job]]:
    def h(seg: Segment, ctx: Ctx | None) -> list[Job]:
        if seg.via_xargs:
            return [_xargs(OP_DELETE, DELETE, ADV_XARGS)]
        return [_job(OP_DELETE, DELETE, w, seg, ctx) for w in _args(seg, values)[2]]
    return h


def _find(seg: Segment, ctx: Ctx | None) -> list[Job]:
    a = literal_args(seg)
    if "-delete" not in a and not any(x in ("-exec", "-execdir") and a[i + 1:i + 2] == ["rm"] for i, x in enumerate(a)):
        return []
    n = next((i for i, x in enumerate(a) if x.startswith("-") or x in ("!", "(", ")")), len(a))
    starts = [expand(w, seg) for w in seg.argv[1:1 + n]]   # 시작 경로만 셸처럼 확장 — 표현식의 '*.py' 는 find 가 본다
    paths = None
    if ctx is not None and seg.cwd is not None and not seg.via_xargs and None not in starts:
        paths = find_preview([p for s in starts for p in s] + a[n:], seg.cwd, ctx)  # type: ignore[union-attr]
    return [Job(OP_DELETE, DELETE, " ".join(["find", *a]), paths)]


def _into(seg: Segment, ctx: Ctx | None, dest: Word, srcs: list[Word], force_dir: bool, no_dir: bool,
          contents: bool = False) -> Job:
    """목적지 덮어쓰기: 목적지가 폴더면 `폴더/원본이름` 들. contents = rsync 의 `원본/` (안의 항목들이 들어감)."""
    d = _job(OP_OVERWRITE, OVERWRITE, dest, seg, ctx)
    if d.paths is None or len(d.paths) != 1:
        return replace(d, paths=None)
    t = d.paths[0]
    if no_dir or not (force_dir or os.path.isdir(t)):
        return d
    names: list[str] = []
    for s in srcs:
        ps = expand(s, seg)
        if ps is None:
            return replace(d, paths=None)
        for x in ps:
            if contents and x.endswith("/"):
                try:
                    names += os.listdir(x)
                except OSError:
                    return replace(d, paths=None)
            else:
                names.append(os.path.basename(x.rstrip("/")))
    return replace(d, paths=[os.path.join(t, n) for n in names])


_COPY_VALUES = frozenset({"-t", "--target-directory", "-S", "--suffix", "-m", "--mode", "-o", "--owner", "-g", "--group"})


def _copy(seg: Segment, ctx: Ctx | None) -> list[Job]:
    flags, vals, ops = _args(seg, _COPY_VALUES if seg.name == "install" else _COPY_VALUES - {"-m", "-o", "-g"})
    if seg.name == "install" and flags & {"-d", "--directory"}:
        return []
    if seg.via_xargs:
        return [_xargs(OP_OVERWRITE, OVERWRITE)]
    tdir = vals.get("-t") or vals.get("--target-directory")
    if tdir is None:
        if len(ops) < 2:
            return []
        tdir, ops, force = ops[-1], ops[:-1], False
    else:
        force = True
    return [_into(seg, ctx, tdir, ops, force, bool(flags & {"-T", "--no-target-directory"}))]


_RSYNC_VALUES = frozenset({"-e", "--rsh", "-f", "--filter", "--exclude", "--include", "--exclude-from", "--include-from",
                           "--files-from", "-T", "--temp-dir", "--backup-dir", "--suffix", "--log-file", "--chmod",
                           "--chown", "-B", "--block-size", "--link-dest", "--compare-dest", "--copy-dest", "--timeout",
                           "--bwlimit", "--max-size", "--min-size", "--port", "--password-file", "-M", "--remote-option"})
_REMOTE = re.compile(r"[^/]*:")


def _rsync(seg: Segment, ctx: Ctx | None) -> list[Job]:
    flags, _, ops = _args(seg, _RSYNC_VALUES)
    if seg.via_xargs:
        return [_xargs(OP_OVERWRITE, OVERWRITE)]
    if len(ops) < 2 or _REMOTE.match(ops[-1].literal()):
        return []   # 원격 목적지는 이 호스트의 손실이 아니다
    if any(f.startswith("--del") for f in flags):
        # --delete* 는 목적지 폴더에서 원본에 없는 것을 지운다 — 폴더째 삭제 규칙
        return [replace(_job(OP_DELETE, DELETE, ops[-1], seg, ctx), trailing=True)]
    return [_into(seg, ctx, ops[-1], ops[:-1], False, False, contents=True)]


def _tee(seg: Segment, ctx: Ctx | None) -> list[Job]:
    flags, _, ops = _args(seg)
    if flags & {"-a", "--append"}:
        return []
    return [_job(OP_OVERWRITE, OVERWRITE, w, seg, ctx) for w in ops]


def _truncate(seg: Segment, ctx: Ctx | None) -> list[Job]:
    if seg.via_xargs:
        return [_xargs(OP_OVERWRITE, OVERWRITE)]
    return [_job(OP_OVERWRITE, OVERWRITE, w, seg, ctx) for w in _args(seg, frozenset({"-s", "--size", "-r", "--reference"}))[2]]


def _dd(seg: Segment, ctx: Ctx | None) -> list[Job]:
    of = [w for w in seg.argv[1:] if w.literal().startswith("of=")]
    return [_job(OP_OVERWRITE, OVERWRITE, _drop(of[-1], 3), seg, ctx)] if of else []


def _mkfs(seg: Segment, ctx: Ctx | None) -> list[Job]:
    # 값 옵션 표는 mkfs 종류마다 달라 두지 않는다 — 값(라벨 등)도 대상으로 보면 작업 영역 밖일 때만 과보호
    return [_job(OP_DISK, MKFS, w, seg, ctx) for w in _args(seg)[2] if not w.literal().isdigit()]


_MODE = re.compile(r"[0-7]+$|[ugoa]*[-+=]")


def _perm(seg: Segment, ctx: Ctx | None) -> list[Job]:
    flags, vals, ops = _args(seg, frozenset({"--reference", "--from"}))
    if "--reference" not in vals and ops and (seg.name != "chmod" or _MODE.match(ops[0].literal())):
        ops = ops[1:]   # 모드·소유자 인자
    if flags & {"-R", "--recursive"}:
        if seg.via_xargs:
            return [_xargs(OP_RPERM, RPERM)]
        return [_job(OP_RPERM, RPERM, w, seg, ctx) for w in ops]
    # 재귀 아닌 권한 변경은 시스템 경로만 판정(spec §3.5)
    jobs = [_job(OP_SYSTEM, PERM, w, seg, ctx) for w in ops]
    return [replace(j, paths=s) for j in jobs if (s := [p for p in j.paths or () if _system(p, True)])]


HANDLERS: dict[str, Callable[[Segment, Ctx | None], list[Job]]] = {
    "rm": _delete(), "unlink": _delete(),
    "shred": _delete(frozenset({"-n", "--iterations", "-s", "--size", "--random-source"})),
    "find": _find,
    "cp": _copy, "mv": _copy, "install": _copy, "rsync": _rsync,
    "tee": _tee, "truncate": _truncate, "dd": _dd, "mkfs": _mkfs,
    "chmod": _perm, "chown": _perm, "chgrp": _perm,
}


def _redirects(seg: Segment, ctx: Ctx | None) -> list[Job]:
    out = []
    for r in seg.redirects:
        lit = r.target.literal() if r.target is not None else ""
        # `>& 파일` 은 `&>` 와 같다(숫자·'-' 면 fd 복제). `>>`·`&>>` 는 추가라 제외
        if r.target is not None and (r.op in (">", ">|", "&>") or (r.op == ">&" and not lit.isdigit() and lit != "-")):
            out.append(_job(OP_OVERWRITE, OVERWRITE, r.target, seg, ctx))
    return out


def _host_jobs(seg: Segment, ctx: Ctx | None) -> list[Job]:
    h = HANDLERS.get("mkfs" if seg.name.startswith("mkfs") else seg.name)
    out = []
    for j in _redirects(seg, ctx) + (h(seg, ctx) if h else []):
        if j.rule == OVERWRITE and j.paths is not None:
            keep = [p for p in j.paths if not p.startswith(BENIGN_DEVICES)]   # /dev/null 등은 손실 없음
            if not keep:
                continue
            j = replace(j, paths=keep)
        out.append(j)
    return out


# ---- 판정 ----

def _system(p: str, follow: bool, trailing: bool = False) -> bool:
    # 삭제는 링크 자체를(normalize), 쓰기·권한은 링크가 가리키는 곳을 본다
    q = os.path.realpath(p) if follow else normalize(p, trailing)
    return any(q == r or q.startswith(r + "/") for r in SYSTEM_ROOTS)


def _device(p: str) -> bool:
    return any(q.startswith("/dev/") and not q.startswith(DEVICE_EXEMPT) for q in (p, os.path.realpath(p)))


def _unresolved_advice(detail: str, default: str) -> str:
    # target_class 의 확정 불가 사유는 '… — <대안>' 형식이면 그 대안(임시 루트 자체·폴더 상한·시간 초과)
    return detail.partition(" — ")[2] or default


def _judge_path(j: Job, p: str, ctx: Ctx) -> Finding | None:
    if _system(p, j.rule != DELETE, j.trailing):
        return Finding(OP_SYSTEM, p, "SYSTEM", ADV_SYSTEM)
    if j.rule == PERM:
        return None
    if j.rule == RPERM:
        return None if in_workspace(p, ctx) else Finding(j.op, p, "OUTSIDE_WORKSPACE", ADV_WORKSPACE)
    if j.rule == MKFS or (j.rule == OVERWRITE and _device(p)):
        return None if j.rule == MKFS and in_workspace(p, ctx) else Finding(OP_DISK, p, "OUTSIDE_WORKSPACE", ADV_DISK)
    c = classify(p, ctx, j.trailing)
    target = c.path or p
    if c.kind in _ALLOWED:
        return None
    if c.kind == UNRESOLVED:
        return Finding(j.op, target, UNRESOLVED, _unresolved_advice(c.detail, j.advice))
    if c.kind in (PROTECTED_NAME, PRESERVED):
        return Finding(j.op, target, c.kind, ADV_PRESERVED)
    # GIT_TRACKED
    if j.rule == DELETE:
        return Finding(j.op, target, GIT_TRACKED, ADV_GIT_RM)
    repo = target if os.path.isdir(target) and not os.path.islink(target) else os.path.dirname(target)
    dirty = git_dirty(repo, [target], ctx)
    if dirty is None:   # 조회 실패는 허용이 아니라 확정 불가
        return Finding(j.op, target, UNRESOLVED, j.advice)
    if all(is_session_change(d, ctx) for d in dirty):
        return None
    return Finding(j.op, target, "DIRTY", ADV_DIRTY)


def _judge(jobs: list[Job], ctx: Ctx) -> list[Finding]:
    out: list[Finding] = []
    for j in jobs:
        if j.paths is None:
            out.append(Finding(j.op, j.label, UNRESOLVED, j.advice))
            continue
        out += [f for p in j.paths if (f := _judge_path(j, p, ctx)) is not None]
    return out


def evaluate(seg: Segment, ctx: Ctx) -> list[Finding]:
    if seg.context.kind != "host":
        return []   # 컨테이너 문맥(spec §3.6) — Task 8
    return _judge(_host_jobs(seg, ctx), ctx)


def judged_targets(seg: Segment, ctx: Ctx) -> list[str]:
    if seg.context.kind != "host":
        return []   # 바인드 마운트의 호스트 경로 — Task 8
    return [p for j in _host_jobs(seg, ctx) for p in j.paths or ()]


# ---- 판정 대상 여부 (spec §3.8 시간 예산 — 조회 없이 명령 모양만) ----

_GIT_GLOBAL_VALUES = ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env")


def _short(r: list[str]) -> str:
    return "".join(x[1:] for x in r if x.startswith("-") and not x.startswith("--"))


def _git_judged(seg: Segment) -> bool:
    a, i = literal_args(seg), 0
    while i < len(a) and a[i].startswith("-"):
        i += 2 if a[i] in _GIT_GLOBAL_VALUES else 1
    if i >= len(a):
        return False
    sub, r = a[i], a[i + 1:]
    words = [x for x in r if not x.startswith("-")]
    first = words[0] if words else ""
    if sub == "reset":
        return "--hard" in r
    if sub == "checkout":
        return bool({"-f", "--force", "--", "."} & set(r)) or (
            seg.cwd is not None and any(os.path.lexists(os.path.join(seg.cwd, x)) for x in words))
    if sub == "switch":
        return bool({"--force", "--discard-changes"} & set(r)) or "f" in _short(r)
    if sub == "restore":
        return not (bool({"--staged", "-S"} & set(r)) and not {"--worktree", "-W"} & set(r))
    if sub == "rm":
        return "--force" in r or "f" in _short(r)
    if sub == "worktree":
        return first == "remove"
    if sub == "stash":
        return first in ("drop", "clear")
    if sub == "branch":
        s = _short(r)
        return "D" in s or (("--delete" in r or "d" in s) and ("--force" in r or "f" in s))
    if sub == "reflog":
        return first in ("expire", "delete")
    if sub == "gc":
        return any(x.startswith("--prune") for x in r)
    return sub in ("clean", "push", "prune", "filter-branch", "filter-repo")


def _docker_judged(seg: Segment) -> bool:
    a, compose, i = seg.argv, seg.name == "docker-compose", 1
    try:
        if not compose:
            i, _ = _opts(a, 1, _DOCKER_GLOBAL)
            if i < len(a) and a[i].literal() == "compose":
                compose, i = True, i + 1
        if compose:
            i, _ = _opts(a, i, _COMPOSE_GLOBAL)
    except LexError:
        return True   # 모르는 전역 옵션 — 판정 대상으로(보수적)
    w = [x.literal() for x in a[i:]]
    if compose:
        return w[:1] == ["down"] and any(x == "--volumes" or (x.startswith("-") and not x.startswith("--") and "v" in x)
                                         for x in w[1:])
    if w[:1] == ["volume"]:
        return w[1:2] in (["rm"], ["remove"], ["prune"])
    return w[:2] == ["system", "prune"] and "--volumes" in w


def is_judged_op(seg: Segment) -> bool:
    return bool(_host_jobs(seg, None)) or (seg.name == "git" and _git_judged(seg)) or (
        seg.name in ("docker", "podman", "docker-compose") and _docker_judged(seg))
