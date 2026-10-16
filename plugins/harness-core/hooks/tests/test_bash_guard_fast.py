"""bash-guard 빠른 길(_TRIVIAL): 큰 모듈 없이 내는 결과가 전체 판정과 같은지, 그리고 정말 큰 모듈을 안 부르는지."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import policy
import shell_parse as sp
from _world import World, WorldCase
from bash_guard import _TRIVIAL, judge
from shell_parse import parse

w: World = None  # type: ignore[assignment]  # WorldCase.setUp 이 테스트마다 넣는다

NAMES = ("ls", "pwd", "cd", "echo", "cat", "head", "tail", "wc", "grep")
GIT_SUBS = ("status", "log", "diff", "show")
TRIVIAL = ["ls", "ls -la", "pwd", "git status --short", "ls dir && echo | wc -l", "cd {REPO} && git status",
           "git log --oneline -5", "git diff --stat HEAD~1", "git show HEAD:a.py", "cat a.txt | grep -n x; echo done",
           "head -5 src/main.py || tail -n 2 x", "cat ~/.ssh/id_rsa", "  echo a=b,c@d%e+f  ", "cd {HOME} && ls {REPO}/src"]
NOT_TRIVIAL = ["rm x", "ls > x", "echo $HOME", "ls *.py", "git push", "git -C . status", "git branch -D x", "echo 'a'",
               "ls & echo", "ls\necho", "ls; rm x", "lsx", "git statusx", "echo {a,b}", "ls # c",
               "X=1 ls", "(ls)", "ls `rm x`", "ls\tx", ""]


class ShapeTest(unittest.TestCase):
    def test_accepts_and_rejects(self):
        for c in TRIVIAL:
            c = c.replace("{REPO}", "/r").replace("{HOME}", "/h")
            self.assertIsNotNone(_TRIVIAL.fullmatch(c), c)
        for c in NOT_TRIVIAL:
            self.assertIsNone(_TRIVIAL.fullmatch(c), c)
        for n in ("rm", "find", "sed", "tee", "mv", "xargs", "bash", "sudo", "docker", "eval", "git branch", "git stash"):
            self.assertIsNone(_TRIVIAL.fullmatch(n), n)

    def test_names_have_no_handler_wrapper_or_inplace(self):
        special = (set(policy.HANDLERS) | set(sp._WRAPPER_VALUE_OPTS) | set(sp._SIMPLE_WRAPPERS) | sp.SHELLS
                   | set(sp._CONTAINER_CLIS) | set(sp._VAR_DECL) | set(sp._RESERVED) | set(sp._LOOP_HEAD)
                   | {"eval", "xargs", "tee", "sed", "perl", "popd", "pushd"})
        for n in NAMES:
            self.assertIsNotNone(_TRIVIAL.fullmatch(n), n)
            self.assertNotIn(n, special)
            self.assertFalse(n.startswith("mkfs"))
        for s in GIT_SUBS:   # 표 밖 내장 하위명령 — alias 조회·긴 옵션 풀이·판정 행이 없다
            self.assertIsNotNone(_TRIVIAL.fullmatch(f"git {s}"), s)
            self.assertIn(s, policy._GIT_BUILTINS)
            self.assertNotIn(s, policy._GIT_JUDGED_SUBS)
            self.assertFalse(any(k.split()[0] == s for k in policy._GIT_LONGS), s)


class EquivalenceTest(WorldCase):
    def test_full_path_agrees(self):
        # 빠른 길의 전제(해석 오류 없음·전부 호스트·판정 대상·대상·장부 기록 없음)를 전체 경로로 확인한다
        w.set_repo_switch("on")
        ctx = w.ctx()
        for c in TRIVIAL:
            cmd = w.fmt(c)
            self.assertIsNotNone(_TRIVIAL.fullmatch(cmd), cmd)
            res = parse(cmd, w.fmt("{HOME}"), w.environ)
            self.assertIsNone(res.error, cmd)
            for seg in res.segments:
                self.assertEqual((seg.context.kind, seg.via_xargs), ("host", False), cmd)
                self.assertFalse(policy.is_judged_op(seg), cmd)
                self.assertEqual(policy.assess(seg, ctx), ([], []), cmd)
                self.assertEqual(policy.inplace_targets(seg), [], cmd)
                self.assertNotEqual(seg.name, "mv", cmd)
            # 단위 cwd 가 스위치 on 저장소여도 판정 대상이 없으니 모드는 세션 env·훅 cwd 값
            d = judge(w.payload(c, cwd="{HOME}"), w.environ)
            self.assertEqual((d.allow, d.reasons, d.mode, d.error), (True, [], "off", None), cmd)
            d = judge(w.payload(c), w.environ)
            self.assertEqual((d.allow, d.reasons, d.mode, d.error), (True, [], "on", None), cmd)
        self.assertFalse((Path(w.environ["XDG_STATE_HOME"]) / "harness-core" / "ledger.tsv").exists())


class ImportTest(WorldCase):
    def _modules(self, command: str) -> list[str]:
        code = ("import json, sys; sys.path.insert(0, sys.argv[1]); import bash_guard; "
                "bash_guard.judge(json.loads(sys.argv[2]), {}); "
                "print(json.dumps(sorted(m for m in ('dataclasses', 'policy', 'shell_parse', 'target_class', 'ledger', 'subprocess') "
                "if m in sys.modules)))")
        out = subprocess.run([sys.executable, "-c", code, str(SCRIPTS), json.dumps(w.payload(command))],
                             capture_output=True, text=True, check=True, env=w.environ)
        return json.loads(out.stdout)

    def test_fast_path_imports_nothing_heavy(self):
        self.assertEqual(self._modules("ls dir && echo | wc -l"), [])
        self.assertEqual(self._modules("git status --short"), [])

    def test_full_path_imports_without_subprocess(self):
        # 판정 대상이 없는 일반 명령은 외부 명령(stat 포함)을 띄우지 않는다
        self.assertEqual(self._modules("python3 x.py"), ["dataclasses", "ledger", "policy", "shell_parse", "target_class"])


if __name__ == "__main__":
    unittest.main()
