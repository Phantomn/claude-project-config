from __future__ import annotations

import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _world import World, WorldCase
from ledger import (
    KIND_CREATED,
    KIND_PRE_DIRTY,
    KIND_PRE_SESSION,
    KIND_TOUCHED,
    Ledger,
    state_dir,
)

HOOKS_JSON = Path(__file__).resolve().parents[1] / "hooks.json"   # plugins/harness-core/hooks/hooks.json
HOOK = SCRIPTS / "touch-ledger.py"
w: World = None  # type: ignore[assignment]  # WorldCase.setUp 이 테스트마다 넣는다


def run_hook(payload_or_text, extra_env=None):
    data = payload_or_text if isinstance(payload_or_text, str) else json.dumps(payload_or_text)
    r = subprocess.run([sys.executable, str(HOOK)], input=data.encode(), capture_output=True,
                       env={**w.environ, **(extra_env or {})}, timeout=30, check=False)
    return r.returncode, r.stdout.decode()


def kinds(path: str) -> set[str]:
    return {e.kind for e in Ledger(w.environ).entries(w.fmt(path))}


class TouchLedgerTest(WorldCase):
    def test_records_without_switch(self):          # 스위치 없음(off)에서도 기록
        self.assertEqual(run_hook(w.edit_payload("{HOME}/notes.md")), (0, ""))
        self.assertIn(KIND_PRE_SESSION, kinds("{HOME}/notes.md"))

    def test_records_touched_and_pre_dirty(self):
        run_hook(w.edit_payload("{REPO}/README.md"))
        self.assertTrue({KIND_PRE_DIRTY, KIND_TOUCHED} <= kinds("{REPO}/README.md"))

    def test_write_new_file_records_created(self):
        run_hook(w.edit_payload("{REPO}/new.txt", tool="Write"))
        self.assertIn(KIND_CREATED, kinds("{REPO}/new.txt"))

    def test_notebook_path(self):
        run_hook(w.edit_payload("{HOME}/notes.md", tool="NotebookEdit"))
        self.assertIn(KIND_TOUCHED, kinds("{HOME}/notes.md"))

    def test_relative_path_uses_cwd(self):
        p = w.edit_payload("README.md"); p["cwd"] = str(w.repo)
        run_hook(p)
        self.assertIn(KIND_TOUCHED, kinds("{REPO}/README.md"))

    def test_tilde_path_is_home(self):             # `~/x` 는 cwd 아래가 아니라 홈 아래
        p = w.edit_payload("~/notes.md"); p["cwd"] = str(w.repo)
        run_hook(p)
        self.assertIn(KIND_TOUCHED, kinds("{HOME}/notes.md"))
        self.assertEqual(kinds("{REPO}/~/notes.md"), set())

    def test_broken_module_is_silent(self):        # 판정 모듈을 못 불러와도 Write·Edit 에 오류를 내지 않는다
        solo = Path(w.root) / "solo"; solo.mkdir()
        shutil.copy(HOOK, solo / HOOK.name)   # 같은 폴더에 target_class 가 없는 실제 훅 파일
        r = subprocess.run([sys.executable, str(solo / HOOK.name)], input=json.dumps(w.edit_payload("{HOME}/notes.md")).encode(),
                           capture_output=True, env=w.environ, timeout=30, check=False)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, b"", b""))

    def test_lock_wait_is_capped(self):            # 장부 잠금을 누가 쥐고 있어도 훅 timeout(5초) 안에 끝나고, 기록은 남는다
        f = state_dir(w.environ) / "ledger.tsv"; f.parent.mkdir(parents=True)
        fd = os.open(f, os.O_RDWR | os.O_CREAT, 0o600); self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        t0 = time.monotonic()
        r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(w.edit_payload("{HOME}/notes.md")).encode(),
                           capture_output=True, env=w.environ, timeout=10, check=False)
        self.assertLess(time.monotonic() - t0, 4.0)
        self.assertEqual((r.returncode, r.stdout), (0, b""))
        # 기록을 버리면 세션 전 파일이 바꿔치기 저장 뒤 '세션이 만든 파일'이 된다 — 잠금 없이라도 한 줄 남긴다
        self.assertTrue({KIND_PRE_SESSION, KIND_TOUCHED} <= kinds("{HOME}/notes.md"))

    def test_malformed_input(self):
        self.assertEqual(run_hook("not json"), (0, ""))
        self.assertEqual(run_hook("[1]"), (0, ""))
        self.assertEqual(run_hook({"tool_name": "Edit", "tool_input": {}}), (0, ""))

    def test_hooks_json_registration(self):
        h = json.loads(HOOKS_JSON.read_text())["hooks"]["PreToolUse"]
        e = next(g for g in h if g.get("matcher") == "Write|Edit|NotebookEdit")["hooks"][0]
        self.assertEqual((e["timeout"], e["command"]), (5, 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/touch-ledger.py"'))


if __name__ == "__main__":
    unittest.main()
