from __future__ import annotations

import hashlib
import json
import os
import re
import random
import shlex
import shutil
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
            "SUPERPOWERS_AUDIT_STATE": str(self.tmp / "state"),
            "CLAUDE_CODE_SESSION_ID": "sess-test",
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
        rc, out, err = self.cli("init", "--skill-version", audit_ws.skill_hash(), *args)
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
               extra: str = "") -> Path:
        body = "```findings\n" + "".join(json.dumps(f, ensure_ascii=False) + "\n" for f in findings) + "```\n"
        body += "```coverage\n" + "".join(c + "\n" for c in coverage) + "```\n"
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
        rc, _, err = self.cli("aggregate", "--ws", str(ws))
        self.assertEqual(rc, 0, err)
        return ws

    def finish(self, ws: Path, disp: dict) -> tuple[int, dict | None, str]:
        p = self.tmp / "disp.json"
        p.write_text(json.dumps({"findings": disp}, ensure_ascii=False))
        return self.cli("finish", "--ws", str(ws), "--dispositions", str(p))

    def apply_all(self, ws: Path) -> dict:
        """집계된 모든 라운드의 처분 대상 finding에 apply."""
        return {f["id"]: {"d": "apply"} for p in sorted(ws.glob("round-*/aggregate.json"))
                for f in json.loads(p.read_text())["findings"] if f["unverified_reason"] != "context"}


class OpenStateTest(Base):
    FILES = {"plans/p.md": "# p\n`a.txt`\n", "a.txt": "x\n"}

    def open_json(self, ws: Path) -> Path:
        return audit_ws.open_path(ws)

    def start(self) -> Path:
        d = self.repo(self.FILES)
        rc, out, err = self.c1("--plan", str(d / "plans/p.md"))
        self.assertEqual(rc, 0, err)
        self.d = d
        return Path(out["ws"])

    def test_c1_writes_open(self):
        ws = self.start()
        o = json.loads(self.open_json(ws).read_text())
        self.assertEqual((o["round"], o["session"], o["ws"]), (1, "sess-test", str(ws)))
        self.assertEqual(o["tree"], str(self.d.resolve()))
        self.assertIn(str((self.d / "plans/p.md").resolve()), o["targets"])
        self.assertTrue(all(Path(t).is_absolute() for t in o["targets"]))

    def test_session_null_without_env(self):
        os.environ.pop("CLAUDE_CODE_SESSION_ID")
        ws = self.start()
        self.assertIsNone(json.loads(self.open_json(ws).read_text())["session"])

    def test_c3_exit0_removes_open(self):
        ws = self.round1_done(self.FILES)
        self.assertFalse(self.open_json(ws).exists())

    def test_c3_target_modified_removes_open(self):
        ws = self.start()
        (self.d / "plans/p.md").write_text("changed\n")
        rc, out, _ = self.cli("aggregate", "--ws", str(ws))
        self.assertEqual(rc, 3)
        self.assertIn("target_modified", out)
        self.assertFalse(self.open_json(ws).exists())

    def test_c3_invalid_keeps_open(self):
        ws = self.start()
        rc, out, _ = self.cli("aggregate", "--ws", str(ws))
        self.assertEqual(rc, 3)
        self.assertIn("invalid", out)
        self.assertTrue(self.open_json(ws).exists())

    def edit_and_review(self) -> tuple[Path, tuple]:
        ws = self.round1_done(self.FILES)
        Path(json.loads((ws / "round-1/targets.json").read_text())["targets"][0]["path"]).write_text("# p2\n")
        return ws, self.cli("review", "--ws", str(ws))

    def test_c2_writes_open_round2(self):
        ws, (rc, _, err) = self.edit_and_review()
        self.assertEqual(rc, 0, err)
        self.assertEqual(json.loads(self.open_json(ws).read_text())["round"], 2)

    def test_clean_while_open_aborts(self):
        ws = self.start()
        self.assertEqual(self.cli("clean", "--ws", str(ws))[0], 0)
        self.assertTrue((ws / audit_ws.ABORTED).exists())
        self.assertFalse((audit_ws.tmproot() / "spec-audit" / ws.name).exists())

    def test_clean_after_close_no_abort(self):
        ws = self.round1_done(self.FILES)
        self.assertEqual(self.cli("clean", "--ws", str(ws))[0], 0)
        self.assertFalse((ws / audit_ws.ABORTED).exists())

    def aborted_round2(self) -> Path:
        ws, (rc, _, err) = self.edit_and_review()
        self.assertEqual(rc, 0, err)
        self.assertEqual(self.cli("clean", "--ws", str(ws))[0], 0)
        return ws

    def test_c2_after_abort_fails(self):
        ws = self.aborted_round2()
        rc, _, err = self.cli("review", "--ws", str(ws))
        self.assertNotEqual(rc, 0)
        self.assertIn("감사 중단됨", err)

    def test_c3_after_abort_fails(self):
        ws = self.start()
        self.cli("clean", "--ws", str(ws))
        rc, _, err = self.cli("aggregate", "--ws", str(ws))
        self.assertNotEqual(rc, 0)
        self.assertIn("감사 중단됨", err)

    def test_c1_clears_abort(self):
        ws = self.start()
        self.cli("clean", "--ws", str(ws))
        rc, _, err = self.c1("--plan", str(self.d / "plans/p.md"))
        self.assertEqual(rc, 0, err)
        self.assertFalse((ws / audit_ws.ABORTED).exists())


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
        self.assertEqual((set(out), out["round"]), ({"ws", "round", "agents"}, 1))
        self.assertTrue({"name", "prompt"} <= set(out["agents"][0]))
        self.assertEqual(json.loads((W / "round-1/assign.json").read_text()), {"agents": out["agents"]})
        (W / "round-2").mkdir()
        (self.tmproot() / "spec-audit" / W.name / "stale").mkdir(parents=True)
        self.ok("--plan", p, "--spec", s)  # D6 재생성(이전 W는 보관)
        self.assertEqual(sorted(x.name for x in W.iterdir()), ["round-1"])
        self.assertFalse((self.tmproot() / "spec-audit" / W.name / "stale").exists())

    def test_c1_archives_previous_ws(self):
        repo = self.repo({"docs/specs/s.md": "# S\nx\n"})
        s = str(repo / "docs/specs/s.md")
        W = Path(self.ok("--spec", s)["ws"])
        (W / "round-1/marker").write_text("1")
        self.ok("--spec", s)
        (W / "round-1/marker").write_text("2")
        self.ok("--spec", s)  # 같은 초에 두 번 보관해도 덮지 않는다
        old = sorted(x for x in W.parent.iterdir() if x.name.startswith(W.name + "."))
        self.assertEqual(len(old), 2, old)
        for x in old:
            self.assertRegex(x.name, re.escape(W.name) + r"\.\d{8}-\d{6}(-\d+)?$")
        self.assertEqual(sorted((x / "round-1/marker").read_text() for x in old), ["1", "2"])
        self.assertFalse((W / "round-1/marker").exists())

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
        rc, _, err = self.cli("init", "--skill-version", "0" * 12, "--spec", s)
        self.assertNotEqual(rc, 0)
        self.assertIn("/reload-plugins", err)
        self.assertFalse((repo / ".superpowers").exists())
        rc, _, err = self.cli("init", "--spec", s)
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
        return self.cli("aggregate", "--ws", str(self.ws))

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
                self.assertEqual(retry["ranges"], orig["ranges"])
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
        self.assertEqual(set(agg), {"findings", "review_gap", "counts"})

    def test_aggregate_md(self):
        self.start()
        self.write_all({R1: [self.finding(R1, 1, claim="a|b\nc")],
                        S1: [self.finding(S1, 1, verdict="unverified", unverified_reason="context")]})
        self.ok()
        md = (self.ws / "round-1/aggregate.md").read_text()
        lines = md.splitlines()
        version = json.loads(PLUGIN_JSON.read_text())["version"]
        self.assertEqual(lines[0], "# SPEC Audit · round 1 · 지적 1건")
        self.assertTrue(lines[1].startswith("대상: docs/specs/s.md, docs/canon/c.md · "), lines[1])
        self.assertIn(f"플러그인 {version}", lines[1])
        for name in self.agents:
            self.assertIn(name, lines[1])
        self.assertRegex(lines[2], r"^fail 1 · unverified 0 · 미검토 1줄$")
        self.assertIn("| id | 판정 | 축 | 위치 | 주장 | 근거 | 권고 | 영향 위치 |", md)
        i = lines.index("|---|---|---|---|---|---|---|---|")
        self.assertEqual(len(lines) - i - 1, 1)  # context finding은 표에 없다
        self.assertIn("a\\|b c", lines[i + 1])

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

class CleanTest(Base):
    FILES = {"docs/specs/s.md": "".join(f"s{k}\n" for k in range(1, 21))}

    def test_T19_clean(self):
        ws = self.round1_done(self.FILES)
        tmp = audit_ws.tmproot() / "spec-audit" / ws.name
        tmp.mkdir(parents=True, exist_ok=True)
        (tmp / "k").write_text("x")
        self.assertEqual(self.cli("clean", "--ws", str(ws))[0], 0)
        self.assertFalse(tmp.exists())
        self.assertTrue(ws.exists())


def lines(n: int) -> list[str]:
    return [f"s{k}\n" for k in range(1, n + 1)]


SP = "docs/specs/s.md"
CANON_FILES = {SP: "상위 정본: `docs/canon/c.md`\n" + "".join(lines(40)[1:]),
               "docs/canon/c.md": "".join(f"c{k}\n" for k in range(1, 11))}
RR, SC2 = "refs-r2-s1", "selfcontained-r2-s1"


def r(n: int, a: int, b: int | None = None, snap: str = "1-s.md") -> str:
    return audit_ws.fmt_range(n, snap, a, b or a)


class GateTest(Base):
    PLAN, SPEC = "docs/plans/p-plan.md", "docs/specs/s-spec.md"
    FILES = {PLAN: "# p\n", SPEC: "# s\n"}
    SDD = Path(audit_ws.__file__).resolve().parents[2] / "subagent-driven-development" / "scripts" / "sdd-workspace"

    def passed(self, files: dict[str, str] | None = None) -> tuple[Path, dict]:
        """init → 보고 → aggregate → finish(전부 apply, check 없음)."""
        ws = self.round1_done(files or self.FILES)
        rc, out, err = self.finish(ws, self.apply_all(ws))
        self.assertEqual((rc, out["done"]), (0, True), err)
        tj = json.loads((ws / "round-1" / "targets.json").read_text())
        return ws, {Path(t["path"]).name: Path(t["path"]) for t in tj["targets"]}

    def records(self) -> list[Path]:
        return list((audit_ws.state_dir() / "audit-pass").glob("*.json"))

    def gate(self, plan: Path) -> tuple[int, str]:
        rc, _, err = self.cli("gate", str(plan))
        return rc, err

    def test_pass_with_plan_writes_record(self):
        ws, f = self.passed()
        sha = hashlib.sha256(f["p-plan.md"].read_bytes()).hexdigest()
        rec = json.loads(audit_ws.pass_record_path(sha).read_text())
        self.assertEqual(rec["plan"], str(f["p-plan.md"]))
        self.assertEqual({t["path"] for t in rec["targets"]}, {str(f["p-plan.md"]), str(f["s-spec.md"])})
        self.assertTrue(all(set(t) == {"path", "sha256"} for t in rec["targets"]))
        self.assertEqual((rec["ws"], rec["plugin_version"]), (str(ws), json.loads(PLUGIN_JSON.read_text())["version"]))

    def test_pass_without_plan_no_record(self):
        self.passed({self.SPEC: "# s\n"})
        self.assertEqual(self.records(), [])

    def test_fix_no_record(self):
        d = self.repo(self.FILES)
        rc, out, err = self.c1("--plan", str(d / self.PLAN), "--spec", str(d / self.SPEC))
        self.assertEqual(rc, 0, err)
        for i, a in enumerate(out["agents"]):
            fs = [self.finding(a["name"], 1)] if i == 0 else []
            self.report(Path(out["ws"]), 1, a["name"], fs, a["ranges"])
        self.assertEqual(self.cli("aggregate", "--ws", out["ws"])[0], 0)
        rc, res, err = self.finish(Path(out["ws"]), {})
        self.assertEqual((rc, res["done"]), (1, False), err)
        self.assertEqual(self.records(), [])

    def test_record_excludes_other(self):
        _, f = self.passed({self.PLAN: "# p\n", self.SPEC: "# s\n상위 정본: `docs/canon.md`\n",
                            "docs/canon.md": "c\n"})
        rec = self.records()[0].read_text()
        self.assertIn("s-spec.md", rec)
        self.assertNotIn("canon", rec)

    def test_state_dir_xdg_default(self):
        os.environ.pop("SUPERPOWERS_AUDIT_STATE")
        for xdg in (None, ""):
            if xdg is None:
                os.environ.pop("XDG_STATE_HOME", None)
            else:
                os.environ["XDG_STATE_HOME"] = xdg
            self.assertEqual(audit_ws.state_dir(), Path.home() / ".local/state/superpowers")
        os.environ["XDG_STATE_HOME"] = str(self.tmp / "x")
        self.addCleanup(os.environ.pop, "XDG_STATE_HOME", None)
        self.assertEqual(audit_ws.state_dir(), self.tmp / "x" / "superpowers")

    def test_gate_pass(self):
        _, f = self.passed()
        self.assertEqual(self.gate(f["p-plan.md"]), (0, ""))

    def test_gate_no_record(self):
        d = self.repo(self.FILES)
        rc, err = self.gate(d / self.PLAN)
        self.assertEqual(rc, 1)
        self.assertIn("감사 완료 기록 없음", err)

    def test_gate_plan_changed(self):
        _, f = self.passed()
        f["p-plan.md"].write_text("# p changed\n")
        rc, err = self.gate(f["p-plan.md"])
        self.assertEqual(rc, 1)
        self.assertIn("감사 완료 기록 없음", err)

    def test_gate_spec_changed(self):
        _, f = self.passed()
        f["s-spec.md"].write_text("# s changed\n")
        rc, err = self.gate(f["p-plan.md"])
        self.assertEqual(rc, 1)
        self.assertIn(f"{f['s-spec.md']}가 감사 완료 뒤 바뀌었다", err)

    def test_gate_spec_missing(self):
        _, f = self.passed()
        f["s-spec.md"].unlink()
        rc, err = self.gate(f["p-plan.md"])
        self.assertEqual(rc, 1)
        self.assertIn(f"{f['s-spec.md']}가 감사 완료 뒤 바뀌었다", err)

    def test_gate_other_changed_passes(self):
        _, f = self.passed({self.PLAN: "# p\n", self.SPEC: "# s\n상위 정본: `docs/canon.md`\n",
                            "docs/canon.md": "c\n"})
        (f["p-plan.md"].parents[1] / "canon.md").write_text("changed\n")
        self.assertEqual(self.gate(f["p-plan.md"]), (0, ""))

    def sdd(self, plan: Path, gate: bool) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env.pop("SUPERPOWERS_AUDIT_GATE", None)
        if gate:
            env["SUPERPOWERS_AUDIT_GATE"] = "1"
        return subprocess.run(["bash", str(self.SDD), str(plan)], cwd=plan.parent,
                              env=env, capture_output=True, text=True)

    def test_sdd_workspace_gate_off(self):
        d = self.repo(self.FILES)
        self.assertEqual(self.sdd(d / self.PLAN, False).returncode, 0)

    def test_sdd_workspace_gate_on_blocks(self):
        d = self.repo(self.FILES)
        p = self.sdd(d / self.PLAN, True)
        self.assertEqual(p.returncode, 1)
        self.assertIn("감사 완료 기록 없음", p.stderr)

    def test_sdd_workspace_gate_on_passes(self):
        _, f = self.passed()
        p = self.sdd(f["p-plan.md"], True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(Path(p.stdout.strip()).parent.name, "sdd")


class ReviewTest(Base):
    def setup1(self, files: dict[str, str], findings: dict | None = None) -> Path:
        ws = self.round1_done(files, findings)
        self.targets = json.loads((ws / "round-1/targets.json").read_text())["targets"]
        return ws

    def write(self, L: list[str], k: int = 0) -> None:
        Path(self.targets[k]["path"]).write_text("".join(L))

    def c2(self, ws: Path) -> tuple[int, dict | None, str]:
        return self.cli("review", "--ws", str(ws))

    def ok2(self, ws: Path) -> dict:
        rc, out, err = self.c2(ws)
        self.assertEqual(rc, 0, err)
        return out

    def axis_ranges(self, out: dict) -> dict:
        res: dict[str, list] = {}
        for a in out["agents"]:
            res.setdefault(a["axis"], []).extend(a["ranges"])
        return res

    def write2(self, ws: Path, out: dict, findings: dict | None = None) -> None:
        for a in out["agents"]:
            self.report(ws, 2, a["name"], (findings or {}).get(a["name"], []), a["ranges"])

    def agg2(self, ws: Path) -> tuple[int, dict | None, str]:
        return self.cli("aggregate", "--ws", str(ws))

    def test_T09_changed(self):
        ws = self.setup1({SP: "".join(lines(10))})
        L = lines(10)
        L[3] = "X4\n"
        self.write(L)
        out = self.ok2(ws)
        self.assertEqual(out["round"], 2)
        self.assertEqual(self.axis_ranges(out), {ax: [r(2, 4)] for ax in ("refs", "selfcontained", "rootcause")})
        patch = (ws / "round-2/diff.patch").read_bytes()
        for part in (b"-s4\n", b"+X4\n", SP.encode()):
            self.assertIn(part, patch)

    def test_T09_delete_only(self):
        old = [f"{k}\n".encode() for k in range(1, 11)]
        self.assertEqual(audit_ws.changed_lines(old, old[:4] + old[5:]), {4, 5})
        self.assertEqual(audit_ws.changed_lines(old, old[1:]), {1})
        self.assertEqual(audit_ws.changed_lines(old, old[:-1]), {9})

    def three(self, n: int = 3000) -> list[str]:
        L = lines(n)
        for k in (100, 200, 300):
            L[k - 1] = f"X{k}\n"
        return L

    def test_T05_basic(self):
        ws = self.setup1({SP: "".join(lines(3000))}, {R1: [self.finding(R1, 1, target=r(1, 50))]})
        self.write(self.three())
        out = self.ok2(ws)
        want = [r(2, 100), r(2, 200), r(2, 300)]  # 지적 위치(50)가 아니라 바뀐 줄만
        for ax in ("refs", "selfcontained", "rootcause"):
            got = [a for a in out["agents"] if a["axis"] == ax]
            self.assertEqual([a["ranges"] for a in got], [want], ax)
        self.assertFalse([a for a in out["agents"] if a["axis"] == "oracle"])
        self.assertEqual(json.loads((ws / "round-2/assign.json").read_text()), {"agents": out["agents"]})

    def test_T05_other_only(self):
        ws = self.setup1(CANON_FILES)
        self.write([f"c{k}\n" if k != 2 else "X\n" for k in range(1, 11)], k=1)
        out = self.ok2(ws)
        self.assertEqual(self.axis_ranges(out), {"refs": [r(2, 2, snap="2-c.md")]})

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

    def test_unchanged_fails(self):
        ws = self.setup1({SP: "".join(lines(10))})
        rc, _, err = self.c2(ws)
        self.assertNotEqual(rc, 0)
        self.assertIn("바뀐 줄이 없다", err)
        self.assertFalse((ws / "round-2").exists())

    def r2_basic(self) -> tuple[Path, dict]:
        """40줄 spec, 라운드 1 refs finding(:1), 4번째 줄 수정 후 C2."""
        ws = self.setup1({SP: "".join(lines(40))}, {R1: [self.finding(R1, 1, target=r(1, 1))]})
        L = lines(40)
        L[3] = "X4\n"
        self.write(L)
        return ws, self.ok2(ws)

    def test_second_review_fails(self):
        ws, out = self.r2_basic()
        r2 = lines(40)
        r2[3] = "X4\n"
        before = (ws / "round-2/assign.json").read_text()

        def again() -> None:
            more = list(r2)
            more[9] = "X10\n"
            self.write(more)
            rc, _, err = self.c2(ws)
            self.assertNotEqual(rc, 0)
            self.assertIn("한 번뿐", err)
            self.assertFalse((ws / "round-3").exists())
            self.assertEqual((ws / "round-2/assign.json").read_text(), before)
            self.write(r2)

        again()  # C2 직후
        self.write2(ws, out)
        self.assertEqual(self.agg2(ws)[:2], (0, {}))
        again()  # C3 뒤

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
        self.assertEqual(self.cli("aggregate", "--ws", str(self.ws))[0], 0)
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
        rc, _, err = self.c2(self.ws)
        self.assertNotEqual(rc, 0)
        self.assertIn("aggregate.json 없음", err)

    def test_T33_c2_missing_other(self):
        ws = self.setup1(CANON_FILES)
        Path(self.targets[1]["path"]).unlink()
        rc, _, err = self.c2(ws)
        self.assertNotEqual(rc, 0)
        self.assertIn("docs/canon/c.md", err)

    def test_T34_c2(self):
        ws, out = self.r2_basic()
        self.assertTrue(out["agents"])
        for a in out["agents"]:
            text = Path(a["prompt"]).read_text()
            for part in [*a["ranges"], str(ws / "round-2/diff.patch"), "라운드: 2 (수정분 재검토)"]:
                self.assertIn(part, text, a["name"])
        r1 = json.loads((ws / "round-1/assign.json").read_text())["agents"]
        self.assertNotIn("- diff.patch(", Path(r1[0]["prompt"]).read_text())

    def test_T10_n2_target_outside_assignment(self):
        ws, out = self.r2_basic()
        self.write2(ws, out, {SC2: [self.finding(SC2, 1, target=r(2, 10))]})
        rc, res, err = self.agg2(ws)
        self.assertEqual(rc, 3, err)
        self.assertEqual(len(res["invalid"]), 1, res)
        self.assertIn(SC2, res["invalid"][0]["reason"])
        self.assertIn("배정 범위", res["invalid"][0]["reason"])

    def test_T25_n2(self):
        ws, out = self.r2_basic()
        self.write2(ws, out, {SC2: [self.finding(SC2, 1, target=r(2, 3, 5))],
                              RR: [self.finding(RR, 1, target=r(2, 10))]})  # refs는 배정 밖도 허용
        rc, res, err = self.agg2(ws)
        self.assertEqual((rc, res), (0, {}), err)
        agg = json.loads((ws / "round-2/aggregate.json").read_text())
        self.assertEqual(sorted(f["id"] for f in agg["findings"]), [f"{RR}-001", f"{SC2}-001"])
        self.assertTrue((ws / "round-2/aggregate.md").read_text().startswith("# SPEC Audit · round 2 (수정분 재검토)"))

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
    """C3 ② check 재현 검증(verify_check)."""

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
        return self.cli("aggregate", "--ws", str(self.ws))

    def agg(self, n: int = 1) -> dict:
        return json.loads((self.ws / f"round-{n}/aggregate.json").read_text())

    def ok(self, res: tuple) -> None:
        self.assertEqual(res[:2], (0, {}), res[2])

    def bad(self, res: tuple) -> None:
        rc, out, err = res
        self.assertEqual(rc, 3, err)
        self.assertEqual(len(out["invalid"]), 1, out)
        self.assertIn("check", out["invalid"][0]["reason"])

    def test_check_valid(self):
        self.ok(self.r1())
        self.assertEqual([(f["id"], f["check"]) for f in self.agg()["findings"]], [(FC, CHK)])

    def test_check_null(self):
        self.ok(self.r1(None))
        self.assertIsNone(self.agg()["findings"][0]["check"])

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
        self.bad(self.cli("aggregate", "--ws", str(self.ws)))
        self.assertEqual(sorted(x.name for x in (self.ws / "round-1").iterdir() if "snapshot" in x.name),
                         ["snapshot"])
        self.assertEqual([x.name for x in snap.iterdir()], ["1-s.md"])

    def test_recover_stranded_verifying(self):
        self.ok(self.r1())
        snap = self.ws / "round-1/snapshot"
        snap.rename(snap.with_name("snapshot.verifying"))
        rc, out, err = self.finish(self.ws, {FC: {"d": "reject", "why": "w"}})
        self.assertEqual(rc, 0, err)
        self.assertTrue(snap.is_dir())
        self.assertFalse(snap.with_name("snapshot.verifying").exists())

    def test_both_snapshot_dirs_fail_with_path(self):
        self.ok(self.r1())
        snap = self.ws / "round-1/snapshot"
        hid = snap.with_name("snapshot.verifying")
        shutil.copytree(snap, hid)
        for cmd in (["finish", "--ws", str(self.ws), "--dispositions", str(self.tmp / "none.json")],
                    ["aggregate", "--ws", str(self.ws)], ["review", "--ws", str(self.ws)]):
            with self.subTest(cmd[0]):
                rc, out, err = self.cli(*cmd)
                self.assertNotEqual(rc, 0)
                self.assertIn(str(hid), err)

    def test_run_check_timeout(self):
        self.assertIsNone(audit_ws.run_check("sleep 5", self.tmp, self.tmp, timeout=1)[0])

    def test_run_check_env(self):
        self.ok(self.r1())
        tree = Path(json.loads((self.ws / "round-1/targets.json").read_text())["tree"])
        cmd = 'test -f 1-s.md && test "$TREE" = ' + shlex.quote(str(tree))
        self.assertEqual(audit_ws.run_check(cmd, self.ws / "round-1/snapshot", tree)[0], 0)

    def test_run_check_non_utf8(self):
        code, out = audit_ws.run_check(r"printf '\xff\xfe'; exit 1", self.tmp, self.tmp)
        self.assertEqual(code, 1)
        self.assertIsInstance(out, str)


class FinishTest(Base):
    r1 = CheckTest.r1
    APPLY = {FC: {"d": "apply"}}

    def fin(self, disp: dict) -> tuple[int, dict | None, str]:
        return self.finish(self.ws, disp)

    def result(self, n: int) -> dict:
        return json.loads((self.ws / f"round-{n}/result.json").read_text())

    def test_invalid_dispositions(self):
        self.assertEqual(self.r1()[0], 0)
        cases = [("처분 누락", {}, f"{FC}: 처분 없음"),
                 ("reject why 누락", {FC: {"d": "reject"}}, f"{FC}: 기각 사유(why) 없음"),
                 ("accept why 빈 값", {FC: {"d": "accept", "why": ""}}, f"{FC}: 수용 사유(why) 없음"),
                 ("모르는 id", {FC: {"d": "reject", "why": "w"}, "refs-r1-s1-009": {"d": "apply"}},
                  "refs-r1-s1-009: 이 감사의 지적이 아님"),
                 ("처분 값", {FC: {"d": "fix"}}, f"{FC}: 처분은 apply|reject|accept 중 하나")]
        for label, disp, want in cases:
            with self.subTest(label):
                rc, out, err = self.fin(disp)
                self.assertEqual((rc, out["done"]), (1, False), err)
                self.assertIn(want, out["invalid"])
                self.assertEqual(self.result(1), out)
                self.assertTrue((self.ws / "round-1/result.md").read_text().startswith("# SPEC Audit · 미완"))

    def test_apply_check_failed(self):
        self.assertEqual(self.r1()[0], 0)
        rc, out, err = self.fin(self.APPLY)
        self.assertEqual(rc, 1, err)
        self.assertEqual((out["done"], out["invalid"], out["review_needed"]), (False, [], False))
        self.assertEqual(len(out["failed"]), 1, out)
        f = out["failed"][0]
        self.assertEqual(set(f), {"id", "claim", "output"})
        self.assertEqual(f["id"], FC)
        self.assertTrue(f["output"].startswith("exit 1\n"), f["output"])
        self.assertIn("1-s.md:5", f["output"])
        self.assertTrue((self.tmp / "tmproot/spec-audit" / self.ws.name / "check/1-s.md").is_file())

    def test_reject_check_ignored(self):
        self.assertEqual(self.r1()[0], 0)
        rc, out, err = self.fin({FC: {"d": "reject", "why": "오탐"}})
        self.assertEqual((rc, out), (0, {"done": True, "invalid": [], "failed": [], "review_needed": False}), err)

    def test_edit_without_review(self):
        self.assertEqual(self.r1()[0], 0)
        self.spec.write_text("".join(spec20(L5="timeout=30\n")))
        rc, out, err = self.fin(self.APPLY)
        self.assertEqual((rc, out), (1, {"done": False, "invalid": [], "failed": [], "review_needed": True}), err)
        self.assertEqual(self.cli("review", "--ws", str(self.ws))[0], 0)  # 라운드 2 미집계 = 아직 재검토 전
        rc, out, err = self.fin(self.APPLY)
        self.assertEqual((rc, out["review_needed"]), (1, True), err)

    def review_round(self, findings: dict | None = None) -> None:
        rc, out, err = self.cli("review", "--ws", str(self.ws))
        self.assertEqual(rc, 0, err)
        for a in out["agents"]:
            self.report(self.ws, 2, a["name"], (findings or {}).get(a["name"], []), a["ranges"])
        self.assertEqual(self.cli("aggregate", "--ws", str(self.ws))[:2], (0, {}))

    def test_done_after_review(self):
        self.assertEqual(self.r1()[0], 0)
        self.spec.write_text("".join(spec20(L5="timeout=30\n")))
        self.review_round({RR: [self.finding(RR, 1, target=r(2, 5))]})
        rc, out, err = self.fin(self.APPLY)
        self.assertEqual(rc, 1, err)
        self.assertEqual(out["invalid"], [f"{RR}-001: 처분 없음"])
        rc, out, err = self.fin({**self.APPLY, f"{RR}-001": {"d": "accept", "why": "다음 단계"}})
        self.assertEqual((rc, out), (0, {"done": True, "invalid": [], "failed": [], "review_needed": False}), err)
        self.assertEqual(self.result(2), out)
        self.assertTrue((self.ws / "round-2/result.md").read_text().startswith("# SPEC Audit · 완료"))

    def test_context_needs_no_disposition(self):
        ctx = self.finding(S1, 1, verdict="unverified", unverified_reason="context", target=r(1, 2, 3))
        ws = self.round1_done({SP: "".join(lines(10))}, {S1: [ctx]})
        rc, out, err = self.finish(ws, {})
        self.assertEqual((rc, out["done"]), (0, True), err)
        rc, out, err = self.finish(ws, {ctx["id"]: {"d": "apply"}})
        self.assertIn(f"{ctx['id']}: 이 감사의 지적이 아님", out["invalid"])

    def test_rf_empty_all_pass(self):
        ws = self.round1_done({"docs/specs/e.md": ""})
        rc, out, err = self.finish(ws, {})
        self.assertEqual((rc, out["done"]), (0, True), err)

    def test_no_aggregate(self):
        d = self.repo({SP: "".join(spec20())})
        rc, _, err = self.c1("--spec", str(d / SP))
        self.assertEqual(rc, 0, err)
        rc, _, err = self.fin({})
        self.assertNotEqual(rc, 0)
        self.assertIn("aggregate.json 없음", err)

    def test_plan_record_current_sha(self):
        plan, spec = "docs/plans/p-plan.md", "docs/specs/s-spec.md"
        ws = self.round1_done({plan: "# p\n", spec: "# s\n"}, {R1: [self.finding(R1, 1, target=r(1, 1, snap="1-p-plan.md"))]})
        p = Path(json.loads((ws / "round-1/targets.json").read_text())["targets"][0]["path"])
        old = hashlib.sha256(p.read_bytes()).hexdigest()
        p.write_text("# p2\n")
        rc, out, err = self.cli("review", "--ws", str(ws))
        self.assertEqual(rc, 0, err)
        for a in out["agents"]:
            self.report(ws, 2, a["name"], [], a["ranges"])
        self.assertEqual(self.cli("aggregate", "--ws", str(ws))[0], 0)
        rc, out, err = self.finish(ws, self.apply_all(ws))
        self.assertEqual((rc, out["done"]), (0, True), err)
        new = hashlib.sha256(p.read_bytes()).hexdigest()
        self.assertTrue(audit_ws.pass_record_path(new).is_file())
        self.assertFalse(audit_ws.pass_record_path(old).exists())
        self.assertEqual(self.cli("gate", str(p))[0], 0)


class SkillMdTest(Base):
    def test_skill_md_hash(self) -> None:
        text = (SCRIPTS.parent / "SKILL.md").read_text(encoding="utf-8")
        line = "스킬 버전: " + audit_ws.skill_hash()
        self.assertEqual(text.splitlines().count(line), 1)


if __name__ == "__main__":
    unittest.main()


class FinishEdgeTest(Base):
    """에이전트 보고 버그 재현: 처분 파일 형식 오류·대상 파일 비움."""

    def test_findings_not_object_is_invalid(self):
        ws = self.round1_done({"docs/specs/s-spec.md": "# s\n"})
        p = self.tmp / "d.json"
        p.write_text(json.dumps({"findings": []}))
        rc, out, err = self.cli("finish", "--ws", str(ws), "--dispositions", str(p))
        self.assertEqual(rc, 1, err)
        self.assertTrue(out["invalid"] and "형식" in out["invalid"][0])

    def test_emptied_target_needs_no_review(self):
        ws = self.round1_done({"docs/specs/s-spec.md": "# s\na\nb\n"})
        tj = json.loads((ws / "round-1" / "targets.json").read_text())
        Path(tj["targets"][0]["path"]).write_text("")
        p = self.tmp / "d.json"
        p.write_text(json.dumps({"findings": {}}))
        rc, out, err = self.cli("finish", "--ws", str(ws), "--dispositions", str(p))
        self.assertEqual((rc, out["review_needed"]), (0, False), err)
