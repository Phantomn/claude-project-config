from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "scripts"))
import audit_ws  # noqa: E402
import check_expected  # noqa: E402
from test_audit_ws import Base  # noqa: E402

SPEC = "pkg/docs/specs/a-spec.md"
PLAN = "docs/plans/a-plan.md"
LOG_HEAD = ["| F | 결과 | 최종 action | 라운드 수 | 라운드1 fail | 라운드1 unverified | 라운드1 class |",
            "|---|---|---|---|---|---|---|"]


class CheckExpectedTest(Base):
    def setUp(self) -> None:
        super().setUp()
        self.fix = self.repo({SPEC: "".join(f"s{i}\n" for i in range(20)),
                              PLAN: "".join(f"p{i}\n" for i in range(20))})
        self.W = audit_ws.workspace(self.fix.resolve(), self.fix.resolve() / PLAN,
                                    [self.fix.resolve() / SPEC])

    def rnd(self, n: int, findings: list[dict], action: str = "fix",
            header: str = "대상: 플러그인 6.4.2-phantomn.6") -> None:
        R = self.W / f"round-{n}"
        R.mkdir(parents=True, exist_ok=True)
        (R / "targets.json").write_text(json.dumps({"tree": "t", "plugin_version": "v", "targets": [
            {"rel": PLAN, "snapshot": f"1-{Path(PLAN).name}"},
            {"rel": SPEC, "snapshot": f"2-{Path(SPEC).name}"}]}))
        fails = sum(f["verdict"] == "fail" for f in findings)
        (R / "aggregate.json").write_text(json.dumps({"findings": findings, "counts": {
            "fail": fails, "unverified": len(findings) - fails}}))
        (R / "decision.json").write_text(json.dumps({"action": action, "fix": []}))
        (R / "aggregate.md").write_text(f"# SPEC Audit · round {n} · {action}\n{header}\n")

    def f(self, cls: str, target: str, verdict: str = "fail", affected=()) -> dict:
        return {"class": cls, "verdict": verdict, "target": target, "affected": list(affected)}

    def spec(self, a: int, b: int | None = None, n: int = 1) -> str:
        return f"round-{n}/snapshot/2-a-spec.md:{a}" + (f"-{b}" if b else "")

    def run_exp(self, body: str, name: str = "F1") -> int:
        d = self.tmp / "fx" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "EXPECTED.md").write_text(f"targets: {PLAN} {SPEC}\n{body}")
        with contextlib.redirect_stdout(io.StringIO()):
            return check_expected.main([str(d / "EXPECTED.md"), str(self.fix)])

    def test_T27(self):
        self.rnd(1, [self.f("ref-missing", self.spec(5))])
        self.assertEqual(self.run_exp(f"round 1 must: ref-missing @ {SPEC}:4-6\n"), 0)
        self.assertEqual(self.run_exp(f"round 1 must: ref-missing @ {SPEC}:9\n"), 1)
        self.assertEqual(self.run_exp(f"round 1 must: sync-miss @ {SPEC}:5\n"), 1)

    def test_T28(self):
        self.rnd(1, [self.f("ref-missing", self.spec(5))])
        self.assertEqual(self.run_exp(f"round 1 must_not: ref-missing @ {SPEC}:5\n"), 1)
        self.assertEqual(self.run_exp(f"round 1 must_not: ref-missing @ {SPEC}:8\n"), 0)

    def test_T29(self):
        self.rnd(1, [self.f("premise", self.spec(5), "unverified")])
        self.assertEqual(self.run_exp(f"round 1 must: ref-missing|*unverified @ {SPEC}:5\n"), 0)
        self.assertEqual(self.run_exp(f"round 1 must: ref-missing @ {SPEC}:5\n"), 1)

    def test_T30(self):
        self.rnd(1, [self.f("ref-missing", self.spec(3))])
        self.assertEqual(self.run_exp(f"round 1 must: ref-missing @ {PLAN}:1-5, {SPEC}:1-9\n"), 0)

    def test_T31(self):
        self.rnd(1, [], action="cap")
        self.assertEqual(self.run_exp("round 1 header_contains: 6.4.2-phantomn.6\n"), 0)
        self.assertEqual(self.run_exp("round 1 header_contains: nope\n"), 1)
        self.assertEqual(self.run_exp("outcome: pass\n"), 1)
        self.assertEqual(self.run_exp("outcome: any\n"), 0)

    def test_T32(self):
        self.rnd(1, [self.f("ref-missing", self.spec(5)), self.f("ref-missing", self.spec(6)),
                     self.f("cross-doc-conflict", self.spec(7), "unverified")])
        self.assertEqual(self.run_exp(f"round 1 must: ref-missing @ {SPEC}:5\n"), 0)
        self.assertEqual(self.run_exp(f"round 1 must: sync-miss @ {SPEC}:5\n"), 1)
        lines = (self.tmp / "fx" / "ACCEPTANCE-LOG.md").read_text().splitlines()
        self.assertEqual(lines[:2], LOG_HEAD)
        self.assertEqual(len(lines), 4)
        self.assertEqual(lines[2], "| F1 | 일치 | fix | 1 | 2 | 1 | cross-doc-conflict,ref-missing |")
        self.assertIn("| 불일치 |", lines[3])
        self.assertNotIn("/", "".join(lines[2:]))

    def test_affected_match(self):
        self.rnd(1, [self.f("rule-violation", self.spec(1), affected=[self.spec(10, 12)])])
        self.assertEqual(self.run_exp(f"round 1 must: rule-violation @ {SPEC}:11\n"), 0)

    def test_parse_errors(self):
        for bad in ("round 1 maybe: x @ a:1\n", "round 1 must: x @ a\n", "outcome: win\n"):
            with self.assertRaises(ValueError):
                check_expected.parse_expected(f"targets: a.md\n{bad}")
        with self.assertRaises(ValueError):
            check_expected.parse_expected("outcome: any\n")

    def test_fixtures_well_formed(self):
        root = HERE / "fixtures"
        for i in range(1, 8):
            name = f"F{i}"
            with self.subTest(fixture=name):
                case = root / name / "case"
                self.assertTrue(case.is_dir())
                exp = check_expected.parse_expected((root / name / "EXPECTED.md").read_text())
                roles = []
                for rel in exp["targets"]:
                    self.assertTrue((case / rel).is_file(), rel)
                    roles.append(audit_ws.role_of(Path(rel)))
                self.assertNotIn(None, roles)
                for _, _, _, locs in exp["rules"]:
                    for rel, a, b in locs:
                        n = len((case / rel).read_bytes().splitlines())
                        self.assertTrue(1 <= a <= b <= n, f"{rel}:{a}-{b} (줄 수 {n})")
                if name == "F4":
                    self.assertNotIn("plan", roles)
                    self.assertEqual(exp["outcome"], "pass")
                else:
                    self.assertEqual(exp["outcome"], "any")
                if name == "F1":
                    self.assertIn((1, "6.4.2-phantomn.6"), exp["header"])


if __name__ == "__main__":
    import unittest
    unittest.main()
