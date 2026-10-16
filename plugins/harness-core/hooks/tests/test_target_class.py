from __future__ import annotations

import multiprocessing
import os
import stat
import subprocess
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import target_class
from _world import World
from ledger import (
    KIND_CREATED,
    KIND_MOVED_IN,
    KIND_PRE_SESSION,
    KIND_TOUCHED,
    Ledger,
    state_dir,
)
from target_class import (
    births,
    is_scratch,
    is_scratch_root,
    normalize,
    protected_name,
    repo_root,
    run,
    session_start,
    switch_mode,
)

w: World


def stat_birth(p):  # 테스트 파일의 독립 구현(오라클)
    return float(subprocess.check_output(["stat", "-c", "%.9W", p], text=True))


def _writer(env, prefix, n, compact_bytes, barrier):
    L = Ledger(env, compact_bytes=compact_bytes) if compact_bytes else Ledger(env)
    barrier.wait()
    for i in range(n):
        L.record(f"/{prefix}/p {i}", KIND_CREATED, "s")


def _run_two(env, a, b):
    mp = multiprocessing.get_context("fork")
    barrier = mp.Barrier(2)
    ps = [mp.Process(target=_writer, args=(env, *x, barrier)) for x in (a, b)]
    for p in ps:
        p.start()
    for p in ps:
        p.join(120)
    return [p.exitcode for p in ps]


class _WorldCase(unittest.TestCase):
    def setUp(self):
        global w
        w = World()
        self.addCleanup(w.close)


class LedgerTest(_WorldCase):
    def ledger_file(self):
        return state_dir(w.environ) / "ledger.tsv"

    def test_ledger_roundtrip_and_dedupe(self):
        env = w.environ
        L = Ledger(env); L.record("/a b/c", KIND_PRE_SESSION, "s1"); L.record("/a b/c", KIND_PRE_SESSION, "s1")
        self.assertEqual([(e.kind, e.session_id) for e in L.entries("/a b/c")], [(KIND_PRE_SESSION, "s1")])
        L.record("/a b/c", KIND_TOUCHED, "s2"); L.record("/a b/c", KIND_TOUCHED, "s2"); self.assertEqual(len(L.entries("/a b/c")), 3)
        L.record("/x", KIND_CREATED, None); self.assertEqual(L.entries("/x"), [])
        self.assertEqual(state_dir(env), Path(w.root) / "state" / "harness-core")

    def test_moved_in_near(self):
        L = Ledger(w.environ); L.record("/d/sub/f", KIND_MOVED_IN, "s1"); L.record("/e", KIND_CREATED, "s1")
        self.assertEqual(L.moved_in_near("/d/sub/f"), "/d/sub/f")       # 자신
        self.assertEqual(L.moved_in_near("/d/sub/f/inner"), "/d/sub/f")  # 상위에 기록
        self.assertEqual(L.moved_in_near("/d"), "/d/sub/f")              # 하위에 기록
        self.assertIsNone(L.moved_in_near("/d/su")); self.assertIsNone(L.moved_in_near("/e"))

    def test_ledger_concurrent_append(self):  # Review Focus 4
        self.assertEqual(_run_two(w.environ, ("A", 500, 0), ("B", 500, 0)), [0, 0])
        lines = self.ledger_file().read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1000)
        self.assertTrue(all(len(x.split("\t")) == 4 for x in lines))
        L = Ledger(w.environ)
        for pre in "AB":
            for i in range(500):
                self.assertEqual(len(L.entries(f"/{pre}/p {i}")), 1, (pre, i))

    def test_ledger_compaction(self):
        f = self.ledger_file(); f.parent.mkdir(parents=True)
        old = time.time() - 8 * 24 * 3600; now = time.time()
        alive = w.fmt("{HOME}/data/a.txt")
        f.write_text(f"/old\t{KIND_TOUCHED}\ts0\t{old}\n/recent\t{KIND_TOUCHED}\ts0\t{now}\n"
                     f"{alive}\t{KIND_MOVED_IN}\ts0\t{old}\n/gone/x\t{KIND_MOVED_IN}\ts0\t{old}\n"
                     + "".join(f"/old{i}\t{KIND_CREATED}\ts0\t{old}\n" for i in range(5)), encoding="utf-8")
        self.assertGreater(f.stat().st_size, 200)
        L = Ledger(w.environ, compact_bytes=200); L.record("/new", KIND_CREATED, "s1")
        for p in ["/old", "/old0", "/old4", "/gone/x"]:
            self.assertEqual(L.entries(p), [], p)
        for p in ["/recent", alive, "/new"]:
            self.assertEqual(len(L.entries(p)), 1, p)
        self.assertEqual(list(f.parent.glob("*.tmp")), [])
        self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600)          # 압축 뒤에도 권한 유지

    def test_new_ledger_mode(self):
        Ledger(w.environ).record("/a", KIND_CREATED, "s1")
        self.assertEqual(stat.S_IMODE(self.ledger_file().stat().st_mode), 0o600)

    def test_no_home_no_ledger(self):                                    # 상대 경로 장부를 만들지 않는다
        cwd = os.getcwd(); os.chdir(w.fmt("{OUT}")); self.addCleanup(os.chdir, cwd)
        for env in ({"PATH": "/usr/bin"}, {"HOME": "", "PATH": "/usr/bin"}, {"HOME": "", "XDG_STATE_HOME": "rel"}):
            L = Ledger(env); L.record("/a", KIND_CREATED, "s1")
            self.assertEqual(L.entries("/a"), []); self.assertIsNone(L.moved_in_near("/a"))
        self.assertEqual(os.listdir(w.fmt("{OUT}")), [])

    def test_ledger_compaction_concurrent_append(self):  # Review Focus 4, 재감사 rootcause-r1-s1-006
        self.assertEqual(_run_two(w.environ, ("A", 300, 1), ("B", 300, 0)), [0, 0])
        L = Ledger(w.environ)
        for pre in "AB":
            for i in range(300):
                self.assertEqual(len(L.entries(f"/{pre}/p {i}")), 1, (pre, i))


class BasicsTest(_WorldCase):
    def test_session_start(self):
        self.assertAlmostEqual(session_start(w.transcript, w.environ), stat_birth(w.transcript), places=3)
        self.assertIsNone(session_start(None, w.environ)); self.assertIsNone(session_start("/nope", w.environ))
        self.assertAlmostEqual(w.ctx().session_start, w.session_start, places=3)

    def test_births_skips_zero(self):
        self.assertEqual(target_class._parse_stat("0.000000000 /p\n12.5 /q\n"), {"/q": 12.5})

    def test_births_real_names(self):
        odd = w.fmt("{OUT}/공백 이름.txt"); Path(odd).write_text("x")
        nl = w.fmt("{OUT}/줄\n바꿈"); Path(nl).write_text("x")
        pre = w.fmt("{HOME}/notes.md")
        b = births([odd, pre, nl, w.fmt("{OUT}/none"), "-n"], w.ctx())
        self.assertEqual(set(b), {odd, pre})
        self.assertAlmostEqual(b[odd], stat_birth(odd), places=3)
        self.assertLess(b[pre], w.session_start)

    def test_run_respects_deadline(self):
        self.assertIsNone(run(["true"], w.ctx(budget=0)))
        r = run(["pwd"], w.ctx(), cwd=w.fmt("{REPO}")); self.assertEqual(r.stdout.strip(), w.fmt("{REPO}"))
        self.assertIsNone(run(["/nonexistent-cmd"], w.ctx()))

    def test_normalize(self):
        self.assertEqual(normalize("/a/b/../c", False), "/a/c")
        out = w.fmt("{OUT}"); os.mkdir(f"{out}/real"); os.symlink(f"{out}/real", f"{out}/lnk")
        self.assertEqual(normalize(f"{out}/lnk/f", False), f"{out}/real/f")    # 부모가 링크 → 실제 경로
        self.assertEqual(normalize(f"{out}/lnk", False), f"{out}/lnk")         # 대상 자체가 링크, '/' 없음 → 링크
        self.assertEqual(normalize(f"{out}/lnk", True), f"{out}/real")         # '/' 있음 → 링크 대상
        self.assertEqual(normalize("/", False), "/")
        os.symlink(w.fmt("{REPO}/src"), w.fmt("{SCRATCH}/lnk"))       # 링크 뒤 '..' 는 링크 대상의 부모
        n = normalize(w.fmt("{SCRATCH}/lnk/../README.md"), False)
        self.assertEqual(n, w.fmt("{REPO}/README.md")); self.assertFalse(is_scratch(n, w.ctx()))
        self.assertEqual(normalize(w.fmt("{SCRATCH}/lnk/.."), False), w.fmt("{REPO}"))
        self.assertEqual(normalize(w.fmt("{SCRATCH}/lnk/."), False), w.fmt("{REPO}/src"))
        self.assertEqual(normalize(w.fmt("{SCRATCH}/lnk/"), False), w.fmt("{REPO}/src"))

    def test_scratch(self):
        ctx = w.ctx()
        self.assertTrue(is_scratch(w.fmt("{SCRATCH}/s1/x.txt"), ctx)); self.assertFalse(is_scratch(w.fmt("{SCRATCH}"), ctx))
        self.assertTrue(is_scratch_root(w.fmt("{SCRATCH}"), ctx)); self.assertTrue(is_scratch(w.fmt("{HOME}/.cache/x"), ctx))
        self.assertTrue(is_scratch("/mnt/c/Users/u/AppData/Local/Temp/x", ctx))      # 패턴 일치(실재 무관)
        self.assertFalse(is_scratch("/mnt/c/Users/u/AppData/Local/Temp", ctx))
        self.assertTrue(is_scratch_root("/mnt/c/Users/u/AppData/Local/Temp", ctx))
        self.assertTrue(is_scratch("/tmp/a", ctx)); self.assertTrue(is_scratch_root("/var/tmp", ctx))
        self.assertTrue(is_scratch("/mnt/c/Windows/Temp/a", ctx))
        self.assertFalse(is_scratch("/tmpx/a", ctx)); self.assertFalse(is_scratch(w.fmt("{OUT}/a"), ctx))

    def test_protected_name(self):
        for p in ["/r/.git", "/r/.git/config", "/r/.env", "/r/.env.prod", "/r/.claude/settings.local.json", "/r/x.local.yml",
                  "/h/.ssh/config", "/h/k.pem", "/h/id_ed25519", "/h/.aws/credentials", "/h/.netrc"]:
            self.assertTrue(protected_name(p), p)
        for p in ["/r/.env.example", "/r/.env.sample", "/r/.env.template", "/r/src/env.py", "/r/.github/x"]:
            self.assertFalse(protected_name(p), p)

    def test_world_layout(self):
        for rel in ["README.md", "src/main.py", ".gitignore", ".env", "local.sqlite", "build/out.o", "notes_presession.txt"]:
            self.assertLess(stat_birth(w.fmt("{REPO}/" + rel)), w.session_start, rel)   # 세션 전 파일
        self.assertGreaterEqual(stat_birth(w.fmt("{REPO}/src/probe.ts")), w.session_start)
        self.assertGreaterEqual(stat_birth(w.fmt("{SCRATCH}/s1/x.txt")), w.session_start)
        st = w.sh("git status --porcelain=v1 --ignored=matching")
        for s in [" M README.md", "?? notes_presession.txt", "!! .env", "!! local.sqlite", "!! build/"]:
            self.assertIn(s, st.splitlines(), s)
        self.assertEqual(w.sh("git symbolic-ref refs/remotes/origin/HEAD").strip(), "refs/remotes/origin/main")
        def reflog_time(ref):
            return float(w.sh(f"git reflog show -1 --date=unix --format=%gd {ref}").split("@{")[1].rstrip("}\n"))
        t0 = reflog_time("stash"); t1 = float(w.sh("git log -1 --format=%ct 'stash@{1}'"))
        self.assertGreaterEqual(t0, w.session_start); self.assertLess(t1, w.session_start)
        w.local_branch("sq", pushed=True, before_session=True, squash_merged=True, delete_remote=True)
        w.local_branch("mine", pushed=False, before_session=False)
        self.assertNotEqual(w.sh("git rev-parse sq"), w.sh("git rev-parse origin/main"))
        self.assertEqual(w.sh("git diff sq origin/main -- sq.txt"), "")
        self.assertGreaterEqual(reflog_time("mine"), w.session_start)
        w.clean_tree(); self.assertNotIn(" M README.md", w.sh("git status --porcelain").splitlines())


class SwitchTest(_WorldCase):
    def test_repo_root_relative(self):
        cwd = os.getcwd(); os.chdir(w.fmt("{REPO}")); self.addCleanup(os.chdir, cwd)
        self.assertEqual(repo_root("x/y", w.environ), w.fmt("{REPO}"))
        os.chdir(w.fmt("{OUT}")); self.assertIsNone(repo_root("x/y", w.environ))

    def test_switch_mode(self):
        self.assertEqual(switch_mode(w.fmt("{REPO}/src/main.py"), w.environ), "off")
        w.set_repo_switch("shadow"); self.assertEqual(switch_mode(w.fmt("{REPO}/src/main.py"), w.environ), "shadow")
        w.set_repo_switch("on", local=True); self.assertEqual(switch_mode(w.fmt("{REPO}/x"), w.environ), "on")   # local 우선
        self.assertEqual(switch_mode(w.fmt("{HOME}/data/a.txt"), w.environ), "off")                               # 저장소 밖
        self.assertEqual(switch_mode(None, w.environ), "off")
        self.assertEqual(switch_mode(w.fmt("{REPO}/.git/config"), w.environ), "on")                              # .git 내부
        w.set_repo_switch("bogus", local=True); self.assertEqual(switch_mode(w.fmt("{REPO}/x"), w.environ), "off")


if __name__ == "__main__":
    unittest.main()
