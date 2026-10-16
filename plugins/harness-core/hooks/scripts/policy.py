"""bash-guard 정책: 명령 단위마다 거부 사유(Finding)를 낸다 (spec §3.5·§3.6). 삭제·덮어쓰기·디스크·시스템·권한·git·Docker."""
from __future__ import annotations

import glob
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from fnmatch import fnmatch

from shell_parse import (
    _COMPOSE_GLOBAL,
    _DOCKER_GLOBAL,
    HOLE,
    LexError,
    Mount,
    Part,
    Segment,
    Word,
    _cmd_name,
    _drop,
    _expand,
    _opts,
    _resolve_dir,
    _strip_all,
    expand,
    expand_hole,
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
    SEVERITY,
    UNRESOLVED,
    Ctx,
    _git,
    before_session,
    classify,
    compose_container_id,
    docker_container_info,
    docker_volume_created,
    docker_volumes,
    find_preview,
    git_branch_info,
    git_clean_preview,
    git_default_branch,
    git_dirty,
    git_extra_items,
    git_remote_names,
    git_stash_created,
    git_upstream_branch,
    in_workspace,
    is_linked_worktree_root,
    is_scratch,
    is_scratch_root,
    is_session_change,
    normalize,
    protected_name,
)

SYSTEM_ROOTS = ("/etc", "/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/boot")
BENIGN_DEVICES = ("/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty", "/dev/fd/")
# /dev/tcp·/dev/udp 는 bash 가 소켓으로 여는 가상 경로라 디스크가 아니다
DEVICE_EXEMPT = BENIGN_DEVICES + ("/dev/shm/", "/dev/tcp/", "/dev/udp/")

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
ADV_GIT_DIRTY = "먼저 `git stash push -u` 하거나 커밋하라"
ADV_WORKTREE = "worktree 안에 유일본이 있다. 옮기거나 사용자에게 요청하라"
ADV_DEFAULT_BRANCH = "기능 브랜치로 push 하고 PR 을 열어라"
ADV_UNPUSHED = "먼저 push 하거나 태그를 남겨라. 병합된 브랜치면 `git fetch` 뒤 다시 실행하라"
ADV_VOLUME = "기존 볼륨(데이터)이다. 사용자에게 요청하라"
# spec §3.5 git 표의 stash·reflog 행과 기본 브랜치 추정에는 대안 문구가 없다 — 아래 셋은 이 구현의 문구
ADV_STASH = "세션 전 보관본이다. 지워야 하면 사용자에게 요청하라"
ADV_REFLOG = "reflog 는 실수 복구 경로다. 필요하면 사용자에게 요청하라"
ADV_DEFAULT_GUESS = "기본 브랜치(main·master 로 추정)에 강제·삭제 push 는 거부된다. 정말 필요하면 사용자에게 요청하라"

OP_DELETE, OP_OVERWRITE, OP_DISK, OP_SYSTEM, OP_RPERM = "삭제", "덮어쓰기", "디스크 쓰기", "시스템 경로 쓰기", "재귀 권한 변경"
OP_VOLUME = "docker 볼륨 삭제"
DELETE, OVERWRITE, MKFS, PERM, RPERM = "delete", "overwrite", "mkfs", "perm", "rperm"
_PATH_RULES = (DELETE, OVERWRITE, MKFS, PERM, RPERM)
# 경로별 분류가 아니라 작업 단위로 판정하는 규칙(paths: None = 확정 불가, [] = 저장소 전체·경로 없음)
GIT_DIRTY, WORKTREE, CLEAN, STASH, BRANCH, PUSH, REFLOG, VOLUMES = (
    "git-dirty", "worktree", "clean", "stash", "branch", "push", "reflog", "volumes")
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
    repo: str | None = None    # git 규칙: 명령이 도는 폴더(-C 반영)
    args: tuple[str, ...] = ()  # git·docker 규칙: 판정에 쓰는 인자


# ---- 인자 해석 ----

_COMMON_LONGS = ("--help", "--version")
# 명령 → (모르는 긴 옵션일 때의 작업, 규칙, GNU 긴 옵션 전부). 표에 있는 명령만 접두 약어를 풀고 모르는 옵션을 확정 불가로 본다
_LONGS: dict[str, tuple[str, str, frozenset[str]]] = {
    "rm": (OP_DELETE, DELETE, frozenset(("--force", "--interactive", "--one-file-system", "--no-preserve-root",
                                         "--preserve-root", "--recursive", "--dir", "--verbose", *_COMMON_LONGS))),
    "unlink": (OP_DELETE, DELETE, frozenset(_COMMON_LONGS)),
    "shred": (OP_DELETE, DELETE, frozenset(("--force", "--iterations", "--random-source", "--size", "--remove", "--verbose",
                                            "--exact", "--zero", *_COMMON_LONGS))),
    "cp": (OP_OVERWRITE, OVERWRITE, frozenset((
        "--archive", "--attributes-only", "--backup", "--copy-contents", "--debug", "--dereference", "--force",
        "--interactive", "--link", "--no-clobber", "--no-dereference", "--preserve", "--no-preserve", "--parents",
        "--recursive", "--reflink", "--remove-destination", "--sparse", "--strip-trailing-slashes", "--suffix",
        "--symbolic-link", "--target-directory", "--no-target-directory", "--update", "--verbose",
        "--keep-directory-symlink", "--one-file-system", "--context", *_COMMON_LONGS))),
    "mv": (OP_OVERWRITE, OVERWRITE, frozenset((
        "--backup", "--debug", "--exchange", "--force", "--interactive", "--no-clobber", "--no-copy",
        "--strip-trailing-slashes", "--suffix", "--target-directory", "--no-target-directory", "--update", "--verbose",
        "--context", *_COMMON_LONGS))),
    "install": (OP_OVERWRITE, OVERWRITE, frozenset((
        "--backup", "--compare", "--debug", "--directory", "--group", "--mode", "--owner", "--preserve-timestamps",
        "--strip", "--strip-program", "--suffix", "--target-directory", "--no-target-directory", "--verbose",
        "--preserve-context", "--context", *_COMMON_LONGS))),
    "tee": (OP_OVERWRITE, OVERWRITE, frozenset(("--append", "--ignore-interrupts", "--output-error", *_COMMON_LONGS))),
    "truncate": (OP_OVERWRITE, OVERWRITE, frozenset(("--no-create", "--io-blocks", "--reference", "--size", *_COMMON_LONGS))),
}
_PERM_LONGS = ("--changes", "--dereference", "--no-dereference", "--no-preserve-root", "--preserve-root", "--quiet",
               "--silent", "--reference", "--recursive", "--verbose", *_COMMON_LONGS)
_LONGS.update({n: (OP_RPERM, RPERM, frozenset(_PERM_LONGS + (("--from",) if n == "chown" else ())))
               for n in ("chmod", "chown", "chgrp")})


class _BadOption(Exception):
    """모르는 긴 옵션·모호한 접두 — 값을 받는지 몰라 피연산자 경계를 확정할 수 없다."""


def _long(k: str, longs: frozenset[str] | None) -> str:
    # getopt_long 처럼 정확한 이름 또는 모호하지 않은 접두를 받는다
    if longs is None or k in longs:
        return k
    hit = [o for o in longs if o.startswith(k)]
    if len(hit) != 1:
        raise _BadOption(k)
    return hit[0]


def _args(seg: Segment, values: frozenset[str] = frozenset()) -> tuple[set[str], dict[str, Word], list[Word]]:
    """GNU 식 옵션(어디에 있어도 옵션, `--` 뒤는 모두 피연산자). (플래그, 값 옵션, 피연산자). 긴 옵션은 정식 이름으로."""
    longs = _LONGS[seg.name][2] if seg.name in _LONGS else None
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
            raw, eq, _ = s.partition("=")
            k = _long(raw, longs)
            flags.add(k)
            if k in values:
                if eq:
                    vals[k] = _drop(w, len(raw) + 1)
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


# 미확정 마지막 구성요소 자리에 넣는 없는 이름 — 분류가 MISSING(허용)이 된다
_HOLE_NAME = "bash-guard-hole-" + os.urandom(6).hex()


def _scratch_hole(word: Word, seg: Segment, ctx: Ctx) -> list[str] | None:
    """확정 접두가 임시 루트 아래 세션 폴더(SCRATCH)이고 미확정 요소가 마지막 구성요소 안에만 있으면 [그 자리의 대표 경로].
    정직한 실수 모델(spec §1.5) — 임시 폴더 안 한 구성요소를 다루는 명령이다. 접두 폴더 안·대상 이름이 보호 이름이면 None."""
    p = expand_hole(word, seg)
    if p is None or HOLE not in p:
        return None
    d, _, name = p.rpartition("/")
    if not d or HOLE in d:
        return None
    nd = normalize(d, True)
    target = os.path.join(nd, name.replace(HOLE, _HOLE_NAME))
    if not is_scratch(nd, ctx) or is_scratch_root(nd, ctx) or protected_name(target):
        return None
    return [target] if classify(d, ctx, True).kind == SCRATCH else None


def _job(op: str, rule: str, word: Word, seg: Segment, ctx: Ctx | None, advice: str = ADV_UNRESOLVED) -> Job:
    paths = expand(word, seg)
    if paths is None and ctx is not None:
        paths = _scratch_hole(word, seg, ctx)
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


_FIND_EXEC = ("-exec", "-execdir", "-ok", "-okdir")
_DELETERS = ("rm", "unlink", "shred")


def _find_deletes(seg: Segment) -> bool:
    a = seg.argv[1:]
    for i, w in enumerate(a):
        if w.literal() in _FIND_EXEC:
            j = next((k for k in range(i + 1, len(a)) if a[k].literal() in (";", "+")), len(a))
            # /bin/rm·sudo rm·\rm 도 rm — 해석기의 래퍼 벗기기와 같은 규칙
            if _cmd_name(_strip_all(a[i + 1:j], {}, seg.env)) in _DELETERS:
                return True
    return False


def _find(seg: Segment, ctx: Ctx | None) -> list[Job]:
    a = literal_args(seg)
    if "-delete" not in a and not _find_deletes(seg):
        return []
    # find_preview 는 '-delete' 와 '-exec|-execdir rm … {} ;|+' 만 받는다 — 그 밖의 삭제 형태(/bin/rm, -ok, shred …)는 None → 확정 불가
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
        if contents and _REMOTE.match(s.literal()):
            # rsync 원격 원본(첫 '/' 앞에 ':'): 'host:' 뒤 마지막 이름이 목적지 아래 이름. 끝 '/'·빈 경로·글롭·변수면
            # 안의 항목을 모르므로 목적지 폴더 자체를 덮어쓰기 규칙으로(폴더 분류 = 안의 가장 보호 쪽)
            name = os.path.basename(s.literal().split(":", 1)[1]).lstrip(":")
            if not name or any(c in name for c in "*?[$`"):
                return replace(d, paths=[t], trailing=True)
            names.append(name)
            continue
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


_COPY_VALUES = frozenset({"-t", "--target-directory", "-S", "--suffix", "-m", "--mode", "-o", "--owner", "-g", "--group",
                          "--no-preserve", "--sparse", "--strip-program"})


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


_GIT_GLOBAL_VALUES = ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env")

# 판정 행 하위명령의 긴 옵션 전부(`git <sub> -h`, git 2.43 실측). git 은 모호하지 않은 접두와 `--no-` 부정을 받으므로
# 이 표로 정식 이름으로 풀고, 모호하거나 표에 없으면 판정할 수 없다(git 도 모르는 옵션은 거부한다)
_GIT_LONGS: dict[str, frozenset[str]] = {k: frozenset(v.split() + ["help"]) for k, v in {
    "push": "all atomic branches delete dry-run exec follow-tags force force-if-includes force-with-lease mirror porcelain "
            "progress prune push-option quiet receive-pack recurse-submodules repo set-upstream signed tags thin verbose "
            "ipv4 ipv6 no-verify verify",
    "branch": "abbrev color column copy create-reflog delete edit-description force format ignore-case list move omit-empty "
              "points-at quiet recurse-submodules set-upstream-to show-current sort track unset-upstream verbose all "
              "contains merged no-contains no-merged remotes",
    "reset": "intent-to-add patch pathspec-file-nul pathspec-from-file quiet recurse-submodules hard keep merge mixed "
             "no-refresh refresh soft",
    "checkout": "conflict detach force guess ignore-other-worktrees ignore-skip-worktree-bits merge orphan overlay "
                "overwrite-ignore patch pathspec-file-nul pathspec-from-file progress quiet recurse-submodules track ours theirs",
    "switch": "conflict create detach discard-changes force force-create guess ignore-other-worktrees merge orphan "
              "overwrite-ignore progress quiet recurse-submodules track",
    "restore": "conflict ignore-skip-worktree-bits ignore-unmerged merge overlay patch pathspec-file-nul pathspec-from-file "
               "progress quiet recurse-submodules source staged worktree ours theirs",
    "rm": "cached dry-run force ignore-unmatch pathspec-file-nul pathspec-from-file quiet sparse",
    "clean": "dry-run force interactive quiet exclude",
    "gc": "aggressive auto cruft force keep-largest-pack prune quiet max-cruft-size",
    "worktree remove": "force",
    "stash drop": "quiet", "stash clear": "quiet",
}.items()}
_GIT_JUDGED_SUBS = {"reset", "checkout", "switch", "restore", "rm", "worktree", "clean", "stash", "branch", "reflog", "gc",
                    "prune", "filter-branch", "filter-repo", "push"}
# git 은 내장 명령과 같은 이름의 alias 를 무시한다 — 내장 명령은 alias 조회를 건너뛴다.
# 출처: `git --list-cmds=builtins`(git 2.43, 2026-10-16 실측)
_GIT_BUILTINS = frozenset((
    "add", "am", "annotate", "apply", "archive", "bisect", "blame", "branch", "bugreport", "bundle", "cat-file",
    "check-attr", "check-ignore", "check-mailmap", "check-ref-format", "checkout", "checkout--worker",
    "checkout-index", "cherry", "cherry-pick", "clean", "clone", "column", "commit", "commit-graph", "commit-tree",
    "config", "count-objects", "credential", "credential-cache", "credential-cache--daemon", "credential-store",
    "describe", "diagnose", "diff", "diff-files", "diff-index", "diff-tree", "difftool", "fast-export",
    "fast-import", "fetch", "fetch-pack", "fmt-merge-msg", "for-each-ref", "for-each-repo", "format-patch", "fsck",
    "fsck-objects", "fsmonitor--daemon", "gc", "get-tar-commit-id", "grep", "hash-object", "help", "hook",
    "index-pack", "init", "init-db", "interpret-trailers", "log", "ls-files", "ls-remote", "ls-tree", "mailinfo",
    "mailsplit", "maintenance", "merge", "merge-base", "merge-file", "merge-index", "merge-ours", "merge-recursive",
    "merge-recursive-ours", "merge-recursive-theirs", "merge-subtree", "merge-tree", "mktag", "mktree",
    "multi-pack-index", "mv", "name-rev", "notes", "pack-objects", "pack-redundant", "pack-refs", "patch-id",
    "pickaxe", "prune", "prune-packed", "pull", "push", "range-diff", "read-tree", "rebase", "receive-pack",
    "reflog", "remote", "remote-ext", "remote-fd", "repack", "replace", "rerere", "reset", "restore", "rev-list",
    "rev-parse", "revert", "rm", "send-pack", "shortlog", "show", "show-branch", "show-index", "show-ref",
    "sparse-checkout", "stage", "stash", "status", "stripspace", "submodule--helper", "switch", "symbolic-ref",
    "tag", "unpack-file", "unpack-objects", "update-index", "update-ref", "update-server-info", "upload-archive",
    "upload-archive--writer", "upload-pack", "var", "verify-commit", "verify-pack", "verify-tag", "version",
    "whatchanged", "worktree", "write-tree",
))


# diff 출력 옵션을 받는 하위명령 — `--output[=]<파일>` 은 그 파일을 덮어쓴다(git 2.43 실측: 공백 값도 받음)
_GIT_OUTPUT_SUBS = frozenset(("log", "diff", "show", "format-patch", "whatchanged", "diff-files", "diff-index", "diff-tree",
                              "range-diff"))


def _git_output(seg: Segment, repo: str | None, rest: list[Word], k: int) -> list[Job]:
    out = []
    for n, w in enumerate(rest[:k]):
        x = w.literal()
        name, eq, _ = x[2:].partition("=")
        # git 2.43 은 접두 약어(--outp)를 거부하지만 버전마다 다를 수 있어 접두도 덮어쓰기로 본다
        if not x.startswith("--") or not name or not "output".startswith(name):
            continue
        v = _drop(w, len(name) + 3) if eq else (rest[n + 1] if n + 1 < len(rest) else None)
        if v is not None:
            out.append(Job(OP_OVERWRITE, OVERWRITE, v.literal(), _expand(v, seg.env, repo) if repo else None))
    return out


def _short(r: list[str]) -> str:
    return "".join(x[1:] for x in r if x.startswith("-") and not x.startswith("--"))


def _git_long(x: str, names: frozenset[str]) -> str:
    k, eq, v = x[2:].partition("=")
    cand = names | {"no-" + n for n in names}
    if k not in cand:   # 정확한 이름이 접두보다 우선(`--force` ≠ `--force-with-lease`)
        hit = [c for c in cand if c.startswith(k)] if k else []
        if len(hit) != 1:
            raise _BadOption(x)
        k = hit[0]
    return "--" + k + eq + v


def _git_cmd(seg: Segment) -> tuple[str | None, str, list[Word], dict[str, str]] | None:
    """(명령이 도는 폴더 | None=확정 불가, 하위명령, 하위명령 뒤 인자, 같은 줄 `-c alias.X=값`)."""
    a, i, repo = seg.argv, 1, seg.cwd
    aliases: dict[str, str] = {}
    while i < len(a) and a[i].literal().startswith("-"):
        x = a[i].literal()
        if x == "-C" and i + 1 < len(a):
            r = _expand(a[i + 1], seg.env, repo)
            repo = os.path.normpath(r[0]) if r and len(r) == 1 else None
        elif x == "-c" and i + 1 < len(a):
            key, _, val = a[i + 1].literal().partition("=")
            if key.lower().startswith("alias."):
                aliases[key[6:].lower()] = val
        elif x.startswith(("--git-dir", "--work-tree")):
            repo = None   # 작업 트리를 따로 가리키면 판정할 저장소를 확정할 수 없다
        i += 2 if x in _GIT_GLOBAL_VALUES else 1
    if i >= len(a):
        return None
    return repo, a[i].literal(), a[i + 1:], aliases


def _git_handler(seg: Segment, ctx: Ctx | None, exists: Callable[[str], bool] = os.path.lexists) -> list[Job]:
    """spec §3.5 git 표의 판정 행. 표 밖의 하위명령(rebase·amend·update-ref·stash pop 등)은 작업 없음 = 허용.

    exists: 경로 인자가 실재하는지(checkout 의 경로/브랜치 구분) — 컨테이너 문맥은 호스트로 사상해 본다."""
    parsed = _git_cmd(seg)
    if parsed is None:
        return []
    repo, sub, rest, aliases = parsed
    label = " ".join(["git", *literal_args(seg)])
    if sub not in _GIT_JUDGED_SUBS and sub not in _GIT_BUILTINS:
        val = aliases.get(sub.lower())
        if val is None and ctx is not None and repo:
            val = (_git(repo, ["config", "--get", f"alias.{sub}"], ctx) or "").strip() or None
        if val is not None:
            if val.startswith("!"):   # 셸 alias — 무엇을 실행할지 해석하지 않는다
                return [Job(f"git {sub}", GIT_DIRTY, label, None, repo=repo)]
            head = val.split()
            # 한 단계만 펼친다(alias 의 alias 는 git 도 따로 푼다 — 여기서는 표 밖이면 허용)
            sub, rest = (head[0] if head else ""), [Word((Part(x, "'"),)) for x in head[1:]] + rest
    r = [w.literal() for w in rest]
    k = r.index("--") if "--" in r else len(r)
    pre, post = rest[:k], rest[k + 1:]
    words = [w for w in pre if not w.literal().startswith("-")]
    first = words[0].literal() if words else ""
    names = _GIT_LONGS.get(f"{sub} {first}", _GIT_LONGS.get(sub))
    if names is not None:
        try:
            r = [_git_long(x, names) if n < k and x.startswith("--") and x != "--" else x for n, x in enumerate(r)]
        except _BadOption:
            return [Job(f"git {sub}", GIT_DIRTY, label, None, repo=repo)]
    s = _short(r[:k])

    def job(rule: str, paths: list[str] | tuple[()] | None = (), args: tuple[str, ...] = (), op: str = f"git {sub}") -> Job:
        return Job(op, rule, repo or label, None if repo is None or paths is None else list(paths), repo=repo, args=args)

    def specs(ws: list[Word]) -> list[str] | None:
        # pathspec 은 -C 폴더 기준이고, 하나라도 확정할 수 없으면 범위 전체를 모른다
        out: list[str] = []
        for w in ws:
            e = _expand(w, seg.env, repo) if repo else None
            if e is None:
                return None
            out += e
        return out

    def dirty(ws: list[Word] | None) -> list[Job]:   # ws None = 저장소 전체
        return [Job(f"git {sub}", GIT_DIRTY, repo or label, None if repo is None else specs(ws or []), repo=repo)]

    if sub in _GIT_OUTPUT_SUBS:
        return _git_output(seg, repo, rest, k)
    force = "--force" in r or "f" in s
    if sub == "reset":
        return dirty(None) if "--hard" in r else []
    if sub == "checkout":
        paths = post or [w for w in words if repo and exists(os.path.join(repo, w.literal()))]
        return dirty(paths) if paths else dirty(None) if force else []
    if sub == "switch":
        return dirty(None) if force or "--discard-changes" in r else []
    if sub == "restore":
        if ("--staged" in r or "S" in s) and not ("--worktree" in r or "W" in s):
            return []
        paths = post + [w for n, w in enumerate(pre) if not r[n].startswith("-") and not (n and r[n - 1] in ("-s", "--source"))]
        return dirty(paths) if paths else []
    if sub == "rm":
        return dirty(post + words) if force and "--cached" not in r and (post or words) else []
    if sub == "worktree":
        return [job(WORKTREE, specs((words[1:] + post)[:1]), op="git worktree")] if first == "remove" else []
    if sub == "clean":
        return [] if "--dry-run" in r or "n" in s else [job(CLEAN, args=tuple(r))]
    if sub == "stash" and first in ("drop", "clear"):
        ref = words[1].literal() if first == "drop" and len(words) > 1 else "stash@{0}"
        return [job(STASH, args=(first, f"stash@{{{ref}}}" if ref.isdigit() else ref))]
    if sub == "branch":
        delete = "D" in s or (("--delete" in r or "d" in s) and force)
        if not delete or "--remotes" in r or "r" in s:
            return []
        return [replace(job(BRANCH, args=(w.literal(),), op="git branch -D"), label=w.literal()) for w in words]
    if (sub == "reflog" and first in ("expire", "delete")) or (sub == "gc" and {"--prune=now", "--prune=all"} & set(r)) \
            or sub in ("prune", "filter-branch", "filter-repo"):
        return [replace(job(REFLOG), paths=[])]   # 저장소를 몰라도 거부 — 조회가 필요 없다
    if sub == "push":
        # 평범한 push 는 기본 브랜치를 덮지 않는다 — 저장소·원격 조회 없이 판정 생략
        return [job(PUSH, args=tuple(r))] if "--dry-run" not in r and "n" not in s and _push_rewrites(r) else []
    return []


def _compose_project(g: list[tuple[str, Word]], seg: Segment, ctx: Ctx | None) -> str:
    """compose 프로젝트명: -p, COMPOSE_PROJECT_NAME(줄 안 export 또는 실행 env), 없으면 프로젝트 폴더 이름
    (compose 정규화: 소문자, [a-z0-9_-] 만). 모르면 ''."""
    proj = [w.literal() for k, w in g if k in ("-p", "--project-name")]
    env = seg.env.get("COMPOSE_PROJECT_NAME") or (ctx.environ.get("COMPOSE_PROJECT_NAME") if ctx else None)
    if proj or env:
        return proj[-1] if proj else env  # type: ignore[return-value]
    pdir = [w for k, w in g if k == "--project-directory"]
    files = [w for k, w in g if k in ("-f", "--file")]
    if pdir:
        d = _resolve_dir(pdir[-1], seg.cwd, seg.env)
    elif files:
        f = _expand(files[0], seg.env, seg.cwd)
        d = os.path.dirname(os.path.normpath(f[0])) if f and len(f) == 1 else None
    else:
        d = seg.cwd
    return re.sub(r"[^a-z0-9_-]", "", os.path.basename(d).lower()) if d else ""


def _docker_handler(seg: Segment, ctx: Ctx | None) -> list[Job]:
    """spec §3.5 Docker 표의 볼륨 삭제 행. args = (목록 종류, 값…): names / dangling / compose-project."""
    a, compose, i = seg.argv, seg.name == "docker-compose", 1
    g: list[tuple[str, Word]] = []
    label = " ".join([seg.name, *literal_args(seg)])
    try:
        if not compose:
            i, _ = _opts(a, 1, _DOCKER_GLOBAL)
            if i < len(a) and a[i].literal() == "compose":
                compose, i = True, i + 1
        if compose:
            i, g = _opts(a, i, _COMPOSE_GLOBAL)
    except LexError:
        return [Job(OP_VOLUME, VOLUMES, label, None, advice=ADV_VOLUME)]   # 모르는 전역 옵션 — 보수적으로
    w = [x.literal() for x in a[i:]]
    if compose:
        if w[:1] == ["down"] and any(x == "--volumes" or (x.startswith("-") and not x.startswith("--") and "v" in x)
                                     for x in w[1:]):
            return [Job(OP_VOLUME, VOLUMES, label, [], advice=ADV_VOLUME, args=("compose-project", _compose_project(g, seg, ctx)))]
        return []
    if w[:1] == ["volume"] and w[1:2] in (["rm"], ["remove"]):
        return [Job(OP_VOLUME, VOLUMES, label, [], advice=ADV_VOLUME, args=("names", *[x for x in w[2:] if not x.startswith("-")]))]
    if w[:2] == ["volume", "prune"] or (w[:2] == ["system", "prune"] and "--volumes" in w):
        return [Job(OP_VOLUME, VOLUMES, label, [], advice=ADV_VOLUME, args=("dangling",))]
    return []


HANDLERS: dict[str, Callable[[Segment, Ctx | None], list[Job]]] = {
    "rm": _delete(), "unlink": _delete(),
    "shred": _delete(frozenset({"-n", "--iterations", "-s", "--size", "--random-source"})),
    "find": _find,
    "cp": _copy, "mv": _copy, "install": _copy, "rsync": _rsync,
    "tee": _tee, "truncate": _truncate, "dd": _dd, "mkfs": _mkfs,
    "chmod": _perm, "chown": _perm, "chgrp": _perm,
    "git": _git_handler, "docker": _docker_handler, "podman": _docker_handler, "docker-compose": _docker_handler,
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
    try:
        jobs = h(seg, ctx) if h else []
    except _BadOption:
        op, rule, _ = _LONGS[seg.name]
        jobs = [Job(op, rule, " ".join([seg.name, *literal_args(seg)]), None)]
    out = []
    for j in _redirects(seg, ctx) + jobs:
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


def _dirty(op: str, repo: str, pathspecs: list[str], ctx: Ctx) -> Finding | None:
    """영향 범위(pathspecs, [] = 저장소 전체)에 이번 세션 것이 아닌 커밋 안 된 변경이 있으면 DIRTY."""
    dirty = git_dirty(repo, pathspecs, ctx)
    if dirty is None:   # 조회 실패는 허용이 아니라 확정 불가
        return Finding(op, repo, UNRESOLVED, ADV_UNRESOLVED)
    left = [d for d in dirty if not is_session_change(d, ctx)]
    if not left:
        return None
    return Finding(op, left[0] + (f" 외 {len(left) - 1}개" if len(left) > 1 else ""), "DIRTY", ADV_GIT_DIRTY)


def _worktree(op: str, wt: str, ctx: Ctx) -> Finding | None:
    """spec §3.4 워크트리 최상위 규칙: ① 커밋 안 된 변경 ② 미추적·ignore 항목 중 보호 분류."""
    f = _dirty(op, wt, [], ctx)
    if f is not None:
        return f
    items = git_extra_items(wt, ctx)
    if items is None:
        return Finding(op, wt, UNRESOLVED, ADV_UNRESOLVED)
    for p in items:
        c = classify(p, ctx)
        if SEVERITY[c.kind] > 0:
            advice = _unresolved_advice(c.detail, ADV_UNRESOLVED) if c.kind == UNRESOLVED else ADV_WORKTREE
            return Finding(op, c.path or p, c.kind, advice)
    return None


def _judge_path(j: Job, p: str, ctx: Ctx, host: bool = True) -> Finding | None:
    # host False = 컨테이너 바인드 마운트를 호스트 경로로 바꾼 대상 — 시스템 경로 규칙은 호스트 문맥에만(spec §3.6)
    if host and _system(p, j.rule != DELETE, j.trailing):
        return Finding(OP_SYSTEM, p, "SYSTEM", ADV_SYSTEM)
    if j.rule == PERM:
        return None
    if j.rule == RPERM:
        return None if in_workspace(p, ctx) else Finding(j.op, p, "OUTSIDE_WORKSPACE", ADV_WORKSPACE)
    if j.rule == MKFS or (j.rule == OVERWRITE and _device(p)):
        return None if j.rule == MKFS and in_workspace(p, ctx) else Finding(OP_DISK, p, "OUTSIDE_WORKSPACE", ADV_DISK)
    c = classify(p, ctx, j.trailing)
    target = c.path or p
    if c.worktree_root and j.rule == DELETE:
        return _worktree(j.op, c.worktree_root, ctx)
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


def _old(t: float, ctx: Ctx) -> bool:
    return before_session(t, ctx)


# ---- 작업 단위 규칙 (git·docker 볼륨) ----

def _j_dirty(j: Job, ctx: Ctx) -> list[Finding]:
    f = _dirty(j.op, j.repo or j.label, j.paths or [], ctx)
    return [f] if f else []


def _j_worktree(j: Job, ctx: Ctx) -> list[Finding]:
    wt = normalize(j.paths[0], True) if j.paths else None
    # worktree 가 아닌 경로·없는 경로는 git 이 스스로 거부한다
    f = _worktree(j.op, wt, ctx) if wt and is_linked_worktree_root(wt) else None
    return [f] if f else []


def _j_clean(j: Job, ctx: Ctx) -> list[Finding]:
    items = git_clean_preview(j.repo or "", list(j.args), ctx)
    if items is None:
        return [Finding(j.op, j.label, UNRESOLVED, ADV_UNRESOLVED)]
    d = Job(j.op, DELETE, j.label, items)
    return next(([f] for p in items if (f := _judge_path(d, p, ctx)) is not None), [])   # 보호 분류인 첫 항목


def _j_stash(j: Job, ctx: Ctx) -> list[Finding]:
    repo, what = j.repo or "", j.args[0]
    if what == "clear":
        out = _git(repo, ["stash", "list", "--format=%ct"], ctx)
        times = None if out is None else [float(x) for x in out.split() if x.isdigit()]
        target = "refs/stash"
    else:
        t = git_stash_created(repo, j.args[1], ctx)
        times, target = (None if t is None else [t]), j.args[1]
    if times is None:
        return [Finding(j.op, target, UNRESOLVED, ADV_UNRESOLVED)]
    return [Finding(j.op, target, "OLD_STASH", ADV_STASH)] if any(_old(t, ctx) for t in times) else []


def _j_branch(j: Job, ctx: Ctx) -> list[Finding]:
    b = j.args[0]
    info = git_branch_info(j.repo or "", b, ctx)
    if info is None:
        return [Finding(j.op, b, UNRESOLVED, ADV_UNRESOLVED)]
    if (info.upstream_ref_exists and info.ahead == 0) or info.merged_into_default or info.reachable_elsewhere or (
            info.created_at is not None and not _old(info.created_at, ctx)):
        return []
    return [Finding(j.op, b, "UNPUSHED", ADV_UNPUSHED)]


def _j_reflog(j: Job, ctx: Ctx) -> list[Finding]:
    return [Finding(j.op, j.label, "REFLOG", ADV_REFLOG)]


_PUSH_VALUES = ("--repo", "-o", "--push-option", "--receive-pack", "--exec")


def _push_opts(a: list[str]) -> tuple[bool, bool, bool, bool, bool, str | None, list[str]]:
    """(force, delete, mirror, every, tags, --repo 값, 위치 인자)."""
    force = delete = mirror = every = tags = False
    remote_opt, pos, i, opts = None, [], 0, True
    while i < len(a):
        x = a[i]
        i += 1
        if not opts or not x.startswith("-") or x == "-":
            pos.append(x)
        elif x == "--":
            opts = False
        elif x.startswith("--"):
            k, eq, v = x.partition("=")
            if k in _PUSH_VALUES and not eq and i < len(a):
                v, i = a[i], i + 1
            # --force-with-lease·--force-if-includes 는 강제가 아니다(원격이 예상과 같을 때만 덮는다)
            force, delete, mirror = force or k == "--force", delete or k == "--delete", mirror or k == "--mirror"
            every, tags = every or k in ("--all", "--branches"), tags or k == "--tags"
            remote_opt = v if k == "--repo" else remote_opt
        else:
            for n, ch in enumerate(x[1:], 1):
                if "-" + ch in _PUSH_VALUES:
                    i += 0 if x[n + 1:] else 1
                    break
                force, delete = force or ch == "f", delete or ch == "d"
    return force, delete, mirror, every, tags, remote_opt, pos


def _push_rewrites(a: list[str]) -> bool:
    """원격 이력을 덮거나 지울 수 있는 push 인가 — 강제·삭제·미러·`+ref`·`:dst`."""
    force, delete, mirror, _, _, _, pos = _push_opts(a)
    return force or delete or mirror or any(p.startswith(("+", ":")) for p in pos[1:])


def _j_push(j: Job, ctx: Ctx) -> list[Finding]:
    repo = j.repo or ""
    force, delete, mirror, every, tags, remote_opt, pos = _push_opts(list(j.args))
    cur =(_git(repo, ["symbolic-ref", "-q", "--short", "HEAD"], ctx) or "").strip() or None
    remote = pos[0] if pos else remote_opt or (
        cur and (_git(repo, ["config", f"branch.{cur}.remote"], ctx) or "").strip()) or "origin"
    names = git_remote_names(repo, ctx)
    if names is None:
        return [Finding(j.op, j.label, UNRESOLVED, ADV_UNRESOLVED)]
    if remote not in names:
        return []   # URL·경로로 push — 원격 저장소 판정 대상 아님(spec §3.5)
    # 덮어쓰기·삭제가 걸린 목적지들. 글롭은 'refs/heads/' 를 붙인 패턴으로 기본 브랜치와 맞춘다
    dsts: list[str] = []
    for spec in pos[1:]:
        plus = spec.startswith("+")
        src, colon, dst = spec[plus:].partition(":")
        if not colon:
            dst = src
        if force or plus or delete or (colon and not src):
            dsts.append((cur or "") if dst == "HEAD" else dst)
    if not pos[1:] and not mirror and not tags and (force or delete):
        dsts += ["\0all"] if every else [x for x in (cur, git_upstream_branch(repo, ctx)) if x]
    if not mirror and not dsts:
        return []
    default = git_default_branch(repo, remote, ctx)
    # spec §3.5: 기본 브랜치 = origin/HEAD, 없으면 main·master. 그것도 확정 못 하면 두 이름 모두를 기본 브랜치로 본다
    defaults, advice = ([default], ADV_DEFAULT_BRANCH) if default else (["main", "master"], ADV_DEFAULT_GUESS)

    def hits(d: str, b: str) -> bool:
        full = "refs/heads/" + b
        if d == "\0all":   # --all·--branches: 로컬에 기본 브랜치가 있으면 그것도 대상
            return _git(repo, ["rev-parse", "--verify", "-q", full], ctx) is not None
        pat = d if d.startswith("refs/") else "refs/heads/" + d
        return fnmatch(full, pat) if "*" in d else pat == full

    hit = defaults[0] if mirror else next((b for b in defaults for d in dsts if hits(d, b)), None)
    return [Finding(j.op, f"{remote}/{hit}", "DEFAULT_BRANCH", advice)] if hit else []


def _volume(op: str, name: str, target: str, ctx: Ctx) -> Finding | None:
    t = docker_volume_created(name, ctx)
    if t is None:   # 데몬 없음 등 — 볼륨 삭제는 확정 불가(spec §3.5 Docker)
        return Finding(op, target, UNRESOLVED, ADV_VOLUME)
    return Finding(op, target, "OLD_VOLUME", ADV_VOLUME) if _old(t, ctx) else None


def _j_volumes(j: Job, ctx: Ctx) -> list[Finding]:
    kind, *rest = j.args
    names = rest if kind == "names" else docker_volumes(kind, rest[0] if rest else None, ctx)
    if names is None:
        return [Finding(j.op, j.label, UNRESOLVED, ADV_VOLUME)]
    return [f for n in names if (f := _volume(j.op, n, n, ctx)) is not None]


_RULE_JUDGES: dict[str, Callable[[Job, Ctx], list[Finding]]] = {
    GIT_DIRTY: _j_dirty, WORKTREE: _j_worktree, CLEAN: _j_clean, STASH: _j_stash, BRANCH: _j_branch,
    PUSH: _j_push, REFLOG: _j_reflog, VOLUMES: _j_volumes,
}


def _judge(jobs: list[Job], ctx: Ctx, host: bool = True) -> list[Finding]:
    out: list[Finding] = []
    for j in jobs:
        if j.paths is None:
            out.append(Finding(j.op, j.label, UNRESOLVED, j.advice))
        elif j.rule in _RULE_JUDGES:
            out += _RULE_JUDGES[j.rule](j, ctx)
        else:
            out += [f for p in j.paths if (f := _judge_path(j, p, ctx, host)) is not None]
    return out


# ---- 컨테이너 문맥 (spec §3.6) ----

def _mount_of(p: str, mounts: tuple[Mount, ...]) -> Mount | None:
    best = None
    for m in mounts:
        d = m.destination.rstrip("/")
        # Destination 자체도 대상 — `rm -rf /app` 은 Source 폴더 내용 전체를 지운다
        if (p == (d or "/") or p.startswith(d + "/")) and (best is None or len(d) > len(best.destination.rstrip("/"))):
            best = m
    return best


def _container_jobs(seg: Segment, ctx: Ctx) -> tuple[list[Job], list[Finding]]:
    """(호스트 경로로 바꾼 바인드 마운트 대상 작업들, 볼륨·확정 불가 판정들). 마운트 밖 = 컨테이너 내부 경로 → 판정 없음."""
    cx = seg.context
    workdir: str | None = None
    # compose run 은 인자의 -v 말고도 compose 파일의 서비스 마운트가 붙는다 — 인자 마운트 밖도 '모름'
    partial = cx.launcher == "compose-run"
    if cx.launcher in ("run", "compose-run"):
        mounts = cx.mounts   # None = run 의 -v 출발지를 확정할 수 없음
    elif cx.launcher in ("exec", "compose-exec"):
        cid = cx.container
        if cx.launcher == "compose-exec":
            cid = compose_container_id(cx.container, cx.project_dir, cx.project, ctx) if cx.container and cx.project_dir else None
        info = docker_container_info(cid, ctx) if cid else None
        if info is None:
            return [], []   # 조회 실패 = 컨테이너 안 경로 허용(spec §3.5 Docker)
        mounts, workdir = info
    else:
        return [], []
    may_mount = mounts is None or partial or bool(mounts)

    def place(p: str, deep: bool = False) -> list[tuple[str, str, str]]:
        """[('out'|'unknown'|'volume'|'bind', 볼륨 이름 | 호스트 경로, 컨테이너 경로)].

        deep: 아래를 모두 훑는 작업(find·재귀 삭제·재귀 권한)이라 p 아래에 있는 마운트 Destination 도 대상 —
        `find /`·`rm -rf /srv`(마운트 /srv/w)는 마운트 지점 안으로 내려가 호스트 원본을 지운다."""
        q = os.path.normpath(p)
        m = _mount_of(q, mounts or ())
        res: list[tuple[str, str, str]] = []
        if m is not None:
            res.append(("volume", m.source, q) if m.kind == "volume" else
                       ("bind", m.source.rstrip("/") + q[len(m.destination.rstrip("/")):], q))
        elif mounts is None or partial:
            res.append(("unknown", q, q))
        if deep:
            pre = q.rstrip("/") + "/"
            for n in mounts or ():
                d = n.destination.rstrip("/")
                if d.startswith(pre):
                    res.append(("volume" if n.kind == "volume" else "bind", n.source, d))
        return res or [("out", q, q)]

    def bind_exists(p: str) -> bool:
        k, h, _ = place(p)[0]
        return k == "bind" and os.path.lexists(h)

    cseg = replace(seg, cwd=seg.cwd or workdir or None)   # -w 가 없으면 컨테이너 WorkingDir 기준
    out: list[Job] = []
    if seg.name == "git":
        jobs = _git_handler(cseg, None, bind_exists)   # ctx None: 사용자 alias 조회는 컨테이너 설정이라 하지 않는다
    elif seg.name == "find":
        jobs, out, found = _container_find(cseg, ctx, place)
    else:   # ctx None: 호스트 임시 루트 규칙은 컨테이너 경로에 맞지 않다
        jobs = [j for j in _host_jobs(cseg, None) if j.rule in _PATH_RULES]
    if seg.name != "find":
        found = []
    for j in jobs:
        unresolved = Finding(j.op, j.label, UNRESOLVED, j.advice)
        if j.rule not in _PATH_RULES:   # git: 저장소가 바인드 마운트 아래면 호스트 저장소로 같은 규칙(spec §3.5 Docker)
            kind, host_repo, _ = place(j.repo)[0] if j.repo else ("unknown", "", "")
            if kind == "unknown" and may_mount:
                found.append(unresolved)
            if kind != "bind":
                continue   # 마운트 밖·볼륨 안 저장소는 판정 없음
            paths = j.paths
            if paths:
                paths = [h for k, h, _ in (place(x)[0] for x in paths) if k == "bind"]
                if not paths:
                    continue   # 경로가 모두 마운트 밖 — [] 로 두면 저장소 전체로 읽힌다
            out.append(replace(j, repo=host_repo, paths=paths, label=host_repo if j.label == j.repo else j.label))
            continue
        if j.paths is None:
            if may_mount:
                found.append(unresolved)
            continue
        host: list[str] = []
        deep = _recursive(cseg, j)
        for kind, v, t in (x for p in j.paths for x in place(p, deep)):
            if kind == "unknown":
                found.append(replace(unresolved, target=v))
            elif kind == "volume":
                if v and (f := _volume(j.op, v, t, ctx)) is not None:   # '' = run 의 새 익명 볼륨
                    found.append(f)
            elif kind == "bind":
                # 와일드카드는 호스트 셸이 컨테이너 경로로 펼치지 못해 글자 그대로 왔다 — 호스트 쪽에서 펼친다
                host += (sorted(glob.glob(v)) or [v]) if any(c in v for c in "*?[") else [v]
        if host:
            out.append(replace(j, paths=host))
    return out, found


def _recursive(seg: Segment, j: Job) -> bool:
    """폴더 아래를 모두 훑는 작업인가 — 재귀 권한, rm -r, rsync --delete*."""
    if j.rule == RPERM:
        return True
    if j.rule != DELETE or seg.name not in ("rm", "rsync"):
        return False
    try:
        return seg.name == "rsync" or bool(_args(seg)[0] & {"-r", "-R", "--recursive"})
    except _BadOption:
        return True


_FIND_PATH_TESTS = frozenset(("-mindepth", "-maxdepth", "-path", "-ipath", "-wholename", "-iwholename", "-regex", "-iregex",
                              "-newer"))


def _container_find(cseg: Segment, ctx: Ctx, place: Callable[..., list[tuple[str, str, str]]]
                    ) -> tuple[list[Job], list[Job], list[Finding]]:
    """컨테이너 안 find 삭제: 시작 경로(와 그 아래 마운트)를 사상해 바인드 원본은 호스트에서 미리보기(spec §3.6).
    (확정 불가 작업들, 호스트 경로 작업들, 볼륨·모름 판정들)."""
    jobs = _find(cseg, None)
    if not jobs:
        return [], [], []
    a = literal_args(cseg)
    n = next((i for i, x in enumerate(a) if x.startswith("-") or x in ("!", "(", ")")), len(a))
    starts = [expand(w, cseg) for w in cseg.argv[1:1 + n]] if n else [[cseg.cwd] if cseg.cwd else None]
    if None in starts:
        return jobs, [], []   # 시작 경로를 확정할 수 없다 — paths None 그대로(마운트가 있으면 확정 불가)
    j = jobs[0]
    hosts: list[str] = []
    found: list[Finding] = []
    for kind, v, t in (x for s in starts for p in s for x in place(p, True)):   # type: ignore[union-attr]
        if kind == "bind":
            hosts.append(v)
        elif kind == "volume":
            if v and (f := _volume(j.op, v, t, ctx)) is not None:
                found.append(f)
        elif kind == "unknown":
            found.append(Finding(j.op, t, UNRESOLVED, j.advice))
    if not hosts:
        return [], [], found
    if _FIND_PATH_TESTS.intersection(a[n:]):
        # 깊이·컨테이너 절대경로를 보는 조건은 호스트 경로에서 다른 항목을 고른다 — 재생하지 않고 원본 폴더 전체를 재귀 삭제로 본다
        return [], [Job(j.op, DELETE, h, [h], trailing=True) for h in hosts], found
    hseg = replace(cseg, argv=[cseg.argv[0], *[Word((Part(h, "'"),)) for h in hosts], *cseg.argv[1 + n:]], cwd="/")
    return [], _find(hseg, ctx), found


def _targets(jobs: list[Job]) -> list[str]:
    return [p for j in jobs for p in j.paths or ()] + [j.repo for j in jobs if j.repo]


def assess(seg: Segment, ctx: Ctx) -> tuple[list[Finding], list[str]]:
    """(판정, 판정 대상 경로) — 작업 목록(find 미리보기·docker 조회)을 한 번만 만든다."""
    if seg.context.kind != "host":
        jobs, found = _container_jobs(seg, ctx)
        return found + _judge(jobs, ctx, host=False), _targets(jobs)
    jobs = _host_jobs(seg, ctx)
    return _judge(jobs, ctx), _targets(jobs)


def evaluate(seg: Segment, ctx: Ctx) -> list[Finding]:
    return assess(seg, ctx)[0]


def judged_targets(seg: Segment, ctx: Ctx) -> list[str]:
    return _targets(_container_jobs(seg, ctx)[0] if seg.context.kind != "host" else _host_jobs(seg, ctx))


def is_judged_op(seg: Segment) -> bool:
    # 판정 대상 여부(spec §3.8 시간 예산)도 판정과 같은 처리기 표를 본다 — 조회 없이 명령 모양만
    return bool(_host_jobs(seg, None))


# ---- 장부 기록용 해석 (spec §3.7 기록 주체 2) ----

def _sed_perl_files(seg: Segment) -> list[Word]:
    """`sed -i|--in-place`·`perl -i|-pi` 의 파일 인자. 제자리 수정이 아니면 []."""
    perl = seg.name == "perl"
    a, i, inplace, script, ops = seg.argv[1:], 0, False, False, []
    while i < len(a):
        s = a[i].literal()
        i += 1
        if s == "--":
            ops += a[i:]
            break
        if not s.startswith("-") or s == "-":
            if perl:   # perl 은 첫 비옵션에서 옵션이 끝난다
                ops += a[i - 1:]
                break
            ops.append(a[i - 1])
        elif s.startswith("--"):
            k, eq, _ = s.partition("=")
            inplace |= k == "--in-place"
            if k in ("--expression", "--file"):
                script = True
            if k in ("--expression", "--file", "--line-length") and not eq:
                i += 1
        else:
            for n, c in enumerate(s[1:], 1):
                if c == "i":   # 뒤 글자는 백업 접미사
                    inplace = True
                    break
                if c in ("eE" if perl else "efl"):
                    script = script or c != "l"
                    i += n == len(s) - 1
                    break
                if perl and c in "IMmlx0CdDV":   # 값이 붙어 오는 옵션
                    break
    if not inplace:
        return []
    return ops if script else ops[1:]


def inplace_targets(seg: Segment) -> list[str]:
    """제자리 수정의 닫힌 목록(리다이렉트·tee·sed -i·perl -i·truncate·cp/mv/install/rsync/dd 목적지·git checkout/restore)."""
    words = [r.target for r in seg.redirects if r.target is not None and r.op in (">", ">|", "&>", ">>", "&>>")]
    out: list[str] = []
    try:
        if seg.name == "tee":
            words += _args(seg)[2]
        elif seg.name in ("sed", "perl"):
            words += _sed_perl_files(seg)
        elif seg.name in ("truncate", "cp", "mv", "install", "rsync", "dd"):
            out += [p for j in HANDLERS[seg.name](seg, None) if j.rule == OVERWRITE for p in j.paths or ()]
        elif seg.name == "git":
            out += [p if j.rule == OVERWRITE else os.path.join(j.repo, p) for j in _git_handler(seg, None)
                    if j.rule == OVERWRITE or (j.op in ("git checkout", "git restore") and j.repo) for p in j.paths or ()]
    except _BadOption:
        pass
    out += [p for w in words for p in expand(w, seg) or ()]
    return [p for p in out if os.path.lexists(p) and not os.path.isdir(p)]


def mv_moves(seg: Segment) -> list[tuple[str, str]]:
    """mv 의 (원본, 목적지) 쌍. 확정할 수 없으면 생략."""
    try:
        flags, vals, ops = _args(seg, _COPY_VALUES - {"-m", "-o", "-g"})
    except _BadOption:
        return []
    tdir = vals.get("-t") or vals.get("--target-directory")
    force = tdir is not None
    if tdir is None:
        if len(ops) < 2:
            return []
        tdir, ops = ops[-1], ops[:-1]
    dest = expand(tdir, seg)
    if dest is None or len(dest) != 1:
        return []
    srcs = [p for w in ops for p in expand(w, seg) or ()]
    if flags & {"-T", "--no-target-directory"} or not (force or os.path.isdir(dest[0])):
        return [(srcs[0], dest[0])] if len(srcs) == 1 else []
    return [(s, os.path.join(dest[0], os.path.basename(s.rstrip("/")))) for s in srcs]
