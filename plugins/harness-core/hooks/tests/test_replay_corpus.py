"""replay_corpus.py 종단 테스트: World 안에 합성 세션 기록을 만들고 CLI 를 실제로 돌린다 (대역 없음, spec D13)."""
from __future__ import annotations

import datetime
import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _world import WorldCase

TOOL = Path(__file__).resolve().parent / "tools" / "replay_corpus.py"
w = None  # WorldCase 가 테스트마다 채운다


def _iso(t: float) -> str:
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _bash(cmd: str, cwd: str, ts: str) -> str:
    return json.dumps({"type": "assistant", "cwd": cwd, "timestamp": ts,
                       "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": cmd}}]}})


class ReplayCorpus(WorldCase):
    def _run(self, out: Path) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(TOOL), "--projects", str(Path(w.root) / "projects"), "--out", str(out)],
                              env=w.environ, capture_output=True, text=True, timeout=120, check=False)

    def _corpus(self) -> None:
        repo, ts = str(w.repo), _iso(w.session_start)
        lines = [
            _bash("ls -la", repo, ts),
            _bash(w.fmt("rm -f {REPO}/notes_presession.txt"), repo, ts),   # 세션 전 유일본 → deny, 문맥 부족 아님
            _bash(w.fmt("rm -f {REPO}/src/probe.ts"), repo, ts),            # 세션 중 생성 → deny 지만 문맥 부족
            _bash("ls -la", repo, ts),                                      # 중복
            json.dumps({"type": "assistant", "cwd": repo, "timestamp": ts,
                        "message": {"content": [{"type": "tool_use", "name": "Read", "input": {"file_path": "/x"}}]}}),
            _bash("pwd", repo, ts)[:-10],                                 # 쓰는 중인(잘린) 줄
        ]
        p = Path(w.root) / "projects/-home-u-proj/s1.jsonl"
        p.parent.mkdir(parents=True)
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_summary_dedupe_and_context_gap(self):
        self._corpus()
        out = Path(w.root) / "replay"
        r = self._run(out)
        self.assertEqual(r.returncode, 0, r.stderr)
        s = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual({k: s[k] for k in ("commands", "errors", "deny", "parse_errors", "context_gap")},
                         {"commands": 3, "errors": 0, "deny": 2, "parse_errors": 1, "context_gap": 1})
        for k in ("p50_ms", "p99_ms", "max_ms"):
            self.assertIsInstance(s[k], float)
        self.assertEqual(s["deny_by_kind"], {"PRESERVED": 2})
        denies = [json.loads(x) for x in (out / "denies.jsonl").read_text(encoding="utf-8").splitlines()]
        gap = {Path(d["command"].split()[-1]).name: d["context_gap"] for d in denies}
        self.assertEqual(gap, {"notes_presession.txt": False, "probe.ts": True})
        self.assertEqual((out / "errors.jsonl").read_text(encoding="utf-8"), "")

    def test_out_inside_repo_refused(self):
        self._corpus()
        out = TOOL.parents[1] / "replay-should-not-exist"
        r = self._run(out)
        self.assertEqual(r.returncode, 2)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
