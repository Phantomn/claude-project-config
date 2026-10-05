#!/usr/bin/env python3
"""spec-audit 작업 공간 도구 (stdlib only, Python 3.10+)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

Z = 1500
CAP = 5
AXES = ("refs", "selfcontained", "rootcause", "oracle")
EXEC_AXES = AXES[1:]

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


# ---- 위치(4.2) ----

HERE = Path(__file__).resolve()
SKILL_MD = HERE.parents[1] / "SKILL.md"
AUDITORS = HERE.parents[1] / "auditors"
PLUGIN_JSON = HERE.parents[3] / ".claude-plugin" / "plugin.json"


def die(msg: str) -> None:
    raise SystemExit(msg)


def tmproot() -> Path:
    return Path(os.environ.get("SUPERPOWERS_AUDIT_TMPROOT") or f"/tmp/claude-{os.getuid()}")


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


# ---- 라운드 구성(4.6) ----

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
    arc.stdout.close()
    if arc.wait() != 0 or tar.returncode != 0:
        shutil.rmtree(x)
        return None
    return x


def write_prompt(ws: Path, item: dict, targets: list[dict], n: int) -> Path:
    R = ws / f"round-{n}"
    tree = json.loads((R / "targets.json").read_text())["tree"]
    lines = ["", "## 배정", "",
             f"- 작업공간 W: {ws}", f"- 라운드: {n}", f"- 이름: {item['name']} · 축: {item['axis']}",
             f"- <tree>: {tree}", "- 배정 범위(W 기준):", *[f"  - {r}" for r in item["ranges"]],
             "- recheck: " + (", ".join(item["recheck"]) or "없음"), "- 대상 스냅샷:",
             *[f"  - {R / 'snapshot' / t['snapshot']} · role {t['role']} · rel {t['rel']}" for t in targets]]
    if item["axis"] in EXEC_AXES:
        if item["exec_dir"]:
            lines.append(f"- 실행 디렉토리 X: {item['exec_dir']}")
        else:
            lines.append("- 실행 디렉토리 X: 없음(생성 실패) — 실행 검증은 `unverified(tool)`")
    if n >= 2:
        lines += [f"- scope.json: {R / 'scope.json'}",
                  f"- 직전 aggregate.json: {ws / f'round-{n - 1}' / 'aggregate.json'}",
                  f"- diff.patch: {R / 'diff.patch'}"]
    lines.append(f"- 보고 경로: {R / 'reports' / (item['name'] + '.md')}")
    text = (AUDITORS / "common.md").read_text() + (AUDITORS / f"{item['axis']}.md").read_text()
    p = R / "prompts" / f"{item['name']}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text + "\n".join(lines) + "\n")
    return p


def build_round(ws: Path, n: int, targets: list[dict], ranges: dict[str, list[Range]],
                recheck: dict[str, list[str]]) -> dict:
    """ranges = 축별 배정 범위(샤드 전), recheck = 감사자 이름 → id. assign.json·prompts·X 생성, C8 반환."""
    R = ws / f"round-{n}"
    tree = Path(json.loads((R / "targets.json").read_text())["tree"])
    agents = []
    for axis in AXES:
        for k, sh in enumerate(shard(ranges.get(axis, [])), 1):
            name = f"{axis}-r{n}-s{k}"
            item = {"name": name, "axis": axis, "prompt": None, "exec_dir": None,
                    "ranges": [fmt_range(n, targets[i - 1]["snapshot"], a, b) for i, a, b in sh],
                    "recheck": recheck.get(name, [])}
            if axis in EXEC_AXES:
                x = make_exec_dir(tree, tmproot() / "spec-audit" / ws.name / f"r{n}" / name)
                item["exec_dir"] = str(x) if x else None
            item["prompt"] = str(write_prompt(ws, item, targets, n))
            agents.append(item)
    (R / "reports").mkdir(parents=True, exist_ok=True)
    (R / "assign.json").write_text(json.dumps({"agents": agents}, ensure_ascii=False, indent=1))
    return {"ws": str(ws), "agents": agents}


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
    tj = {"tree": str(tree), "plugin_version": json.loads(PLUGIN_JSON.read_text())["version"], "targets": targets}
    (R / "targets.json").write_text(json.dumps(tj, ensure_ascii=False, indent=1))
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
    for line in doc.read_text(errors="replace").splitlines():
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


def cmd_init_round1(a: argparse.Namespace) -> dict:
    if a.skill_version != skill_hash():
        die("스킬 버전 불일치: `/reload-plugins`(A2 불성립이면 세션 재시작) 필요")
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
    for d in (ws, tmproot() / "spec-audit" / ws.name):
        shutil.rmtree(d, ignore_errors=True)
    ws.mkdir(parents=True)
    (ws.parent / ".gitignore").write_text("*\n")
    exclude = {p for p in [plan, *specs] if p}
    canon = sorted({c for p in exclude for c in collect_canon(p, tree, exclude)}, key=str)
    docs = ([(plan, "plan")] if plan else []) + [(s, "spec") for s in specs] + [(c, "other") for c in canon]
    targets = snapshot_targets(ws / "round-1", tree, docs)
    ranges = {ax: axis_lines(targets, ax) for ax in AXES}
    if not any(t["role"] == "spec" and oracle_needed(Path(t["path"]).read_text()) for t in targets):
        ranges["oracle"] = []
    return build_round(ws, 1, targets, ranges, {})


# ---- C3 aggregate(4.5·4.7) ----

CLASSES = {"ref-missing", "ref-mismatch", "exec-fail", "oracle-deviation", "cross-doc-conflict", "sync-miss",
           "ordering", "interface-mismatch", "constraint-drift", "contract-gap", "placeholder",
           "unverifiable-step", "assumption-form", "premise", "root-cause", "regression", "security",
           "concurrency", "under-scope", "over-scope", "requirement-uncovered", "oracle-missing", "rule-violation"}
KEYS = ("id", "verdict", "axis", "class", "target", "claim", "evidence", "recommended", "fix_class",
        "affected", "unverified_reason", "check")
REASONS = {"policy", "external", "tool", "context"}
BLOCKS = ("findings", "coverage", "resolved")
_FENCE_RE = re.compile(r"^```(\w+)\n(.*?)^```$", re.M | re.S)


def parse_report(text: str) -> dict[str, list[str]]:
    """블록 이름 → 비어 있지 않은 줄. findings·coverage·resolved 외 펜스는 무시."""
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
    want = REASONS if f["verdict"] == "unverified" else {None}
    if f["unverified_reason"] not in want:
        bad.append(f"verdict {f['verdict']!r}에 unverified_reason {f['unverified_reason']!r}")
    try:
        if not overlaps([to_range(f["target"], ctx)], ctx["axis_lines"][axis]):
            bad.append(f"target {f['target']!r}이 {axis} 축의 대상 줄과 겹치지 않음")
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
    bad = [f"{b} 블록 없음" for b in ("findings", "coverage") if b not in blocks]
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


def fmt_lines(lines: set[tuple[int, int]], n: int, targets: list[dict]) -> list[str]:
    """줄 집합 → 연속 구간 범위 문자열(targets 순서)."""
    out: list[list[int]] = []
    for i, k in sorted(lines):
        if out and out[-1][0] == i and out[-1][2] == k - 1:
            out[-1][2] = k
        else:
            out.append([i, k, k])
    return [fmt_range(n, targets[i - 1]["snapshot"], a, b) for i, a, b in out]


def make_retry(ws: Path, n: int, item: dict, targets: list[dict]) -> dict:
    """C8 retry 항목 생성 — 같은 범위·recheck, 프롬프트·X, assign.json에 추가."""
    R = ws / f"round-{n}"
    tree = Path(json.loads((R / "targets.json").read_text())["tree"])
    name = item["name"] + "-retry"
    retry = {**item, "name": name, "prompt": None, "exec_dir": None}
    if item["axis"] in EXEC_AXES:
        x = make_exec_dir(tree, tmproot() / "spec-audit" / ws.name / f"r{n}" / name)
        retry["exec_dir"] = str(x) if x else None
    retry["prompt"] = str(write_prompt(ws, retry, targets, n))
    aj = R / "assign.json"
    agents = json.loads(aj.read_text())["agents"] + [retry]
    aj.write_text(json.dumps({"agents": agents}, ensure_ascii=False, indent=1))
    return retry


def cmd_aggregate(ws: Path, n: int) -> tuple[int, dict]:
    R = ws / f"round-{n}"
    targets = json.loads((R / "targets.json").read_text())["targets"]
    # ① 대상 변경 탐지(4.5.5)
    changed = [t["rel"] for t in targets if not Path(t["path"]).is_file()
               or hashlib.sha256(Path(t["path"]).read_bytes()).hexdigest() != t["sha256"]]
    if changed:
        return 3, {"target_modified": changed}
    # ② 보고 검증 — retry 항목이 있으면 그것이 유효 감사자(원래 보고 무시, 재retry 없음)
    ctx = {"n": n, "targets": targets, "axis_lines": {ax: axis_lines(targets, ax) for ax in AXES}}
    agents = json.loads((R / "assign.json").read_text())["agents"]
    by_name = {a["name"]: a for a in agents}
    invalid, valid = [], []
    for orig in (a for a in agents if not a["name"].endswith("-retry")):
        item = by_name.get(orig["name"] + "-retry", orig)
        p = R / "reports" / f"{item['name']}.md"
        if not p.is_file():
            bad = ["보고 파일 없음"]
        else:
            try:
                blocks = parse_report(p.read_text(encoding="utf-8"))
                bad = validate_report(item["name"], blocks, item, ctx)
            except (OSError, UnicodeDecodeError) as e:
                bad = [f"보고 읽기 실패: {e}"]
        if bad:
            retry = None if item is not orig else make_retry(ws, n, orig, targets)
            invalid.append({"reason": f"{item['name']}: " + "; ".join(bad), "retry": retry})
        else:
            valid.append((item, blocks))
    if invalid:
        return 3, {"invalid": invalid}
    # ③ 집계
    findings, unresolved = [], []
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
        unresolved += [m.group(1) for l in blocks.get("resolved", [])
                       if (m := re.match(r"^(\S+): unresolved\b", l))]
    gap = {ax: fmt_lines(assigned[ax] - covered[ax], n, targets) for ax in assigned if assigned[ax] - covered[ax]}
    counts = {"fail": sum(f["verdict"] == "fail" for f in findings),
              "unverified": sum(f["verdict"] == "unverified" and f["unverified_reason"] != "context"
                                for f in findings)}
    out = {"findings": findings, "review_gap": gap, "unresolved": unresolved, "counts": counts}
    (R / "aggregate.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return 0, {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="audit_ws.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--round", type=int, required=True)
    p.add_argument("--ws")
    p.add_argument("--skill-version")
    p.add_argument("--plan", action="append")
    p.add_argument("--spec", action="append")
    p.add_argument("--tree")
    p = sub.add_parser("aggregate")
    p.add_argument("--ws", required=True)
    p.add_argument("--round", type=int, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "aggregate":
        rc, out = cmd_aggregate(Path(a.ws).resolve(), a.round)
        print(json.dumps(out, ensure_ascii=False))
        return rc
    if a.round != 1:
        die("init --round N(N≥2)은 아직 구현되지 않음")
    out = cmd_init_round1(a)
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
