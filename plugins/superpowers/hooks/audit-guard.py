#!/usr/bin/env python3
"""spec-audit 강제 훅 (G1–G3 감사자, M1–M2 감사 중 리드). spec-audit-stage2 4.2·4.3·4.5.

PreToolUse 입력(stdin JSON)을 받아 차단이면 stdout에 deny JSON 한 줄, 허용이면 출력 없음.
항상 exit 0 — 훅 오류가 모든 세션의 도구를 막지 않는다(fail-open, L34).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "spec-audit" / "scripts"))
import audit_ws  # noqa: E402

AUDITOR = "superpowers:spec-auditor"

# ── G2 시크릿 이름 (spec 4.2) — 경로 세그먼트 전체 매치 ──────────────
_SECRET_EXAMPLE = {".env.example", ".env.sample", ".env.template"}
_SECRET_FIXED = {"id_rsa", "id_ed25519", "id_ecdsa", "id_dsa", ".netrc",
                 ".secret", ".secrets", ".env"}
# 확장자형: <1자+>.env/.pem/.key/.p12/.pfx — Bash에서는 이것만 제외
_EXT_RE = re.compile(r".+\.(env|pem|key|p12|pfx)$")
# 접미형: .env.<접미>, .secrets.<접미>
_SUFFIX_RE = re.compile(r"\.(env|secrets)\..+$")


def _is_secret_seg(seg: str) -> bool:
    """세그먼트(소문자) 하나가 시크릿 이름이면 True (확장자형 포함 전부)."""
    s = seg.lower()
    if s in _SECRET_EXAMPLE:
        return False
    return s in _SECRET_FIXED or bool(_SUFFIX_RE.match(s)) or bool(_EXT_RE.match(s))


def is_secret(text: str, no_ext: bool = False) -> bool:
    """경로 문자열에 시크릿 이름이 경로 구성요소로 나타나면 True.

    no_ext=True(Bash)면 확장자형(<x>.env·.pem·.key·.p12·.pfx)을 뺀 이름만 본다 —
    확장자형은 코드 표현(process.env·jq .data.key)과 구분할 수 없어서(spec 4.2 G2).
    또는 /.ssh/·/.aws/ 포함.
    """
    low = text.lower()
    if "/.ssh/" in low or "/.aws/" in low:
        return True
    for seg in re.split(r"[/\s]+", text):
        if not seg:
            continue
        s = seg.lower()
        if s in _SECRET_EXAMPLE:
            continue
        ext = bool(_EXT_RE.match(s))
        if no_ext and ext:
            continue
        if s in _SECRET_FIXED or bool(_SUFFIX_RE.match(s)) or ext:
            return True
    return False


# ── G3 위험 명령 (spec 4.2) ──────────────────────────────────────
# 명령 위치: 문자열 시작, 또는 ; & | ( 개행 뒤 공백 다음. 선행 sudo·NAME=VALUE 허용.
_DANGER = (
    r"(?:npm|pnpm|yarn)\s+(?:install|i|add)"
    r"|(?:pip|pip3)\s+install"
    r"|uv\s+pip\s+install"
    r"|(?:kill|pkill|killall)(?:\s|$)"
)
_LEAD = r"(?:(?:sudo|[A-Za-z_][A-Za-z0-9_]*=\S+)\s+)*"
_DANGER_RE = re.compile(r"(?:^|[;&|(\n])\s*" + _LEAD + r"(?:" + _DANGER + r")")


def is_danger(cmd: str) -> bool:
    return bool(_DANGER_RE.search(cmd))


# ── 경로 해소 ────────────────────────────────────────────────────
def _resolve(cwd: str, p: str) -> Path:
    return (Path(cwd) / p).resolve()


# ── 차단 사유 (spec 4.2·4.3) ─────────────────────────────────────
_UNVERIFIED = " — 이 검증은 unverified(policy)로 보고한다"
_G2_GUIDE = ("시크릿 파일은 열지 않는다 — 문자열 검색이면 Grep 도구의 pattern으로, "
             "일반 파일이면 Read로 다시 하고, 시크릿 값 자체가 필요한 검증만 unverified(policy)")


def _lead_reason(rule: str, rec: dict) -> str:
    return (f"audit-guard: {rule}: spec-audit 라운드 {rec['round']} 진행 중 — "
            f"감사자 응답과 C3를 기다린다. 감사를 버리려면 "
            f"python3 {Path(audit_ws.__file__).resolve()} clean --ws {rec['ws']}")


# ── 감사자 규칙 (G1–G3, spec 4.2) ────────────────────────────────
def _auditor(inp: dict) -> str | None:
    tool = inp.get("tool_name", "")
    ti = inp.get("tool_input") or {}
    cwd = inp.get("cwd", "")
    # G1 write
    if tool == "Write":
        fp = _resolve(cwd, str(ti.get("file_path", "")))
        ok_report = re.search(r"/round-\d+/reports/[^/]+\.md$", str(fp))
        ok_tmp = str(fp).startswith(str(audit_ws.tmproot() / "spec-audit") + "/")
        if not (ok_report or ok_tmp):
            return f"audit-guard: write: 감사자 Write는 보고 파일만 허용{_UNVERIFIED}"
    # G2 secret
    if tool in ("Read", "Grep", "Glob", "Bash"):
        if tool == "Bash":
            hit = is_secret(str(ti.get("command", "")), no_ext=True)
        else:
            vals = []
            if tool == "Read":
                vals = [ti.get("file_path")]
            elif tool == "Grep":
                vals = [ti.get("path"), ti.get("glob")]
            elif tool == "Glob":
                vals = [ti.get("pattern"), ti.get("path")]
            hit = any(is_secret(str(v)) for v in vals if v)
        if hit:
            return f"audit-guard: secret: {_G2_GUIDE}"
    # G3 danger
    if tool == "Bash" and is_danger(str(ti.get("command", ""))):
        return f"audit-guard: danger: 감사 중 설치·프로세스 종료 명령은 금지{_UNVERIFIED}"
    return None


# ── 리드 규칙 (M1–M2, spec 4.3) ──────────────────────────────────
def _open_audits(session: str | None) -> list[dict]:
    """이 세션의 열린 감사 — open.json 중 session이 입력 session_id와 같거나 null."""
    out = []
    for p in (audit_ws.tmproot() / "spec-audit").glob("*/open.json"):
        rec = json.loads(p.read_text(encoding="utf-8"))
        if rec.get("session") is None or rec.get("session") == session:
            out.append(rec)
    return out


def _lead(inp: dict) -> str | None:
    recs = _open_audits(inp.get("session_id"))
    if not recs:
        return None
    tool = inp.get("tool_name", "")
    ti = inp.get("tool_input") or {}
    cwd = inp.get("cwd", "")
    # M2 lead-code
    if tool == "LSP" or re.match(r"mcp__(serena|codegraph)__", tool):
        return _lead_reason("lead-code", recs[0])
    # M2 lead-bash
    if tool == "Bash":
        if "audit_ws.py" not in str(ti.get("command", "")):
            return _lead_reason("lead-bash", recs[0])
        return None
    # M1 lock
    if tool in ("Write", "Edit", "NotebookEdit"):
        key = "notebook_path" if tool == "NotebookEdit" else "file_path"
        fp = str(_resolve(cwd, str(ti.get(key, ""))))
        for rec in recs:
            if fp in {str(Path(t).resolve()) for t in rec["targets"]}:
                return _lead_reason("lock", rec)
        return None
    # M2 lead-read
    if tool in ("Read", "Grep", "Glob"):
        raw = ti.get("file_path") if tool == "Read" else ti.get("path")
        fp = _resolve(cwd, str(raw)) if raw else Path(cwd).resolve()
        fps = str(fp)
        for rec in recs:
            ws = str(Path(rec["ws"]).resolve())
            slug = str((audit_ws.tmproot() / "spec-audit" / Path(rec["ws"]).name).resolve())
            targets = {str(Path(t).resolve()) for t in rec["targets"]}
            under_tree = fps == rec["tree"] or fps.startswith(rec["tree"] + "/")
            under_slug = fps.startswith(slug + "/")
            under_ws = fps == ws or fps.startswith(ws + "/")
            if (under_tree or fps in targets or under_slug) and not under_ws:
                return _lead_reason("lead-read", rec)
        return None
    return None


def decide(inp: dict) -> str | None:
    if inp.get("agent_type") == AUDITOR:
        return _auditor(inp)
    return _lead(inp)


def _deny(reason: str) -> str:
    return json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}, ensure_ascii=False)


def main() -> None:
    try:
        inp = json.loads(sys.stdin.read())
        reason = decide(inp)
    except Exception as e:  # fail-open (L34)
        print(f"audit-guard: 오류로 통과: {e}", file=sys.stderr)
        return
    if reason:
        print(_deny(reason))


if __name__ == "__main__":
    main()
