#!/usr/bin/env python3
"""replay_corpus.py — 과거 세션 기록의 Bash 명령을 새 판정기로 다시 판정해 오탐·속도·오류를 집계한다 (spec §8 전수 재생, SC3).

★왜: 재구성 사례만으로는 현실 명령의 부당 거부를 다 못 본다 — 로컬 기록 전부를 판정해 사람이 거부 목록을 검토한다.
계약: replay_corpus.py --projects <dir> --out <dir> [--limit N]
  입력: <projects>/**/*.jsonl 의 assistant tool_use(name == "Bash").input.command 와 그 레코드의 cwd. 명령 문자열 기준 중복 제거.
  판정: bash_guard.judge 를 프로세스 안에서 직접 부른다(명령 자체는 실행하지 않는다). transcript·session_id 없음(§8 재생 문맥).
  environ: 실제 환경 + XDG_STATE_HOME=<out>/state, HARNESS_BASH_GUARD=on — 장부·기록이 실제 상태 폴더에 닿지 않게.
  출력(<out> 아래만): summary.json, denies.jsonl, errors.jsonl. 명령 원문이 들어 있으니 저장소·PR 에 옮기지 말 것.
종료: 0 정상, 2 --out 이 이 저장소 작업 트리 안.
테스트: python3 hooks/tests/test_replay_corpus.py
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "scripts"))
import bash_guard
from policy import KIND_TEXT

CMD_CAP = 500
_KIND_BY_TEXT = {f" — {text}.": kind for kind, text in KIND_TEXT.items()}


def repo_top() -> Path:
    r = subprocess.run(["git", "-C", str(HERE), "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False)
    return Path(r.stdout.strip()).resolve() if r.returncode == 0 else HERE.parents[4]


def _epoch(ts: object) -> float | None:
    if not isinstance(ts, str):
        return None
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def extract(projects: Path, limit: int | None) -> tuple[dict[str, tuple[str | None, float | None]], int]:
    """{명령: (cwd, 그 세션 기록의 첫 시각)}, 깨진 줄 수. 첫 등장 기준.
    shortcut: 깨진 줄은 '"Bash"' 가 든 후보 줄만 센다(6GB 전부 json 해석은 느림) — 전체 집계가 필요해지면 모든 줄을 해석."""
    seen: dict[str, tuple[str | None, float | None]] = {}
    bad = 0
    for f in sorted(projects.rglob("*.jsonl")):
        start: float | None = None
        try:
            fh = open(f, "rb")  # noqa: SIM115 — 열기 실패(쓰는 중 삭제 등)만 건너뛰려고 with 밖에서 연다
        except OSError:
            continue
        with fh:
            for line in fh:
                try:
                    if start is None and b'"timestamp"' in line:
                        start = _epoch(json.loads(line).get("timestamp"))
                    if b'"Bash"' not in line:
                        continue
                    rec = json.loads(line)
                except ValueError:   # 다른 세션이 쓰는 중인 마지막 줄 등
                    bad += 1
                    continue
                content = (rec.get("message") or {}).get("content") if isinstance(rec, dict) else None
                if not isinstance(content, list):
                    continue
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") == "Bash":
                        cmd = (c.get("input") or {}).get("command")
                        if isinstance(cmd, str) and cmd and cmd not in seen:
                            cwd = rec.get("cwd")
                            seen[cmd] = (cwd if isinstance(cwd, str) else None, start)
                            if limit is not None and len(seen) >= limit:
                                return seen, bad
    return seen, bad


def kind_of(reason: str) -> str:
    if reason == bash_guard.R_PARSE:
        return "PARSE"
    if reason == bash_guard.R_TIMEOUT:
        return "TIMEOUT"
    if reason == bash_guard.R_MODEL:
        return "MODEL"
    if reason == bash_guard.R_DYNAMIC:
        return "DYNAMIC"
    return next((k for t, k in _KIND_BY_TEXT.items() if t in reason), "OTHER")


def _target(reason: str, cwd: str | None) -> str | None:
    """'거부: <작업> <대상> — …' 에서 지금 있는 대상 경로. 작업 이름이 여러 단어일 수 있어 가장 긴 존재 접미를 고른다."""
    body = reason.split("거부: ", 1)[-1].split(" — ", 1)[0]
    for i, ch in enumerate(body):
        if ch == " ":
            p = os.path.join(cwd or "/", body[i + 1:])
            if os.path.lexists(p):
                return p
    return None


def _birth(p: str) -> float:
    r = subprocess.run(["stat", "-c", "%.9W", "--", p], capture_output=True, text=True, check=False)
    try:
        return float(r.stdout) if r.returncode == 0 else 0.0
    except ValueError:
        return 0.0


def context_gap(reasons: list[str], cwd: str | None, start: float | None) -> bool:
    """PRESERVED 거부 중 대상이 지금 없거나, 생성 시각이 그 세션 시작 이후(또는 모름)라 세션 생성물이었을 수 있는 것."""
    for r in reasons:
        if kind_of(r) != "PRESERVED":
            continue
        p = _target(r, cwd)
        b = _birth(p) if p else 0.0
        if not b or start is None or b >= start:
            return True
    return False


def _pct(xs: list[float], q: float) -> float:
    return round(xs[min(len(xs) - 1, int(q * len(xs)))], 2) if xs else 0.0


def replay(projects: Path, out: Path, limit: int | None) -> dict:
    cmds, parse_errors = extract(projects, limit)
    environ = {**os.environ, "XDG_STATE_HOME": str(out / "state"), "HARNESS_BASH_GUARD": "on"}
    times: list[float] = []
    by_kind: dict[str, int] = {}
    deny = errors = gaps = 0
    with open(out / "denies.jsonl", "w", encoding="utf-8") as dn, open(out / "errors.jsonl", "w", encoding="utf-8") as er:
        for n, (c, (cwd, start)) in enumerate(cmds.items(), 1):
            payload = {"tool_name": "Bash", "tool_input": {"command": c}, "cwd": cwd, "session_id": None, "transcript_path": None}
            row = {"id": hashlib.sha256(c.encode("utf-8", "surrogatepass")).hexdigest()[:8], "command": c[:CMD_CAP], "cwd": cwd}
            t0 = time.perf_counter()
            try:
                d = bash_guard.judge(payload, environ, budget=5.0)
                err = d.error
            except Exception as e:  # noqa: BLE001 — 판정기 내부 오류를 세는 것이 이 도구의 목적
                d, err = None, f"{type(e).__name__}: {e}"
            times.append((time.perf_counter() - t0) * 1000)
            if err:
                errors += 1
                er.write(json.dumps({**row, "error": err}, ensure_ascii=False) + "\n")
            if d is not None and not d.allow:
                deny += 1
                kinds = sorted({kind_of(r) for r in d.reasons if not r.startswith("… 외 ")})
                for k in kinds:
                    by_kind[k] = by_kind.get(k, 0) + 1
                gap = context_gap(d.reasons, cwd, start)
                gaps += gap
                dn.write(json.dumps({**row, "reasons": d.reasons, "kinds": kinds, "context_gap": gap}, ensure_ascii=False) + "\n")
            if n % 1000 == 0:
                print(f"[replay] {n}/{len(cmds)} deny={deny} errors={errors}", file=sys.stderr, flush=True)
    times.sort()
    summary = {"commands": len(cmds), "errors": errors, "deny": deny,
               "p50_ms": _pct(times, 0.50), "p99_ms": _pct(times, 0.99), "max_ms": round(times[-1], 2) if times else 0.0,
               "parse_errors": parse_errors, "context_gap": gaps, "deny_by_kind": dict(sorted(by_kind.items()))}
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--projects", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args(argv)
    out = a.out.expanduser().resolve()
    top = repo_top()
    if out == top or top in out.parents:   # 결과에 명령 원문이 든다 — 공개 저장소에 섞이지 않게
        print(f"replay_corpus: --out 이 저장소 작업 트리({top}) 안이다", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    print(json.dumps(replay(a.projects.expanduser(), out, a.limit)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
