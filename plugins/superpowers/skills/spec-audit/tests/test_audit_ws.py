from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import audit_ws  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        env = {
            "HOME": str(self.tmp / "home"),
            "SUPERPOWERS_AUDIT_TMPROOT": str(self.tmp / "tmproot"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
        }
        (self.tmp / "home").mkdir()
        saved = {k: os.environ.get(k) for k in env}
        os.environ.update(env)

        def restore() -> None:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        self.addCleanup(restore)

    def repo(self, files: dict[str, str], git: bool = True) -> Path:
        d = Path(tempfile.mkdtemp(dir=self.tmp))
        for rel, text in files.items():
            p = d / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(text.encode())
        if git:
            run = lambda *a: subprocess.run(["git", *a], cwd=d, check=True, capture_output=True)
            run("init", "-q")
            run("add", "-A")
            run("commit", "-q", "-m", "init")
        return d

    def cli(self, *args: str) -> tuple[int, dict | None, str]:
        p = subprocess.run([sys.executable, str(SCRIPTS / "audit_ws.py"), *args],
                           capture_output=True, text=True)
        try:
            data = json.loads(p.stdout)
        except ValueError:
            data = None
        return p.returncode, data, p.stderr


def expand(rs):
    return [(i, n) for i, a, b in rs for n in range(a, b + 1)]


class AssignTest(Base):
    def t(self, *spec): return [{"role": r, "lines": n} for r, n in spec]

    def test_T04_counts(self):
        for n, k in [(1500, 1), (1501, 2), (3000, 2), (4501, 4)]:
            self.assertEqual(len(audit_ws.shard(audit_ws.axis_lines(self.t(("spec", n)), "selfcontained"))), k)

    def test_T06_invariant(self):
        rng = random.Random(0)
        for _ in range(20):
            targets = self.t(*[(rng.choice(["spec", "plan", "other"]), rng.randint(1, 5000))
                               for _ in range(rng.randint(1, 3))])
            for axis in audit_ws.AXES:
                al = audit_ws.axis_lines(targets, axis)
                shards = audit_ws.shard(al)
                for s in shards:
                    self.assertGreater(audit_ws.range_len(s), 0)
                for x in range(len(shards)):
                    for y in range(x + 1, len(shards)):
                        self.assertFalse(audit_ws.overlaps(shards[x], shards[y]))
                self.assertEqual([l for s in shards for l in expand(s)], expand(al))

    def test_T24_axis_lines(self):
        t = self.t(("spec", 1400), ("other", 300))
        self.assertEqual(len(audit_ws.shard(audit_ws.axis_lines(t, "refs"))), 2)
        sc = audit_ws.axis_lines(t, "selfcontained")
        self.assertEqual(sc, [(1, 1, 1400)])

    def test_T07_oracle(self):
        ok = "# S\n## Reference Oracle\n\n원본 legacy/p.c v1 전체\n"
        self.assertTrue(audit_ws.oracle_needed(ok))
        self.assertFalse(audit_ws.oracle_needed("## Reference Oracle (optional)\n[기존 시스템을 …]\n"))
        self.assertFalse(audit_ws.oracle_needed("```\n## Reference Oracle\nx\n```\n"))

    def test_rf_empty_lines_excluded(self):
        self.assertEqual(audit_ws.axis_lines(self.t(("spec", 0), ("plan", 10)), "refs"), [(2, 1, 10)])
        self.assertEqual(audit_ws.shard([]), [])


if __name__ == "__main__":
    unittest.main()
