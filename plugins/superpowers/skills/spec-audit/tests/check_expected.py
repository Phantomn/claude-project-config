"""수용 시험 판정기(7.3): EXPECTED.md 문법을 fixture 저장소의 감사 산출물과 대조한다.

사용: check_expected.py <EXPECTED.md> <fixture 저장소 디렉토리>  → exit 0 일치 / 1 불일치.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import audit_ws  # noqa: E402

LOG_HEAD = ["| F | 결과 | 최종 action | 라운드 수 | 라운드1 fail | 라운드1 unverified | 라운드1 class |",
            "|---|---|---|---|---|---|---|"]
_RULE_RE = re.compile(r"^round (\d+) (must|must_not): (.+?) @ (.+)$")
_HEADER_RE = re.compile(r"^round (\d+) header_contains: (.+)$")


def _loc(s: str) -> tuple[str, int, int]:
    rel, sep, rng = s.strip().rpartition(":")
    m = re.fullmatch(r"(\d+)(?:-(\d+))?", rng)
    if not sep or not rel or not m:
        raise ValueError(f"위치 형식 위반: {s!r}")
    a = int(m.group(1))
    return rel, a, int(m.group(2) or a)


def parse_expected(text: str) -> dict:
    out: dict = {"targets": [], "rules": [], "header": [], "outcome": "any"}
    outcome_seen = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("targets:"):
            out["targets"] = line[len("targets:"):].split()
        elif line.startswith("outcome:"):
            v = line[len("outcome:"):].strip()
            if v not in ("pass", "any"):
                raise ValueError(f"outcome 값 위반: {v!r}")
            out["outcome"], outcome_seen = v, True
        elif m := _HEADER_RE.match(line):
            out["header"].append((int(m.group(1)), m.group(2).strip()))
        elif m := _RULE_RE.match(line):
            out["rules"].append((int(m.group(1)), m.group(2), m.group(3).strip().split("|"),
                                 [_loc(x) for x in m.group(4).split(",")]))
        else:
            raise ValueError(f"문법 위반: {line!r}")
    if not out["targets"]:
        raise ValueError("targets 줄 없음")
    return out


def _workspace(exp: dict, repo: Path) -> Path:
    tree = repo.resolve()
    plan, specs = None, []
    for rel in exp["targets"]:
        role = audit_ws.role_of(Path(rel))
        if role == "plan":
            plan = tree / rel
        elif role == "spec":
            specs.append(tree / rel)
    return audit_ws.workspace(tree, plan, specs)


def _load(p: Path) -> dict:
    return json.loads(p.read_text())


def _hits(f: dict, n: int, snap_rel: dict[str, str], rel: str, a: int, b: int) -> bool:
    for s in [f["target"], *f.get("affected", [])]:
        rn, snap, x, y = audit_ws.parse_range(s)
        if rn == n and snap_rel.get(snap) == rel and x <= b and a <= y:
            return True
    return False


def check(expected: Path, repo: Path) -> list[str]:
    exp = parse_expected(expected.read_text())
    W = _workspace(exp, repo)
    bad: list[str] = []
    for n, kind, classes, locs in exp["rules"]:
        R = W / f"round-{n}"
        try:
            snap_rel = {t["snapshot"]: t["rel"] for t in _load(R / "targets.json")["targets"]}
            findings = _load(R / "aggregate.json")["findings"]
        except (OSError, ValueError, KeyError):
            bad.append(f"round {n}: 산출물 없음")
            continue
        unv = "*unverified" in classes
        found = any(
            (f["class"] in classes or (unv and f["verdict"] == "unverified"))
            and any(_hits(f, n, snap_rel, *loc) for loc in locs)
            for f in findings)
        label = f"round {n} {kind}: {'|'.join(classes)} @ " + ", ".join(
            f"{r}:{a}-{b}" for r, a, b in locs)
        if kind == "must" and not found:
            bad.append(f"{label} — 일치 finding 없음")
        if kind == "must_not" and found:
            bad.append(f"{label} — 위반 finding 있음")
    for n, text in exp["header"]:
        try:
            head = "\n".join((W / f"round-{n}" / "aggregate.md").read_text().splitlines()[:3])
        except OSError:
            bad.append(f"round {n} header_contains: aggregate.md 없음")
            continue
        if text not in head:
            bad.append(f"round {n} header_contains: {text!r} — 첫 세 줄에 없음")
    if exp["outcome"] == "pass" and _final_action(W) != "pass":
        bad.append(f"outcome: pass — 최종 action {_final_action(W)!r}")
    return bad


def _rounds(W: Path) -> list[Path]:
    return sorted(W.glob("round-*"), key=lambda p: int(p.name.split("-")[1])) if W.is_dir() else []


def _final_action(W: Path) -> str:
    rs = _rounds(W)
    try:
        return _load(rs[-1] / "decision.json")["action"] if rs else "none"
    except (OSError, ValueError, KeyError):
        return "none"


def _log_row(expected: Path, repo: Path, ok: bool) -> str:
    try:
        W = _workspace(parse_expected(expected.read_text()), repo)
    except ValueError:
        W = repo / ".none"
    fail = unv = 0
    classes: set[str] = set()
    try:
        agg = _load(W / "round-1" / "aggregate.json")
        fail, unv = agg["counts"]["fail"], agg["counts"]["unverified"]
        classes = {f["class"] for f in agg["findings"]}
    except (OSError, ValueError, KeyError):
        pass
    cells = [expected.resolve().parent.name, "일치" if ok else "불일치", _final_action(W),
             str(len(_rounds(W))), str(fail), str(unv), ",".join(sorted(classes))]
    return "| " + " | ".join(cells) + " |"


def main(argv: list[str]) -> int:
    expected, repo = Path(argv[0]), Path(argv[1])
    try:
        bad = check(expected, repo)
    except ValueError as e:
        bad = [str(e)]
    log = expected.resolve().parent.parent / "ACCEPTANCE-LOG.md"
    new = not log.exists()
    with log.open("a") as fh:
        if new:
            fh.write("\n".join(LOG_HEAD) + "\n")
        fh.write(_log_row(expected, repo, not bad) + "\n")
    for b in bad:
        print(b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
