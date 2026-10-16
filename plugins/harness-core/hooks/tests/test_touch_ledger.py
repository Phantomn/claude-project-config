from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _world import World, WorldCase
from ledger import KIND_CREATED, KIND_PRE_DIRTY, KIND_PRE_SESSION, KIND_TOUCHED, Ledger

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
