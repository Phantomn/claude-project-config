from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import policy
from _world import World, WorldCase
from shell_parse import parse
from target_class import GIT_TRACKED, PRESERVED, PROTECTED_NAME, UNRESOLVED

w: World = None  # type: ignore[assignment]  # WorldCase.setUp 이 테스트마다 넣는다


def ev(cmd, cwd="{REPO}", ctx=None):
    return [(f.op, f.kind) for f in w.evaluate_all(w.fmt(cmd), cwd, ctx)]


_WorldCase = WorldCase   # 벽시계 계단 이동 시 세계 재생성·재시도 (_world.py)


class DeleteTest(_WorldCase):
    def test_delete(self):
        self.assertEqual(ev("rm -f src/probe.ts"), []); self.assertEqual(ev("rm -rf build out"), [])
        self.assertEqual(ev("rm -rf /nope 2>/dev/null"), []); self.assertEqual(ev("rmdir emptydir"), [])
        self.assertEqual(ev("rm src/main.py"), [("삭제", GIT_TRACKED)]); self.assertEqual(ev("git rm src/main.py"), [])
        self.assertEqual(ev("rm notes_presession.txt"), [("삭제", PRESERVED)]); self.assertEqual(ev("rm .env"), [("삭제", PROTECTED_NAME)])
        self.assertEqual(ev("rm local.sqlite"), [("삭제", PRESERVED)])
        self.assertEqual(ev('rm -rf "$UNKNOWN/x"'), [("삭제", UNRESOLVED)]); self.assertEqual(ev("rm -rf {SCRATCH}/*"), [("삭제", UNRESOLVED)])
        self.assertEqual(ev("rm -rf {SCRATCH}/s1"), []); self.assertEqual(ev("shred -u {HOME}/data/a.txt"), [("삭제", PRESERVED)])
        self.assertEqual(ev("unlink {HOME}/notes.md"), [("삭제", PRESERVED)])

    def test_delete_reason_text(self):
        f = w.evaluate_all(w.fmt("rm src/main.py"), "{REPO}")[0]
        self.assertEqual(f.reason(), f"거부: 삭제 {w.fmt('{REPO}/src/main.py')} — git 이 추적하는 파일. 대안: `git rm <경로>` 로 삭제하라(변경 내역에 남아 검토·복구 가능)")

    def test_find_and_xargs(self):
        self.assertEqual(ev("find . -name '*.o' -delete"), []); self.assertEqual(ev("find . -name '*.py' -delete"), [("삭제", GIT_TRACKED)])
        self.assertEqual(ev("find . -name x -exec mv {} /t \\;"), []); self.assertEqual(ev("find . -fprint /t/x -delete"), [("삭제", UNRESOLVED)])
        self.assertEqual(ev("ls | xargs rm -f"), [("삭제", UNRESOLVED)]); self.assertEqual(ev("git ls-files -z | xargs -0 git rm --cached"), [])


class OverwriteTest(_WorldCase):
    def test_overwrite(self):
        self.assertEqual(ev("echo x > src/main.py"), []); self.assertEqual(ev("echo x > README.md"), [("덮어쓰기", "DIRTY")])
        self.assertEqual(ev("echo x >> notes_presession.txt"), []); self.assertEqual(ev("echo x > /dev/null"), [])
        self.assertEqual(ev("echo x > {HOME}/data/important.csv"), [("덮어쓰기", PRESERVED)])
        self.assertEqual(ev("tee -a {HOME}/notes.md"), []); self.assertEqual(ev("tee {HOME}/notes.md"), [("덮어쓰기", PRESERVED)])
        self.assertEqual(ev("cp src/probe.ts notes_presession.txt"), [("덮어쓰기", PRESERVED)])
        self.assertEqual(ev("cp src/probe.ts {HOME}/data/"), []); self.assertEqual(ev("mv {HOME}/notes.md {SCRATCH}/s1/"), [])
        self.assertEqual(ev("truncate -s0 {HOME}/data/db.sqlite"), [("덮어쓰기", PRESERVED)]); self.assertEqual(ev("sed -i s/a/b/ {HOME}/notes.md"), [])
        self.assertEqual(ev("rsync -a --delete src/ {HOME}/data/"), [("삭제", PRESERVED)]); self.assertEqual(ev("rsync -a src/ {SCRATCH}/s1/"), [])

    def test_git_output_overwrites(self):   # git log/diff/show 의 --output 은 그 파일을 덮어쓴다(git 2.43 실측)
        self.assertEqual(ev("echo x > README.md"), [("덮어쓰기", "DIRTY")])
        for c in ("git log -1 --output=README.md", "git diff --output README.md", "git show --outp=README.md",
                  "git -C {REPO}/src log --output=../README.md", "git format-patch -1 --output={REPO}/README.md",
                  "git diff-tree -p HEAD --output=README.md"):
            self.assertEqual(ev(c, cwd="{REPO}" if "{REPO}/src" not in c else "{HOME}"), [("덮어쓰기", "DIRTY")], c)
        self.assertEqual(ev('git log --output="$X"'), [("덮어쓰기", UNRESOLVED)])
        self.assertEqual(ev("git log --output=src/probe.ts"), [])            # 세션이 만든 파일
        self.assertEqual(ev("git log --oneline --output-indicator-new=x -- README.md"), [])
        self.assertEqual(ev("git diff -- --output=README.md"), [])            # `--` 뒤는 경로
        self.assertTrue(policy.is_judged_op(parse("git log --output=x", w.fmt("{REPO}"), w.environ).segments[0]))
        seg = parse("git -C src log --output ../README.md", w.fmt("{REPO}"), w.environ).segments[0]
        self.assertEqual(policy.inplace_targets(seg), [w.fmt("{REPO}/src/../README.md")])   # `>` 처럼 장부에 기록
        self.assertFalse(w.judge_cmd("git log -1 --output=README.md").allow)
        self.assertTrue(w.judge_cmd("git log --oneline -5").allow)


class DiskSystemTest(_WorldCase):
    def test_disk_system_chmod(self):
        self.assertEqual(ev("cat img > /dev/sdb"), [("디스크 쓰기", "OUTSIDE_WORKSPACE")])
        self.assertEqual(ev("dd if=/dev/zero of=build/img bs=1M count=1"), []); self.assertEqual(ev("dd if=fw.bin of=rootfs.img bs=1 skip=10"), [])
        self.assertEqual(ev("dd if=/dev/zero of=/dev/sdb"), [("디스크 쓰기", "OUTSIDE_WORKSPACE")])
        self.assertEqual(ev("mkfs.ext4 /dev/sdb1"), [("디스크 쓰기", "OUTSIDE_WORKSPACE")])
        self.assertEqual(ev("echo x > /dev/nvme0n1"), [("디스크 쓰기", "OUTSIDE_WORKSPACE")]); self.assertEqual(ev("dd if=a of={HOME}/new.img"), [])
        self.assertEqual(ev("cp a /dev/sdb"), [("디스크 쓰기", "OUTSIDE_WORKSPACE")]); self.assertEqual(ev("tee /dev/sdb"), [("디스크 쓰기", "OUTSIDE_WORKSPACE")])
        self.assertEqual(ev("dd if=a of={HOME}/data/db.sqlite"), [("덮어쓰기", PRESERVED)])           # 장치 아닌 dd 는 덮어쓰기 규칙
        self.assertEqual(ev("chmod 644 /etc/hosts"), [("시스템 경로 쓰기", "SYSTEM")]); self.assertEqual(ev("chown root /usr/bin/x"), [("시스템 경로 쓰기", "SYSTEM")])
        self.assertEqual(ev("echo x > /etc/hosts"), [("시스템 경로 쓰기", "SYSTEM")]); self.assertEqual(ev("sudo rm /usr/bin/x"), [("시스템 경로 쓰기", "SYSTEM")])
        self.assertEqual(ev("chmod -R 777 {HOME}"), [("재귀 권한 변경", "OUTSIDE_WORKSPACE")])
        self.assertEqual(ev("chmod -R 755 build"), []); self.assertEqual(ev("chmod 777 {HOME}/notes.md"), [])
        self.assertEqual(ev("killall node; systemctl --user stop svc; pkill -f x"), [])


class JudgedOpTest(_WorldCase):
    def test_is_judged_op(self):
        j = lambda c: [policy.is_judged_op(s) for s in parse(w.fmt(c), w.fmt("{REPO}"), w.environ).segments]
        self.assertEqual(j("ls; git status; docker ps; git log; git push"), [False, False, False, False, False])   # 평범한 push 는 판정 생략
        self.assertEqual(j("rm x; echo a > f; git reset --hard; git push -f; docker volume rm v"), [True, True, True, True, True])


def judged(c):
    return [policy.is_judged_op(s) for s in parse(w.fmt(c), w.fmt("{REPO}"), w.environ).segments]


class ReviewFixTest(_WorldCase):
    def test_find_exec_variants(self):                 # 리뷰 1: -exec 뒤 명령 이름 정규화
        for c in ["find {HOME}/data -exec /bin/rm {} +", "find {HOME}/data -exec sudo rm {} +",
                  "find {HOME}/data -exec shred -u {} +", "find {HOME}/data -exec unlink {} \\;", "find {HOME}/data -ok rm {} \\;"]:
            self.assertEqual(ev(c), [("삭제", UNRESOLVED)], c)
            self.assertEqual(judged(c), [True], c)
        self.assertEqual(ev("find {HOME}/data -name '*.txt' -exec rm -f {} +"), [("삭제", PRESERVED)])   # 미리보기 형태
        self.assertEqual(ev("find . -name x -exec mv {} /t \\;"), []); self.assertEqual(judged("find . -name x -exec mv {} /t \\;"), [False])

    def test_rsync_remote_source(self):                # 리뷰 2: 원격 원본
        self.assertEqual(ev("rsync -a host:data {HOME}/"), [("덮어쓰기", PRESERVED)])
        self.assertEqual(ev("rsync -a host:src/ {HOME}/data/"), [("덮어쓰기", PRESERVED)])
        self.assertEqual(ev("rsync -a user@host:x/new {HOME}/data/"), [])
        self.assertEqual(ev("rsync -a rsync://host/mod/ {SCRATCH}/s1/"), [])
        self.assertEqual(ev("rsync -a src/ {HOME}/data/"), [])

    def test_long_option_prefix(self):                 # 리뷰 3: GNU 긴 옵션 약어
        self.assertEqual(ev("cp --target=/etc/x a"), [("시스템 경로 쓰기", "SYSTEM")])
        self.assertEqual(ev("cp --target-dir={HOME}/data a.txt"), [("덮어쓰기", PRESERVED)])
        self.assertEqual(ev("rm --rec --forc {HOME}/data"), [("삭제", PRESERVED)])
        self.assertEqual(ev("cp --frobnicate a {HOME}/notes.md"), [("덮어쓰기", UNRESOLVED)])   # 모르는 옵션
        self.assertEqual(ev("cp --no a {HOME}/notes.md"), [("덮어쓰기", UNRESOLVED)])           # 모호한 접두
        self.assertEqual(ev("cp --backup=numbered src/probe.ts {HOME}/data/"), [])


class GitPolicyTest(_WorldCase):
    def test_discard_ops(self):
        w.clean_tree(); self.assertEqual(ev("git reset --hard"), []); self.assertEqual(ev("git checkout -- ."), [])
        w.touch_modify("{REPO}/src/main.py"); self.assertEqual(ev("git reset --hard HEAD"), [])          # 이번 세션 변경만
        w.make_worktree(); w.dirty_before_session("{REPO}/README.md"); w.dirty_before_session("{WT}/README.md")
        for c in ["git reset --hard", "git checkout .", "git checkout -- README.md", "git restore .", "git switch -f main",
                  "git checkout -f main", "git rm -f README.md", "git worktree remove --force {WT}"]:
            self.assertEqual([k for _, k in ev(c)], ["DIRTY"], c)
        self.assertEqual(ev("git restore --staged README.md"), []); self.assertEqual(ev("git rm --cached README.md"), [])

    def test_clean(self):
        self.assertEqual(ev("git clean -n"), []); self.assertEqual(ev("git clean -fd"), [("git clean", PRESERVED)])
        self.assertEqual(ev("git clean -fdX"), [("git clean", PROTECTED_NAME)])   # ignore 대상 .env — 재생성 아님
        w.sh("rm .env local.sqlite"); self.assertEqual(ev("git clean -fdX"), [])  # 남은 ignore 는 build/ 뿐

    def test_stash(self):
        self.assertEqual(ev("git stash drop stash@{1}"), [("git stash", "OLD_STASH")]); self.assertEqual(ev("git stash drop"), [])
        self.assertEqual(ev("git stash clear"), [("git stash", "OLD_STASH")])

    def test_push(self):
        for c in ["git push origin +main", "git push --force origin main", "git push -f origin HEAD:main", "git push origin :main",
                  "git push origin --delete main", "git push --mirror", "git push --force --all origin",
                  "git push origin '+refs/heads/*:refs/heads/*'"]:
            self.assertEqual([k for _, k in ev(c)], ["DEFAULT_BRANCH"], c)
        for c in ["git push -u origin feat/x", "git push --force origin feat/x", "git push --force-with-lease origin feat/x",
                  "git push origin --delete feat/x", "git push -q origin --delete feat/x; git log -1 --format=%h", "git push --all origin"]:
            self.assertEqual(ev(c), [], c)
        w.checkout("feat/x", upstream="origin/feat/x"); self.assertEqual(ev("git push --force"), [])
        w.checkout("main", upstream="origin/main"); self.assertEqual([k for _, k in ev("git push --force")], ["DEFAULT_BRANCH"])

    def test_default_branch_fallback(self):            # Review Focus 3
        w.drop_origin_head(); self.assertEqual([k for _, k in ev("git push --force origin main")], ["DEFAULT_BRANCH"])
        w.remove_remote("origin"); self.assertEqual(ev("git push --force origin main"), [])

    def test_branch_delete(self):                      # 감사 rootcause-s1-001·r2-002, 재감사 rootcause-r1-s1-003
        w.local_branch("pushed", pushed=True, before_session=True); w.local_branch("lonely", pushed=False, before_session=True)
        w.local_branch("mine", pushed=False, before_session=False); w.local_branch("ahead", pushed=True, before_session=True, extra_unpushed=1)
        w.local_branch("merged", pushed=True, before_session=True, squash_merged=True, delete_remote=True)      # 스쿼시 병합 후 원격 삭제
        w.local_branch("merged_more", pushed=True, before_session=True, squash_merged=True, delete_remote=True, extra_unpushed=1)
        w.local_branch("gone", pushed=True, before_session=True, delete_remote=True)                            # 병합 안 됐는데 원격만 삭제
        for b in ["pushed", "mine", "merged"]: self.assertEqual(ev(f"git branch -D {b}"), [], b)
        for b in ["ahead", "lonely", "merged_more", "gone"]: self.assertEqual([k for _, k in ev(f"git branch -D {b}")], ["UNPUSHED"], b)
        self.assertTrue(w.evaluate_all(w.fmt("git branch -D gone"), "{REPO}")[0].reason().endswith("병합된 브랜치면 `git fetch` 뒤 다시 실행하라"))
        self.assertEqual(ev("git branch -d lonely"), [])

    def test_reflog_destroyers(self):
        for c in ["git reflog expire --expire=now --all", "git gc --prune=now", "git prune", "git filter-branch -- --all", "git filter-repo --force"]:
            self.assertEqual([k for _, k in ev(c)], ["REFLOG"], c)

    def test_allowed_history_ops(self):
        for c in ["git rebase origin/main", "git commit --amend -m x", "git worktree add ../wt2 -b y", "git update-ref -d refs/heads/y", "git stash pop"]:
            self.assertEqual(ev(c), [], c)
        w.make_worktree(); self.assertEqual(ev("git worktree remove {WT}"), [])

    def test_linked_worktree_rm(self):                  # 재감사 rootcause-r1-s1-002
        WT_FORMS = ["rm -rf {WT}", "git worktree remove {WT}", "git worktree remove --force {WT}"]
        w.make_worktree()
        for c in WT_FORMS: self.assertEqual(ev(c), [], c)                                       # 세션 worktree, 깨끗함
        w.dirty_before_session("{WT}/README.md"); self.assertEqual([k for _, k in ev("rm -rf {WT}")], ["DIRTY"])
        w2 = World(worktree=True); self.addCleanup(w2.close)
        e = lambda cmd: [f.kind for f in w2.evaluate_all(w2.fmt(cmd), "{REPO}")]
        for c in WT_FORMS: self.assertEqual(e(c), [PRESERVED], c)                               # 세션 전 ignore 유일본 local.sqlite
        self.assertIn("worktree 안에 유일본이 있다", w2.evaluate_all(w2.fmt("rm -rf {WT}"), "{REPO}")[0].reason())
        w2.sh("rm local.sqlite", cwd="{WT}"); self.assertEqual(e("rm -rf {WT}"), [])                # 남은 build/ 는 재생성 산출물


class GitReviewFixTest(_WorldCase):
    def test_long_option_abbrev(self):                 # 리뷰 8-1: git 은 긴 옵션의 모호하지 않은 접두를 받는다
        self.assertEqual([k for _, k in ev("git push origin --delet main")], ["DEFAULT_BRANCH"])
        self.assertEqual([k for _, k in ev("git push --mirro origin")], ["DEFAULT_BRANCH"])
        w.local_branch("lonely", pushed=False, before_session=True)
        self.assertEqual([k for _, k in ev("git branch --delete --forc lonely")], ["UNPUSHED"])
        self.assertEqual([k for _, k in ev("git reset --har")], ["DIRTY"])
        self.assertEqual(ev("git push --dry-ru --delet origin main"), [])
        self.assertEqual([k for _, k in ev("git push --forc origin main")], [UNRESOLVED])      # force·force-with-lease·force-if-includes 모호
        self.assertEqual([k for _, k in ev("git push --frobnicate origin main")], [UNRESOLVED])
        self.assertEqual(ev("git push --set-upstream --verbose --quiet --no-verify --follow-tags --porcelain --progress --atomic "
                            "-o ci.skip --push-option=x --signed=if-asked --thin --force origin feat/x"), [])
        self.assertEqual(ev("git branch --set-upstream-to=origin/main --track --list"), [])

    def test_alias(self):                              # 리뷰 8-6: alias 한 단계 펼침
        self.assertEqual([k for _, k in ev("git -c alias.zap='reset --hard' zap")], ["DIRTY"])
        w._git("config", "alias.discard", "checkout --")
        self.assertEqual([k for _, k in ev("git discard .")], ["DIRTY"])
        self.assertEqual([k for _, k in ev("git -c alias.x='!sh -c true' x")], [UNRESOLVED])
        self.assertEqual(ev("git -c alias.st=status st; git status"), [])
        w._git("config", "alias.mv", "reset --hard")                         # 리뷰 8-2(라운드 2): 내장 명령은 alias 로 가려지지 않는다
        self.assertEqual(ev("git mv a b"), [])

    def test_default_branch_guess(self):               # 리뷰 8-5: 기본 브랜치를 모르면 main·master 로 추정
        w.drop_origin_head(); w._git("branch", "-m", "main", "trunk"); w._git("update-ref", "-d", "refs/remotes/origin/main")
        self.assertEqual(ev("git push --force origin feat/x"), [])
        self.assertEqual([k for _, k in ev("git push --force origin master")], ["DEFAULT_BRANCH"])
        self.assertIn("main·master 로 추정", w.evaluate_all(w.fmt("git push origin :main"), "{REPO}")[0].reason())

    def test_compose_run(self):                        # 리뷰 8-4: compose run 마운트는 compose 파일에 있어 모른다
        self.assertEqual(ev("docker compose -p p run web rm -rf /app/src", cwd="{OUT}"), [("삭제", UNRESOLVED)])
        self.assertEqual(ev("docker compose -p p run -v {REPO}:/w web rm -f /w/notes_presession.txt", cwd="{OUT}"), [("삭제", PRESERVED)])
        self.assertEqual(ev("docker compose -p p run web ls", cwd="{OUT}"), [])


class DockerPolicyTest(_WorldCase):
    def test_container_git(self):                      # 리뷰 8-2: 바인드 마운트 위 git 은 호스트 저장소 규칙
        w2 = World(docker=True); self.addCleanup(w2.close); d = w2.docker
        if d is None: self.skipTest("docker 또는 sleep 이 도는 로컬 이미지 없음")
        e = lambda cmd: [(f.op, f.kind) for f in w2.evaluate_all(w2.fmt(cmd), "{REPO}")]
        c = d.container
        self.assertEqual([k for _, k in e(f"docker exec {c} git checkout -- .")], ["DIRTY"])
        self.assertEqual([k for _, k in e(f"docker exec {c} git reset --hard")], ["DIRTY"])
        self.assertEqual(e(f"docker exec {c} git clean -fdx"), [("git clean", PROTECTED_NAME)])
        self.assertEqual(e(f"docker exec -w /srv {c} git reset --hard"), [])
        self.assertEqual(e(f"docker exec {c} git -C /srv clean -fdx"), [])

    def test_container_find(self):                     # 리뷰 8-3: 마운트 밖 find 는 허용, 안이면 호스트에서 미리보기
        w2 = World(docker=True); self.addCleanup(w2.close); d = w2.docker
        if d is None: self.skipTest("docker 또는 sleep 이 도는 로컬 이미지 없음")
        e = lambda cmd: [(f.op, f.kind) for f in w2.evaluate_all(w2.fmt(cmd), "{REPO}")]
        c = d.container
        self.assertEqual(e(f"docker exec {c} find /tmp -name '*.log' -delete"), [])
        self.assertEqual(e(f"docker exec {c} find /app -name '*.py' -delete"), [("삭제", GIT_TRACKED)])
        self.assertEqual(e(f"docker exec {c} find . -name '*.o' -delete"), [])
        self.assertEqual(e(f"docker exec {c} find /data -delete"), [("삭제", "OLD_VOLUME")])

    def test_container_mount_ancestor(self):           # 리뷰 8-1(라운드 2): 마운트 Destination 의 조상을 훑는 재귀 작업
        w2 = World(docker=True); self.addCleanup(w2.close); d = w2.docker
        if d is None: self.skipTest("docker 또는 sleep 이 도는 로컬 이미지 없음")
        e = lambda cmd: [(f.op, f.kind) for f in w2.evaluate_all(w2.fmt(cmd), "{REPO}")]
        k = lambda cmd: sorted({f.kind for f in w2.evaluate_all(w2.fmt(cmd), "{REPO}")})
        c = d.container
        for cmd in [f"docker exec {c} find / -name '*.py' -delete", f"docker exec -w / {c} find . -name '*.py' -delete",
                    f"docker exec {c} find /tmp/.. -name '*.py' -delete"]:
            self.assertEqual(k(cmd), [GIT_TRACKED, "OLD_VOLUME"], cmd)                        # /app 바인드 = {REPO}, /data 볼륨
        run = f"docker run --rm -v {{REPO}}:/srv/w {d.image}"
        self.assertEqual(e(f"{run} find /srv -name '*.py' -delete"), [("삭제", GIT_TRACKED)])
        self.assertIn(e(f"{run} rm -rf /srv")[0][1], (PROTECTED_NAME, PRESERVED))
        self.assertEqual(e(f"{run} chmod -R 777 /srv"), [])                                       # {REPO} 는 작업 영역 안
        self.assertEqual(e(f"docker run --rm -v {{HOME}}/data:/srv/w {d.image} chmod -R 777 /srv"), [("재귀 권한 변경", "OUTSIDE_WORKSPACE")])
        self.assertEqual(e(f"{run} rm -rf /tmp /srv2; {run} find /srv2 -delete; {run} rm /srv"), [])
        self.assertEqual(e(f"{run} find /tmp -name '*.py' -delete"), [])
        self.assertIn("OLD_VOLUME", k(f"docker exec {c} rm -rf /"))                                # /data 볼륨도 포함
        self.assertIn(PROTECTED_NAME, k(f"docker exec {c} rm -rf /"))

    def test_container_find_path_tests(self):          # 리뷰 8-1(라운드 3): 깊이·경로 조건은 호스트에서 재생하지 않는다
        w2 = World(docker=True); self.addCleanup(w2.close); d = w2.docker
        if d is None: self.skipTest("docker 또는 sleep 이 도는 로컬 이미지 없음")
        k = lambda cmd: sorted({f.kind for f in w2.evaluate_all(w2.fmt(cmd), "{REPO}")})
        whole = lambda kinds: bool({PROTECTED_NAME, PRESERVED} & set(kinds))   # 호스트 원본 폴더 전체 분류
        c, run = d.container, f"docker run --rm -v {{REPO}}:/srv/w {d.image}"
        for cmd in [f"{run} find /srv -mindepth 2 -name '*.txt' -delete", f"{run} find /srv/w -path '/srv/w/*' -name x -delete",
                    f"docker exec {c} find / -mindepth 3 -name '*.py' -delete",
                    f"docker exec {c} find / -path '/app/*' -name '*.py' -delete",
                    f"docker exec {c} find /app -maxdepth 1 -name '*.py' -delete"]:
            self.assertTrue(whole(k(cmd)), (cmd, k(cmd)))
        self.assertEqual(k(f"docker exec {c} find /app -name '*.o' -delete"), [])               # 조건이 이름뿐이면 미리보기
        self.assertEqual(k(f"{run} find /srv -name '*.py' -delete"), [GIT_TRACKED])
        self.assertEqual(k(f"{run} find /tmp -maxdepth 1 -delete"), [])                          # 마운트와 무관

    def test_compose_project_env(self):                # 리뷰 8-7
        w2 = World(docker=True); self.addCleanup(w2.close); d = w2.docker
        if d is None: self.skipTest("docker 또는 sleep 이 도는 로컬 이미지 없음")
        ctx = w2.ctx(environ_extra={"COMPOSE_PROJECT_NAME": d.project})
        self.assertEqual([f.kind for f in w2.evaluate_all("docker compose down -v", "{REPO}", ctx)], ["OLD_VOLUME"])
        self.assertEqual([f.kind for f in w2.evaluate_all(f"export COMPOSE_PROJECT_NAME={d.project}; docker compose down -v", "{REPO}")],
                         ["OLD_VOLUME"])


    def test_container(self):
        w2 = World(docker=True); self.addCleanup(w2.close); d = w2.docker
        if d is None: self.skipTest("docker 또는 sleep 이 도는 로컬 이미지 없음")
        e = lambda cmd, cwd="{REPO}": [(f.op, f.kind) for f in w2.evaluate_all(w2.fmt(cmd), cwd)]
        c = d.container
        self.assertEqual(e(f"docker exec -u root {c} sh -c 'echo x >> /etc/hosts && rm -rf /var/lib/x'"), [])
        self.assertEqual(e(f"docker exec {c} rm -rf /app/src"), [("삭제", GIT_TRACKED)])                 # main.py 추적 + probe.ts 세션
        self.assertEqual(e(f"docker exec {c} rm -rf src"), [("삭제", GIT_TRACKED)])                      # WorkingDir /app
        self.assertIn(e(f"docker exec {c} sh -c 'rm -rf /app'")[0][1], (PROTECTED_NAME, PRESERVED))         # Destination 자체 = {REPO} 전체
        self.assertEqual(e(f"docker exec {c} rm -rf /data/x"), [("삭제", "OLD_VOLUME")])
        self.assertEqual(e(f'docker run --rm -v "$(pwd)":/app {d.image} rm -f /app/notes_presession.txt'), [("삭제", PRESERVED)])
        if d.compose: self.assertEqual(e(f"docker compose -p {d.project} exec web rm -rf /app/src/probe.ts", cwd="{OUT}"), [])

    def test_volume_ops(self):
        w2 = World(docker=True); self.addCleanup(w2.close); d = w2.docker
        if d is None: self.skipTest("docker 또는 sleep 이 도는 로컬 이미지 없음")
        e = lambda cmd: [(f.op, f.kind) for f in w2.evaluate_all(w2.fmt(cmd), "{REPO}")]
        d.make_fresh_volume()
        self.assertEqual(e(f"docker volume rm {d.volume}"), [("docker 볼륨 삭제", "OLD_VOLUME")])
        self.assertEqual(e(f"docker volume rm {d.fresh_volume}"), [])
        self.assertEqual([k for _, k in e(f"docker compose -p {d.project} down -v")], ["OLD_VOLUME"])
        self.assertEqual(e(f"docker rm -f {d.container}; docker compose -p {d.project} down"), [])

    def test_docker_unavailable_policy(self):
        ctx = w.ctx(environ_extra={"DOCKER_HOST": "unix:///nonexistent.sock"})
        self.assertEqual([k for _, k in ev("docker volume rm db", ctx=ctx)], [UNRESOLVED])
        self.assertEqual(ev("docker exec c sh -c 'rm -rf /var/lib/x'", ctx=ctx), [])


class ReplayFixTest(_WorldCase):   # 전수 재생 오탐 군집 — 군집 구조를 재구성한 합성 명령
    def test_a_dev_tcp_is_not_disk(self):
        for c in ("exec 3<>/dev/tcp/h/80", "echo x > /dev/tcp/h/80", "printf q > /dev/udp/h/53", "timeout 1 bash -c 'echo > /dev/tcp/h/22'"):
            self.assertEqual(ev(c), [], c)
        self.assertEqual(ev("cat x > /dev/sdb"), [("디스크 쓰기", "OUTSIDE_WORKSPACE")])
        self.assertEqual(ev("echo x > /dev/tcpx"), [("디스크 쓰기", "OUTSIDE_WORKSPACE")])
        self.assertEqual(ev("cat x > /dev/tcp/../sda"), [("디스크 쓰기", "OUTSIDE_WORKSPACE")])   # 없는 /dev/tcp 아래 .. 는 /dev/sda

    def test_b_plain_push_needs_no_lookup(self):
        for c, cwd in (('git -C "$X" push origin feat', "{REPO}"), ("git push origin feat", "{OUT}"),
                       ("GIT_DIR=/nonexistent git push -u origin feat", "{REPO}"), ("git push --all origin", "{OUT}"),
                       ("git push --force-with-lease origin feat", "{OUT}"), ("git push origin a:b", "{OUT}")):
            self.assertEqual(ev(c, cwd=cwd), [], c)
        for c, cwd in (('git -C "$X" push -f origin main', "{REPO}"), ("git push --force origin main", "{OUT}"),
                       ("git push origin +main", "{OUT}"), ("git push origin :main", "{OUT}"), ("git push --mirror", "{OUT}"),
                       ("git push -d origin x", "{OUT}"), ("git push --all -f origin", "{OUT}")):
            self.assertEqual([k for _, k in ev(c, cwd=cwd)], [UNRESOLVED], c)
        self.assertEqual(ev("git push origin :main"), [("git push", "DEFAULT_BRANCH")])
        self.assertEqual(ev("git push origin +main"), [("git push", "DEFAULT_BRANCH")])

    def test_b_push_option_value_is_not_dry_run(self):   # 적대 리뷰(범위 밖 Important): -o 값은 플래그가 아니다
        for c in ("git push -onx origin +main", "git push -o -n origin +main", "git push -o --dry-run origin +main",
                  "git push --push-option -n origin +main", "git push --push-option=-n -f origin main"):
            self.assertEqual(ev(c), [("git push", "DEFAULT_BRANCH")], c)
        for c in ("git push -n origin +main", "git push --dry-run -f origin main", "git push -fn origin main", "git push -o x -n origin +main"):
            self.assertEqual(ev(c), [], c)

    def test_d_commit_message_heredoc(self):
        msg = "git commit -m \"$(cat <<'EOF'\nfix: it's (x) > y\nEOF\n)\""
        self.assertTrue(w.judge_cmd(msg + " && git push origin feat").allow)
        self.assertEqual(ev(msg + " && rm src/main.py"), [("삭제", GIT_TRACKED)])

    def test_d_heredoc_delimiter_shapes(self):   # 적대 리뷰 I7·M1·M2 — bash 5.2 실측 동작
        self.assertTrue(w.judge_cmd("git commit -m \"$(cat <<'EOF'\nmsg\nEOF)\" && git push origin feat").allow)   # EOF) 로 닫힘
        self.assertEqual(ev("X=\"$(cat <<'EOF'\nmsg\nEOF)\"; echo $X | tee {HOME}/notes.md"), [("덮어쓰기", PRESERVED)])
        self.assertEqual(ev("for f in a b; do cat <<EOF; done\nx\nEOF\necho y | tee {HOME}/notes.md"), [("덮어쓰기", PRESERVED)])
        self.assertEqual(ev("echo $((1<<y\n+0)); rm -f src/main.py\ny\n# ))"), [("삭제", GIT_TRACKED)])   # 산술 안 << 는 heredoc 이 아니다
        d = w.judge_cmd("X=$(cat <<EOF\nmsg\nEOF )\nrm -rf src\nEOF\n)")   # bash 는 여기서 heredoc·치환을 끝내고 rm 을 실행한다
        self.assertFalse(d.allow); self.assertIn("해석하지 못했다", d.reasons[0])

    def test_e_case_judges_every_branch(self):
        self.assertTrue(w.judge_cmd('case "$1" in\n  a|b) echo hi > /dev/null ;;\n  *) rm -f {SCRATCH}/s1/x.txt ;;\nesac').allow)
        self.assertEqual(ev('case "$1" in a) rm -rf {SCRATCH}/s1;; *) rm src/main.py;; esac'), [("삭제", GIT_TRACKED)])
        self.assertEqual(ev("case x in a) cd {HOME};; esac; rm -rf data"), [("삭제", UNRESOLVED)])   # 분기 뒤 cwd 미확정
        self.assertEqual(ev("case x in a) echo;; esac > {HOME}/notes.md"), [("덮어쓰기", PRESERVED)])

    def test_f_for_literal_list(self):
        self.assertEqual(ev("for f in a b; do echo x > {SCRATCH}/s1/$f.txt; mv {SCRATCH}/s1/$f.txt {SCRATCH}/s1/$f.bak; done"), [])
        self.assertEqual(ev("for f in probe.ts main.py; do rm src/$f; done"), [("삭제", GIT_TRACKED)])
        self.assertEqual(ev("for f in src/*.py; do cp $f $f.orig; done"), [])
        self.assertEqual(ev("for f in $(ls); do rm $f; done"), [("삭제", UNRESOLVED)])
        self.assertEqual(ev("for f in a; do echo $f; done > {HOME}/notes.md"), [("덮어쓰기", PRESERVED)])

    def test_f_unmodeled_variable_changes(self):   # 적대 리뷰 C1·I4·I6: 모델링 못 한 변수 변화를 예전 확정값으로 믿지 않는다
        for c in ('L=; L+=" main.py"; for f in $L; do rm -f src/$f; done', "L=; read L; for f in $L; do rm -rf src/$f; done",
                  "for f in nothing; do unset f; rm -rf src/$f; done", "for f in nothing; do read -r f < list.txt; rm -rf src/$f; done",
                  "for f in nothing; do printf -v f %s src; rm -rf src/$f; done", "f=nothing; unset f; rm -rf src/$f",
                  "f=nothing; read -rp q f; rm -rf src/$f", "f=nothing; mapfile -t f < l; rm -rf src/$f", "f=x; f+=y; rm -rf src/$f",
                  "f=nothing; getopts ab f; rm -rf src/$f", "f=nothing; let f=1; rm -rf src/$f", "f=nothing; export f+=/..; rm -rf src/$f",
                  "f=nothing; for f in $(cat list); do rm -rf src/$f; done",
                  "f=nothing; for f in " + " ".join(f"a{i}" for i in range(51)) + "; do rm -rf src/$f; done",
                  "f=nothing; for f in a; do while t; do rm -rf src/$f; done; done"):
            self.assertEqual(ev(c), [("삭제", UNRESOLVED)], c)
        for c in ('L=; L+=" x"; for f in $L; do rm -rf src; done', "E=; for f in $E; do rm -rf src; done"):   # 0개 확정이어도 본문을 본다
            self.assertEqual(ev(c), [("삭제", GIT_TRACKED)], c)
        self.assertEqual(ev("f=nothing; read -r g; rm -rf src/$f"), [])   # 바뀌지 않은 변수는 그대로

    def test_f_more_variable_changes(self):   # 재검토 Out-of-Scope 2: readonly·nameref·원소·연산자 대입·source·동적 이름
        (w.scratch / "s1/sub").mkdir()
        for c in ("f=nothing; readonly f=..; rm -rf src/$f", "f=nothing; declare -n r=f; r=..; rm -rf src/$f",
                  "f=nothing; typeset -n r=f; r=..; rm -rf src/$f", "declare -n r=f; f=nothing; r=..; rm -rf src/$f",
                  "f=nothing; f[0]=..; rm -rf src/$f", "f=nothing; f[$i]+=..; rm -rf src/$f",
                  'f=; : "${f:=../..}"; rm -rf "{SCRATCH}/s1/sub/$f"',"f=nothing; : ${f:=..}; rm -rf src/$f",
                  "f=nothing; echo ${f=..} > /dev/null; rm -rf src/$f", "f=nothing; source ./env.sh; rm -rf src/$f",
                  "f=nothing; . ./env.sh; rm -rf src/$f", 'v=f; f=nothing; read "$v"; rm -rf src/$f',
                  'v=f; f=nothing; printf -v "$v" ..; rm -rf src/$f', 'v=f; f=nothing; declare "$v"=..; rm -rf src/$f',
                  'v=f; f=nothing; unset "$v"; rm -rf src/$f', 'v=f; f=nothing; readonly "$v"=..; rm -rf src/$f'):
            self.assertEqual(ev(c), [("삭제", UNRESOLVED)], c)
        self.assertEqual(ev('f=nothing; eval "f=.."; rm -rf src/$f'), [("삭제", PROTECTED_NAME)])   # eval 은 이미 해석한다(src/.. = 저장소)
        for c in ("f=x; source ./env.sh; rm -f {SCRATCH}/s1/x.txt", "f=x; readonly g=1; rm -f {SCRATCH}/s1/$f.txt",
                  "f=x; g[0]=1; : ${h:=1}; rm -f {SCRATCH}/s1/$f.txt"):   # 다른 변수·변수 안 쓰는 대상은 그대로
            self.assertEqual(ev(c), [], c)

    def test_f_assume_success_honest_failures(self):   # fix-brief-3 항목 3: 실패 경로 없음으로 둔 명령이 정직하게 실패하는 경우
        s1 = w.scratch / "s1"
        (s1 / "ro").mkdir(); (s1 / "ro").chmod(0o555); self.addCleanup((s1 / "ro").chmod, 0o755)
        (s1 / "nox").mkdir(); (s1 / "nox" / "k").touch(); (s1 / "nox").chmod(0o600); self.addCleanup((s1 / "nox").chmod, 0o755)
        (s1 / "dangling").symlink_to(s1 / "gone")
        rm = "; rm -rf ./*"
        for c in ("mkdir {SCRATCH}/s1/x.txt && cd {SCRATCH}/s1/x.txt" + rm,          # 대상이 이미 파일
                  "mkdir -p {SCRATCH}/s1/x.txt/d && cd {SCRATCH}/s1/x.txt/d" + rm,    # 상위가 파일
                  "mkdir {SCRATCH}/s1 && cd {SCRATCH}/s1" + rm,                       # -p 없이 이미 있는 폴더
                  "cd {SCRATCH}/s1/x.txt && true" + rm,                               # cd 대상이 파일
                  "mkdir -p {SCRATCH}/s1/ro/n && cd {SCRATCH}/s1/ro/n" + rm,          # 상위에 쓰기 권한 없음
                  "cd {SCRATCH}/s1/nox && true" + rm,                                 # 들어갈(x) 권한 없음
                  "mkdir -p /proc/bgx && cd /proc/bgx" + rm,                          # 쓸 수 없는 파일 시스템
                  "mkdir -p {SCRATCH}/s1/dangling && cd {SCRATCH}/s1/dangling" + rm,  # 끊긴 심볼릭 링크
                  "T=$(mktemp) && cd $T" + rm,                                        # mktemp(파일)로 cd
                  "TMPDIR=/nonexistent; T=$(mktemp -d) && cd $T" + rm,                # mktemp 실패
                  "D=$(cat missing) && cd {SCRATCH}/s1" + rm,                         # 실패하는 치환을 담은 대입
                  "echo x > /nonexistent/f && cd {SCRATCH}/s1" + rm,                  # 리다이렉트 실패
                  "local v=1 && cd {SCRATCH}/s1" + rm,                                # 함수 밖 local 은 늘 실패
                  "false && mkdir -p {SCRATCH}/s1/n; cd {SCRATCH}/s1/n && true" + rm):  # 돌지 않은 mkdir
            self.assertEqual(ev(c), [("삭제", UNRESOLVED)], c)
        # 정직한 실수 모델의 잔여 위험(LIMITS): 형식 오류 printf·readonly 재대입은 실패해도 성공으로 본다
        for c in ("printf %d abc && cd {SCRATCH}/s1" + rm, "readonly R=1; readonly R=2 && cd {SCRATCH}/s1" + rm):
            self.assertEqual(ev(c), [], c)

    def test_f_source_venv_activate(self):   # fix-brief-3 항목 2: 가상환경 activate 만 변수를 미확정으로 두지 않는다
        for c in ("f=main.py; source .venv/bin/activate; rm src/$f", "f=main.py; . venv/bin/activate.sh; rm src/$f",
                  "f=main.py; source {REPO}/.venv/bin/activate && rm src/$f"):
            self.assertEqual(ev(c), [("삭제", GIT_TRACKED)], c)
        self.assertEqual(ev("f=x; source .venv/bin/activate; rm -f {SCRATCH}/s1/$f.txt"), [])
        for c in ("f=nothing; source ./env; rm -rf src/$f", "f=nothing; source activate; rm -rf src/$f",
                  "f=nothing; source .venv/bin/activate.fish; rm -rf src/$f", "f=nothing; . ./activate-x; rm -rf src/$f"):
            self.assertEqual(ev(c), [("삭제", UNRESOLVED)], c)

    def test_f_conditional_changes_are_merged(self):   # 재검토 Out-of-Scope 1: if·&&/||·while/until·0회 for 본문의 변화를 믿지 않는다
        for c in ("f=..; if false; then f=nothing; fi; rm -rf src/$f",
                  "f=..; while false; do f=nothing; done; rm -rf src/$f", "D=src; if [ -d tmp ]; then D=tmp/out; fi; rm -rf $D",
                  "if [ -d x ]; then cd {SCRATCH}/s1; fi; rm -rf src", "[ -d x ] && cd {SCRATCH}/s1; rm -rf src"):
            self.assertEqual(ev(c), [("삭제", UNRESOLVED)], c)
        for c in ("if cd {SCRATCH}/s1; then rm -f x.txt; fi", "cd {SCRATCH} && cd s1 && rm -f x.txt",
                  "if true; then f=x.txt; else f=x.txt; fi; rm -f {SCRATCH}/s1/$f"):
            self.assertEqual(ev(c), [], c)

    def test_f_assume_success_left_side(self):   # fix-brief-3 항목 1: 실패 경로가 사실상 없는 `&&`·`||` 좌변
        # bash: true 는 늘 성공해 `||` 우변(f=nothing)이 돌지 않는다 — f 는 `..` 그대로, src/.. = 저장소
        self.assertEqual(ev("f=..; true || f=nothing; rm -rf src/$f"), [("삭제", PROTECTED_NAME)])
        self.assertEqual(ev("f=nothing; true || f=..; rm -rf src/$f"), [])
        self.assertEqual(ev("true || cd {SCRATCH}/s1; rm -f main.py"), [])   # cd 는 돌지 않는다 — cwd 는 저장소
        for c in ("mkdir -p {SCRATCH}/s1/n && cd {SCRATCH}/s1/n && echo x > a.txt; rm -rf ./*",
                  "cd {SCRATCH}/s1 && F=x.txt; rm -f $F", "cd {SCRATCH}/s1 && T=$(mktemp -d) && echo x > $T/a; rm -rf $T",
                  "cd {SCRATCH} && mkdir -p s1/m && cd s1/m && echo x > o.txt\nrm -f o.txt"):
            self.assertEqual(ev(c), [], c)
        for c in ("[ -d x ] && cd {SCRATCH}/s1; rm -rf ./*", "./build.sh && cd {SCRATCH}/s1; rm -rf ./*",
                  "cd missing_dir && true; rm -rf ./*", "cd missing_dir && F=x.txt; rm -f {SCRATCH}/s1/$F"):
            self.assertEqual(ev(c), [("삭제", UNRESOLVED)], c)

    def test_f4_condition_and_exit_paths(self):   # fix-brief-4 NB3·OS1·OS6: 조건 자리·`;` 뒤 cd 의 실패 경로, exit 으로 끝나는 갈래
        rm = "; rm -rf ./*"
        for c in ("cd {SCRATCH}/missing" + rm, "cd {SCRATCH}/missing\nrm -rf ./*", "cd {SCRATCH}/missing; cd .." + rm,
                  "if cd {SCRATCH}/missing; then :; fi" + rm, "while cd {SCRATCH}/missing; do break; done" + rm,
                  "until cd {SCRATCH}/missing; do sleep 1; break; done" + rm, "if t; then :; elif cd {SCRATCH}/missing; then :; fi" + rm,
                  "cd {SCRATCH}/missing || { cd {SCRATCH}/s1 || exit 1; }" + rm):
            self.assertEqual(ev(c), [("삭제", UNRESOLVED)], c)
        for c in ("if ! cd {SCRATCH}/missing; then rm src/main.py; fi", "if cd {SCRATCH}/missing; then :; else rm src/main.py; fi",
                  "(cd {SCRATCH}/missing || exit); rm src/main.py"):
            self.assertEqual(ev(c), [("삭제", GIT_TRACKED)], c)
        for c in ("if true; then cd {SCRATCH}/s1; fi; rm -f x.txt", "if cd {SCRATCH}/s1; then :; fi; rm -f x.txt",
                  "cd {SCRATCH}/s1 || { echo no; exit 1; }; rm -f x.txt", "if cd {SCRATCH}/s1; then :; else exit 1; fi; rm -f x.txt",
                  "if ! cd {SCRATCH}/s1; then rm src/main.py; fi; rm -f x.txt"):
            self.assertEqual(ev(c), [], c)

    def test_f4_function_definition(self):   # fix-brief-4 OS2: 정의만으로는 cwd·변수가 바뀌지 않고, 호출은 미확정
        self.assertEqual(ev("f() { cd {SCRATCH}/s1; }; rm src/main.py"), [("삭제", GIT_TRACKED)])
        self.assertEqual(ev("g() { cd {SCRATCH}/missing || return 1; }; rm src/main.py"), [("삭제", GIT_TRACKED)])
        self.assertEqual(ev("f=nothing; g() { f=..; }; g; rm -rf src/$f"), [("삭제", UNRESOLVED)])
        self.assertEqual(ev("f() { cd {SCRATCH}/s1; }; f; rm -rf ./*"), [("삭제", UNRESOLVED)])
        self.assertEqual(ev("f() { local v=1 && cd {SCRATCH}/s1; }; rm -rf {SCRATCH}/s1"), [])
        self.assertEqual(ev("f() { rm src/main.py; }"), [("삭제", GIT_TRACKED)])   # 본문은 판정한다

    def test_f4_assume_success_refinements(self):   # fix-brief-4 NB4–NB7: 성공 가정 집합이 실제 성공 조건을 더 반영한다
        s1 = w.scratch / "s1"
        (s1 / "ro").mkdir(); (s1 / "ro").chmod(0o555); self.addCleanup((s1 / "ro").chmod, 0o755)
        rm = "; rm -rf ./*"
        for c in ("T=$(mktemp -d -p {SCRATCH}/s1/nonexist) && cd {SCRATCH}/s1" + rm,       # NB4 mktemp 실패 대입
                  "TMPDIR={SCRATCH}/s1/nonexist; T=$(mktemp -d) && cd {SCRATCH}/s1" + rm,
                  "T=$(mktemp -d -p {SCRATCH}/s1/ro) && cd {SCRATCH}/s1" + rm,
                  "mkdir -m 644 {SCRATCH}/s1/m && cd {SCRATCH}/s1/m" + rm,                     # NB5 실행 비트 없는 모드
                  "mkdir --mode=600 {SCRATCH}/s1/m && cd {SCRATCH}/s1/m" + rm, "mkdir -pm 000 {SCRATCH}/s1/m && cd {SCRATCH}/s1/m" + rm,
                  "sudo -n true && cd {SCRATCH}/s1" + rm, "env true && cd {SCRATCH}/s1" + rm,                  # NB6 래퍼
                  "timeout 1 true && cd {SCRATCH}/s1" + rm, "sudo mkdir -p {SCRATCH}/s1/n && cd {SCRATCH}/s1/n" + rm):
            self.assertEqual(ev(c), [("삭제", UNRESOLVED)], c)
        self.assertEqual(ev("sudo cd {SCRATCH}/s1; rm src/main.py"), [("삭제", GIT_TRACKED)])   # 래퍼 뒤 cd 는 돌지 않는다
        for c in ("mkdir -m 700 {SCRATCH}/s1/m && cd {SCRATCH}/s1/m" + rm, "command true && cd {SCRATCH}/s1" + rm,
                  "builtin cd {SCRATCH}/s1 && true" + rm, "time true && cd {SCRATCH}/s1" + rm):
            self.assertEqual(ev(c), [], c)

    def test_bash_only_glob_is_unresolved(self):   # 적대 리뷰 I5: 파이썬 glob 이 bash 와 다르게 읽는 패턴은 0건이 아니라 확정 불가
        for c in ("rm -rf [^.]*", "rm -rf [[:alpha:]]*", "cd src && rm -rf [^.]*", "rm -f [!.]*", "rm -f src/[[:lower:]]*.py",
                  'for f in [^.]*; do rm -rf "$f"; done', 'for f in [[:alpha:]]*; do rm -rf "$f"; done'):
            self.assertEqual(ev(c), [("삭제", UNRESOLVED)], c)
        self.assertEqual(ev("rm -f *.tmp {SCRATCH}/s1/[ab]*"), [])

    def test_extglob_is_unresolved(self):   # 재검토 New Breakage 2: 확장 글롭은 bash(extglob)만 펼친다 — 확정 불가
        for c in ("shopt -s extglob\nrm -rf !(keep)", "shopt -s extglob\nrm -f src/@(main|x).py", "rm -rf +(a|b)", "rm -rf *(a)",
                  "rm -rf ?(a)", "cd src && rm -f !(probe.ts)", 'for f in !(keep); do rm -rf "$f"; done',
                  "rm -rf {SCRATCH}/s1/a-$X@(k)"):
            self.assertEqual(ev(c), [("삭제", UNRESOLVED)], c)
        self.assertEqual(ev('rm -f "!(keep)" {SCRATCH}/s1/@x'), [])   # 따옴표 안·괄호 없는 @ 는 리터럴

    def test_g_mktemp_result_is_scratch(self):
        for c in ("T=$(mktemp -d); echo x > $T/a; cp src/main.py $T/; rm -rf $T", "F=$(mktemp); git diff > $F; rm -f $F",
                  'D="$(mktemp -d -p {SCRATCH})"; cd "$D" && echo x > out.txt && cd - >/dev/null; rm -rf "$D"'):
            self.assertEqual(ev(c), [], c)
        self.assertEqual(ev("T=$(mktemp -d); rm -rf $T/.."), [("삭제", UNRESOLVED)])   # 임시 루트 자체
        self.assertEqual(ev("T=$(mktemp); mv $T {HOME}/notes.md"), [("덮어쓰기", PRESERVED)])
        self.assertEqual(ev("T=$(mktemp -p {HOME}); rm -f $T"), [("삭제", UNRESOLVED)])   # 임시 루트 밖 -p
        self.assertEqual(ev("T=$(date +%s); rm -rf {SCRATCH}/s1 /x/$T"), [("삭제", UNRESOLVED)])

    def test_g_mktemp_unmodeled_failure_or_root(self):   # 적대 리뷰 I1·I2·M3
        for c in ("export TMPDIR={REPO}; X=$(mktemp -d); rm -rf $X/../*", "TMPDIR={REPO}; X=$(mktemp -d); rm -rf $X/x",
                  'X=$(mktemp -d -p {SCRATCH}/nope); rm -rf "$X"/*', "X=$(mktemp {SCRATCH}/nope/f.XXXX); rm -rf $X",
                  "for d in $(mktemp -d -p {SCRATCH}/nope); do rm -rf $d/*; done", "X=$(mktemp -d); rm -rf $X/../*",
                  "X=$(mktemp -d); rm -rf $X/../s1", "X=$(mktemp -d); rm -rf $X/*",
                  "X=$(mktemp -d -p {SCRATCH} ../home/proj/tXXXX); rm -f $X/../src/main.py"):
            self.assertEqual(ev(c), [("삭제", UNRESOLVED)], c)
        self.assertEqual(ev("X=$(mktemp -d -p {SCRATCH}/s1); rm -rf $X; rm -f $(mktemp)"), [])   # 있는 폴더 아래는 그대로 확정

    def test_h_scratch_prefix_with_unresolved_last_component(self):
        for c in ('rm -rf "{SCRATCH}/s1/run-$$"', "echo x > {SCRATCH}/s1/$N.log", "cp src/main.py {SCRATCH}/s1/r-${ID}",
                  "rm -f {SCRATCH}/s1/out-$(date +%s).txt", "cd {SCRATCH}/s1 && rm -rf ./run-$ID", 'rm -f "{SCRATCH}/s1/a-$(ls | head -1)"',
                  "rm -f {SCRATCH}/s1/id-$(uuidgen)", 'rm -f "{SCRATCH}/s1/r$RANDOM.txt"', "rm -f {SCRATCH}/s1/d-$(date -u '+%Y%m%dT%H%M%S')"):
            self.assertEqual(ev(c), [], c)
        (w.scratch / "s2").mkdir()
        (w.scratch / "s2/key.pem").write_text("k\n", encoding="utf-8")
        for c in ("rm -rf {SCRATCH}/s1/$ID/sub", "rm -rf {SCRATCH}/s1/$ID/", "rm -rf {SCRATCH}/$ID", "rm -rf {HOME}/data/$ID", "rm -rf $DIR/x",
                  "rm -f {SCRATCH}/s1/$K.pem", "rm -f {SCRATCH}/s1/.env.$X", "rm -rf {SCRATCH}/s2/$ID", "rm -rf {SCRATCH}/s1/../$ID",
                  "rm -rf {SCRATCH}/s1/*$ID", "rm -rf {SCRATCH}/s1/{a,$ID}", "rm -rf {SCRATCH}/nope/$ID", "rm -rf {SCRATCH}/s1/.git/$X"):
            self.assertEqual(ev(c), [("삭제", UNRESOLVED)], c)

    def test_h_hole_only_for_single_word_expansions(self):   # 적대 리뷰 H: 여러 단어·연산자·점 이름은 표식으로 채우지 않는다
        (w.scratch / "s1/src").mkdir()
        for c in ("rm -rf {SCRATCH}/s1/a-$(ls {SCRATCH}/s1)", "rm -rf {SCRATCH}/s1/$(ls {SCRATCH}/s1)",
                  "rm -rf {SCRATCH}/s1/a-$(ls -t {SCRATCH}/s1 | tail -n +2)", 'rm -rf "{SCRATCH}/s1/a-${F[@]}"',
                  "rm -rf {SCRATCH}/s1/a-${FILES[*]}", 'rm -rf "{SCRATCH}/s1/a-$@"', "rm -rf {SCRATCH}/s1/a-$*", 'rm -rf "{SCRATCH}/s1/a-$1"',
                  "rm -rf {SCRATCH}/s1/${X:-..}", 'rm -rf "{SCRATCH}/s1/${X:-../..}"', 'rm -rf "{SCRATCH}/s1/a-${X%/*}"',
                  "rm -rf {SCRATCH}/s1/a-${X:+y}", "rm -f {SCRATCH}/s1/out-$(date).txt", "rm -f {SCRATCH}/s1/a-`ls`",
                  "rm -rf {SCRATCH}/s1/.$X", "rm -rf {SCRATCH}/s1/..$X", "rm -rf {SCRATCH}/s1/.$X.", "rm -rf {SCRATCH}/s1/$ID",
                  'rm -rf "{SCRATCH}/s1/${ID}"', "cd {SCRATCH}/s1 && rm -rf ./$ID", "rm -rf {SCRATCH}/s1/$X$Y",
                  "rm -rf {SCRATCH}/s1/id-$(uuidgen --help)", "rm -rf {SCRATCH}/s1/id-$(uuidgen -V)",   # 재검토 New Breakage 1
                  "rm -rf {SCRATCH}/s1/x-$_", 'rm -rf "{SCRATCH}/s1/x-${_}"'):
            self.assertEqual(ev(c), [("삭제", UNRESOLVED)], c)
        for c in ("rm -f {SCRATCH}/s1/id-$(uuidgen -r)", "rm -f {SCRATCH}/s1/id-$(uuidgen -t)"):
            self.assertEqual(ev(c), [], c)

    def test_h_basename_name(self):   # 재검토 점검 요청 (2): basename 은 한 줄·슬래시 없음 — 값 ""·.·..·/ 도 부모가 세션 폴더면 그 안
        (w.scratch / "s1/sub").mkdir()
        for c in ("for f in $(git ls-tree --name-only HEAD); do git show HEAD:$f > {SCRATCH}/s1/sub/$(basename $f); done",
                  "rm -rf {SCRATCH}/s1/sub/$(basename $f)", 'rm -rf "{SCRATCH}/s1/sub/$(basename "$f")"',
                  "rm -rf {SCRATCH}/s1/sub/$(basename -- $f .txt)", "rm -rf {SCRATCH}/s1/sub/a-$(basename $f)",
                  "cd {SCRATCH}/s1/sub && rm -rf ./`basename $f`"):
            self.assertEqual(ev(c), [], c)
        for c in ("rm -rf {SCRATCH}/s1/$(basename $f)", "f=..; rm -rf {SCRATCH}/s1/$(basename $f)",   # 부모가 임시 루트
                  "f=/; rm -rf {SCRATCH}/s1/$(basename $f)", "f=; rm -rf {SCRATCH}/s1/$(basename $f)",
                  "cd {SCRATCH}/s1 && rm -rf ./$(basename $f)", "rm -rf {HOME}/data/$(basename $f)",
                  "rm -rf {SCRATCH}/s1/sub/$(basename -a $f)", "rm -rf {SCRATCH}/s1/sub/a-$(basename -s .x $f)",
                  "rm -rf {SCRATCH}/s1/sub/a-$(basename -z $f)", "rm -rf {SCRATCH}/s1/sub/a-$(basename --multiple $f)",
                  "rm -rf {SCRATCH}/s1/sub/a-$(basename a b c)", "rm -rf {SCRATCH}/s1/sub/$(dirname $f)",
                  "rm -rf {SCRATCH}/s1/sub/a-$(dirname $f)", "rm -rf {SCRATCH}/s1/sub/$(basename $f)/x",
                  "rm -rf {SCRATCH}/s1/sub/$(basename $f)$(basename $g)"):
            self.assertEqual(ev(c), [("삭제", UNRESOLVED)], c)
        (w.scratch / "s1/.env").write_text("k\n", encoding="utf-8")   # 값이 .. 면 부모(s1) 전체 — 안의 보호 이름까지 지운다
        self.assertEqual(ev("rm -rf {SCRATCH}/s1/sub/$(basename $f)"), [("삭제", UNRESOLVED)])
        self.assertEqual(ev("rm -rf {SCRATCH}/s1/sub/a-$(basename $f)"), [])


if __name__ == "__main__":
    unittest.main()
