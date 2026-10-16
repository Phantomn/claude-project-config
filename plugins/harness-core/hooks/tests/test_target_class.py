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
from _world import World, WorldCase
from ledger import (
    KIND_CREATED,
    KIND_MOVED_IN,
    KIND_PRE_DIRTY,
    KIND_PRE_SESSION,
    KIND_TOUCHED,
    Ledger,
    state_dir,
)
from shell_parse import Mount
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
    compose_container_id,
    docker_container_info,
    docker_volume_created,
    docker_volumes,
    find_preview,
    git_branch_info,
    git_clean_preview,
    git_default_branch,
    git_dirty,
    git_extra_items,
    git_ignored,
    git_remote_names,
    git_stash_created,
    git_toplevel,
    git_tracked,
    git_upstream_branch,
    in_workspace,
    is_linked_worktree_root,
    is_scratch,
    is_scratch_root,
    is_session_change,
    make_ctx,
    normalize,
    note_touch,
    protected_name,
    repo_root,
    run,
    session_start,
    switch_mode,
)

w: World = None  # type: ignore[assignment]  # WorldCase.setUp 이 테스트마다 넣는다


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


_WorldCase = WorldCase   # 벽시계 계단 이동 시 세계 재생성·재시도 (_world.py)


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
        # touch_modify 는 벽시계 역행과 무관하게 세션 시작 뒤 수정 시각을 남긴다(리뷰 8 라운드 3 — test_discard_ops 간헐 실패)
        w.touch_modify("{REPO}/src/main.py")
        self.assertGreaterEqual(os.stat(w.fmt("{REPO}/src/main.py")).st_mtime, w.session_start + 1)
        w.local_branch("sq", pushed=True, before_session=True, squash_merged=True, delete_remote=True)
        w.local_branch("mine", pushed=False, before_session=False)
        self.assertNotEqual(w.sh("git rev-parse sq"), w.sh("git rev-parse origin/main"))
        self.assertEqual(w.sh("git diff sq origin/main -- sq.txt"), "")
        self.assertGreaterEqual(reflog_time("mine"), w.session_start)
        w.clean_tree(); self.assertNotIn(" M README.md", w.sh("git status --porcelain").splitlines())

    def test_world_clock_order(self):           # 벽시계 역행 시 세계를 다시 만드는 검증(fix 라운드 2)
        self.assertTrue(w._order_ok())
        self.assertFalse(w._order_ok(margin=1e9))                                   # 불가능한 간격 → 어긋남으로 판정


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


class GitStateTest(_WorldCase):
    def test_git_dirty_and_session_change(self):
        ctx = w.ctx(); self.assertEqual(git_dirty(w.fmt("{REPO}"), ["."], ctx), [w.fmt("{REPO}/README.md")])
        w.touch_modify("{REPO}/src/main.py"); self.assertTrue(is_session_change(w.fmt("{REPO}/src/main.py"), ctx))
        self.assertFalse(is_session_change(w.fmt("{REPO}/README.md"), ctx))
        ctx.ledger.record(w.fmt("{REPO}/src/main.py"), KIND_PRE_DIRTY, ctx.session_id)
        self.assertFalse(is_session_change(w.fmt("{REPO}/src/main.py"), ctx))

    def test_other_session_touched_is_not_mine(self):          # D12
        a = w.ctx(session_id="A"); w.touch_modify("{REPO}/src/main.py")
        a.ledger.record(w.fmt("{REPO}/src/main.py"), KIND_TOUCHED, "B"); self.assertFalse(is_session_change(w.fmt("{REPO}/src/main.py"), a))

    def test_default_branch(self):
        ctx = w.ctx(); self.assertEqual(git_default_branch(w.fmt("{REPO}"), "origin", ctx), "main")
        w.drop_origin_head(); self.assertEqual(git_default_branch(w.fmt("{REPO}"), "origin", ctx), "main")

    def test_stash_created(self):
        ctx = w.ctx(); self.assertLess(git_stash_created(w.fmt("{REPO}"), "stash@{1}", ctx), ctx.session_start)
        self.assertGreaterEqual(git_stash_created(w.fmt("{REPO}"), "stash@{0}", ctx), ctx.session_start)

    def test_clean_preview(self):
        ctx = w.ctx(); self.assertIn(w.fmt("{REPO}/notes_presession.txt"), git_clean_preview(w.fmt("{REPO}"), ["-fd"], ctx))
        # git clean -n 은 통째로 지울 미추적 폴더를 폴더 하나로 낸다(실측) — brief 의 '{REPO}/build/out.o' 대신 폴더 항목
        self.assertIn(w.fmt("{REPO}/build"), git_clean_preview(w.fmt("{REPO}"), ["-xffd"], ctx))

    def test_branch_info(self):
        ctx = w.ctx(); w.local_branch("pushed", pushed=True, before_session=True); w.local_branch("lonely", pushed=False, before_session=True)
        w.local_branch("mine", pushed=False, before_session=False); w.local_branch("ahead", pushed=True, before_session=True, extra_unpushed=1)
        pi = git_branch_info(w.fmt("{REPO}"), "pushed", ctx); self.assertEqual((pi.has_upstream, pi.ahead), (True, 0))
        self.assertEqual(git_branch_info(w.fmt("{REPO}"), "ahead", ctx).ahead, 1)
        li = git_branch_info(w.fmt("{REPO}"), "lonely", ctx); self.assertFalse(li.has_upstream or li.reachable_elsewhere)
        self.assertGreaterEqual(git_branch_info(w.fmt("{REPO}"), "mine", ctx).created_at, ctx.session_start)   # 세션 전 커밋에서 분기 — %ct 면 실패
        self.assertLess(li.created_at, ctx.session_start)
        w.local_branch("squashed", pushed=True, before_session=True, squash_merged=True, delete_remote=True)
        w.local_branch("gone", pushed=True, before_session=True, delete_remote=True)
        si = git_branch_info(w.fmt("{REPO}"), "squashed", ctx); self.assertEqual((si.upstream_ref_exists, si.merged_into_default), (False, True))
        self.assertFalse(git_branch_info(w.fmt("{REPO}"), "gone", ctx).merged_into_default)

    def test_worktree_extra_items(self):
        w2 = World(worktree=True); self.addCleanup(w2.close)
        self.assertEqual(sorted(git_extra_items(w2.fmt("{WT}"), w2.ctx())), [w2.fmt("{WT}/build"), w2.fmt("{WT}/local.sqlite")])


class FindTest(_WorldCase):
    def test_find_preview(self):
        ctx = w.ctx(); r = w.fmt("{REPO}")
        self.assertEqual(sorted(find_preview([r, "-name", "*.o", "-delete"], r, ctx)), [w.fmt("{REPO}/build/out.o")])
        self.assertIsNotNone(find_preview([".", "-name", "*.o", "-exec", "rm", "-f", "{}", "+"], r, ctx))
        self.assertIsNone(find_preview([".", "-name", "x", "-exec", "mv", "{}", "/t", ";"], r, ctx))
        self.assertIsNone(find_preview([".", "-fprint", "/t/x", "-delete"], r, ctx))


class DockerTest(_WorldCase):
    def test_docker(self):
        w2 = World(docker=True); self.addCleanup(w2.close); d = w2.docker
        if d is None: self.skipTest("docker 또는 sleep 이 도는 로컬 이미지 없음")
        ctx = w2.ctx(); mounts, wd = docker_container_info(d.container, ctx)
        self.assertIn(Mount(w2.fmt("{REPO}"), "/app", "bind"), mounts); self.assertIn(Mount(d.volume, "/data", "volume"), mounts)
        self.assertEqual(wd, "/app"); self.assertLess(docker_volume_created(d.volume, ctx), ctx.session_start)
        self.assertEqual(docker_volumes("compose-project", d.project, ctx), [d.volume])
        if d.compose: self.assertIsNotNone(compose_container_id("web", w2.fmt("{OUT}"), d.project, ctx))

    def test_docker_unavailable(self):
        ctx = w.ctx(environ_extra={"DOCKER_HOST": "unix:///nonexistent.sock"})
        self.assertIsNone(docker_container_info("c", ctx)); self.assertIsNone(docker_volume_created("v", ctx))


class QueryRegressionTest(_WorldCase):
    """Task 6 리뷰 라운드 1 회귀."""

    def test_clean_preview_quiet_is_dropped(self):
        ctx = w.ctx(); r = w.fmt("{REPO}")
        base = sorted(git_clean_preview(r, ["-fd"], ctx))
        self.assertIn(w.fmt("{REPO}/notes_presession.txt"), base)
        for args in (["-fdq"], ["-fd", "--quiet"], ["-q", "-f", "-d"]):
            self.assertEqual(sorted(git_clean_preview(r, args, ctx)), base, args)

    def test_clean_preview_long_option_prefixes(self):
        # git 은 긴 옵션의 모호하지 않은 접두를 받는다 — `clean -n -fd --q` 는 quiet 라 출력이 비고(실측), --inter 는 대화 메뉴
        ctx = w.ctx(); r = w.fmt("{REPO}")
        self.assertEqual(w.sh("git clean -n -fd --q"), "")
        base = sorted(git_clean_preview(r, ["-fd"], ctx))
        for q in ("--q", "--qui", "--quie"):
            self.assertEqual(sorted(git_clean_preview(r, ["-fd", q], ctx)), base, q)
        for bad in (["-fd", "--inter"], ["-fd", "--interactive"], ["-i", "-fd"], ["-fdi"], ["-fd", "--zzz"], ["-fd", "--no-quiet"]):
            self.assertIsNone(git_clean_preview(r, bad, ctx), bad)
        # 집합 {dry-run, force, interactive, quiet, exclude} 안에는 모호한 접두가 없다 — 목록 밖 '--no-*' 로 확정 불가를 덮는다
        self.assertEqual(sorted(git_clean_preview(r, ["--for", "--d", "-d"], ctx)), base)
        self.assertNotIn(w.fmt("{REPO}/build"), git_clean_preview(r, ["-fdx", "--excl=build"], ctx))
        self.assertNotIn(w.fmt("{REPO}/build"), git_clean_preview(r, ["-fdx", "--ex", "build"], ctx))

    def test_clean_preview_ff_keeps_nested_repo(self):
        ctx = w.ctx(); r = w.fmt("{REPO}")
        w.sh("git init -q nested")
        self.assertIn("Would remove nested/", w.sh("git clean -n -ffd"))
        self.assertIn(w.fmt("{REPO}/nested"), git_clean_preview(r, ["-ffd"], ctx))
        self.assertIn(w.fmt("{REPO}/nested"), git_clean_preview(r, ["-f", "-f", "-d"], ctx))
        self.assertNotIn(w.fmt("{REPO}/nested"), git_clean_preview(r, ["-fd"], ctx))   # -f 하나는 중첩 저장소를 건너뜀

    def test_clean_preview_exclude_value_kept(self):
        ctx = w.ctx(); r = w.fmt("{REPO}")
        for args in (["-fdx", "-e", "build"], ["-xfebuild", "-d"], ["-fdx", "--exclude", "build"], ["-fdx", "--exclude=build"]):
            got = git_clean_preview(r, args, ctx)
            self.assertNotIn(w.fmt("{REPO}/build"), got, args); self.assertIn(w.fmt("{REPO}/local.sqlite"), got, args)

    def test_find_preview_keeps_dotdot_for_normalize(self):
        ctx = w.ctx(); work = w.fmt("{OUT}/work"); os.makedirs(work)
        os.symlink(w.fmt("{REPO}/src"), os.path.join(work, "lnk"))
        got = find_preview(["lnk/..", "-maxdepth", "1", "-name", "README.md", "-delete"], work, ctx)
        self.assertEqual(got, [os.path.join(work, "lnk/../README.md")])
        c = classify(got[0], ctx); self.assertEqual((c.kind, c.path), (GIT_TRACKED, w.fmt("{REPO}/README.md")))

    def test_docker_volumes_needs_value(self):
        self.assertIsNone(docker_volumes("compose-project", None, w.ctx()))

    def test_upstream_branch(self):
        ctx = w.ctx(); r = w.fmt("{REPO}")
        self.assertEqual(git_upstream_branch(r, ctx), "main")               # push -u 로 설정됨
        w.checkout("plain"); self.assertIsNone(git_upstream_branch(r, ctx))  # 설정 없음
        w.checkout("feat", upstream="origin/nothere"); self.assertEqual(git_upstream_branch(r, ctx), "nothere")  # 추적 ref 없음

    def test_remote_names(self):
        ctx = w.ctx(); r = w.fmt("{REPO}")
        self.assertEqual(git_remote_names(r, ctx), ["origin"])
        w.remove_remote("origin"); self.assertEqual(git_remote_names(r, ctx), [])


MARGIN = "HARNESS_BASH_GUARD_CLOCK_MARGIN"


class ClockMarginTest(_WorldCase):
    """벽시계 역행(WSL2 실측 약 30초마다 −1.28초) 방어: 세션 시작 + 여유 안의 시각은 '세션 전'으로 본다."""

    def mctx(self, margin, **kw):
        return w.ctx(environ_extra={MARGIN: margin}, **kw)

    def test_default_and_parse(self):
        self.assertEqual(make_ctx({}, {}, 1.0).clock_margin, 2.0)
        for bad in ("-1", "abc", "nan", "inf", ""):
            self.assertEqual(make_ctx({}, {MARGIN: bad}, 1.0).clock_margin, 2.0, bad)
        self.assertEqual(make_ctx({}, {MARGIN: "0.5"}, 1.0).clock_margin, 0.5)
        self.assertEqual(make_ctx({}, {MARGIN: "0"}, 1.0).clock_margin, 0.0)

    def test_ambiguous_session_file_is_preserved(self):     # (a) probe.ts 는 세션 시작 약 0.02초 뒤에 만든 파일
        self.assertEqual(k("{REPO}/src/probe.ts", self.mctx("2.0")), PRESERVED)
        self.assertEqual(k("{REPO}/src/probe.ts", self.mctx("0")), SESSION_NEW)

    def test_presession_file_stamped_after_start(self):     # (b) 세션 전 파일이 세션 시작 뒤로 찍힌 모양(역행의 결과)
        tr = w.fmt("{OUT}/t2.jsonl"); Path(tr).write_text(""); time.sleep(0.01)   # 같은 jiffy 면 birth 가 같다
        f = w.fmt("{HOME}/pre.txt"); Path(f).write_text("x")
        ctx = self.mctx("2.0", transcript=tr)
        self.assertGreater(stat_birth(f), ctx.session_start)
        self.assertEqual(k(f, ctx), PRESERVED)
        note_touch(f, ctx, "Edit"); self.assertIn(KIND_PRE_SESSION, [e.kind for e in ctx.ledger.entries(f)])
        t = ctx.session_start + 0.5; os.utime(f, (t, t))
        self.assertFalse(is_session_change(f, ctx)); self.assertTrue(is_session_change(f, self.mctx("0", transcript=tr)))

    def test_session_repo_needs_margin(self):               # (c) 분류 1b
        tr = w.fmt("{OUT}/t3.jsonl"); Path(tr).write_text("")
        repo = w.fmt("{OUT}/fresh"); subprocess.run(["git", "init", "-q", repo], env=w.environ, check=True)
        f = f"{repo}/a.txt"; Path(f).write_text("x")
        c = classify(f, self.mctx("2.0", transcript=tr)); self.assertEqual((c.kind, c.session_repo), (PRESERVED, False))
        c = classify(f, self.mctx("0", transcript=tr)); self.assertEqual((c.kind, c.session_repo), (SCRATCH, True))

    def test_policy_times_use_margin(self):                 # branch -D·stash 의 세션 전 판정(_old)도 같은 여유
        w.local_branch("mine", pushed=False, before_session=False)
        big = self.mctx("3600")
        self.assertEqual(w.evaluate_all("git branch -D mine", ctx=w.ctx()), [])
        self.assertEqual([f.kind for f in w.evaluate_all("git branch -D mine", ctx=big)], ["UNPUSHED"])
        self.assertEqual(w.evaluate_all("git stash drop stash@{0}", ctx=w.ctx()), [])
        self.assertEqual([f.kind for f in w.evaluate_all("git stash drop stash@{0}", ctx=big)], ["OLD_STASH"])


class ClassifyBudgetTest(_WorldCase):   # 재생 최대 판정 시간: 경로 수백 개의 파일 조회도 예산을 본다
    def test_classify_many_stops_at_budget(self):
        d = w.fmt("{OUT}/c2"); os.mkdir(d)
        paths = [f"{d}/f{i}" for i in range(575)]
        for p in paths:
            open(p, "w").close()
        with self.assertRaises(target_class._Unresolved) as e:
            target_class._classify_many(paths, w.ctx(budget=0))
        self.assertIn("시간 초과", str(e.exception))
        c = classify(d, w.ctx(budget=0)); self.assertEqual(c.kind, UNRESOLVED); self.assertIn("시간 초과", c.detail)

    def test_loop_check_alone(self):   # 루프 안 검사가 없으면 저장소 조회가 먼저 실패해 사유가 'git 조회 실패'가 된다
        with self.assertRaises(target_class._Unresolved) as e:
            target_class._classify_many([w.fmt("{REPO}/src/main.py"), w.fmt("{REPO}/README.md")], w.ctx(budget=0))
        self.assertIn("시간 초과", str(e.exception))

    def test_births_check_alone(self):   # 루프를 돌지 않아도(경로 0개) births 앞 검사가 예산을 본다
        with self.assertRaises(target_class._Unresolved) as e:
            target_class._classify_many([], w.ctx(budget=0))
        self.assertIn("시간 초과", str(e.exception))

    def test_judge_ends_near_budget(self):
        from bash_guard import judge
        for n in ("c1", "c2"):
            os.mkdir(w.fmt(f"{{OUT}}/{n}"))
            for i in range(575):
                open(w.fmt(f"{{OUT}}/{n}/f{i}"), "w").close()
        budget = 0.005
        t0 = time.monotonic()
        d = judge(w.payload("rm -rf {OUT}/c1 {OUT}/c2"), {**w.environ, "HARNESS_BASH_GUARD": "on"}, budget=budget)
        self.assertLess(time.monotonic() - t0, budget + 0.5)
        self.assertFalse(d.allow); self.assertTrue(all("범위를 좁혀라" in r for r in d.reasons), d.reasons)   # 세션 파일이어도 못 다 보면 거부


if __name__ == "__main__":
    unittest.main()
