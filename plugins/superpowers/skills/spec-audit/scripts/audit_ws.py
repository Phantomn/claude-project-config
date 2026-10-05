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
    docs = ([(plan, "plan")] if plan else []) + [(s, "spec") for s in specs]
    targets = snapshot_targets(ws / "round-1", tree, docs)
    ranges = {ax: axis_lines(targets, ax) for ax in AXES}
    if not any(t["role"] == "spec" and oracle_needed(Path(t["path"]).read_text()) for t in targets):
        ranges["oracle"] = []
    return build_round(ws, 1, targets, ranges, {})


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
    a = ap.parse_args(argv)
    if a.round != 1:
        die("init --round N(N≥2)은 아직 구현되지 않음")
    out = cmd_init_round1(a)
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
