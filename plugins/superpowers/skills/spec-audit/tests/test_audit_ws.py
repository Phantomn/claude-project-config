from __future__ import annotations

import hashlib
import json
import os
import re
import random
import shlex
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

    def test_tmproot_relative(self):
        os.environ["SUPERPOWERS_AUDIT_TMPROOT"] = "rel/tmp"
        self.assertTrue(audit_ws.tmproot().is_absolute())

    def test_c1_non_utf8_spec(self):
        repo = self.repo({"docs/specs/s.md": "# S\n"})
        (repo / "docs/specs/s.md").write_bytes(b"# S\n\xff\xfe x\n## Reference Oracle\n\nsrc v1\n")
        out = self.ok("--spec", str(repo / "docs/specs/s.md"))
        self.assertIn("oracle-r1-s1", [a["name"] for a in out["agents"]])

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
        rc, _, err = self.cli("init", "--round", "1", "--spec", s)
        self.assertNotEqual(rc, 0)
        self.assertIn("--skill-version 필요", err)
        self.assertNotIn("/reload-plugins", err)
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


R1, S1, C1N = "refs-r1-s1", "selfcontained-r1-s1", "rootcause-r1-s1"


class C3Test(Base):
    SPEC = "상위 정본: `docs/canon/c.md`\n" + "".join(f"s{k}\n" for k in range(2, 41))
    FILES = {"docs/specs/s.md": SPEC, "docs/canon/c.md": "".join(f"c{k}\n" for k in range(1, 11))}

    def start(self, files: dict | None = None, spec: str = "docs/specs/s.md", d: Path | None = None) -> None:
        self.d = d or self.repo(files or self.FILES)
        rc, out, err = self.c1("--spec", str(self.d / spec))
        self.assertEqual(rc, 0, err)
        self.agents = {a["name"]: a for a in out["agents"]}

    def write_all(self, findings: dict | None = None, coverage: dict | None = None, skip: tuple = ()) -> None:
        for name, a in self.agents.items():
            if name not in skip:
                self.report(self.ws, 1, name, (findings or {}).get(name, []), (coverage or {}).get(name, a["ranges"]))

    def agg(self) -> tuple[int, dict | None, str]:
        return self.cli("aggregate", "--ws", str(self.ws), "--round", "1")

    def ok(self) -> dict:
        rc, out, err = self.agg()
        self.assertEqual((rc, out), (0, {}), err)
        return json.loads((self.ws / "round-1/aggregate.json").read_text())

    def raw(self, name: str, text: str | bytes) -> None:
        p = self.ws / "round-1/reports" / f"{name}.md"
        p.write_bytes(text if isinstance(text, bytes) else text.encode())

    def test_T13(self):
        self.start()
        self.write_all()
        spec = self.d / "docs/specs/s.md"
        data = spec.read_bytes()
        spec.write_bytes(b"X" + data[1:])
        self.assertEqual(self.agg()[:2], (3, {"target_modified": ["docs/specs/s.md"]}))
        spec.unlink()
        self.assertEqual(self.agg()[:2], (3, {"target_modified": ["docs/specs/s.md"]}))
        spec.write_bytes(data)
        (self.d / "other.txt").write_text("x\n")
        git(self.d, "add", "-A")
        git(self.d, "commit", "-q", "-m", "x")
        self.ok()

    def cases(self) -> list:
        f = self.finding
        no_ev = f(R1, 1)
        del no_ev["evidence"]
        fence = lambda n, body: "```" + n + "\n" + body + "```\n"
        cov = "round-1/snapshot/1-s.md:1-40\nround-1/snapshot/2-c.md:1-10\n"
        return [
            ("키 누락(evidence)", R1, [no_ev], None),
            ("verdict 'warn'", R1, [f(R1, 1, verdict="warn")], None),
            ("class 'typo'", R1, [f(R1, 1, **{"class": "typo"})], None),
            ("fix_class 'minor'", R1, [f(R1, 1, fix_class="minor")], None),
            ("unverified인데 reason null", R1, [f(R1, 1, verdict="unverified")], None),
            ("fail인데 reason 'tool'", S1, [f(S1, 1, unverified_reason="tool")], None),
            ("id 'refs-r1-s1-1'", R1, [f(R1, 1, id="refs-r1-s1-1")], None),
            ("id 중복", R1, [f(R1, 1), f(R1, 1)], None),
            ("axis 'rootcause' in refs", R1, [f(R1, 1, axis="rootcause")], None),
            ("claim ''", C1N, [f(C1N, 1, claim="")], None),
            ("coverage 블록 없음", R1, None, fence("findings", "")),
            ("findings 블록 없음", R1, None, fence("coverage", cov)),
            ("target이 축 대상 줄 밖", S1, [f(S1, 1, target="round-1/snapshot/2-c.md:1")], None),
            ("target 라운드 round-2", R1, [f(R1, 1, target="round-2/snapshot/1-s.md:1")], None),
            ("affected 라운드 round-2", R1, [f(R1, 1, affected=["round-2/snapshot/1-s.md:1"])], None),
            ("보고 파일 없음", R1, None, None),
            ("class [\"x\"]", R1, [f(R1, 1, **{"class": ["x"]})], None),
            ("unverified_reason {}", R1, [f(R1, 1, unverified_reason={})], None),
            ("id [\"a\"]", R1, [f(R1, 1, id=["a"])], None),
            ("비 UTF-8 보고", R1, None, b"\xff\xfe```findings\n```\n"),
        ]

    def test_T10(self):
        d = self.repo(self.FILES)
        self.start(d=d)
        keys = ["evidence", "'warn'", "'typo'", "'minor'", "None", "'tool'", "id 'refs-r1-s1-1'", "중복", "axis",
                "claim", "coverage 블록", "findings 블록", "겹치지", "target: 라운드", "affected: 라운드", "보고 파일 없음",
                "class", "unverified_reason", "id", "보고 읽기 실패"]
        for (label, victim, findings, raw), key in zip(self.cases(), keys, strict=True):
            with self.subTest(label):
                self.start(d=d)
                self.write_all({victim: findings or []}, skip=(victim,) if findings is None else ())
                if raw is not None:
                    self.raw(victim, raw)
                rc, out, err = self.agg()
                self.assertEqual(rc, 3, err)
                self.assertEqual(len(out["invalid"]), 1)
                inv = out["invalid"][0]
                self.assertIn(key, inv["reason"])
                orig, retry = self.agents[victim], inv["retry"]
                self.assertEqual(retry["name"], victim + "-retry")
                self.assertEqual((retry["ranges"], retry["recheck"]), (orig["ranges"], orig["recheck"]))
                if orig["axis"] in audit_ws.EXEC_AXES:
                    self.assertTrue(Path(retry["exec_dir"]).is_dir())
                agents = json.loads((self.ws / "round-1/assign.json").read_text())["agents"]
                self.assertIn(retry, agents)
                self.assertTrue((self.ws / "round-1/prompts" / f"{victim}-retry.md").is_file())

    def test_T11(self):
        self.start()
        self.write_all({R1: [self.finding(R1, 1, verdict="warn")]})
        rc, out, _ = self.agg()
        self.assertEqual(rc, 3)
        retry = out["invalid"][0]["retry"]
        self.report(self.ws, 1, retry["name"], [self.finding(retry["name"], 1)], retry["ranges"])
        agg = self.ok()
        self.assertEqual([f["id"] for f in agg["findings"]], ["refs-r1-s1-retry-001"])
        self.report(self.ws, 1, retry["name"], [self.finding(retry["name"], 1, claim="")], retry["ranges"])
        rc, out, _ = self.agg()
        self.assertEqual(rc, 3)
        self.assertEqual(len(out["invalid"]), 1)
        self.assertIsNone(out["invalid"][0]["retry"])

    def test_T11_retry_report_missing(self):
        self.start()
        self.write_all({R1: [self.finding(R1, 1, verdict="warn")]})
        rc, out, _ = self.agg()
        self.assertEqual(rc, 3)
        rc, out, err = self.agg()
        self.assertEqual(rc, 3, err)
        self.assertEqual(len(out["invalid"]), 1)
        self.assertIsNone(out["invalid"][0]["retry"])
        self.assertIn("보고 파일 없음", out["invalid"][0]["reason"])
        agents = json.loads((self.ws / "round-1/assign.json").read_text())["agents"]
        self.assertEqual([a["name"] for a in agents].count(R1 + "-retry"), 1)

    def test_T12(self):
        self.start()
        self.write_all(coverage={R1: ["round-1/snapshot/1-s.md:1-40", "round-1/snapshot/2-c.md:1-4"]})
        gap = self.ok()["review_gap"]
        self.assertEqual(gap["refs"], ["round-1/snapshot/2-c.md:5-10"])
        self.assertFalse(gap.get("selfcontained"))
        self.start(d=self.d)
        ctx = self.finding(S1, 1, verdict="unverified", unverified_reason="context",
                           target="round-1/snapshot/1-s.md:10-20")
        self.write_all({S1: [ctx]})
        agg = self.ok()
        self.assertEqual(agg["review_gap"]["selfcontained"], ["round-1/snapshot/1-s.md:10-20"])
        self.assertEqual(agg["counts"]["unverified"], 0)
        self.start({"docs/specs/s.md": "".join(f"l{k}\n" for k in range(1, 2001))})
        s2 = "selfcontained-r1-s2"
        self.assertEqual(self.agents[s2]["ranges"], ["round-1/snapshot/1-s.md:1501-2000"])
        ctx = self.finding(S1, 1, verdict="unverified", unverified_reason="context",
                           target="round-1/snapshot/1-s.md:100-200")
        self.write_all({S1: [ctx]}, {S1: ["round-1/snapshot/1-s.md:1-1500"], s2: ["round-1/snapshot/1-s.md:1-2000"]})
        self.assertEqual(self.ok()["review_gap"]["selfcontained"], ["round-1/snapshot/1-s.md:100-200"])

    def test_T25_r1(self):
        self.start()
        self.write_all({C1N: [self.finding(C1N, 1, target="round-1/snapshot/2-c.md:1")]})
        self.assertEqual(self.agg()[0], 3)
        self.start(d=self.d)
        self.write_all({R1: [self.finding(R1, 1, target="round-1/snapshot/2-c.md:1")]})
        self.ok()

    def test_T34_retry(self):
        self.start()
        self.write_all({S1: [self.finding(S1, 1, claim="")]})
        rc, out, _ = self.agg()
        retry = out["invalid"][0]["retry"]
        head = (AUDITORS / "common.md").read_text() + (AUDITORS / "selfcontained.md").read_text()
        orig = Path(self.agents[S1]["prompt"]).read_text()[len(head):]
        new = Path(retry["prompt"]).read_text()
        self.assertTrue(new.startswith(head))
        viol = [l for l in new[len(head):].splitlines(keepends=True) if l.startswith("- 직전 시도 위반: ")]
        self.assertTrue(viol)
        self.assertEqual("".join(l for l in new[len(head):].splitlines(keepends=True) if l not in viol),
                         orig.replace(S1, S1 + "-retry"))

    def test_retry_prompt_reason(self):
        self.start()
        self.write_all({S1: [self.finding(S1, 1, claim="")]})
        rc, out, _ = self.agg()
        self.assertEqual(rc, 3)
        reason = out["invalid"][0]["reason"]
        self.assertIn("claim 빈 값", reason)
        text = Path(out["invalid"][0]["retry"]["prompt"]).read_text()
        self.assertIn("- 직전 시도 위반: " + f"{S1}-001: claim 빈 값", text)

    def test_counts(self):
        self.start()
        f = self.finding
        self.write_all({R1: [f(R1, 1), f(R1, 2, verdict="unverified", unverified_reason="external")],
                        S1: [f(S1, 1), f(S1, 2, verdict="unverified", unverified_reason="context")]})
        agg = self.ok()
        self.assertEqual(agg["counts"], {"fail": 2, "unverified": 1})
        self.assertEqual(len(agg["findings"]), 4)
        self.assertEqual(agg["unresolved"], [])

    def test_rf_unknown_fence_ignored(self):
        self.start()
        self.write_all()
        a = self.agents[R1]
        self.report(self.ws, 1, R1, [], a["ranges"], extra="메모\n```python\nprint(1)\n```\n")
        self.ok()

    def test_rf_space_in_basename(self):
        self.start({"docs/specs/my spec-2.md": "a\nb\n"}, spec="docs/specs/my spec-2.md")
        self.write_all({R1: [self.finding(R1, 1)]})
        f = self.ok()["findings"]
        self.assertEqual(f[0]["target"], "round-1/snapshot/1-my spec-2.md:1")

    def test_round1_done(self):
        ws = self.round1_done(self.FILES)
        self.assertTrue((ws / "round-1/aggregate.json").is_file())

class C4Test(Base):
    FILES = {"docs/specs/s.md": "".join(f"s{k}\n" for k in range(1, 21))}

    @staticmethod
    def agg(fail=0, unv=0, gap=None, unres=(), findings=()):
        return {"findings": list(findings), "review_gap": gap or {}, "unresolved": list(unres),
                "counts": {"fail": fail, "unverified": unv}}

    def fnd(self, i, **over):
        f = {"id": i, "verdict": "fail", "fix_class": "align", "unverified_reason": None}
        f.update(over)
        return f

    def test_T14(self):
        d = audit_ws.decide
        self.assertEqual(d(self.agg(), 1)["action"], "pass")
        self.assertEqual(d(self.agg(fail=1), 1)["action"], "fix")
        r = d(self.agg(gap={"refs": ["round-1/snapshot/1-s.md:1"]}), 1)
        self.assertEqual(r, {"action": "fix", "fix": {"align": [], "approval": []}})
        self.assertEqual(d(self.agg(unres=["x"]), 1)["action"], "fix")

    def test_T15(self):
        self.assertEqual(audit_ws.decide(self.agg(unv=1), 2)["action"], "fix")

    def test_T16(self):
        d = audit_ws.decide
        self.assertEqual(d(self.agg(fail=1), 5)["action"], "cap")
        self.assertEqual(d(self.agg(), 5)["action"], "pass")
        self.assertEqual(d(self.agg(fail=1), 3)["action"], "fix")

    def test_T17(self):
        fs = [self.fnd("a"), self.fnd("r", fix_class="requirement"),
              self.fnd("c", verdict="unverified", unverified_reason="context")]
        r = audit_ws.decide(self.agg(fail=2, findings=fs), 1)
        self.assertEqual(r["fix"], {"align": ["a"], "approval": ["r"]})

    def test_T18(self):
        ws = self.round1_done(self.FILES)
        a = json.loads((ws / "round-1/assign.json").read_text())["agents"]
        refs = next(x for x in a if x["axis"] == "refs")
        self.report(ws, 1, refs["name"], [self.finding(refs["name"], 1, claim="a|b\nc")], refs["ranges"])
        self.assertEqual(self.cli("aggregate", "--ws", str(ws), "--round", "1")[0], 0)
        rc, out, err = self.cli("decide", "--ws", str(ws), "--round", "1")
        self.assertEqual(rc, 0, err)
        self.assertEqual(out["action"], "fix")
        self.assertEqual(json.loads((ws / "round-1/decision.json").read_text()), out)
        md = (ws / "round-1/aggregate.md").read_text()
        lines = md.splitlines()
        tj = json.loads((ws / "round-1/targets.json").read_text())
        rels = [t["rel"] for t in tj["targets"]]
        version = json.loads(PLUGIN_JSON.read_text())["version"]
        self.assertEqual(lines[0], "# SPEC Audit · round 1 · fix")
        self.assertTrue(lines[1].startswith("대상: " + ", ".join(rels) + " · "))
        self.assertIn(f"플러그인 {version}", lines[1])
        self.assertIn("감사자: ", lines[1])
        for x in a:
            self.assertIn(x["name"], lines[1])
        self.assertRegex(lines[2], r"^fail 1 · unverified 0 · review-gap \d+줄 · 직전 미해소 0$")
        self.assertIn("| id | 판정 | 축 | 위치 | 주장 | 근거 | 수정 분류 | 영향 위치 |", md)
        i = lines.index("|---|---|---|---|---|---|---|---|")
        self.assertEqual(len(lines) - i - 1, 1)
        self.assertIn("a\\|b c", lines[i + 1])

    def test_T19_clean(self):
        ws = self.round1_done(self.FILES)
        tmp = audit_ws.tmproot() / "spec-audit" / ws.name
        tmp.mkdir(parents=True, exist_ok=True)
        (tmp / "k").write_text("x")
        self.assertEqual(self.cli("clean", "--ws", str(ws))[0], 0)
        self.assertFalse(tmp.exists())
        self.assertTrue(ws.exists())

    def test_rf_empty_all_pass(self):
        d = self.repo({"docs/specs/e.md": ""})
        rc, out, err = self.c1("--spec", str(d / "docs/specs/e.md"))
        self.assertEqual(rc, 0, err)
        for a in out["agents"]:
            self.report(self.ws, 1, a["name"], [], a["ranges"])
        self.assertEqual(self.cli("aggregate", "--ws", str(self.ws), "--round", "1")[0], 0)
        rc, out, err = self.cli("decide", "--ws", str(self.ws), "--round", "1")
        self.assertEqual((rc, out["action"]), (0, "pass"), err)


def lines(n: int) -> list[str]:
    return [f"s{k}\n" for k in range(1, n + 1)]


SP = "docs/specs/s.md"
CANON_FILES = {SP: "상위 정본: `docs/canon/c.md`\n" + "".join(lines(40)[1:]),
               "docs/canon/c.md": "".join(f"c{k}\n" for k in range(1, 11))}
RR, SC2 = "refs-r2-s1", "selfcontained-r2-s1"
F1 = "refs-r1-s1-001"


def r(n: int, a: int, b: int | None = None, snap: str = "1-s.md") -> str:
    return audit_ws.fmt_range(n, snap, a, b or a)


class C2Test(Base):
    def setup1(self, files: dict[str, str], findings: dict | None = None) -> Path:
        ws = self.round1_done(files, findings)
        self.targets = json.loads((ws / "round-1/targets.json").read_text())["targets"]
        return ws

    def write(self, L: list[str], k: int = 0) -> None:
        Path(self.targets[k]["path"]).write_text("".join(L))

    def c2(self, ws: Path, n: int = 2) -> tuple[int, dict | None, str]:
        return self.cli("init", "--ws", str(ws), "--round", str(n))

    def ok2(self, ws: Path) -> dict:
        rc, out, err = self.c2(ws)
        self.assertEqual(rc, 0, err)
        return out

    def scope(self, ws: Path) -> dict:
        return json.loads((ws / "round-2/scope.json").read_text())["ranges"]

    def axis_ranges(self, out: dict) -> dict:
        res: dict[str, list] = {}
        for a in out["agents"]:
            res.setdefault(a["axis"], []).extend(a["ranges"])
        return res

    def write2(self, ws: Path, out: dict, findings: dict | None = None, resolved: dict | None = None) -> None:
        for a in out["agents"]:
            default = [f"{i}: resolved" for i in a["recheck"]] if a["recheck"] else None
            res = (resolved or {}).get(a["name"], default)
            self.report(ws, 2, a["name"], (findings or {}).get(a["name"], []), a["ranges"], res)

    def agg2(self, ws: Path) -> tuple[int, dict | None, str]:
        return self.cli("aggregate", "--ws", str(ws), "--round", "2")

    def set_agg(self, ws: Path, **over) -> None:
        p = ws / "round-1/aggregate.json"
        p.write_text(json.dumps({**json.loads(p.read_text()), **over}))

    def test_T09_changed(self):
        ws = self.setup1({SP: "".join(lines(10))})
        L = lines(10)
        L[3] = "X4\n"
        self.write(L)
        out = self.ok2(ws)
        sc = self.scope(ws)
        for ax in ("refs", "selfcontained", "rootcause"):
            self.assertEqual(sc[ax], [r(2, 4)], ax)
        self.assertEqual(sc["oracle"], [])
        self.assertEqual(self.axis_ranges(out), {ax: [r(2, 4)] for ax in ("refs", "selfcontained", "rootcause")})
        patch = (ws / "round-2/diff.patch").read_bytes()
        for part in (b"-s4\n", b"+X4\n", SP.encode()):
            self.assertIn(part, patch)

    def test_T09_delete_only(self):
        old = [f"{k}\n".encode() for k in range(1, 11)]
        self.assertEqual(audit_ws.changed_lines(old, old[:4] + old[5:]), {4, 5})
        self.assertEqual(audit_ws.changed_lines(old, old[1:]), {1})
        self.assertEqual(audit_ws.changed_lines(old, old[:-1]), {9})

    def test_T09_move(self):
        ws = self.setup1({SP: "".join(lines(10))}, {R1: [self.finding(R1, 1, target=r(1, 7))]})
        L = lines(10)
        L[1:1] = ["n1\n", "n2\n", "n3\n"]
        self.write(L)
        self.ok2(ws)
        sc = self.scope(ws)
        self.assertEqual(sc["refs"], [r(2, 2, 4), r(2, 10)])
        self.assertEqual(sc["selfcontained"], [r(2, 2, 4)])
        enc = lambda xs: [x.encode() for x in xs]
        self.assertEqual(audit_ws.move_range(enc(lines(10)), enc(L), 7, 7), (10, 10))
        self.assertEqual(audit_ws.move_range(enc(lines(10)), enc(L), 1, 3), (1, 6))

    def test_T09_gap(self):
        ws = self.setup1({SP: "".join(lines(40))})
        self.set_agg(ws, review_gap={"refs": [r(1, 20, 25)]})
        out = self.ok2(ws)
        sc = self.scope(ws)
        self.assertEqual((sc["refs"], sc["selfcontained"], sc["rootcause"]), ([r(2, 20, 25)], [], []))
        self.assertEqual({a["axis"] for a in out["agents"]}, {"refs"})

    def three(self, n: int = 3000) -> list[str]:
        L = lines(n)
        for k in (100, 200, 300):
            L[k - 1] = f"X{k}\n"
        return L

    def test_T05_basic(self):
        ws = self.setup1({SP: "".join(lines(3000))})
        self.write(self.three())
        out = self.ok2(ws)
        want = [r(2, 100), r(2, 200), r(2, 300)]
        for ax in ("refs", "selfcontained", "rootcause"):
            got = [a for a in out["agents"] if a["axis"] == ax]
            self.assertEqual([a["ranges"] for a in got], [want], ax)
        self.assertFalse([a for a in out["agents"] if a["axis"] == "oracle"])

    def test_T05_recheck(self):
        ws = self.setup1({SP: "".join(lines(3000))}, {R1: [self.finding(R1, 1, target=r(1, 50))]})
        self.write(self.three())
        out = self.ok2(ws)
        ar = self.axis_ranges(out)
        self.assertEqual(ar["refs"], [r(2, 50), r(2, 100), r(2, 200), r(2, 300)])
        self.assertNotIn(r(2, 50), ar["selfcontained"] + ar["rootcause"])
        owners = [a["name"] for a in out["agents"] if F1 in a["recheck"]]
        self.assertEqual(owners, [RR])
        self.assertEqual(json.loads((ws / "round-2/assign.json").read_text()), {"agents": out["agents"]})

    def test_T05_other_only(self):
        ws = self.setup1(CANON_FILES)
        self.write([f"c{k}\n" if k != 2 else "X\n" for k in range(1, 11)], k=1)
        out = self.ok2(ws)
        self.assertEqual(self.axis_ranges(out), {"refs": [r(2, 2, snap="2-c.md")]})

    def test_T05_boundary(self):
        ws = self.setup1({SP: "".join(lines(3000))}, {S1: [self.finding(S1, 1, target=r(1, 1499, 1502))]})
        self.write([x if 1499 <= k <= 1502 else f"X{k}\n" for k, x in enumerate(lines(3000), 1)])
        out = self.ok2(ws)
        sc = [a for a in out["agents"] if a["axis"] == "selfcontained"]
        self.assertEqual([a["name"] for a in sc], ["selfcontained-r2-s1", "selfcontained-r2-s2"])
        self.assertEqual([a["recheck"] for a in sc], [["selfcontained-r1-s1-001"], []])

    def test_T05_context(self):
        ctx = self.finding(S1, 1, verdict="unverified", unverified_reason="context", target=r(1, 10, 20))
        ws = self.setup1({SP: "".join(lines(40))}, {S1: [ctx]})
        out = self.ok2(ws)
        self.assertFalse([a for a in out["agents"] if ctx["id"] in a["recheck"]])
        self.assertEqual(self.scope(ws)["selfcontained"], [r(2, 10, 20)])
        self.set_agg(ws, review_gap={})
        out = self.ok2(ws)
        self.assertEqual(self.scope(ws)["selfcontained"], [])
        self.assertEqual(out["agents"], [])

    def test_T05_oracle(self):
        ws = self.setup1({SP: "".join(lines(40))})
        L = lines(40)
        for k in (5, 6, 7):
            L[k - 1] = "X\n"
        self.write(L)
        out = self.ok2(ws)
        self.assertFalse([a for a in out["agents"] if a["axis"] == "oracle"])
        ws = self.setup1({SP: "# S\n" + "".join(lines(40))})
        self.write(["# S\n", *lines(40), "## Reference Oracle\n", "\n", "원본 legacy/p.c v1 전체\n"])
        out = self.ok2(ws)
        orc = [a for a in out["agents"] if a["axis"] == "oracle"]
        self.assertEqual([(a["name"], a["ranges"]) for a in orc], [("oracle-r2-s1", [r(2, 42, 44)])])

    def r2_basic(self) -> tuple[Path, dict]:
        """40줄 spec, 라운드 1 refs finding F1(:1), 4번째 줄 수정 후 C2."""
        ws = self.setup1({SP: "".join(lines(40))}, {R1: [self.finding(R1, 1, target=r(1, 1))]})
        L = lines(40)
        L[3] = "X4\n"
        self.write(L)
        return ws, self.ok2(ws)

    def test_T35_unresolved(self):
        ws, out = self.r2_basic()
        self.assertEqual({a["name"]: a["recheck"] for a in out["agents"]}[RR], [F1])
        self.write2(ws, out, {RR: [self.finding(RR, 1)]}, {RR: [f"{F1}: unresolved {RR}-001"]})
        rc, res, err = self.agg2(ws)
        self.assertEqual((rc, res), (0, {}), err)
        agg = json.loads((ws / "round-2/aggregate.json").read_text())
        self.assertEqual(agg["unresolved"], [F1])
        self.assertEqual(audit_ws.decide(agg, 2)["action"], "fix")

    def test_unresolved_leading_space(self):
        ws, out = self.r2_basic()
        self.write2(ws, out, {RR: [self.finding(RR, 1)]}, {RR: [f"  {F1}: unresolved {RR}-001"]})
        rc, res, err = self.agg2(ws)
        self.assertEqual((rc, res), (0, {}), err)
        self.assertEqual(json.loads((ws / "round-2/aggregate.json").read_text())["unresolved"], [F1])

    def test_diff_patch_no_final_newline(self):
        ws = self.setup1({"docs/plans/p.md": "a\nb", SP: "c\nd"})
        self.write(["a\n", "B"], 0)
        self.write(["c\n", "D"], 1)
        self.ok2(ws)
        patch = (ws / "round-2/diff.patch").read_bytes()
        self.assertRegex(patch, rb"(?m)^--- " + re.escape(self.targets[1]["rel"].encode()))
        self.assertRegex(patch, rb"(?m)^\+B$")
        self.assertEqual(patch.count(b"\\ No newline at end of file\n"), 4)

    def test_T08_c2_new_head(self):
        ws = self.setup1({SP: "# S\nx\n", "src/m.py": "v1\n"})
        tree = Path(json.loads((ws / "round-1/targets.json").read_text())["tree"])
        (tree / "src/m.py").write_text("v2\n")
        git(tree, "commit", "-q", "-am", "m")
        self.write(["# S\n", "y\n"])
        out = self.ok2(ws)
        r1 = json.loads((ws / "round-1/assign.json").read_text())["agents"]
        for agents, want in ((r1, "v1\n"), (out["agents"], "v2\n")):
            sc = [a for a in agents if a["axis"] == "selfcontained"]
            self.assertTrue(sc)
            for a in sc:
                self.assertEqual((Path(a["exec_dir"]) / "head/src/m.py").read_text(), want)

    def test_T26_c2(self):
        P = self.repo({SP: "# S\nx\n"})
        Q = self.repo({"q.txt": "Q1\n"})
        rc, out, err = self.c1("--spec", str(P / SP), "--tree", str(Q))
        self.assertEqual(rc, 0, err)
        for a in out["agents"]:
            self.report(self.ws, 1, a["name"], [], a["ranges"])
        self.assertEqual(self.cli("aggregate", "--ws", str(self.ws), "--round", "1")[0], 0)
        (Q / "q.txt").write_text("Q2\n")
        git(Q, "commit", "-q", "-am", "q")
        (P / SP).write_text("# S\ny\n")
        out = self.ok2(self.ws)
        sc = [a for a in out["agents"] if a["axis"] == "selfcontained"]
        self.assertTrue(sc)
        self.assertEqual((Path(sc[0]["exec_dir"]) / "head/q.txt").read_text(), "Q2\n")

    def test_T33_c2_missing_agg(self):
        d = self.repo({SP: "# S\nx\n"})
        rc, _, err = self.c1("--spec", str(d / SP))
        self.assertEqual(rc, 0, err)
        self.assertNotEqual(self.c2(self.ws)[0], 0)

    def test_T33_c2_missing_other(self):
        ws = self.setup1(CANON_FILES)
        Path(self.targets[1]["path"]).unlink()
        rc, _, err = self.c2(ws)
        self.assertNotEqual(rc, 0)
        self.assertIn("docs/canon/c.md", err)

    def test_T34_c2(self):
        ws, out = self.r2_basic()
        for a in out["agents"]:
            text = Path(a["prompt"]).read_text()
            for part in [*a["recheck"], str(ws / "round-2/scope.json"), str(ws / "round-1/aggregate.json"),
                         str(ws / "round-2/diff.patch")]:
                self.assertIn(part, text, a["name"])
        self.assertIn(F1, Path({a["name"]: a for a in out["agents"]}[RR]["prompt"]).read_text())

    def test_T10_n2(self):
        cases = [("resolved 블록 없음", RR, {}, {RR: None}),
                 ("비배정", RR, {}, {RR: [f"{F1}: resolved", "refs-r1-s1-009: resolved"]}),
                 ("누락", RR, {}, {RR: []}),
                 ("가리킨 finding", RR, {}, {RR: [f"{F1}: unresolved {RR}-009"]}),
                 ("배정 범위", SC2, {SC2: [self.finding(SC2, 1, target=r(2, 10))]}, {})]
        ws, _ = self.r2_basic()
        for key, victim, findings, resolved in cases:
            with self.subTest(key):
                out = self.ok2(ws)
                self.write2(ws, out, findings, resolved)
                rc, res, err = self.agg2(ws)
                self.assertEqual(rc, 3, err)
                self.assertEqual(len(res["invalid"]), 1, res)
                self.assertIn(victim, res["invalid"][0]["reason"])
                self.assertIn(key, res["invalid"][0]["reason"])

    def test_T25_n2(self):
        ws, out = self.r2_basic()
        self.write2(ws, out, {SC2: [self.finding(SC2, 1, target=r(2, 3, 5))],
                              RR: [self.finding(RR, 1, target=r(2, 10))]})
        rc, res, err = self.agg2(ws)
        self.assertEqual((rc, res), (0, {}), err)

    def no_owner(self, ws: Path, fid: str) -> None:
        rc, _, err = self.c2(ws)
        self.assertNotEqual(rc, 0)
        self.assertIn(fid, err)
        self.assertFalse((ws / "round-2").exists())

    def test_T05_no_owner_empty(self):
        ws = self.setup1({SP: "".join(lines(40))}, {S1: [self.finding(S1, 1, target=r(1, 1))]})
        self.write([])
        self.no_owner(ws, f"{S1}-001")

    def test_T05_no_owner_oracle(self):
        o1 = "oracle-r1-s1"
        head = ["# S\n", "## Reference Oracle\n", "\n", "원본 legacy/p.c v1 전체\n"]
        ws = self.setup1({SP: "".join(head + lines(10))}, {o1: [self.finding(o1, 1, target=r(1, 4))]})
        self.write(head[:1] + lines(10))
        self.no_owner(ws, f"{o1}-001")

    def test_rf_crlf_no_final_newline(self):
        old = b"a\r\nb\r\nc".splitlines(keepends=True)
        new = b"a\nb\r\nc".splitlines(keepends=True)
        self.assertEqual(len(old), 3)
        self.assertEqual(audit_ws.changed_lines(old, new), {1})


CHK = 'grep -Hn "timeout=60" 1-s.md && exit 1 || exit 0'
FC = "refs-r1-s1-001"


def spec20(**edits: str) -> list[str]:
    L = lines(20)
    L[4] = "timeout=60\n"
    for k, v in edits.items():
        L[int(k[1:]) - 1] = v
    return L


class CheckTest(Base):
    def r1(self, check: str | None = CHK, **over) -> tuple[int, dict | None, str]:
        """spec 20줄(5줄 timeout=60) C1 → refs finding(:5, check) + 나머지 빈 보고 → C3."""
        d = self.repo({SP: "".join(spec20())})
        self.spec = d / SP
        rc, out, err = self.c1("--spec", str(self.spec))
        self.assertEqual(rc, 0, err)
        f = self.finding(R1, 1, **{"class": "ref-mismatch", "target": r(1, 5), "affected": [r(1, 5)],
                                   "check": check, **over})
        for a in out["agents"]:
            self.report(self.ws, 1, a["name"], [f] if a["name"] == R1 else [], a["ranges"])
        return self.cli("aggregate", "--ws", str(self.ws), "--round", "1")

    def agg(self, n: int = 1) -> dict:
        return json.loads((self.ws / f"round-{n}/aggregate.json").read_text())

    def round2(self, L: list[str], findings: dict | None = None, resolved: dict | None = None,
               ) -> tuple[int, dict | None, str]:
        self.spec.write_text("".join(L))
        rc, out, err = self.cli("init", "--ws", str(self.ws), "--round", "2")
        self.assertEqual(rc, 0, err)
        for a in out["agents"]:
            default = [f"{i}: resolved" for i in a["recheck"]] if a["recheck"] else None
            self.report(self.ws, 2, a["name"], (findings or {}).get(a["name"], []), a["ranges"],
                        (resolved or {}).get(a["name"], default))
        return self.cli("aggregate", "--ws", str(self.ws), "--round", "2")

    def ok(self, res: tuple) -> None:
        self.assertEqual(res[:2], (0, {}), res[2])

    def bad(self, res: tuple) -> None:
        rc, out, err = res
        self.assertEqual(rc, 3, err)
        self.assertEqual(len(out["invalid"]), 1, out)
        self.assertIn("check", out["invalid"][0]["reason"])

    def set_check(self, cmd: str) -> None:
        p = self.ws / "round-1/aggregate.json"
        agg = json.loads(p.read_text())
        agg["checks"][FC]["check"] = cmd
        p.write_text(json.dumps(agg))

    def c9(self) -> tuple[int, dict | None, str]:
        return self.cli("check", "--ws", str(self.ws))

    def test_check_valid(self):
        self.ok(self.r1())
        checks = self.agg()["checks"]
        self.assertEqual(list(checks), [FC])
        self.assertEqual(checks[FC]["check"], CHK)
        self.assertEqual(checks[FC], next(f for f in self.agg()["findings"] if f["id"] == FC))

    def test_check_null(self):
        self.ok(self.r1(None))
        self.assertEqual(self.agg()["checks"], {})

    def test_check_not_reproducing(self):
        self.bad(self.r1("exit 0"))

    def test_check_error(self):
        self.bad(self.r1("exit 2"))
        self.bad(self.r1("exit 1", verdict="unverified", unverified_reason="external"))

    def test_check_line_shift(self):
        for cmd in ("sed -n 5p 1-s.md | grep 60 && exit 1 || exit 0",
                    "sed -n 1,12p 1-s.md | grep 60 && exit 1 || exit 0"):
            with self.subTest(cmd):
                self.bad(self.r1(cmd))

    def test_check_abs_snapshot_path(self):
        self.ok(self.r1())
        snap = self.ws / "round-1/snapshot"
        cmd = f'grep -Hn "timeout=60" {shlex.quote(str(snap))}/1-s.md && exit 1 || exit 0'
        f = self.finding(R1, 1, **{"class": "ref-mismatch", "target": r(1, 5), "affected": [r(1, 5)], "check": cmd})
        agents = json.loads((self.ws / "round-1/assign.json").read_text())["agents"]
        self.report(self.ws, 1, R1, [f], next(a for a in agents if a["name"] == R1)["ranges"])
        self.bad(self.cli("aggregate", "--ws", str(self.ws), "--round", "1"))
        self.assertEqual(sorted(x.name for x in (self.ws / "round-1").iterdir() if "snapshot" in x.name),
                         ["snapshot"])
        self.assertEqual([x.name for x in snap.iterdir()], ["1-s.md"])

    def test_run_check_timeout(self):
        self.assertIsNone(audit_ws.run_check("sleep 5", self.tmp, self.tmp, timeout=1)[0])

    def test_run_check_env(self):
        self.ok(self.r1())
        tree = Path(json.loads((self.ws / "round-1/targets.json").read_text())["tree"])
        cmd = 'test -f 1-s.md && test "$TREE" = ' + shlex.quote(str(tree))
        self.assertEqual(audit_ws.run_check(cmd, self.ws / "round-1/snapshot", tree)[0], 0)

    def test_check_fixed_kept(self):
        self.ok(self.r1())
        self.ok(self.round2(spec20(L5="timeout=30\n")))
        agg = self.agg(2)
        self.assertNotIn(FC, [f["id"] for f in agg["findings"]])
        self.assertTrue(agg["checks"][FC]["target"].startswith("round-2/"))

    def test_check_regression_readded(self):
        self.ok(self.r1())
        self.ok(self.round2(spec20(L5="timeout=30\n", L12="timeout=60\n")))
        agg = self.agg(2)
        f = next(f for f in agg["findings"] if f["id"] == FC)
        self.assertTrue(f["target"].startswith("round-2/"))
        self.assertTrue(all(a.startswith("round-2/") for a in f["affected"]) and f["affected"])
        self.assertTrue(f["evidence"].startswith("exit 1"))
        self.assertIn("1-s.md:12", f["evidence"])
        self.assertEqual(agg["counts"]["fail"], 1)
        rc, dec, err = self.cli("decide", "--ws", str(self.ws), "--round", "2")
        self.assertEqual((rc, dec["action"]), (0, "fix"), err)

    def test_check_error_readded(self):
        self.ok(self.r1())
        self.set_check("exit 2")
        self.ok(self.round2(spec20(L5="timeout=30\n")))
        self.assertIn(FC, [f["id"] for f in self.agg(2)["findings"]])

    def test_check_unresolved_not_duplicated(self):
        self.ok(self.r1())
        self.ok(self.round2(spec20(L5="timeout=30\n", L12="timeout=60\n"),
                            {RR: [self.finding(RR, 1, target=r(2, 5))]}, {RR: [f"{FC}: unresolved {RR}-001"]}))
        agg = self.agg(2)
        self.assertNotIn(FC, [f["id"] for f in agg["findings"]])
        self.assertEqual(agg["counts"]["fail"], 1)

    def test_checks_cumulative(self):
        self.ok(self.r1())
        chk2 = 'grep -Hn "^X12$" 1-s.md && exit 1 || exit 0'
        self.ok(self.round2(spec20(L12="X12\n"), {RR: [self.finding(RR, 1, target=r(2, 12), check=chk2)]}))
        self.assertEqual(set(self.agg(2)["checks"]), {FC, f"{RR}-001"})

    def test_c9_failed(self):
        self.ok(self.r1())
        rc, out, err = self.c9()
        self.assertEqual(rc, 0, err)
        self.assertEqual(len(out["failed"]), 1, out)
        f = out["failed"][0]
        self.assertEqual(set(f), {"id", "fix_class", "claim", "output"})
        self.assertEqual(f["id"], FC)
        self.assertIn("1-s.md:5", f["output"])
        self.assertTrue((self.tmp / "tmproot/spec-audit" / self.ws.name / "check/1-s.md").is_file())
        self.spec.write_text("".join(spec20(L5="timeout=30\n")))
        rc, out, err = self.c9()
        self.assertEqual((rc, out), (0, {"failed": []}), err)

    def test_c9_error(self):
        self.ok(self.r1())
        self.set_check("exit 2")
        rc, out, err = self.c9()
        self.assertEqual(rc, 0, err)
        self.assertEqual([f["id"] for f in out["failed"]], [FC])

    def test_run_check_non_utf8(self):
        code, out = audit_ws.run_check(r"printf '\xff\xfe'; exit 1", self.tmp, self.tmp)
        self.assertEqual(code, 1)
        self.assertIsInstance(out, str)

    def test_c9_non_utf8(self):
        self.ok(self.r1())
        self.set_check(r"printf '\xff\xfe'; exit 1")
        rc, out, err = self.c9()
        self.assertEqual(rc, 0, err)
        self.assertEqual([f["id"] for f in out["failed"]], [FC])

    def test_check_readded_recheck_r3(self):
        self.ok(self.r1())
        self.ok(self.round2(spec20(L5="timeout=30\n", L12="timeout=60\n")))
        self.assertIn(FC, [f["id"] for f in self.agg(2)["findings"]])
        rc, out, err = self.cli("init", "--ws", str(self.ws), "--round", "3")
        self.assertEqual(rc, 0, err)
        owners = [a["name"] for a in out["agents"] if FC in a["recheck"]]
        self.assertEqual(len(owners), 1, out["agents"])
        self.assertTrue(owners[0].startswith("refs-"))

    def test_c9_no_aggregate(self):
        d = self.repo({SP: "".join(spec20())})
        rc, _, err = self.c1("--spec", str(d / SP))
        self.assertEqual(rc, 0, err)
        self.assertNotEqual(self.c9()[0], 0)


class SkillMdTest(Base):
    def test_skill_md_hash(self) -> None:
        text = (SCRIPTS.parent / "SKILL.md").read_text(encoding="utf-8")
        line = "스킬 버전: " + audit_ws.skill_hash()
        self.assertEqual(text.splitlines().count(line), 1)


if __name__ == "__main__":
    unittest.main()
