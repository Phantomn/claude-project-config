from __future__ import annotations

import hashlib
import json
import os
import re
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import audit_ws  # noqa: E402

PLUGIN_JSON = Path(audit_ws.__file__).resolve().parents[3] / ".claude-plugin" / "plugin.json"
NAME_RE = re.compile(r"^(refs|selfcontained|rootcause|oracle)-r\d+-s\d+(-retry)?$")


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

    def c1(self, *args: str) -> tuple[int, dict | None, str]:
        rc, out, err = self.cli("init", "--round", "1", "--skill-version", audit_ws.skill_hash(), *args)
        if rc == 0:
            self.ws = Path(out["ws"])
        return rc, out, err

    def finding(self, name: str, k: int, **over) -> dict:
        """유효 기본 finding. 기본 target = 마지막 C1 배정에서 그 감사자 첫 범위의 첫 줄."""
        target = ""
        n = int(re.search(r"-r(\d+)-", name).group(1))
        aj = getattr(self, "ws", None) and self.ws / f"round-{n}" / "assign.json"
        if aj and aj.exists():
            for a in json.loads(aj.read_text())["agents"]:
                if a["name"] == name and a["ranges"]:
                    rn, snap, lo, _ = audit_ws.parse_range(a["ranges"][0])
                    target = audit_ws.fmt_range(rn, snap, lo, lo)
        f = {"id": f"{name}-{k:03d}", "verdict": "fail", "axis": name.split("-")[0], "class": "ref-missing",
             "target": target, "claim": "c", "evidence": "e", "recommended": "r", "fix_class": "align",
             "affected": [], "unverified_reason": None, "check": None}
        f.update(over)
        return f

    def report(self, ws: Path, n: int, name: str, findings: list[dict], coverage: list[str],
               resolved: list[str] | None = None, extra: str = "") -> Path:
        body = "```findings\n" + "".join(json.dumps(f, ensure_ascii=False) + "\n" for f in findings) + "```\n"
        body += "```coverage\n" + "".join(c + "\n" for c in coverage) + "```\n"
        if resolved is not None:
            body += "```resolved\n" + "".join(r + "\n" for r in resolved) + "```\n"
        p = Path(ws) / f"round-{n}" / "reports" / f"{name}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body + extra)
        return p

    def round1_done(self, files: dict[str, str], findings_by_name: dict[str, list[dict]] | None = None) -> Path:
        """C1 → 모든 배정 감사자 보고(coverage = 배정 범위) → C3. W 반환."""
        d = self.repo(files)
        args: list[str] = []
        for rel in files:
            role = audit_ws.role_of(Path(rel))
            if role:
                args += [f"--{role}", str(d / rel)]
        rc, out, err = self.c1(*args)
        self.assertEqual(rc, 0, err)
        ws = Path(out["ws"])
        for a in out["agents"]:
            self.report(ws, 1, a["name"], (findings_by_name or {}).get(a["name"], []), a["ranges"])
        rc, _, err = self.cli("aggregate", "--ws", str(ws), "--round", "1")
        self.assertEqual(rc, 0, err)
        return ws


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

    def test_oracle_subheading_in_section(self):
        self.assertTrue(audit_ws.oracle_needed("## Reference Oracle\n### 원본\nlegacy/p.c\n"))

    def test_oracle_empty_section_ends_at_h2(self):
        self.assertFalse(audit_ws.oracle_needed("## Reference Oracle\n\n## 다음\nx\n"))

    def test_rf_empty_lines_excluded(self):
        self.assertEqual(audit_ws.axis_lines(self.t(("spec", 0), ("plan", 10)), "refs"), [(2, 1, 10)])
        self.assertEqual(audit_ws.shard([]), [])


AUDITORS = Path(audit_ws.__file__).resolve().parents[1] / "auditors"
LFS_FILES = {"docs/specs/s.md": "# S\nx\n", ".gitattributes": "*.bin filter=lfs\n", "a.bin": "blob\n"}


def git(d: Path, *a: str) -> None:
    subprocess.run(["git", "-C", str(d), *a], check=True, capture_output=True)


class C1Test(Base):
    def tmproot(self) -> Path:
        return Path(os.environ["SUPERPOWERS_AUDIT_TMPROOT"])

    def ok(self, *args: str) -> dict:
        rc, out, err = self.c1(*args)
        self.assertEqual(rc, 0, err)
        for a in out["agents"]:
            self.assertRegex(a["name"], NAME_RE)
        return out

    def by_axis(self, out: dict, axis: str) -> list[dict]:
        return [a for a in out["agents"] if a["axis"] == axis]

    def lfs_repo(self) -> Path:
        d = self.repo(LFS_FILES)
        git(d, "config", "filter.lfs.process", "false")
        git(d, "config", "filter.lfs.required", "true")
        return d

    def test_T01_workspace(self):
        repo = self.repo({"docs/superpowers/plans/2026-01-01-x.md": "# P\na\n", "docs/specs/s.md": "# S\nb\nc\n"})
        p, s = str(repo / "docs/superpowers/plans/2026-01-01-x.md"), str(repo / "docs/specs/s.md")
        out = self.ok("--plan", p, "--spec", s)
        W = Path(out["ws"])
        self.assertEqual(W.parent, repo.resolve() / ".superpowers/audit")
        self.assertRegex(W.name, r"^2026-01-01-x-[0-9a-f]{8}$")
        self.assertEqual((repo / ".superpowers/audit/.gitignore").read_text().strip(), "*")
        tj = json.loads((W / "round-1/targets.json").read_text())
        self.assertEqual([t["role"] for t in tj["targets"]], ["plan", "spec"])
        self.assertEqual(tj["plugin_version"], json.loads(PLUGIN_JSON.read_text())["version"])
        self.assertEqual(tj["targets"][1]["sha256"], hashlib.sha256(Path(s).read_bytes()).hexdigest())
        self.assertEqual(tj["tree"], str(repo.resolve()))
        self.assertTrue((W / "round-1/snapshot/2-s.md").exists())
        self.assertEqual(set(out), {"ws", "agents"})
        self.assertTrue({"name", "prompt"} <= set(out["agents"][0]))
        self.assertEqual(json.loads((W / "round-1/assign.json").read_text()), {"agents": out["agents"]})
        (W / "round-2").mkdir()
        (self.tmproot() / "spec-audit" / W.name / "stale").mkdir(parents=True)
        self.ok("--plan", p, "--spec", s)  # D6 재생성
        self.assertEqual(sorted(x.name for x in W.iterdir()), ["round-1"])
        self.assertFalse((self.tmproot() / "spec-audit" / W.name / "stale").exists())

    def test_T01_order_independent(self):
        repo = self.repo({"docs/specs/a.md": "a\n", "docs/specs/b.md": "b\n"})
        a, b = str(repo / "docs/specs/a.md"), str(repo / "docs/specs/b.md")
        self.assertEqual(self.ok("--spec", a, "--spec", b)["ws"], self.ok("--spec", b, "--spec", a)["ws"])

    def test_T01_first_spec(self):
        repo = self.repo({"docs/specs/a.md": "a\n", "docs/specs/b.md": "b\n"})
        out = self.ok("--spec", str(repo / "docs/specs/b.md"), "--spec", str(repo / "docs/specs/a.md"))
        self.assertTrue(Path(out["ws"]).name.startswith("a-"))

    def test_T02_spec_outside_tree(self):
        r1 = self.repo({"docs/plans/p.md": "p\n"})
        r2 = self.repo({"docs/specs/s.md": "s\n"})
        out = self.ok("--plan", str(r1 / "docs/plans/p.md"), "--spec", str(r2 / "docs/specs/s.md"))
        W = Path(out["ws"])
        self.assertEqual(W.parent, r1.resolve() / ".superpowers/audit")
        tj = json.loads((W / "round-1/targets.json").read_text())
        self.assertEqual(tj["targets"][0]["rel"], "docs/plans/p.md")
        self.assertEqual(tj["targets"][1]["rel"], str((r2 / "docs/specs/s.md").resolve()))
        self.assertTrue((W / "round-1/snapshot" / tj["targets"][1]["snapshot"]).exists())

    def test_T03_counts(self):
        repo = self.repo({"docs/plans/p.md": "p\n", "docs/plans/q.md": "q\n"})
        rc, _, _ = self.c1("--plan", str(repo / "docs/plans/p.md"), "--plan", str(repo / "docs/plans/q.md"))
        self.assertNotEqual(rc, 0)
        rc, _, _ = self.c1()
        self.assertNotEqual(rc, 0)

    def test_T22_no_head(self):
        d = self.repo({"docs/specs/s.md": "s\n"}, git=False)
        git(d, "init", "-q")
        rc, _, _ = self.c1("--spec", str(d / "docs/specs/s.md"))
        self.assertNotEqual(rc, 0)
        self.assertFalse((d / ".superpowers").exists())

    def test_T33_missing_arg(self):
        repo = self.repo({"docs/specs/s.md": "s\n"})
        rc, _, _ = self.c1("--spec", str(repo / "docs/specs/s.md"), "--spec", str(repo / "docs/specs/none.md"))
        self.assertNotEqual(rc, 0)

    def test_T20_non_git(self):
        d = self.repo({"docs/specs/s.md": "# S\nx\n"}, git=False)
        out = self.ok("--spec", str(d / "docs/specs/s.md"))
        W = Path(out["ws"])
        self.assertEqual(W.parent, (d / "docs/specs").resolve() / ".superpowers/audit")
        for a in self.by_axis(out, "selfcontained"):
            x = Path(a["exec_dir"])
            self.assertEqual(x, self.tmproot() / "spec-audit" / W.name / "r1" / a["name"])
            self.assertTrue(x.is_dir())
            self.assertFalse((x / "head").exists())

    def test_T08_c1_head(self):
        repo = self.repo({"docs/specs/s.md": "# S\nx\n", "src/m.py": "print(1)\n"})
        (repo / "src/m.py").write_text("작업트리 변경\n")  # X/head = HEAD 내용
        out = self.ok("--spec", str(repo / "docs/specs/s.md"))
        for a in self.by_axis(out, "refs"):
            self.assertIsNone(a["exec_dir"])
        sc = self.by_axis(out, "selfcontained")
        self.assertTrue(sc)
        for a in sc:
            self.assertEqual((Path(a["exec_dir"]) / "head/src/m.py").read_text(), "print(1)\n")
            self.assertFalse((Path(a["exec_dir"]) / "head/.git").exists())

    def test_T08_lfs_fail(self):
        d = self.lfs_repo()
        rc, out, err = self.c1("--spec", str(d / "docs/specs/s.md"))
        self.assertEqual(rc, 0, err)
        ex = [a for a in out["agents"] if a["axis"] in audit_ws.EXEC_AXES]
        self.assertTrue(ex)
        for a in ex:
            self.assertIsNone(a["exec_dir"])
            self.assertFalse((self.tmproot() / "spec-audit" / Path(out["ws"]).name / "r1" / a["name"]).exists())

    def test_T26_tree_flag(self):
        P = self.repo({"docs/specs/s.md": "# S\nx\n"})
        Q = self.repo({"q.txt": "Q head\n"})
        out = self.ok("--spec", str(P / "docs/specs/s.md"), "--tree", str(Q))
        W = Path(out["ws"])
        self.assertEqual(W.parent, Q.resolve() / ".superpowers/audit")
        a = self.by_axis(out, "selfcontained")[0]
        self.assertEqual((Path(a["exec_dir"]) / "head/q.txt").read_text(), "Q head\n")
        tj = json.loads((W / "round-1/targets.json").read_text())
        self.assertEqual(tj["targets"][0]["rel"], str((P / "docs/specs/s.md").resolve()))

    def test_T19_tmproot_default(self):
        os.environ.pop("SUPERPOWERS_AUDIT_TMPROOT")
        self.assertEqual(audit_ws.tmproot(), Path(f"/tmp/claude-{os.getuid()}"))

    def test_T07_c1(self):
        repo = self.repo({"docs/specs/s.md": "# S\n## Reference Oracle\n\n원본 legacy/p.c v1 전체\n"})
        out = self.ok("--spec", str(repo / "docs/specs/s.md"))
        self.assertIn("oracle-r1-s1", [a["name"] for a in out["agents"]])
        repo = self.repo({"docs/specs/s.md": "# S\n상위 정본: `docs/canon/c.md`\n",
                          "docs/canon/c.md": "# C\n## Reference Oracle\n\n원본 legacy/p.c v1 전체\n"})
        out = self.ok("--spec", str(repo / "docs/specs/s.md"))
        self.assertEqual(self.by_axis(out, "oracle"), [])

    def prompt_parts(self, a: dict) -> tuple[str, str, str]:
        text = Path(a["prompt"]).read_text()
        common = (AUDITORS / "common.md").read_text()
        axis = (AUDITORS / f"{a['axis']}.md").read_text()
        self.assertTrue(text.startswith(common + axis), a["name"])
        return common, axis, text[len(common) + len(axis):]

    def test_T34_c1(self):
        repo = self.repo({"docs/plans/p.md": "# P\na\n",
                          "docs/specs/s.md": "# S\n## Reference Oracle\n\n원본 legacy/p.c v1 전체\n"})
        out = self.ok("--plan", str(repo / "docs/plans/p.md"), "--spec", str(repo / "docs/specs/s.md"))
        W = Path(out["ws"])
        tj = json.loads((W / "round-1/targets.json").read_text())
        self.assertEqual({a["axis"] for a in out["agents"]}, set(audit_ws.AXES))
        for a in out["agents"]:
            self.assertEqual(Path(a["prompt"]), W / "round-1/prompts" / f"{a['name']}.md")
            _, _, block = self.prompt_parts(a)
            for r in a["ranges"]:
                self.assertIn(r, block)
            self.assertIn(str(repo.resolve()), block)
            for t in tj["targets"]:
                self.assertIn(str(W / "round-1/snapshot" / t["snapshot"]), block)
                self.assertIn(t["role"], block)
                self.assertIn(t["rel"], block)
            self.assertIn(str(W / "round-1/reports" / f"{a['name']}.md"), block)
            if a["exec_dir"]:
                self.assertIn(a["exec_dir"], block)
            self.assertNotIn("unverified(tool)", block)

    def test_T34_no_exec(self):
        d = self.lfs_repo()
        out = self.ok("--spec", str(d / "docs/specs/s.md"))
        for a in out["agents"]:
            _, _, block = self.prompt_parts(a)
            self.assertEqual("unverified(tool)" in block, a["axis"] in audit_ws.EXEC_AXES, a["name"])

    def test_rf_same_basename(self):
        repo = self.repo({"docs/specs/a/spec.md": "a\n", "docs/specs/b/spec.md": "b\n"})
        out = self.ok("--spec", str(repo / "docs/specs/a/spec.md"), "--spec", str(repo / "docs/specs/b/spec.md"))
        W = Path(out["ws"])
        snaps = sorted(x.name for x in (W / "round-1/snapshot").iterdir())
        self.assertEqual(snaps, ["1-spec.md", "2-spec.md"])
        self.assertEqual((W / "round-1/snapshot/1-spec.md").read_text(), "a\n")
        refs = self.by_axis(out, "refs")[0]["ranges"]
        self.assertEqual(refs, ["round-1/snapshot/1-spec.md:1", "round-1/snapshot/2-spec.md:1"])

    def test_rf_empty_target(self):
        repo = self.repo({"docs/specs/s.md": ""})
        self.assertEqual(self.ok("--spec", str(repo / "docs/specs/s.md"))["agents"], [])

    def test_skill_version(self):
        repo = self.repo({"docs/specs/s.md": "s\n"})
        s = str(repo / "docs/specs/s.md")
        rc, _, err = self.cli("init", "--round", "1", "--skill-version", "0" * 12, "--spec", s)
        self.assertNotEqual(rc, 0)
        self.assertIn("/reload-plugins", err)
        self.assertFalse((repo / ".superpowers").exists())
        rc, _, _ = self.cli("init", "--round", "1", "--spec", s)
        self.assertNotEqual(rc, 0)
        self.ok("--spec", s)
        x, y, z = (self.tmp / "x.md", self.tmp / "y.md", self.tmp / "z.md")
        x.write_text("a\n스킬 버전: x\nb\n")
        y.write_text("a\n스킬 버전: y\nb\n")
        z.write_text("a\n스킬 버전: x\nc\n")
        self.assertEqual(audit_ws.skill_hash(x), audit_ws.skill_hash(y))
        self.assertNotEqual(audit_ws.skill_hash(x), audit_ws.skill_hash(z))
        self.assertRegex(audit_ws.skill_hash(x), r"^[0-9a-f]{12}$")

    def test_role_of(self):
        for p, want in [("docs/superpowers/plans/x.md", "plan"), ("a/MY-PLAN.md", "plan"),
                        ("docs/specs/2026-plan.md", "plan"), ("docs/specs/x.md", "spec"),
                        ("a/foo-spec.md", "spec"), ("a/design.md", "spec"), ("a/notes.md", None)]:
            with self.subTest(p=p):
                self.assertEqual(audit_ws.role_of(Path(p)), want)

    def test_range_roundtrip(self):
        self.assertEqual(audit_ws.fmt_range(2, "1-my spec.md", 3, 3), "round-2/snapshot/1-my spec.md:3")
        self.assertEqual(audit_ws.fmt_range(1, "2-s.md", 3, 9), "round-1/snapshot/2-s.md:3-9")
        self.assertEqual(audit_ws.parse_range("round-1/snapshot/2-s.md:3-9"), (1, "2-s.md", 3, 9))
        self.assertEqual(audit_ws.parse_range("round-2/snapshot/1-a:b.md:4"), (2, "1-a:b.md", 4, 4))
        for bad in ["round-1/snapshot/2-s.md", "round-x/snapshot/2-s.md:1", "round-1/snapshot/2-s.md:0",
                    "round-1/snapshot/2-s.md:5-3", "snapshot/2-s.md:1", "round-1/snapshot/s.md:1"]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                audit_ws.parse_range(bad)


class CanonTest(Base):
    FILES = {"docs/canon/a.md": "# A\n", "docs/canon/b.md": "# B\n", "docs/canon/d.md": "# D\n",
             "config.json": "{}\n", "D.md": "# D\n", "docs/specs/D.md": "# D2\n"}

    def others(self, spec_text: str, extra: dict | None = None, plan: str | None = None) -> tuple[Path, list[dict]]:
        files = {**self.FILES, "docs/specs/s.md": spec_text, **(extra or {})}
        if plan is not None:
            files["docs/plans/p.md"] = plan
        d = self.repo(files)
        args = ["--spec", str(d / "docs/specs/s.md")]
        if plan is not None:
            args += ["--plan", str(d / "docs/plans/p.md")]
        rc, out, err = self.c1(*args)
        self.assertEqual(rc, 0, err)
        tj = json.loads((self.ws / "round-1/targets.json").read_text())
        return d, tj["targets"]

    def other_rels(self, targets: list[dict]) -> set[str]:
        return {t["rel"] for t in targets if t["role"] == "other"}

    def test_T23_cases(self):
        cases = [("상위 정본: `docs/canon/a.md`", {"docs/canon/a.md"}),
                 ("정본: `config.json`", set()),
                 ("정본: `docs/canon/none.md`", set()),
                 ("XML 정본 = `docs/canon/b.md §A`", {"docs/canon/b.md"}),
                 ("canonical: `docs/canon/d.md`", {"docs/canon/d.md"}),
                 ("정본 = `D.md`", {"D.md", "docs/specs/D.md"})]
        for line, want in cases:
            with self.subTest(line=line):
                _, t = self.others(f"# S\n{line}\n")
                self.assertEqual(self.other_rels(t), want)

    def test_T23_home(self):
        ext = Path(os.environ["HOME"]) / "ext" / "c.md"
        ext.parent.mkdir()
        ext.write_text("# C\n")
        _, t = self.others("# S\n정본: `~/ext/c.md`\n")
        self.assertEqual(self.other_rels(t), {str(ext.resolve())})

    def test_T21_outside(self):
        d = self.repo({"docs/specs/s.md": "# S\n정본: `../ext/c.md`\n"})
        ext = d.parent / "ext" / "c.md"
        ext.parent.mkdir(exist_ok=True)
        ext.write_text("# C\n")
        rc, out, err = self.c1("--spec", str(d / "docs/specs/s.md"))
        self.assertEqual(rc, 0, err)
        tj = json.loads((self.ws / "round-1/targets.json").read_text())
        o = [t for t in tj["targets"] if t["role"] == "other"]
        self.assertEqual([t["rel"] for t in o], [str(ext.resolve())])
        self.assertTrue((self.ws / "round-1/snapshot" / o[0]["snapshot"]).is_file())

    def test_T01_canon(self):
        d = self.repo({**self.FILES, "docs/specs/s.md": "# S\nx\n"})
        spec = d / "docs/specs/s.md"
        rc, out, err = self.c1("--spec", str(spec))
        self.assertEqual(rc, 0, err)
        before = out["ws"]
        spec.write_text("# S\nx\n정본: `docs/canon/a.md`\n")
        rc, out, err = self.c1("--spec", str(spec))
        self.assertEqual(rc, 0, err)
        self.assertEqual(out["ws"], before)
        tj = json.loads((self.ws / "round-1/targets.json").read_text())
        self.assertEqual(self.other_rels(tj["targets"]), {"docs/canon/a.md"})

    def test_T23_target_excluded(self):
        _, t = self.others("# S\n정본: `docs/plans/p.md`\n", plan="# P\n")
        self.assertEqual(len(t), 2)
        self.assertEqual(self.other_rels(t), set())

    def test_T23_shared_canon(self):
        line = "# S\n정본: `docs/canon/a.md`\n"
        _, t = self.others(line, plan=line.replace("S", "P"))
        self.assertEqual(len([x for x in t if x["role"] == "other"]), 1)

    def test_T07_c1_other_present(self):
        # C1Test.test_T07_c1 후반이 other 대상을 실제로 갖는지 고정
        _, t = self.others("# S\n상위 정본: `docs/canon/a.md`\n",
                           {"docs/canon/a.md": "# C\n## Reference Oracle\n\n원본 legacy/p.c v1 전체\n"})
        self.assertEqual(self.other_rels(t), {"docs/canon/a.md"})


if __name__ == "__main__":
    unittest.main()
