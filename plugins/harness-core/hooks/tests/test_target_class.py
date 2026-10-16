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
    KIND_PRE_DIRTY,
    KIND_PRE_SESSION,
    KIND_TOUCHED,
    Ledger,
    state_dir,
)
from target_class import (
    DIR_ENTRY_CAP,
    GIT_TRACKED,
    IGNORED_ARTIFACT,
    MISSING,
    PRESERVED,
    PROTECTED_NAME,
    SCRATCH,
    SESSION_NEW,
    UNRESOLVED,
    births,
    classify,
    git_ignored,
    git_toplevel,
    git_tracked,
    in_workspace,
    is_linked_worktree_root,
    is_scratch,
    is_scratch_root,
    normalize,
    note_touch,
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

    def test_entries_for(self):
        L = Ledger(w.environ); L.record("/a", KIND_CREATED, "s1"); L.record("/b", KIND_TOUCHED, "s1"); L.record("/c", KIND_TOUCHED, "s1")
        got = L.entries_for(["/a", "/b", "/none"])
        self.assertEqual({p: [e.kind for e in es] for p, es in got.items()}, {"/a": [KIND_CREATED], "/b": [KIND_TOUCHED]})
        self.assertEqual(set(L.entries_for()), {"/a", "/b", "/c"})                     # 인자 없음 = 전부

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


def k(p, ctx=None):
    return classify(w.fmt(p), ctx or w.ctx()).kind


class ClassifyTest(_WorldCase):
    def test_seven_classes(self):
        self.assertEqual(k("{REPO}/nope"), MISSING); self.assertEqual(k("{REPO}/.env"), PROTECTED_NAME)
        self.assertEqual(k("{REPO}/src/main.py"), GIT_TRACKED); self.assertEqual(k("{SCRATCH}/s1/x.txt"), SCRATCH)
        self.assertEqual(k("{REPO}/src/probe.ts"), SESSION_NEW); self.assertEqual(k("{REPO}/build/out.o"), IGNORED_ARTIFACT)
        self.assertEqual(k("{REPO}/local.sqlite"), PRESERVED)                  # ignore 대상이지만 재생성 이름 아님
        self.assertEqual(k("{REPO}/notes_presession.txt"), PRESERVED); self.assertEqual(k("{HOME}/data/a.txt"), PRESERVED)
        self.assertEqual(classify(None, w.ctx()).kind, UNRESOLVED)
        self.assertEqual(k("{SCRATCH}"), UNRESOLVED)                          # 임시 루트 자체(안이 전부 세션 것이어도)

    def test_dir_rule(self):
        self.assertEqual(k("{REPO}/out"), SESSION_NEW); self.assertEqual(k("{REPO}/build"), IGNORED_ARTIFACT)
        self.assertEqual(k("{REPO}/src"), GIT_TRACKED); self.assertEqual(k("{HOME}/data"), PRESERVED)

    def test_session_repo_is_scratch_data(self):      # spec §3.4 분류 1b, 재감사 rootcause-r1-s1-001
        w.sh("git clone -q {REPO} {SCRATCH}/s1/clone"); self.assertEqual(k("{SCRATCH}/s1/clone"), SCRATCH)
        self.assertTrue(classify(w.fmt("{SCRATCH}/s1/clone"), w.ctx()).session_repo)
        self.assertFalse(classify(w.fmt("{SCRATCH}/s1/x.txt"), w.ctx()).session_repo)
        w.sh("git clone -q {REPO} {OUT}/c2"); self.assertEqual(k("{OUT}/c2"), SCRATCH); self.assertEqual(k("{OUT}/c2/.git/config"), SCRATCH)
        w.sh("mkdir -p {SCRATCH}/s1/many && cd {SCRATCH}/s1/many && seq 2001 | xargs touch"); self.assertEqual(k("{SCRATCH}/s1/many"), SCRATCH)
        w.sh("mkdir -p {SCRATCH}/old && echo k > {SCRATCH}/old/k.pem"); self.assertEqual(k("{SCRATCH}/old"), PROTECTED_NAME)   # 임시 폴더라도 보호 이름(재감사 rootcause-r2-s1-001)
        self.assertEqual(k("{SCRATCH}/s1"), SCRATCH)                                       # 안의 세션 clone(.git)으로는 내려가지 않음
        ctx = w.ctx(); ctx.ledger.record(w.fmt("{SCRATCH}/s1/clone/kept.txt"), KIND_MOVED_IN, ctx.session_id)
        self.assertEqual(k("{SCRATCH}/s1/clone", ctx), PRESERVED)                     # 분류 1a 가 먼저

    def test_mv_into_session_dir_is_preserved(self):           # 감사 rootcause-s1-003
        w.sh("mv {HOME}/notes.md {REPO}/out/"); self.assertEqual(k("{REPO}/out"), PRESERVED)

    def test_moved_in_record_protects(self):                    # D14
        ctx = w.ctx(); ctx.ledger.record(w.fmt("{REPO}/build/a.txt"), KIND_MOVED_IN, ctx.session_id); w.sh("mv {HOME}/data/a.txt {REPO}/build/")
        self.assertEqual(k("{REPO}/build/a.txt", ctx), PRESERVED); self.assertEqual(k("{REPO}/build", ctx), PRESERVED)

    def test_dir_cap(self):  # 임시 루트·저장소 밖 폴더는 상한 적용(임시 루트 폴더는 상한 없음 — test_session_repo_is_scratch_data)
        big = w.fmt("{HOME}/big"); os.mkdir(big)
        for i in range(DIR_ENTRY_CAP + 1):
            open(f"{big}/{i}", "w").close()
        c = classify(big, w.ctx()); self.assertEqual(c.kind, UNRESOLVED); self.assertIn("2000", c.detail)
        os.unlink(f"{big}/0"); self.assertEqual(k("{HOME}/big"), SESSION_NEW)          # 정확히 상한이면 순회

    def test_unreadable_subdir_is_unresolved(self):    # Review Focus 5
        if os.geteuid() == 0:
            self.skipTest("root 는 권한 000 폴더도 읽는다")
        locked = w.fmt("{REPO}/out/locked"); os.makedirs(f"{locked}/inner")
        os.chmod(locked, 0); self.addCleanup(os.chmod, locked, 0o755)
        self.assertEqual(k("{REPO}/out"), UNRESOLVED)

    def test_symlink_loop_terminates(self):           # Review Focus 5
        a = w.fmt("{REPO}/out/a"); os.mkdir(a); os.symlink(a, f"{a}/loop")
        t = time.monotonic(); self.assertEqual(k("{REPO}/out"), SESSION_NEW); self.assertLess(time.monotonic() - t, 1.0)

    def test_unicode_space_path(self):                 # Review Focus 2
        Path(w.fmt("{HOME}/보고 서.md")).write_text("x")
        time.sleep(0.02)
        tr = w.fmt("{OUT}/later-transcript.jsonl"); Path(tr).write_text("")       # 그 뒤에 시작한 세션 → 위 파일은 세션 전
        time.sleep(0.02)
        Path(w.fmt("{REPO}/보고서 초안.md")).write_text("x")
        ctx = w.ctx(transcript=tr)
        self.assertEqual(k("{REPO}/보고서 초안.md", ctx), SESSION_NEW); self.assertEqual(k("{HOME}/보고 서.md", ctx), PRESERVED)

    def test_worktree_root(self):
        w.make_worktree(); self.assertEqual(classify(w.fmt("{WT}"), w.ctx()).worktree_root, w.fmt("{WT}"))
        self.assertTrue(is_linked_worktree_root(w.fmt("{WT}"))); self.assertFalse(is_linked_worktree_root(w.fmt("{REPO}")))
        self.assertIsNone(classify(w.fmt("{REPO}/src"), w.ctx()).worktree_root)

    def test_in_workspace(self):
        ctx = w.ctx()
        self.assertTrue(in_workspace(w.fmt("{REPO}/build/img"), ctx)); self.assertTrue(in_workspace(w.fmt("{SCRATCH}/s1/a"), ctx))
        self.assertFalse(in_workspace(w.fmt("{HOME}/data"), ctx)); self.assertFalse(in_workspace("/dev/sdb", ctx))
        self.assertFalse(in_workspace(w.fmt("{REPO}/.git/x"), ctx))
        w.sh("git init -q {HOME}", cwd="{HOME}"); self.assertFalse(in_workspace(w.fmt("{HOME}/data"), w.ctx()))

    def test_session_start_missing_disables_session_new(self):
        self.assertEqual(k("{REPO}/src/probe.ts", w.ctx(transcript=None)), PRESERVED)

    def test_git_helpers(self):
        ctx = w.ctx(); repo = w.fmt("{REPO}")
        self.assertEqual(git_toplevel(w.fmt("{REPO}/src/main.py"), ctx), repo); self.assertIsNone(git_toplevel(w.fmt("{HOME}/data"), ctx))
        ps = [w.fmt("{REPO}/src"), w.fmt("{REPO}/src/main.py"), w.fmt("{REPO}/src/probe.ts"), w.fmt("{REPO}/build")]
        self.assertEqual(git_tracked(repo, ps, ctx), set(ps[:2]))
        self.assertEqual(git_ignored(repo, ps, ctx), {ps[3]})
        self.assertIsNone(git_tracked(repo, ps, w.ctx(budget=0)))                         # 조회 실패 = None(확정 불가 쪽)

    def test_broken_git_is_unresolved(self):          # .git 이 있는데 rev-parse 실패 → 저장소 아님이 아니라 확정 불가
        os.makedirs(w.fmt("{OUT}/bf")); Path(w.fmt("{OUT}/bf/.git")).write_text(""); Path(w.fmt("{OUT}/bf/f")).write_text("x")
        self.assertEqual(k("{OUT}/bf/f"), UNRESOLVED)
        os.makedirs(w.fmt("{OUT}/bd/.git")); Path(w.fmt("{OUT}/bd/f")).write_text("x")
        time.sleep(0.02); tr = w.fmt("{OUT}/later-transcript.jsonl"); Path(tr).write_text("")   # 세션 전 폴더(1b 아님)
        self.assertEqual(k("{OUT}/bd/f", w.ctx(transcript=tr)), UNRESOLVED)


class SharedLedgerTest(_WorldCase):
    def test_ledger_pre_session_overrides_new_birth(self):
        ctx = w.ctx(); note_touch(w.fmt("{HOME}/data/a.txt"), ctx, "Edit"); w.rewrite_atomic("{HOME}/data/a.txt")
        self.assertEqual(k("{HOME}/data/a.txt", ctx), PRESERVED)

    def test_note_touch_rules(self):
        ctx = w.ctx(); L = ctx.ledger
        note_touch(w.fmt("{REPO}/new.txt"), ctx, "Write"); self.assertIn(KIND_CREATED, [e.kind for e in L.entries(w.fmt("{REPO}/new.txt"))])
        note_touch(w.fmt("{REPO}/src/probe.ts"), ctx, "Edit"); self.assertEqual([e.kind for e in L.entries(w.fmt("{REPO}/src/probe.ts"))], [KIND_TOUCHED])
        note_touch(w.fmt("{REPO}/README.md"), ctx, "Edit")
        self.assertTrue({KIND_PRE_SESSION, KIND_PRE_DIRTY, KIND_TOUCHED} <= {e.kind for e in L.entries(w.fmt("{REPO}/README.md"))})

    def test_note_touch_judge_touched_not_created(self):       # spec §3.7 기록 주체 2: 같은 규칙(created 제외)
        ctx = w.ctx(); L = ctx.ledger
        note_touch(w.fmt("{REPO}/none.txt"), ctx, None); self.assertEqual([e.kind for e in L.entries(w.fmt("{REPO}/none.txt"))], [KIND_TOUCHED])
        note_touch(w.fmt("{REPO}/README.md"), ctx, None)
        self.assertEqual({e.kind for e in L.entries(w.fmt("{REPO}/README.md"))}, {KIND_PRE_SESSION, KIND_PRE_DIRTY, KIND_TOUCHED})

    def test_other_session_judge_touch_is_recorded(self):       # (가) B 의 sed -i 상당 → A 의 '이번 세션 변경' 근거(B 의 touched)
        b = w.ctx(session_id="B"); main = w.fmt("{REPO}/src/main.py")
        note_touch(main, b, None)
        self.assertIn((KIND_TOUCHED, "B"), [(e.kind, e.session_id) for e in b.ledger.entries(main)])

    def test_clean_tracked_twice_no_pre_dirty(self):              # (나)
        ctx = w.ctx(); main = w.fmt("{REPO}/src/main.py")
        note_touch(main, ctx, None); w.touch_modify("{REPO}/src/main.py"); note_touch(main, ctx, None)
        kinds = [e.kind for e in ctx.ledger.entries(main)]
        self.assertNotIn(KIND_PRE_DIRTY, kinds); self.assertEqual(kinds.count(KIND_TOUCHED), 2)

    def test_note_touch_query_failure_records_pre_dirty(self):    # 저장소 안인데 조회 실패 → 과보호
        main = w.fmt("{REPO}/src/main.py"); ctx = w.ctx(budget=0)
        note_touch(main, ctx, "Edit"); self.assertIn(KIND_PRE_DIRTY, [e.kind for e in ctx.ledger.entries(main)])
        os.makedirs(w.fmt("{OUT}/broken")); Path(w.fmt("{OUT}/broken/.git")).write_text(""); f = w.fmt("{OUT}/broken/f"); Path(f).write_text("x")
        ctx = w.ctx(); note_touch(f, ctx, "Edit"); self.assertIn(KIND_PRE_DIRTY, [e.kind for e in ctx.ledger.entries(f)])
        a = w.fmt("{HOME}/data/a.txt"); ctx = w.ctx(budget=0)                    # 저장소 밖은 그대로
        note_touch(a, ctx, "Edit"); self.assertNotIn(KIND_PRE_DIRTY, [e.kind for e in ctx.ledger.entries(a)])

    def test_other_session_created_is_not_mine(self):          # D12
        a, b = w.ctx(session_id="A"), w.ctx(session_id="B")
        note_touch(w.fmt("{REPO}/made_by_b.txt"), b, "Write"); w.sh("echo x > made_by_b.txt")   # 실제 훅처럼 Write 직전(파일 없음)에 기록 → created
        self.assertEqual(k("{REPO}/made_by_b.txt", a), PRESERVED); self.assertEqual(k("{REPO}/made_by_b.txt", b), SESSION_NEW)


if __name__ == "__main__":
    unittest.main()
