from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import policy
from _world import World
from shell_parse import parse
from target_class import GIT_TRACKED, PRESERVED, PROTECTED_NAME, UNRESOLVED

w: World


def ev(cmd, cwd="{REPO}"):
    return [(f.op, f.kind) for f in w.evaluate_all(w.fmt(cmd), cwd)]


class _WorldCase(unittest.TestCase):
    def setUp(self):
        global w
        w = World()
        self.addCleanup(w.close)


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
        self.assertEqual(j("ls; git status; docker ps; git log"), [False, False, False, False])
        self.assertEqual(j("rm x; echo a > f; git reset --hard; git push; docker volume rm v"), [True, True, True, True, True])


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


if __name__ == "__main__":
    unittest.main()
