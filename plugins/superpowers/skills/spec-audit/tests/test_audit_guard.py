from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from test_audit_ws import Base, audit_ws, SCRIPTS

GUARD = SCRIPTS.parent.parent.parent / "hooks" / "audit-guard.py"
AUDITOR = "superpowers:spec-auditor"

# spec 4.2 시크릿 이름 목록 (이름마다 행)
SECRET_NAMES = [
    ".env",
    ".env.local",          # .env.<접미>
    "app.env",             # <1자 이상>.env
    ".secret",
    ".secrets",
    ".secrets.prod",       # .secrets.<접미>
    "server.pem",          # <1자 이상>.pem
    "server.key",          # <1자 이상>.key
    "cert.p12",            # <1자 이상>.p12
    "cert.pfx",            # <1자 이상>.pfx
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "id_dsa",
    ".netrc",
]
# 확장자형 = <1자+>.env/.pem/.key/.p12/.pfx. Bash에서 통과하는 것.
_EXT = re.compile(r".+\.(env|pem|key|p12|pfx)$")
BASH_ALLOWED = [n for n in SECRET_NAMES if _EXT.match(n)]
# Bash에서도 막히는 것 = 확장자형을 뺀 나머지(도트파일형)
BASH_BLOCKED = [n for n in SECRET_NAMES if n not in BASH_ALLOWED]
# 뒤에 영숫자를 붙이면 통과하는 이름 = 고정 이름만(접미형은 접미가 바뀔 뿐 여전히 시크릿)
_SUFFIX = re.compile(r"\.(env|secrets)\..+$")
NETRCX_NAMES = [n for n in SECRET_NAMES if not _EXT.match(n) and not _SUFFIX.match(n)]

# spec 4.2 G3 목록
G3_CMDS = [
    "npm install", "npm i", "npm add",
    "pnpm install", "pnpm i", "pnpm add",
    "yarn install", "yarn i", "yarn add",
    "pip install", "pip3 install", "uv pip install",
    "kill", "pkill", "killall",
]
# 명령 위치 앞부분
G3_PREFIXES = ["", "; ", "& ", "| ", "( ", "\n", "sudo ", "FOO=1 "]


class GuardBase(Base):
    def hook(self, inp: dict, cwd: Path | None = None) -> tuple[int, str, str]:
        p = subprocess.run([sys.executable, str(GUARD)],
                           input=json.dumps(inp), capture_output=True, text=True)
        return p.returncode, p.stdout, p.stderr

    def denied(self, out: str) -> str | None:
        try:
            d = json.loads(out)
        except ValueError:
            return None
        return d.get("hookSpecificOutput", {}).get("permissionDecisionReason")

    def aud(self, tool: str, ti: dict, cwd: Path | None = None) -> tuple[int, str, str]:
        inp = {"agent_type": AUDITOR, "session_id": "sess-test",
               "cwd": str(cwd or self.tmp), "tool_name": tool, "tool_input": ti}
        return self.hook(inp)

    def lead(self, tool: str, ti: dict, cwd: Path | None = None,
             session: str = "sess-test", agent_type: str | None = None) -> tuple[int, str, str]:
        inp = {"session_id": session, "cwd": str(cwd or self.tmp),
               "tool_name": tool, "tool_input": ti}
        if agent_type is not None:
            inp["agent_type"] = agent_type
        return self.hook(inp)

    def make_open_audit(self) -> None:
        """C1으로 실제 열린 감사를 만든다. self.W(ws)·self.d(repo)·대상 경로 설정."""
        self.d = self.repo({"docs/plans/p.md": "# plan\n- a\n- b\n",
                            "docs/specs/s.md": "# spec\n- x\n- y\n",
                            "src/a.py": "x=1\n", "notes.md": "n\n", "README.md": "r\n"})
        rc, out, err = self.c1("--plan", str(self.d / "docs/plans/p.md"),
                               "--spec", str(self.d / "docs/specs/s.md"))
        self.assertEqual(rc, 0, err)
        self.W = Path(out["ws"])
        self.plan_t = (self.d / "docs/plans/p.md").resolve()
        self.spec_t = (self.d / "docs/specs/s.md").resolve()


# ── 출력 형식 ────────────────────────────────────────────
class TestShape(GuardBase):
    def test_deny_json_shape(self):
        rc, out, _ = self.aud("Bash", {"command": "npm install"})
        self.assertEqual(rc, 0)
        d = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(d["hookEventName"], "PreToolUse")
        self.assertEqual(d["permissionDecision"], "deny")
        self.assertTrue(d["permissionDecisionReason"].startswith("audit-guard: danger:"))


# ── G1 write ────────────────────────────────────────────
class TestG1(GuardBase):
    def test_g1_report_allowed(self):
        W = self.tmp / "myws"
        f = W / "round-1" / "reports" / "x.md"
        rc, out, _ = self.aud("Write", {"file_path": str(f)})
        self.assertIsNone(self.denied(out), out)

    def test_g1_tmp_allowed(self):
        f = audit_ws.tmproot() / "spec-audit" / "s" / "r1" / "a" / "f"
        rc, out, _ = self.aud("Write", {"file_path": str(f)})
        self.assertIsNone(self.denied(out), out)

    def test_g1_tree_denied(self):
        d = self.repo({"src/a.py": "x\n"})
        rc, out, _ = self.aud("Write", {"file_path": str(d / "src/a.py")})
        self.assertTrue((self.denied(out) or "").startswith("audit-guard: write:"), out)

    def test_g1_dotdot_escape(self):
        W = self.tmp / "myws"
        f = W / "round-1" / "reports" / ".." / ".." / ".." / ".." / "x.md"
        rc, out, _ = self.aud("Write", {"file_path": str(f)})
        self.assertIsNotNone(self.denied(out), out)


# ── G2 secret ───────────────────────────────────────────
class TestG2(GuardBase):
    def test_g2_boundaries(self):
        # Review Focus 5: 통과·차단 값 전부 (도구·입력 키 그대로)
        self.assertIsNotNone(self.denied(self.aud("Read", {"file_path": "/a/.env"})[1]))
        self.assertIsNotNone(self.denied(self.aud("Grep", {"path": "/a/.env"})[1]))
        self.assertIsNotNone(self.denied(self.aud("Grep", {"glob": "**/.env"})[1]))
        self.assertIsNotNone(self.denied(self.aud("Glob", {"pattern": "**/.env"})[1]))
        self.assertIsNotNone(self.denied(self.aud("Glob", {"path": "/a/.env"})[1]))
        # pattern(내용 정규식)은 Grep에서 제외 → 통과
        self.assertIsNone(self.denied(self.aud("Grep", {"pattern": ".env"})[1]))
        # 경계: .envx (뒤에 영숫자) 통과
        self.assertIsNone(self.denied(self.aud("Read", {"file_path": "/a/.envx"})[1]))
        # 코드 표현 process.env 는 경로 구성요소가 아니므로 통과(앞이 영숫자)
        self.assertIsNone(self.denied(self.aud("Bash", {"command": "echo process.env"})[1]))
        # .env.example 제외 → 통과
        self.assertIsNone(self.denied(self.aud("Read", {"file_path": "/a/.env.example"})[1]))
        self.assertIsNone(self.denied(self.aud("Read", {"file_path": "/a/.env.sample"})[1]))
        self.assertIsNone(self.denied(self.aud("Read", {"file_path": "/a/.env.template"})[1]))

    def test_g2_every_name(self):
        for name in SECRET_NAMES:
            with self.subTest(name=name, where="Read file_path"):
                self.assertIsNotNone(self.denied(self.aud("Read", {"file_path": f"/x/{name}"})[1]))
            with self.subTest(name=name, where="Grep path"):
                self.assertIsNotNone(self.denied(self.aud("Grep", {"path": f"/x/{name}"})[1]))
            with self.subTest(name=name, where="Grep glob"):
                self.assertIsNotNone(self.denied(self.aud("Grep", {"glob": f"**/{name}"})[1]))
            with self.subTest(name=name, where="Glob pattern"):
                self.assertIsNotNone(self.denied(self.aud("Glob", {"pattern": f"**/{name}"})[1]))
            with self.subTest(name=name, where="Glob path"):
                self.assertIsNotNone(self.denied(self.aud("Glob", {"path": f"/x/{name}"})[1]))
        for name in NETRCX_NAMES:
            with self.subTest(name=name, where="netrcx"):
                self.assertIsNone(self.denied(self.aud("Read", {"file_path": f"/x/{name}x"})[1]))
        for name in BASH_ALLOWED:
            with self.subTest(name=name, where="Bash allowed"):
                self.assertIsNone(self.denied(self.aud("Bash", {"command": f"cat /x/{name}"})[1]))
        for name in BASH_BLOCKED:
            with self.subTest(name=name, where="Bash blocked"):
                self.assertIsNotNone(self.denied(self.aud("Bash", {"command": f"cat /x/{name}"})[1]))

    def test_reason_guidance(self):
        r = self.denied(self.aud("Read", {"file_path": "/a/.env"})[1])
        self.assertIn("Grep 도구의 pattern", r)
        self.assertIn("Read", r)
        # G1·G3 차단 사유에는 unverified(policy)
        self.assertIn("unverified(policy)", self.denied(self.aud("Bash", {"command": "npm install"})[1]))
        d = self.repo({"src/a.py": "x\n"})
        self.assertIn("unverified(policy)", self.denied(self.aud("Write", {"file_path": str(d / "src/a.py")})[1]))

    def test_g2_ssh_aws(self):
        self.assertIsNotNone(self.denied(self.aud("Read", {"file_path": "/home/u/.ssh/config"})[1]))
        self.assertIsNotNone(self.denied(self.aud("Bash", {"command": "cat ~/.aws/credentials"})[1]))


# ── G3 danger ───────────────────────────────────────────
class TestG3(GuardBase):
    def test_g3_danger(self):
        for cmd in G3_CMDS:
            for pre in G3_PREFIXES:
                full = pre + cmd + " foo"
                with self.subTest(cmd=cmd, prefix=repr(pre)):
                    self.assertIsNotNone(self.denied(self.aud("Bash", {"command": full})[1]), full)

    def test_g3_safe(self):
        for cmd in ["npm ci", "npm test", "echo kill",
                    "grep -n install README.md", "git log"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.denied(self.aud("Bash", {"command": cmd})[1]), cmd)


# ── 리드 (M1·M2) ────────────────────────────────────────
class TestLead(GuardBase):
    def test_no_open_audit_passes(self):
        d = self.repo({"x.py": "y\n"})
        self.assertIsNone(self.denied(self.lead("Write", {"file_path": str(d / "x.py")})[1]))

    def test_m1_lock(self):
        self.make_open_audit()
        for tool, ti in [("Write", {"file_path": str(self.plan_t)}),
                         ("Edit", {"file_path": str(self.plan_t)}),
                         ("NotebookEdit", {"notebook_path": str(self.plan_t)})]:
            with self.subTest(tool=tool):
                r = self.denied(self.lead(tool, ti)[1])
                self.assertTrue((r or "").startswith("audit-guard: lock:"), r)
                self.assertIn("clean --ws", r)
                self.assertIn(str(self.W), r)

    def test_m1_symlink_and_relative(self):
        self.make_open_audit()
        link = self.tmp / "lnk.md"
        link.symlink_to(self.plan_t)
        self.assertIsNotNone(self.denied(self.lead("Write", {"file_path": str(link)})[1]))
        # cwd 기준 상대경로
        rc, out, _ = self.lead("Write", {"file_path": "docs/plans/p.md"}, cwd=self.d)
        self.assertIsNotNone(self.denied(out), out)

    def test_m1_other_file_allowed(self):
        self.make_open_audit()
        self.assertIsNone(self.denied(self.lead("Write", {"file_path": str(self.d / "notes.md")})[1]))

    def test_m2_read(self):
        self.make_open_audit()
        # <tree> 아래
        self.assertTrue((self.denied(self.lead("Read", {"file_path": str(self.d / "README.md")})[1]) or "")
                        .startswith("audit-guard: lead-read:"))
        # W/round-1/assign.json → 통과(W 제외)
        self.assertIsNone(self.denied(self.lead("Read", {"file_path": str(self.W / "round-1" / "assign.json")})[1]))
        # 감사자 실행 디렉토리(TMPROOT/spec-audit/<slug>/) 아래 → 차단
        slug_dir = audit_ws.tmproot() / "spec-audit" / self.W.name
        self.assertIsNotNone(self.denied(self.lead("Read", {"file_path": str(slug_dir / "r1" / "a" / "f.py")})[1]))
        # tree 밖 일반 파일 → 통과
        self.assertIsNone(self.denied(self.lead("Read", {"file_path": "/etc/hostname"})[1]))

    def test_m2_read_target_outside_tree(self):
        # --tree 로 tree 밖에 둔 대상 문서 Read → 차단(∈ targets)
        tree = self.repo({"keep.md": "k\n"})
        spec = self.repo({"s.md": "# spec\n- a\n"})  # tree 밖
        rc, out, err = self.c1("--spec", str(spec / "s.md"), "--tree", str(tree))
        self.assertEqual(rc, 0, err)
        self.assertIsNotNone(self.denied(self.lead("Read", {"file_path": str(spec / "s.md")})[1]))

    def test_m2_grep_without_path_uses_cwd(self):
        self.make_open_audit()
        tree = Path(json.loads((self.W / "round-1" / "targets.json").read_text())["tree"])
        self.assertIsNotNone(self.denied(self.lead("Grep", {"pattern": "x"}, cwd=tree)[1]))
        self.assertIsNone(self.denied(self.lead("Grep", {"pattern": "x"}, cwd=self.tmp)[1]))

    def test_m2_bash(self):
        self.make_open_audit()
        self.assertTrue((self.denied(self.lead("Bash", {"command": "ls"})[1]) or "")
                        .startswith("audit-guard: lead-bash:"))
        ok = f"python3 {audit_ws.__file__} aggregate --ws {self.W} --round 1"
        self.assertIsNone(self.denied(self.lead("Bash", {"command": ok})[1]))

    def test_m2_code(self):
        self.make_open_audit()
        for tool in ["mcp__serena__find_symbol", "mcp__codegraph__codegraph_explore", "LSP"]:
            with self.subTest(tool=tool):
                self.assertTrue((self.denied(self.lead(tool, {})[1]) or "")
                                .startswith("audit-guard: lead-code:"))
        self.assertIsNone(self.denied(self.lead("mcp__qmd__query", {})[1]))

    def test_closed_after_c3(self):
        self.make_open_audit()
        # C3(aggregate) 전: 차단
        self.assertIsNotNone(self.denied(self.lead("Read", {"file_path": str(self.d / "README.md")})[1]))
        # round1_done: aggregate로 open.json 지워짐
        audit_ws.close_open(self.W)
        self.assertIsNone(self.denied(self.lead("Read", {"file_path": str(self.d / "README.md")})[1]))


# ── 세션·호출자 ─────────────────────────────────────────
class TestSession(GuardBase):
    def test_other_session_passes(self):
        self.make_open_audit()  # session sess-test
        self.assertIsNone(self.denied(
            self.lead("Read", {"file_path": str(self.d / "README.md")}, session="other")[1]))

    def test_null_session_applies(self):
        # CLAUDE_CODE_SESSION_ID 없이 C1 → session null
        import os
        saved = os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
        try:
            self.make_open_audit()
        finally:
            if saved is not None:
                os.environ["CLAUDE_CODE_SESSION_ID"] = saved
        # session null → 다른 세션도 차단
        self.assertIsNotNone(self.denied(
            self.lead("Read", {"file_path": str(self.d / "README.md")}, session="other")[1]))

    def test_non_auditor_passes(self):
        # agent_type general-purpose, 열린 감사 없음
        d = self.repo({"x.py": "y\n"})
        self.assertIsNone(self.denied(
            self.lead("Write", {"file_path": str(d / "x.py")}, agent_type="general-purpose")[1]))
        self.assertIsNone(self.denied(
            self.lead("Read", {"file_path": "/a/.env"}, agent_type="general-purpose")[1]))

    def test_non_auditor_lead_rules(self):
        self.make_open_audit()
        # general-purpose, 같은 session_id "sess-test" → 리드 규칙 적용(위임 우회 차단)
        self.assertTrue((self.denied(
            self.lead("Read", {"file_path": str(self.d / "README.md")}, agent_type="general-purpose")[1]) or "")
            .startswith("audit-guard: lead-read:"))
        self.assertTrue((self.denied(
            self.lead("Write", {"file_path": str(self.plan_t)}, agent_type="general-purpose")[1]) or "")
            .startswith("audit-guard: lock:"))
        # session "other"(대화형 teammate 모양) → 통과(L37)
        self.assertIsNone(self.denied(
            self.lead("Read", {"file_path": str(self.d / "README.md")},
                      session="other", agent_type="general-purpose")[1]))


# ── fail-open ───────────────────────────────────────────
class TestFailOpen(GuardBase):
    def test_fail_open_bad_stdin(self):
        p = subprocess.run([sys.executable, str(GUARD)],
                           input="not json", capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout, "")
        self.assertTrue(p.stderr.strip())

    def test_fail_open_bad_open_json(self):
        self.make_open_audit()
        audit_ws.open_path(self.W).write_text("{", encoding="utf-8")
        rc, out, err = self.lead("Read", {"file_path": str(self.d / "README.md")})
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")
        self.assertTrue(err.strip())


# ── 등록·에이전트 파일 ──────────────────────────────────
class TestRegistration(GuardBase):
    def test_hooks_json_registration(self):
        hj = json.loads((GUARD.parent / "hooks.json").read_text())
        pre = hj["hooks"]["PreToolUse"]
        matcher = "Read|Write|Edit|NotebookEdit|Bash|Grep|Glob|LSP|mcp__serena__.*|mcp__codegraph__.*"
        self.assertTrue(any(g["matcher"] == matcher for g in pre))
        grp = next(g for g in pre if g["matcher"] == matcher)
        self.assertIn("audit-guard.py", grp["hooks"][0]["command"])
        # SessionStart 그대로
        self.assertIn("SessionStart", hj["hooks"])

    def test_agent_frontmatter(self):
        md = (GUARD.parent.parent / "agents" / "spec-auditor.md").read_text()
        self.assertIn("name: spec-auditor", md)
        self.assertIn("model: opus", md)
        for t in ["Read", "Grep", "Glob", "Bash", "Write",
                  "mcp__serena__find_symbol", "mcp__serena__find_referencing_symbols",
                  "mcp__serena__get_symbols_overview", "mcp__serena__search_for_pattern",
                  "mcp__codegraph__codegraph_explore"]:
            self.assertIn(t, md)
        # 쓰기 도구 Edit·NotebookEdit·Agent 는 없다
        self.assertNotIn("Edit", md.split("tools:")[1].split("\n")[0])


if __name__ == "__main__":
    import unittest
    unittest.main()
