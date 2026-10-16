from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _world import World, WorldCase, judge_case
from bash_guard import FOOTER, Decision, judge, log_event, render
from ledger import KIND_PRE_DIRTY, KIND_PRE_SESSION, Ledger, state_dir

ON = {"HARNESS_BASH_GUARD": "on"}
OLD_ASK = '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"x"}}'
w: World = None  # type: ignore[assignment]  # WorldCase.setUp 이 테스트마다 넣는다


_WorldCase = WorldCase   # 벽시계 계단 이동 시 세계 재생성·재시도 (_world.py)


class JudgeTest(_WorldCase):
    def test_allow_render_exact(self):
        d = judge(w.payload("ls -la"), {**w.environ, **ON}); self.assertTrue(d.allow)
        self.assertEqual(render(d), '{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}')

    def test_deny_render(self):
        out = json.loads(render(judge(w.payload("rm src/main.py"), {**w.environ, **ON})))["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny"); self.assertTrue(out["permissionDecisionReason"].startswith("[bash-guard] 거부: 삭제 "))
        self.assertTrue(out["permissionDecisionReason"].endswith(FOOTER))

    def test_multiple_reasons(self):
        self.assertEqual(len(judge(w.payload("rm src/main.py; rm {HOME}/notes.md"), {**w.environ, **ON}).reasons), 2)

    def test_reason_cap(self):
        files = " ".join(f"f{i}.txt" for i in range(30))
        w.sh(f"touch {files} && git add {files} && git commit -q -m many")
        d = judge(w.payload(f"rm {files}"), {**w.environ, **ON})
        self.assertEqual(len(d.reasons), 21); self.assertEqual(d.reasons[-1], "… 외 10건")

    def test_mode_resolution(self):
        self.assertEqual(judge(w.payload("rm src/main.py"), w.environ).mode, "off")
        w.set_repo_switch("shadow"); self.assertEqual(judge(w.payload("rm src/main.py"), w.environ).mode, "shadow")
        # 세션 cwd 는 홈(저장소 밖)이고 대상만 스위치 저장소 안 → 대상 저장소 값으로 on
        w.set_repo_switch("on"); self.assertEqual(judge(w.payload("rm {REPO}/src/main.py", cwd="{HOME}"), w.environ).mode, "on")
        self.assertEqual(judge(w.payload('cd {REPO} && rm -rf "$UNSET_X"', cwd="{HOME}"), w.environ).mode, "on")   # 단위 cwd 의 저장소 값
        w2 = World(docker=True); self.addCleanup(w2.close)   # 컨테이너 바인드 마운트 대상(docker 없으면 이 부분 생략)
        if w2.docker:
            w2.set_repo_switch("on")
            self.assertEqual(judge(w2.payload(f"docker exec {w2.docker.container} rm -rf /app/src", cwd="{HOME}"), w2.environ).mode, "on")

    def test_parse_failure_policy(self):
        self.assertTrue(judge(w.payload('echo "unterminated'), {**w.environ, **ON}).allow)
        self.assertTrue(judge(w.payload('echo "rmdir format'), {**w.environ, **ON}).allow)   # 단어 경계: rmdir·format 은 아님
        for c in ['find . -delete "x', 'echo "a > b']:
            self.assertFalse(judge(w.payload(c), {**w.environ, **ON}).allow, c)
        d = judge(w.payload('rm -rf "unterminated'), {**w.environ, **ON}); self.assertFalse(d.allow); self.assertIn("해석하지 못했다", d.reasons[0])

    def test_budget(self):
        self.assertFalse(judge(w.payload("rm {HOME}/notes.md"), {**w.environ, **ON}, budget=0).allow)
        self.assertIn("판정 시간 초과", judge(w.payload("rm {HOME}/notes.md"), {**w.environ, **ON}, budget=0).reasons[0])
        self.assertTrue(judge(w.payload("ls"), {**w.environ, **ON}, budget=0).allow)

    def test_inplace_edit_records_ledger(self):
        judge(w.payload("sed -i s/a/b/ {HOME}/notes.md", session_id=w.session_id), {**w.environ, **ON})
        self.assertIn(KIND_PRE_SESSION, [e.kind for e in Ledger(w.environ).entries(w.fmt("{HOME}/notes.md"))])
        judge(w.payload("echo x >> README.md", session_id=w.session_id), w.environ)   # >> 도 장부 기록(모드 무관, 재감사 rootcause-r1-s2-004)
        self.assertIn(KIND_PRE_DIRTY, [e.kind for e in Ledger(w.environ).entries(w.fmt("{REPO}/README.md"))])

    def test_mv_records_moved_in(self):   # D14 — 모드 off 여도 기록
        judge(w.payload("mv {HOME}/notes.md {REPO}/build/", session_id=w.session_id), w.environ)
        self.assertEqual(Ledger(w.environ).moved_in_near(w.fmt("{REPO}/build/notes.md")), w.fmt("{REPO}/build/notes.md"))
        judge(w.payload("mv src/probe.ts {SCRATCH}/s1/", session_id=w.session_id), w.environ)   # 세션 파일 원본 → 기록 없음
        self.assertIsNone(Ledger(w.environ).moved_in_near(w.fmt("{SCRATCH}/s1/probe.ts")))
        judge(w.payload("mv src/main.py src/app.py", session_id=w.session_id), w.environ)   # 깨끗한 추적 파일 이름 변경 → 기록 없음
        self.assertIsNone(Ledger(w.environ).moved_in_near(w.fmt("{REPO}/src/app.py")))
        judge(w.payload("mv README.md {SCRATCH}/s1/", session_id=w.session_id), w.environ)   # 세션 전 커밋 안 된 수정이 있는 추적 파일 → 기록
        self.assertIsNotNone(Ledger(w.environ).moved_in_near(w.fmt("{SCRATCH}/s1/README.md")))

    def test_log_rotation(self):
        for _ in range(5):
            log_event({"x": "y" * 80}, w.environ, max_bytes=200)
        self.assertTrue((state_dir(w.environ) / "bash-guard.jsonl.1").exists())
        self.assertEqual((state_dir(w.environ) / "bash-guard.jsonl").stat().st_mode & 0o777, 0o600)

    def test_render_prefix_first_line_only(self):
        d = Decision(False, ["거부: a", "거부: b"], "on")
        self.assertEqual(json.loads(render(d))["hookSpecificOutput"]["permissionDecisionReason"],
                         f"[bash-guard] 거부: a\n거부: b\n{FOOTER}")

    def test_ledger_write_failure_keeps_decision(self):   # 리뷰 1: 장부 쓰기 실패가 거부를 허용으로 뒤집지 않는다
        led = state_dir(w.environ) / "ledger.tsv"
        led.parent.mkdir(parents=True, exist_ok=True); led.write_text(""); led.chmod(0o400)
        d = judge(w.payload("cp {HOME}/notes.md README.md"), {**w.environ, **ON})
        self.assertFalse(d.allow); self.assertTrue(d.error)
        d = judge(w.payload("sed -i s/a/b/ {HOME}/notes.md"), {**w.environ, **ON}); self.assertTrue(d.allow)

    def test_git_alias_mode(self):   # 리뷰 2: 저장소 config alias 단위도 모드 계산에 든다
        w.sh("git config alias.nuke 'reset --hard'"); w.set_repo_switch("on")
        d = judge(w.payload("cd {REPO} && git nuke", cwd="{HOME}"), w.environ)
        self.assertEqual(d.mode, "on"); self.assertFalse(d.allow)

    def test_mv_unresolved_source_records(self):   # 리뷰 4: 원본 분류를 확정할 수 없으면(손상된 .git) 보호 쪽으로 기록
        (w.repo / ".git/HEAD").write_text("garbage\n")
        judge(w.payload("mv src/main.py {SCRATCH}/s1/", session_id=w.session_id), w.environ)
        self.assertIsNotNone(Ledger(w.environ).moved_in_near(w.fmt("{SCRATCH}/s1/main.py")))


class MainTest(_WorldCase):
    def run_main(self, payload, old: str = OLD_ASK, extra: dict | None = None) -> subprocess.CompletedProcess:
        stdin = payload if isinstance(payload, str) else json.dumps(payload)
        return subprocess.run([sys.executable, str(SCRIPTS / "bash_guard.py"), "--old", old], input=stdin,
                              env={**w.environ, **(extra or {})}, capture_output=True, text=True, timeout=30, check=False)

    def log_lines(self) -> list[dict]:
        p = state_dir(w.environ) / "bash-guard.jsonl"
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []

    def test_main_outputs(self):
        r = self.run_main(w.payload("rmdir d"))
        self.assertEqual((r.returncode, r.stdout), (0, OLD_ASK + "\n")); self.assertEqual(self.log_lines(), [])
        sh = {"HARNESS_BASH_GUARD": "shadow"}
        r = self.run_main(w.payload("rmdir d"), extra=sh)
        self.assertEqual((r.returncode, r.stdout), (0, OLD_ASK + "\n"))
        logs = self.log_lines(); self.assertEqual(len(logs), 1)
        self.assertEqual((logs[0]["mode"], logs[0]["decision"], logs[0]["old_decision"]), ("shadow", "allow", "ask"))
        r = self.run_main(w.payload("rm src/main.py"), extra=sh)   # 둘 다 비허용 → 기록 추가 없음
        self.assertEqual(r.returncode, 0); self.assertEqual(len(self.log_lines()), 1)
        r = self.run_main(w.payload("rmdir d"), extra=ON)
        self.assertEqual(r.returncode, 0); self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "allow")
        r = self.run_main(w.payload("rmdir d"), old="")
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_ascii_stdout(self):   # 리뷰 3: stdout 인코딩이 ascii 여도 deny JSON 이 나오고 rc 0
        r = subprocess.run([sys.executable, str(SCRIPTS / "bash_guard.py"), "--old", OLD_ASK], input=json.dumps(w.payload("rm src/main.py")).encode(),
                           env={**w.environ, **ON, "PYTHONIOENCODING": "ascii"}, capture_output=True, timeout=30, check=False)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(json.loads(r.stdout.decode("utf-8"))["hookSpecificOutput"]["permissionDecision"], "deny")

    def run_bytes(self, stdin: bytes, extra: dict, stdout=subprocess.PIPE) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPTS / "bash_guard.py"), "--old", OLD_ASK], input=stdin, stdout=stdout,
                              stderr=subprocess.PIPE, env={**w.environ, **extra}, timeout=30, check=False)

    def test_stdout_write_failure(self):   # 리뷰 라운드 2 (a): stdout 이 가득 찬 장치여도 rc 0, 출력 실패는 기록
        with open("/dev/full", "wb") as full:
            r = self.run_bytes(json.dumps(w.payload("rm src/main.py")).encode(), ON, stdout=full)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("출력 실패", self.log_lines()[-1]["error"])

    def test_non_ascii_bytes_input(self):   # 리뷰 라운드 2 (b): 입력은 바이트로 — 텍스트 인코딩과 무관
        w.sh("touch 한글.txt && git add 한글.txt && git commit -q -m k")
        asc = {**ON, "PYTHONIOENCODING": "ascii"}
        r = self.run_bytes(json.dumps(w.payload("rm 한글.txt"), ensure_ascii=False).encode(), asc)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(json.loads(r.stdout.decode())["hookSpecificOutput"]["permissionDecision"], "deny")
        broken = b'{"tool_name": "Bash", "tool_input": {"command": "rm x\xff.txt"}, "cwd": "/"}'   # 깨진 UTF-8
        r = self.run_bytes(broken, asc)
        self.assertEqual(r.returncode, 0)
        out = json.loads(r.stdout.decode())["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny"); self.assertIn("판정기 오류", out["permissionDecisionReason"])

    def test_lone_surrogate_in_command(self):   # 리뷰 라운드 3: 출력에 짝 없는 surrogate 가 들어도 rc 0 + 유효한 deny JSON
        r = self.run_bytes(json.dumps(w.payload('rm -rf "$X\ud800"')).encode(), ON)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout.decode("ascii"))["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_log_mode_fixed_on_existing(self):   # 이전 버전이 0644 로 만든 로그도 0600 으로
        p = state_dir(w.environ) / "bash-guard.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True); p.write_text(""); p.chmod(0o644)
        log_event({"x": 1}, w.environ)
        self.assertEqual(p.stat().st_mode & 0o777, 0o600)

    def test_internal_error_fallback(self):   # spec §3.8 (다), 재감사 rootcause-r1-s2-003·selfcontained-r1-s2-006
        r = self.run_main({"tool_name": "Bash", "tool_input": "rm -rf x", "cwd": str(w.repo)})
        self.assertEqual((r.returncode, r.stdout), (0, OLD_ASK + "\n"))
        logs = self.log_lines(); self.assertEqual(len(logs), 1); self.assertTrue(logs[0]["error"])
        r = self.run_main({"tool_name": "Bash", "tool_input": {"command": "rm -rf x"}, "cwd": 5}, extra=ON)
        self.assertEqual(r.returncode, 0); self.assertNotIn("ask", r.stdout)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny"); self.assertIn("판정기 오류", out["permissionDecisionReason"])
        r = self.run_main({"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": 5}, extra=ON)
        self.assertEqual(r.returncode, 0); self.assertNotIn("ask", r.stdout)
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "allow")


def load(name: str) -> list[dict]:
    with open(Path(__file__).resolve().parent / "fixtures" / name, encoding="utf-8") as f:
        return json.load(f)


class AcceptanceTest(_WorldCase):   # spec §8 합격 묶음 — 부록 B·C
    def test_false_positive_fixtures(self):
        bad = [(c["id"], d.reasons) for c in load("false_positive.json") if not (d := judge_case(c)).allow]
        self.assertEqual(bad, [])

    def test_false_negative_fixtures(self):
        bad = [c["id"] for c in load("false_negative.json") if judge_case(c).allow]
        self.assertEqual(bad, [])

    def test_never_ask_on(self):   # SC1: on 출력은 유효 JSON 이고 결정은 allow·deny 뿐
        for c in load("false_positive.json") + load("false_negative.json"):
            out = json.loads(render(judge_case(c)))["hookSpecificOutput"]
            self.assertIn(out["permissionDecision"], ("allow", "deny"), c["id"])

    def test_pr_flow_scenario(self):
        steps = ["git worktree add {OUT}/wt2 -b feat/y", "cd {OUT}/wt2 && echo a > f.txt && git add f.txt && git commit -qm a",
                 "cd {OUT}/wt2 && mv f.txt g.txt && git add -A && git commit -qm r",
                 "cd {OUT}/wt2 && echo b > g.txt && git commit -qam b",   # 이름 변경은 moved-in 아님
                 "cd {OUT}/wt2 && git push -u origin feat/y", "cd {OUT}/wt2 && git commit -q --amend -m b && git push --force",
                 "git worktree remove {OUT}/wt2", "git branch -D feat/y", "git push origin --delete feat/y"]
        for s in steps:
            d = w.judge_cmd(s); self.assertTrue(d.allow, (s, d.reasons)); w.sh(s)

    def step(self, s: str, allow: bool = True) -> None:
        d = w.judge_cmd(s); self.assertEqual(d.allow, allow, (s, d.reasons))
        if allow:
            w.sh(s)   # 판정한 명령은 실행해 다음 단계가 실제 결과 상태를 보게 한다

    def test_self_revert_scenario(self):
        # 세션 중 수정은 실제 세션 경로로만 만든다 — 장부를 거치지 않은 수정 뒤 checkout 이 pre-dirty 를 남기는 것은 §13 한계(임의 스크립트)
        w.clean_tree()
        # Edit 도구 경로: touch-ledger 기록 뒤 파일 수정
        r = subprocess.run([sys.executable, str(SCRIPTS / "touch-ledger.py")], input=json.dumps(w.edit_payload("{REPO}/src/main.py")),
                           env=w.environ, capture_output=True, text=True, timeout=30, check=True)
        self.assertEqual(r.stdout, ""); w.touch_modify("{REPO}/src/main.py")
        self.step("git checkout -- src/main.py")
        # 판정기를 거치는 Bash 경로
        self.step("echo y >> src/main.py"); self.step("git checkout -- src/main.py")
        self.step("echo y >> src/main.py"); self.step("git reset --hard")
        w.dirty_before_session("{REPO}/README.md"); self.assertFalse(w.judge_cmd("git reset --hard").allow)
        s = "echo x >> README.md"; self.assertTrue(w.judge_cmd(s).allow); w.sh(s)   # >> 로 mtime 이 세션 중이 돼도
        self.assertFalse(w.judge_cmd("git reset --hard").allow)                     # 장부 pre-dirty 로 deny


if __name__ == "__main__":
    unittest.main()
