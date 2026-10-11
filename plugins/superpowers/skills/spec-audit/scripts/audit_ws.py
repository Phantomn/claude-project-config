#!/usr/bin/env python3
"""spec-audit 작업 공간 도구 (stdlib only, Python 3.10+).

감사는 최대 2회다(D23): 라운드 1 = 전체 감사, 라운드 2 = 리드가 고친 줄만 1회 재검토(수정이 있을 때만).
끝(finish) = 모든 지적에 처분 ∧ 반영한 지적의 check 통과 ∧ (라운드 1 뒤 고쳤으면) 라운드 2를 거침.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import NoReturn

Z = 1500
REVIEW = 2  # 마지막 라운드 = 수정분 재검토. 그 뒤 라운드는 없다(D23)
AXES = ("refs", "selfcontained", "rootcause", "oracle")
EXEC_AXES = AXES[1:]
DISPOSITIONS = {"apply": "반영", "reject": "기각", "accept": "수용"}

# (스냅샷 순번 i, a, b) — 1부터, 양끝 포함
Range = tuple[int, int, int]


def axis_lines(targets: list[dict], axis: str) -> list[Range]:
    """축이 맡는 줄 범위. refs = 전부, 다른 축 = role spec·plan만. lines == 0 제외."""
    out: list[Range] = []
    for i, t in enumerate(targets, 1):
        if t["lines"] == 0:
            continue
        if axis != "refs" and t["role"] not in ("spec", "plan"):
            continue
        out.append((i, 1, t["lines"]))
    return out


def shard(ranges: list[Range], z: int = Z) -> list[list[Range]]:
    """범위를 이은 줄을 정확히 z줄마다 자른다(범위·대상 경계를 넘을 수 있음)."""
    shards: list[list[Range]] = []
    cur: list[Range] = []
    room = z
    for i, a, b in ranges:
        while a <= b:
            end = min(b, a + room - 1)
            cur.append((i, a, end))
            room -= end - a + 1
            a = end + 1
            if room == 0:
                shards.append(cur)
                cur, room = [], z
    if cur:
        shards.append(cur)
    return shards


_ORACLE_RE = re.compile(r"^## Reference Oracle\b")


def oracle_needed(text: str) -> bool:
    """코드 펜스 밖 '## Reference Oracle' 절의 첫 비어 있지 않은 줄이 '['로 시작하지 않으면 True."""
    in_fence = False
    in_section = False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            if in_section:
                return True  # 펜스 시작 = 비어 있지 않은 줄, '['가 아님
            continue
        if in_fence:
            continue
        if in_section:
            if re.match(r"#{1,2}(\s|$)", line):
                return False
            if line.strip():
                return not line.lstrip().startswith("[")
        elif _ORACLE_RE.match(line):
            in_section = True
    return False


def range_len(rs: list[Range]) -> int:
    return sum(b - a + 1 for _, a, b in rs)


def overlaps(a: list[Range], b: list[Range]) -> bool:
    return any(i == j and x <= v and u <= y for i, x, y in a for j, u, v in b)


def changed_lines(old: list[bytes], new: list[bytes]) -> set[int]:
    """새 쪽에서 바뀐 줄(1부터). 삭제만이면 새 쪽 삭제 지점 앞뒤 1줄, [1, len(new)]로 잘림."""
    out: set[int] = set()
    for tag, _, _, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag in ("replace", "insert"):
            out.update(range(j1 + 1, j2 + 1))
        elif tag == "delete":
            out.update(k for k in (j1, j1 + 1) if 1 <= k <= len(new))
    return out


# ---- 위치(4.2) ----

HERE = Path(__file__).resolve()
SKILL_MD = HERE.parents[1] / "SKILL.md"
AUDITORS = HERE.parents[1] / "auditors"
PLUGIN_JSON = HERE.parents[3] / ".claude-plugin" / "plugin.json"


def die(msg: str) -> NoReturn:
    raise SystemExit(msg)


def tmproot() -> Path:
    return Path(os.environ.get("SUPERPOWERS_AUDIT_TMPROOT") or f"/tmp/claude-{os.getuid()}").resolve()


def state_dir() -> Path:
    if env := os.environ.get("SUPERPOWERS_AUDIT_STATE"):
        return Path(env)
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "superpowers"


def pass_record_path(plan_sha: str) -> Path:
    return state_dir() / "audit-pass" / f"{plan_sha}.json"


ABORTED = "aborted"


def open_path(ws: Path) -> Path:
    return tmproot() / "spec-audit" / ws.name / "open.json"


def write_open(ws: Path, n: int) -> None:
    """열린 감사 기록(spec 4.3) — 훅이 읽는다."""
    tj = json.loads((ws / f"round-{n}" / "targets.json").read_text(encoding="utf-8"))
    rec = {"ws": str(ws), "round": n, "session": os.environ.get("CLAUDE_CODE_SESSION_ID"),
           "tree": tj["tree"], "targets": [t["path"] for t in tj["targets"]]}
    p = open_path(ws)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")


def close_open(ws: Path) -> None:
    open_path(ws).unlink(missing_ok=True)


def ensure_not_aborted(ws: Path) -> None:
    if (ws / ABORTED).exists():
        die("감사 중단됨 — 새로 시작하려면 C1")


def rounds(ws: Path) -> list[int]:
    return sorted(int(m.group(1)) for d in ws.glob("round-*") if (m := re.fullmatch(r"round-(\d+)", d.name)))


def role_of(path: Path) -> str | None:
    """S0-2 역할 규칙. plan 규칙이 먼저."""
    dirs, base = path.parent.parts, path.name.lower()
    if "plans" in dirs or "plan" in base:
        return "plan"
    if "specs" in dirs or "spec" in base or "design" in base:
        return "spec"
    return None


def git_top(d: Path) -> Path | None:
    p = subprocess.run(["git", "-C", str(d), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return Path(p.stdout.strip()).resolve() if p.returncode == 0 else None


def resolve_tree(plan: Path | None, specs: list[Path], tree: Path | None) -> Path:
    first = plan.resolve() if plan else sorted((s.resolve() for s in specs), key=str)[0]
    base = (tree if tree else first.parent).resolve()
    if not base.is_dir():
        die(f"--tree 디렉토리 없음: {base}")
    top = git_top(base)
    if top is None:
        return base
    if subprocess.run(["git", "-C", str(top), "rev-parse", "--verify", "-q", "HEAD"],
                      capture_output=True).returncode != 0:
        die(f"git 저장소에 HEAD 없음: {top}")
    return top


def workspace(tree: Path, plan: Path | None, specs: list[Path]) -> Path:
    paths = sorted({str(p.resolve()) for p in ([plan] if plan else []) + specs})
    first = plan.resolve() if plan else sorted((s.resolve() for s in specs), key=str)[0]
    digest = hashlib.sha256("\n".join(paths).encode()).hexdigest()[:8]
    return tree / ".superpowers" / "audit" / f"{first.stem}-{digest}"


def rel(path: Path, tree: Path) -> str:
    try:
        return str(path.relative_to(tree))
    except ValueError:
        return str(path)


# ---- 범위 문자열(4.5.2) ----

_RANGE_RE = re.compile(r"^round-(\d+)/snapshot/(\d+-[^/]+):(\d+)(?:-(\d+))?$")


def fmt_range(n: int, snapshot: str, a: int, b: int) -> str:
    return f"round-{n}/snapshot/{snapshot}:{a}" + (f"-{b}" if b != a else "")


def parse_range(s: str) -> tuple[int, str, int, int]:
    m = _RANGE_RE.match(s)
    if not m:
        raise ValueError(f"범위 문자열 형식 위반: {s!r}")
    a = int(m.group(3))
    b = int(m.group(4) or a)
    if a < 1 or b < a:
        raise ValueError(f"범위 줄 위반: {s!r}")
    return int(m.group(1)), m.group(2), a, b


def skill_hash(path: Path = SKILL_MD) -> str:
    keep = [l for l in path.read_bytes().splitlines(keepends=True) if not l.startswith("스킬 버전: ".encode())]
    return hashlib.sha256(b"".join(keep)).hexdigest()[:12]


# ---- 감사자 배정(4.6) ----

def make_exec_dir(tree: Path, x: Path) -> Path | None:
    """X 생성. git이면 X/head/ = HEAD archive 추출, 실패하면 X를 지우고 None."""
    x.mkdir(parents=True)
    if git_top(tree) is None:
        return x
    head = x / "head"
    head.mkdir()
    arc = subprocess.Popen(["git", "-C", str(tree), "archive", "--format=tar", "HEAD"],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    tar = subprocess.run(["tar", "-x", "-C", str(head)], stdin=arc.stdout, capture_output=True)
    if arc.stdout:
        arc.stdout.close()
    if arc.wait() != 0 or tar.returncode != 0:
        shutil.rmtree(x)
        return None
    return x


def write_prompt(ws: Path, item: dict, targets: list[dict], n: int, violations: tuple[str, ...] = ()) -> Path:
    """violations = retry 프롬프트에 적는 직전 시도 위반 사유(C3 ②)."""
    R = ws / f"round-{n}"
    tree = json.loads((R / "targets.json").read_text(encoding="utf-8"))["tree"]
    lines = ["", "## 배정", "",
             f"- 작업공간 W: {ws}", f"- 라운드: {n}" + (" (수정분 재검토)" if n == REVIEW else ""),
             f"- 이름: {item['name']} · 축: {item['axis']}",
             f"- <tree>: {tree}", "- 배정 범위(W 기준):", *[f"  - {r}" for r in item["ranges"]],
             "- 대상 스냅샷:",
             *[f"  - {R / 'snapshot' / t['snapshot']} · role {t['role']} · rel {t['rel']}" for t in targets]]
    if item["axis"] in EXEC_AXES:
        if item["exec_dir"]:
            lines.append(f"- 실행 디렉토리 X: {item['exec_dir']}")
        else:
            lines.append("- 실행 디렉토리 X: 없음(생성 실패) — 실행 검증은 `unverified(tool)`")
    if n == REVIEW:
        lines.append(f"- diff.patch(라운드 1 스냅샷 → 지금): {R / 'diff.patch'}")
    lines += [f"- 직전 시도 위반: {v}".replace("\n", " ") for v in violations]
    lines.append(f"- 보고 경로: {R / 'reports' / (item['name'] + '.md')}")
    text = (AUDITORS / "common.md").read_text(encoding="utf-8") + (AUDITORS / f"{item['axis']}.md").read_text(encoding="utf-8")
    p = R / "prompts" / f"{item['name']}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text + "\n".join(lines) + "\n", encoding="utf-8")
    return p


def build_round(ws: Path, n: int, targets: list[dict], ranges: dict[str, list[Range]]) -> dict:
    """ranges = 축별 배정 범위(샤드 전). assign.json·prompts·X 생성, C8 반환."""
    R = ws / f"round-{n}"
    tree = Path(json.loads((R / "targets.json").read_text(encoding="utf-8"))["tree"])
    agents = []
    for axis in AXES:
        for k, sh in enumerate(shard(ranges.get(axis, [])), 1):
            name = f"{axis}-r{n}-s{k}"
            item = {"name": name, "axis": axis, "prompt": None, "exec_dir": None,
                    "ranges": [fmt_range(n, targets[i - 1]["snapshot"], a, b) for i, a, b in sh]}
            if axis in EXEC_AXES:
                x = make_exec_dir(tree, tmproot() / "spec-audit" / ws.name / f"r{n}" / name)
                item["exec_dir"] = str(x) if x else None
            item["prompt"] = str(write_prompt(ws, item, targets, n))
            agents.append(item)
    (R / "reports").mkdir(parents=True, exist_ok=True)
    (R / "assign.json").write_text(json.dumps({"agents": agents}, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"ws": str(ws), "round": n, "agents": agents}


def snapshot_targets(R: Path, tree: Path, docs: list[tuple[Path, str]]) -> list[dict]:
    """docs = [(realpath, role)] targets 순서. 스냅샷·targets.json(C6) 작성."""
    (R / "snapshot").mkdir(parents=True)
    targets = []
    for i, (path, role) in enumerate(docs, 1):
        data = path.read_bytes()
        snap = f"{i}-{path.name}"
        (R / "snapshot" / snap).write_bytes(data)
        targets.append({"path": str(path), "rel": rel(path, tree), "role": role,
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "lines": len(data.splitlines(keepends=True)), "snapshot": snap})
    tj = {"tree": str(tree), "plugin_version": json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))["version"], "targets": targets}
    (R / "targets.json").write_text(json.dumps(tj, ensure_ascii=False, indent=1), encoding="utf-8")
    return targets


# ---- 명령(4.7) ----

_ROOT_MARKERS = ("package.json", "pyproject.toml", "Cargo.toml", "go.mod")
_TICK_RE = re.compile(r"`([^`]+)`")


def collect_canon(doc: Path, tree: Path, exclude: set[Path]) -> list[Path]:
    """4.7 C1 정본 자동 수집. 정본/canonical 줄의 백틱 .md 토큰을 4.4.2 후보 ①②③에서 찾는다."""
    d = doc.resolve().parent
    root = next((c for c in (d, *d.parents) if any((c / m).exists() for m in _ROOT_MARKERS)), None)
    bases = [b for b in (tree, root, d) if b is not None]
    found: dict[Path, None] = {}
    for line in doc.read_text(encoding="utf-8", errors="replace").splitlines():
        if "정본" not in line and "canonical" not in line:
            continue
        for tok in _TICK_RE.findall(line):
            tok = tok.split()[0] if tok.split() else ""
            if not tok.endswith(".md"):
                continue
            p = Path(tok).expanduser()
            for c in ([p] if p.is_absolute() else [b / p for b in bases]):
                if c.is_file() and c.resolve() not in exclude:
                    found[c.resolve()] = None
    return list(found)


def archive_ws(ws: Path) -> None:
    """같은 대상의 이전 감사 W를 지우지 않고 `<W>.<시각>`으로 옮긴다(D6 개정 — 이력이 사후 분석의 유일한 자료였다)."""
    if not ws.exists():
        return
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dst, k = ws.with_name(f"{ws.name}.{stamp}"), 1
    while dst.exists():
        dst, k = ws.with_name(f"{ws.name}.{stamp}-{k}"), k + 1
    ws.rename(dst)


def _oracle_off(R: Path, targets: list[dict]) -> bool:
    return not any(t["role"] == "spec" and oracle_needed((R / "snapshot" / t["snapshot"]).read_text(encoding="utf-8", errors="replace"))
                   for t in targets)


def cmd_init(a: argparse.Namespace) -> dict:
    """C1: 라운드 1(전체 범위)."""
    if not a.skill_version:
        die("--skill-version 필요")
    if a.skill_version != skill_hash():
        die("스킬 버전 불일치: `/reload-plugins`(플러그인을 캐시에서 로드하는 설치면 세션 재시작) 필요")
    plans = a.plan or []
    if len(plans) > 1:
        die("plan은 최대 1개")
    if not plans and not a.spec:
        die("--plan 또는 --spec 이 1개 이상 필요")
    for f in plans + (a.spec or []):
        if not Path(f).is_file():
            die(f"대상 파일 없음: {f}")
    plan = Path(plans[0]).resolve() if plans else None
    specs = sorted({Path(f).resolve() for f in a.spec or []} - {plan}, key=str)
    tree = resolve_tree(plan, specs, Path(a.tree) if a.tree else None)
    ws = workspace(tree, plan, specs)
    archive_ws(ws)
    shutil.rmtree(tmproot() / "spec-audit" / ws.name, ignore_errors=True)
    ws.mkdir(parents=True)
    (ws.parent / ".gitignore").write_text("*\n", encoding="utf-8")
    exclude = {p for p in [plan, *specs] if p}
    canon = sorted({c for p in exclude for c in collect_canon(p, tree, exclude)}, key=str)
    docs = ([(plan, "plan")] if plan else []) + [(s, "spec") for s in specs] + [(c, "other") for c in canon]
    R = ws / "round-1"
    targets = snapshot_targets(R, tree, docs)
    ranges = {ax: axis_lines(targets, ax) for ax in AXES}
    if _oracle_off(R, targets):
        ranges["oracle"] = []
    out = build_round(ws, 1, targets, ranges)
    write_open(ws, 1)
    return out


def _lines(p: Path) -> list[bytes]:
    return p.read_bytes().splitlines(keepends=True)


def cmd_review(ws: Path) -> dict:
    """C2: 라운드 2 = 라운드 1 스냅샷 뒤 바뀐 줄만 1회 재검토(D23). 대상은 라운드 1과 같은 파일."""
    ensure_not_aborted(ws)
    restore_snapshots(ws)
    P, R = ws / "round-1", ws / f"round-{REVIEW}"
    if R.exists():
        die("수정분 재검토는 한 번뿐이다(D23) — 남은 지적은 처분하고 finish")
    if not (P / "aggregate.json").is_file():
        die(f"라운드 1 aggregate.json 없음: {P / 'aggregate.json'}")
    prev = json.loads((P / "targets.json").read_text(encoding="utf-8"))
    for t in prev["targets"]:
        if not Path(t["path"]).is_file():
            die(f"대상 파일 없음: {t['rel']}")
    targets = snapshot_targets(R, Path(prev["tree"]), [(Path(t["path"]), t["role"]) for t in prev["targets"]])
    old = [_lines(P / "snapshot" / t["snapshot"]) for t in prev["targets"]]
    new = [_lines(R / "snapshot" / t["snapshot"]) for t in targets]
    nl = b"\n\\ No newline at end of file\n"  # 개행 없는 마지막 줄이 다음 줄·대상과 붙지 않게
    (R / "diff.patch").write_bytes(b"".join(
        l if l.endswith(b"\n") else l + nl
        for o, w, t in zip(old, new, targets)
        for l in difflib.diff_bytes(difflib.unified_diff, o, w, t["rel"].encode(), t["rel"].encode())))
    changed = {(i, k) for i in range(1, len(targets) + 1) for k in changed_lines(old[i - 1], new[i - 1])}
    if not changed:
        shutil.rmtree(R)
        die("라운드 1 뒤 바뀐 줄이 없다 — 재검토할 수정분이 없으니 finish")
    ranges = {ax: runs(changed & lines_of(axis_lines(targets, ax))) for ax in AXES}
    if _oracle_off(R, targets):
        ranges["oracle"] = []
    out = build_round(ws, REVIEW, targets, ranges)
    write_open(ws, REVIEW)
    return out


# ---- C3 aggregate(4.5·4.7) ----

CLASSES = {"ref-missing", "ref-mismatch", "exec-fail", "oracle-deviation", "cross-doc-conflict", "sync-miss",
           "ordering", "interface-mismatch", "constraint-drift", "contract-gap", "placeholder",
           "unverifiable-step", "assumption-form", "premise", "root-cause", "regression", "security",
           "concurrency", "under-scope", "over-scope", "requirement-uncovered", "oracle-missing", "rule-violation"}
KEYS = ("id", "verdict", "axis", "class", "target", "claim", "evidence", "recommended", "fix_class",
        "affected", "unverified_reason", "check")
REASONS = {"policy", "external", "tool", "context"}
BLOCKS = ("findings", "coverage")
_FENCE_RE = re.compile(r"^```(\w+)\n(.*?)^```$", re.M | re.S)


def parse_report(text: str) -> dict[str, list[str]]:
    """블록 이름 → 비어 있지 않은 줄. findings·coverage 외 펜스는 무시."""
    return {m.group(1): [l for l in m.group(2).splitlines() if l.strip()]
            for m in _FENCE_RE.finditer(text) if m.group(1) in BLOCKS}


def to_range(s: str, ctx: dict) -> Range:
    """범위 문자열 → (i, a, b). 라운드 ≠ N·모르는 스냅샷·줄 초과면 ValueError."""
    n, snap, a, b = parse_range(s)
    if n != ctx["n"]:
        raise ValueError(f"라운드가 {ctx['n']}이 아님: {s!r}")
    for i, t in enumerate(ctx["targets"], 1):
        if t["snapshot"] == snap:
            if b > t["lines"]:
                raise ValueError(f"줄이 파일 끝을 넘음: {s!r}")
            return i, a, b
    raise ValueError(f"모르는 스냅샷: {s!r}")


def _typed(k: str, v: object) -> bool:
    """4.5.1 키별 타입: affected = 문자열 배열, unverified_reason·check = null 또는 문자열, 나머지 = 문자열."""
    if k == "affected":
        return isinstance(v, list) and all(isinstance(r, str) for r in v)
    return isinstance(v, str) or (v is None and k in ("unverified_reason", "check"))


def validate_finding(f: object, name: str, axis: str, ctx: dict) -> list[str]:
    if not isinstance(f, dict):
        return ["finding이 객체가 아님"]
    miss = [k for k in KEYS if k not in f]
    if miss:
        return [f"키 누락 {miss}"]
    wrong = [k for k in KEYS if not _typed(k, f[k])]
    if wrong:  # 타입이 틀리면 어휘·형식 검사를 하지 않는다(보고 = 신뢰 경계 입력)
        return [f"{k} 타입 오류: {f[k]!r}" for k in wrong]
    bad = []
    if not re.fullmatch(re.escape(name) + r"-\d{3}", f["id"]):
        bad.append(f"id {f['id']!r}")
    if f["verdict"] not in ("fail", "unverified"):
        bad.append(f"verdict {f['verdict']!r}")
    if f["axis"] != axis:
        bad.append(f"axis {f['axis']!r} ≠ {axis}")
    if f["class"] not in CLASSES:
        bad.append(f"class {f['class']!r}")
    if f["fix_class"] not in ("align", "requirement"):
        bad.append(f"fix_class {f['fix_class']!r}")
    for k in ("claim", "evidence", "recommended"):
        if not f[k]:
            bad.append(f"{k} 빈 값")
    if f["check"] is not None and f["verdict"] != "fail":
        bad.append(f"check는 verdict fail에만 (verdict {f['verdict']!r})")
    want = REASONS if f["verdict"] == "unverified" else {None}
    if f["unverified_reason"] not in want:
        bad.append(f"verdict {f['verdict']!r}에 unverified_reason {f['unverified_reason']!r}")
    try:
        t = [to_range(f["target"], ctx)]
        if not overlaps(t, ctx["axis_lines"][axis]):
            bad.append(f"target {f['target']!r}이 {axis} 축의 대상 줄과 겹치지 않음")
        elif ctx["n"] == REVIEW and axis != "refs" and not overlaps(t, ctx["own"]):
            bad.append(f"target {f['target']!r}이 배정 범위와 겹치지 않음")
    except ValueError as e:
        bad.append(f"target: {e}")
    for r in f["affected"]:
        try:
            to_range(r, ctx)
        except ValueError as e:
            bad.append(f"affected: {e}")
    return [f"{f.get('id')}: {b}" for b in bad]


def validate_report(name: str, blocks: dict, item: dict, ctx: dict) -> list[str]:
    """위반 사유 목록(빈 목록 = 유효). ctx = {"n", "targets", "axis_lines": {axis: [Range]}}."""
    bad = [f"{b} 블록 없음" for b in BLOCKS if b not in blocks]
    ctx = {**ctx, "own": [to_range(r, ctx) for r in item["ranges"]]}
    ids = set()
    for line in blocks.get("findings", []):
        try:
            f = json.loads(line)
        except ValueError:
            bad.append(f"JSON 아님: {line[:80]!r}")
            continue
        bad += validate_finding(f, name, item["axis"], ctx)
        fid = f.get("id") if isinstance(f, dict) else None
        if not isinstance(fid, str):
            continue
        if fid in ids:
            bad.append(f"id 중복 {fid!r}")
        ids.add(fid)
    for line in blocks.get("coverage", []):
        try:
            to_range(line, ctx)
        except ValueError as e:
            bad.append(f"coverage: {e}")
    return bad


def lines_of(rs: list[Range]) -> set[tuple[int, int]]:
    return {(i, k) for i, a, b in rs for k in range(a, b + 1)}


def runs(lines: set[tuple[int, int]]) -> list[Range]:
    """줄 집합 → 연속 구간(targets 순서)."""
    out: list[list[int]] = []
    for i, k in sorted(lines):
        if out and out[-1][0] == i and out[-1][2] == k - 1:
            out[-1][2] = k
        else:
            out.append([i, k, k])
    return [(i, a, b) for i, a, b in out]


def fmt_lines(lines: set[tuple[int, int]], n: int, targets: list[dict]) -> list[str]:
    return [fmt_range(n, targets[i - 1]["snapshot"], a, b) for i, a, b in runs(lines)]


# ---- check(4.5.1·D22) ----

def run_check(cmd: str, cwd: Path, tree: Path, timeout: float = 30) -> tuple[int | None, str]:
    """(exit code, stdout+stderr 마지막 2000자). 시간 초과 = (None, "timeout")."""
    try:
        p = subprocess.run(["bash", "-c", cmd], cwd=cwd, env={**os.environ, "TREE": str(tree)},
                           capture_output=True, text=True, errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "timeout"
    return p.returncode, (p.stdout + p.stderr)[-2000:]


_MASKERS = frozenset({"cut", "sed", "sort", "uniq", "head", "tail", "tr", "tee", "cat", "wc", "column", "nl", "fold",
                      "paste", "xargs"})   # 입력이 비어도(결함 없음) 0 으로 끝나는 필터


def masked_exit(cmd: str) -> list[str]:
    """종료코드 가림: 파이프라인의 종료코드로 분기(`&&`·`||`·`if`/`while` 조건)하는데 그 파이프라인이 `_MASKERS` 필터로 끝난다.
    bash 파이프라인의 종료코드는 마지막 명령의 것이라 `grep … | cut … && exit 1` 은 결함 유무와 무관하게 exit 1 이다 —
    스냅샷 재현(verify_check)은 통과하고 고친 뒤 C6 에서 늘 실패한다(2026-10-11 실측). `pipefail` 은 반대 형태
    (`grep … | awk '…END{exit …}'` 처럼 마지막 명령이 판정하는데 grep 이 빈 결과)를 뒤집어 쓰지 않는다(DECISIONS).
    따옴표 안의 `|` 는 shlex 가 단어로 묶는다. 해석할 수 없는 명령은 판정하지 않는다(빈 목록)."""
    import shlex
    lx = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()<>")
    lx.whitespace_split = True
    try:
        toks = list(lx)
    except ValueError:
        return []
    out: list[str] = []
    pipes, last, start, cond = 0, None, True, False
    pending = None          # `if 파이프라인;` 의 조건 — 다음 토큰이 then·do 면 그 조건이 분기를 정한다
    skip = False
    for t in toks:
        if skip:            # 리다이렉션 대상
            skip = False
            continue
        if t in ("then", "do") and pending:
            if pending[0] and pending[1] in _MASKERS:
                out.append(f"`{pending[1]}` 로 끝나는 파이프라인이 `{t}` 분기를 정한다")
            pending = None
            pipes, last, start, cond = 0, None, True, False
            continue
        pending = None
        if t == "|":
            pipes, start = pipes + 1, True
            continue
        if t in ("&&", "||") or (t in ("then", "do") and cond):
            if pipes and last in _MASKERS:
                out.append(f"`{last}` 로 끝나는 파이프라인이 `{t}` 분기를 정한다")
            pipes, last, start, cond = 0, None, True, False
            continue
        if set(t) <= set(";&|()<>"):
            if set(t) & set("<>") and not set(t) & set(";()|"):
                skip = True                     # `>`·`2>&`·`>>` 리다이렉션: 대상 토큰을 건너뛰고 같은 명령을 계속
                continue
            if t == ";" and cond:
                pending = (pipes, last)
            pipes, last, start, cond = 0, None, True, False   # `;`·`(`·`);`·`)&&` 등 명령 경계 — 보수적으로 초기화
            continue
        if start:
            if t in ("if", "while", "until", "elif"):
                cond, pipes, last = True, 0, None
                continue
            if t == "!" or ("=" in t and not t.startswith("=")):    # 부정·앞에 붙은 변수 대입
                continue
            last, start = t.rsplit("/", 1)[-1], False
    return out


def check_text(code: int | None, out: str) -> str:
    """finish `failed[].output` 형식: `exit <code>` 한 줄 + 출력."""
    return f"exit {'timeout' if code is None else code}\n{out}"


def restore_snapshots(ws: Path) -> None:
    """verify_check가 중단돼 남은 `round-*/snapshot.verifying`을 되돌린다. 짝 `snapshot`이 이미 있으면 추측하지 않고 중단."""
    for hid in sorted(ws.glob("round-*/snapshot.verifying")):
        snap = hid.with_name("snapshot")
        if snap.exists():
            die(f"snapshot 복구 불가: {snap}와 {hid}가 둘 다 있다 — 확인 후 수동 정리 필요")
        hid.rename(snap)


def verify_check(ws: Path, R: Path, targets: list[dict], tree: Path, f: dict) -> list[str]:
    """C3 ②: R/snapshot 사본과 빈 줄 사본(각 파일 앞에 그 줄 수만큼 빈 줄) 양쪽에서 exit 1이어야 한다.
    실행 동안 W의 스냅샷 디렉토리를 숨긴다 — 스냅샷 절대경로를 읽는 check가 두 사본을 우회해 통과하지 못하게."""
    restore_snapshots(ws)
    shift = tmproot() / "spec-audit" / ws.name / "shift"
    shutil.rmtree(shift, ignore_errors=True)
    dirs = (shift / "copy", shift / "blank")
    for d in dirs:
        d.mkdir(parents=True)
    for t in targets:
        data = (R / "snapshot" / t["snapshot"]).read_bytes()
        (dirs[0] / t["snapshot"]).write_bytes(data)
        (dirs[1] / t["snapshot"]).write_bytes(b"\n" * t["lines"] + data)
    hidden: list[Path] = []
    try:
        for snap in sorted(ws.glob("round-*/snapshot")):
            snap.rename(snap.with_name("snapshot.verifying"))
            hidden.append(snap)
        codes = [run_check(f["check"], d, tree)[0] for d in dirs]
    finally:
        errs = []
        for snap in hidden:
            try:
                snap.with_name("snapshot.verifying").rename(snap)
            except OSError as e:
                errs.append(f"{snap}: {e}")
        if errs:
            raise RuntimeError("snapshot 복구 실패: " + "; ".join(errs))
    if codes == [1, 1]:
        return []
    return [f"{f['id']}: check 재현 실패(snapshot 사본 exit {codes[0]}, 빈 줄 사본 exit {codes[1]} — 둘 다 1이어야 함)"]


def make_retry(ws: Path, n: int, item: dict, targets: list[dict], violations: list[str]) -> dict:
    """C8 retry 항목 생성 — 같은 범위, 프롬프트(직전 위반 사유 포함)·X, assign.json에 추가."""
    R = ws / f"round-{n}"
    tree = Path(json.loads((R / "targets.json").read_text(encoding="utf-8"))["tree"])
    name = item["name"] + "-retry"
    retry = {**item, "name": name, "prompt": None, "exec_dir": None}
    if item["axis"] in EXEC_AXES:
        x = make_exec_dir(tree, tmproot() / "spec-audit" / ws.name / f"r{n}" / name)
        retry["exec_dir"] = str(x) if x else None
    retry["prompt"] = str(write_prompt(ws, retry, targets, n, tuple(violations)))
    aj = R / "assign.json"
    agents = json.loads(aj.read_text(encoding="utf-8"))["agents"] + [retry]
    aj.write_text(json.dumps({"agents": agents}, ensure_ascii=False, indent=1), encoding="utf-8")
    return retry


def _cell(x: object) -> str:
    return str(x).replace("|", "\\|").replace("\n", " ")


def cmd_aggregate(ws: Path) -> tuple[int, dict]:
    """C3: 가장 큰 라운드의 보고를 검증·집계하고 aggregate.json·aggregate.md를 쓴다."""
    ensure_not_aborted(ws)
    restore_snapshots(ws)
    n = max(rounds(ws), default=0)
    R = ws / f"round-{n}"
    if not (R / "assign.json").is_file():
        die(f"assign.json 없음: {R / 'assign.json'}")
    tj = json.loads((R / "targets.json").read_text(encoding="utf-8"))
    targets = tj["targets"]
    # ① 대상 변경 탐지(4.5.5)
    changed = [t["rel"] for t in targets if not Path(t["path"]).is_file()
               or hashlib.sha256(Path(t["path"]).read_bytes()).hexdigest() != t["sha256"]]
    if changed:
        close_open(ws)
        return 3, {"target_modified": changed}
    # ② 보고 검증 — retry 항목이 있으면 그것이 유효 감사자(원래 보고 무시, 재retry 없음)
    ctx = {"n": n, "targets": targets, "axis_lines": {ax: axis_lines(targets, ax) for ax in AXES}}
    tree = Path(tj["tree"])
    agents = json.loads((R / "assign.json").read_text(encoding="utf-8"))["agents"]
    by_name = {a["name"]: a for a in agents}
    invalid, valid = [], []
    for orig in (a for a in agents if not a["name"].endswith("-retry")):
        item = by_name.get(orig["name"] + "-retry", orig)
        p = R / "reports" / f"{item['name']}.md"
        blocks: dict = {}
        if not p.is_file():
            bad = ["보고 파일 없음"]
        else:
            try:
                blocks = parse_report(p.read_text(encoding="utf-8"))
                bad = validate_report(item["name"], blocks, item, ctx)
                if not bad:  # 형식이 유효할 때만 check 실행(C3 ②)
                    for l in blocks["findings"]:
                        f = json.loads(l)
                        if f["check"] is not None:
                            bad += [f"{f['id']}: check 종료코드 가림 — {m}(판정 명령의 종료코드로 분기할 것)"
                                    for m in masked_exit(f["check"])]
                            bad += verify_check(ws, R, targets, tree, f)
            except (OSError, UnicodeDecodeError) as e:
                bad = [f"보고 읽기 실패: {e}"]
        if bad:
            retry = None if item is not orig else make_retry(ws, n, orig, targets, bad)
            invalid.append({"reason": f"{item['name']}: " + "; ".join(bad), "retry": retry})
        else:
            valid.append((item, blocks))
    if invalid:
        return 3, {"invalid": invalid}
    # ③ 집계
    findings = []
    assigned: dict[str, set] = {}
    covered: dict[str, set] = {}
    for item, blocks in valid:
        fs = [json.loads(l) for l in blocks["findings"]]
        findings += fs
        own = lines_of([to_range(r, ctx) for r in item["ranges"]])
        cov = lines_of([to_range(r, ctx) for r in blocks["coverage"]]) & own
        cov -= lines_of([to_range(f["target"], ctx) for f in fs if f["unverified_reason"] == "context"])
        assigned.setdefault(item["axis"], set()).update(own)
        covered.setdefault(item["axis"], set()).update(cov)
    gap = {ax: fmt_lines(assigned[ax] - covered[ax], n, targets) for ax in assigned if assigned[ax] - covered[ax]}
    counts = {"fail": sum(f["verdict"] == "fail" for f in findings),
              "unverified": sum(f["verdict"] == "unverified" and f["unverified_reason"] != "context"
                                for f in findings)}
    out = {"findings": findings, "review_gap": gap, "counts": counts}
    (R / "aggregate.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    gap_lines = sum(b - a + 1 for rs in gap.values() for r in rs for _, _, a, b in [parse_range(r)])
    md = [f"# SPEC Audit · round {n}{' (수정분 재검토)' if n == REVIEW else ''} · 지적 {counts['fail'] + counts['unverified']}건",
          f"대상: {', '.join(t['rel'] for t in targets)} · 플러그인 {tj['plugin_version']} · "
          f"감사자: {', '.join(a['name'] for a in agents)}",
          f"fail {counts['fail']} · unverified {counts['unverified']} · 미검토 {gap_lines}줄",
          "",
          "| id | 판정 | 축 | 위치 | 주장 | 근거 | 권고 | 영향 위치 |",
          "|---|---|---|---|---|---|---|---|"]
    for f in findings:
        if f["unverified_reason"] == "context":
            continue
        cells = [f["id"], f["verdict"], f["axis"], f["target"], f["claim"], f["evidence"], f["recommended"],
                 ", ".join(f["affected"])]
        md.append("| " + " | ".join(_cell(x) for x in cells) + " |")
    (R / "aggregate.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    close_open(ws)
    return 0, {}


# ---- finish(D23) ----

def run_checks(ws: Path, tj: dict, findings: list[dict]) -> list[dict]:
    """findings의 check를 현재 대상 파일 사본 K(스냅샷과 같은 파일 이름)에서 실행. exit 0이 아니면 실패."""
    K = tmproot() / "spec-audit" / ws.name / "check"
    shutil.rmtree(K, ignore_errors=True)
    K.mkdir(parents=True)
    for t in tj["targets"]:
        if Path(t["path"]).is_file():
            shutil.copyfile(t["path"], K / t["snapshot"])
    failed = []
    for f in findings:
        code, text = run_check(f["check"], K, Path(tj["tree"]))
        if code != 0:
            failed.append({"id": f["id"], "claim": f["claim"], "output": check_text(code, text)})
    return failed


def cmd_finish(ws: Path, dpath: Path) -> tuple[int, dict]:
    """D23 끝 판정. 모든 라운드의 지적에 처분 ∧ 반영한 지적의 check 통과 ∧ 라운드 1 뒤 고쳤으면 라운드 2 집계 완료.
    완료면 합격 기록을 현재 내용 sha로 쓴다(C11)."""
    restore_snapshots(ws)
    ns = [n for n in rounds(ws) if (ws / f"round-{n}" / "aggregate.json").is_file()]
    if 1 not in ns:
        die(f"라운드 1 aggregate.json 없음 — C3 먼저: {ws / 'round-1' / 'aggregate.json'}")
    tj = json.loads((ws / "round-1" / "targets.json").read_text(encoding="utf-8"))
    try:
        disp = json.loads(dpath.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        die(f"처분 파일을 읽지 못함: {e}")
    items = disp.get("findings", {}) if isinstance(disp, dict) else None
    if not isinstance(items, dict):
        items, bad_shape = {}, ["처분 파일 형식: {\"findings\": {\"<id>\": {\"d\", \"why\"}}} 객체여야 한다"]
    else:
        bad_shape = []
    need = {f["id"]: f for n in ns
            for f in json.loads((ws / f"round-{n}" / "aggregate.json").read_text(encoding="utf-8"))["findings"]
            if f["unverified_reason"] != "context"}
    invalid = bad_shape + [f"{i}: 처분 없음" for i in need if i not in items]
    for i, d in items.items():
        if i not in need:
            invalid.append(f"{i}: 이 감사의 지적이 아님")
        elif not isinstance(d, dict) or d.get("d") not in DISPOSITIONS:
            invalid.append(f"{i}: 처분은 {'|'.join(DISPOSITIONS)} 중 하나")
        elif d["d"] != "apply" and not d.get("why"):
            invalid.append(f"{i}: {DISPOSITIONS[d['d']]} 사유(why) 없음")
    applied = [need[i] for i, d in items.items()
               if i in need and isinstance(d, dict) and d.get("d") == "apply" and need[i]["check"]]
    failed = run_checks(ws, tj, applied)
    # 재검토할 줄이 실제로 있을 때만 라운드 2를 요구한다 — 파일을 비우거나 지우면 C2가 배정할 줄이 없다
    review_needed = REVIEW not in ns and any(
        Path(t["path"]).is_file()
        and changed_lines(_lines(ws / "round-1" / "snapshot" / t["snapshot"]), _lines(Path(t["path"])))
        for t in tj["targets"])
    done = not (invalid or failed or review_needed)
    out = {"done": done, "invalid": invalid, "failed": failed, "review_needed": review_needed}
    md = [f"# SPEC Audit · {'완료' if done else '미완'}",
          f"라운드 {', '.join(map(str, ns))} · 처분 {sum(i in items for i in need)}/{len(need)} · check 실패 {len(failed)}"
          + (" · 수정분 재검토 필요(C2)" if review_needed else ""), "",
          "| id | 처분 | 사유 | 주장 |", "|---|---|---|---|"]
    for i, f in need.items():
        d = items.get(i)
        d = d if isinstance(d, dict) else {}
        md.append("| " + " | ".join(_cell(x) for x in
                                     [i, DISPOSITIONS.get(str(d.get("d")), "없음"), d.get("why", ""), f["claim"]]) + " |")
    last = ws / f"round-{max(ns)}"
    (last / "result.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (last / "result.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    plan = next((t for t in tj["targets"] if t["role"] == "plan"), None)
    if done and plan and Path(plan["path"]).is_file():
        cur = [{"path": t["path"], "sha256": hashlib.sha256(Path(t["path"]).read_bytes()).hexdigest()}
               for t in tj["targets"] if t["role"] in ("plan", "spec") and Path(t["path"]).is_file()]
        rec = {"plan": plan["path"], "targets": cur, "ws": str(ws), "plugin_version": tj["plugin_version"]}
        f = pass_record_path(next(c["sha256"] for c in cur if c["path"] == plan["path"]))
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return (0 if done else 1), out


def cmd_clean(ws: Path) -> None:
    """C5: 열린 감사를 끝내면 중단 표시(W/aborted)를 남긴다."""
    if open_path(ws).exists() and ws.is_dir():
        (ws / ABORTED).touch()
    shutil.rmtree(tmproot() / "spec-audit" / ws.name, ignore_errors=True)


def cmd_gate(plan: Path) -> tuple[int, str]:
    """C11: 이 계획 내용으로 감사를 끝냈고(finish 완료) 그 뒤 spec이 그대로인지."""
    sha = hashlib.sha256(plan.read_bytes()).hexdigest()
    f = pass_record_path(sha)
    if not f.is_file():
        return 1, "감사 완료 기록 없음 — 이 계획 내용으로 spec-audit finish를 끝낸 적이 없다(완료 뒤 계획이 바뀌었으면 finish를 다시 실행)"
    rec = json.loads(f.read_text(encoding="utf-8"))
    for t in rec["targets"]:
        if t["path"] == rec["plan"]:
            continue
        p = Path(t["path"])
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != t["sha256"]:
            return 1, f"{t['path']}가 감사 완료 뒤 바뀌었다 — finish를 다시 실행"
    return 0, ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="audit_ws.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--skill-version")
    p.add_argument("--plan", action="append")
    p.add_argument("--spec", action="append")
    p.add_argument("--tree")
    for name in ("review", "aggregate", "clean"):
        sub.add_parser(name).add_argument("--ws", required=True)
    p = sub.add_parser("finish")
    p.add_argument("--ws", required=True)
    p.add_argument("--dispositions", required=True)
    p = sub.add_parser("gate")
    p.add_argument("plan")
    a = ap.parse_args(argv)
    if a.cmd == "gate":
        rc, msg = cmd_gate(Path(a.plan))
        if msg:
            print(msg, file=sys.stderr)
        return rc
    if a.cmd == "clean":
        cmd_clean(Path(a.ws).resolve())
        return 0
    rc = 0
    if a.cmd == "aggregate":
        rc, out = cmd_aggregate(Path(a.ws).resolve())
    elif a.cmd == "finish":
        rc, out = cmd_finish(Path(a.ws).resolve(), Path(a.dispositions))
    elif a.cmd == "review":
        out = cmd_review(Path(a.ws).resolve())
    else:
        out = cmd_init(a)
    print(json.dumps(out, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    sys.exit(main())
