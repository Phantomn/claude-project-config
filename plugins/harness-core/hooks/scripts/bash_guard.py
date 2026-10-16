#!/usr/bin/env python3
"""bash-guard 진입점: Bash 명령을 판정하고 모드(off/shadow/on)에 따라 새 판정 또는 기존 판정(OLD)을 낸다 (spec §3.1·§3.2·§3.7·§3.8·§3.9).

사용: bash_guard.py --old <기존 판정 JSON>   (stdin = PreToolUse payload). 종료 코드는 항상 0.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

import policy
from ledger import KIND_MOVED_IN, state_dir
from shell_parse import Segment, parse
from target_class import (
    GIT_TRACKED,
    MODE_RANK,
    PRESERVED,
    PROTECTED_NAME,
    UNRESOLVED,
    Ctx,
    classify,
    git_dirty,
    is_session_change,
    make_ctx,
    normalize,
    note_touch,
    switch_mode,
)

BUDGET_SECONDS = 5.0
LOG_MAX_BYTES = 10 * 1024 * 1024
FOOTER = "이 판정을 우회하지 말 것. 대안이 맞지 않으면 작업을 멈추고 사용자에게 보고하라."
FAIL_WORDS = re.compile(r"(?<![\w.-])(?:rm|unlink|shred|truncate|dd|mkfs[\w.]*|reset|clean|restore|checkout|push|volume|prune|-delete)(?![\w.-])|>")
REASON_CAP = 20
R_PARSE = "거부: 명령을 해석하지 못했다. 단순한 형태로 나눠 실행하라"
R_TIMEOUT = "거부: 판정 시간 초과 — 범위를 좁혀라"
R_ERROR = "판정기 오류 — 단순한 형태로 나눠 실행하라"


@dataclass
class Decision:
    allow: bool
    reasons: list[str]
    mode: str                    # 이 명령의 모드
    error: str | None = None


def _env_mode(environ: Mapping[str, str]) -> str:
    v = environ.get("HARNESS_BASH_GUARD", "off")
    return v if v in MODE_RANK else "off"


def _strongest(modes: list[str]) -> str:
    return max(modes, key=MODE_RANK.__getitem__, default="off")


# ---- 장부 기록 (spec §3.7 기록 주체 2) ----

def _note_moves(seg: Segment, ctx: Ctx) -> None:
    for src, dst in policy.mv_moves(seg):
        c = classify(src, ctx)
        # 분류·조회 실패는 '조건 거짓'이 아니라 '모름' — 보호 쪽으로 기록(pre-dirty 과보호와 같은 원칙)
        keep = c.kind in (PRESERVED, PROTECTED_NAME, UNRESOLVED)
        if c.kind == GIT_TRACKED and c.path:
            dirty = git_dirty(c.path if os.path.isdir(c.path) else os.path.dirname(c.path), [c.path], ctx)
            keep = dirty is None or (bool(dirty) and not all(is_session_change(d, ctx) for d in dirty))
        if keep:
            ctx.ledger.record(normalize(dst, False), KIND_MOVED_IN, ctx.session_id)


def _record(seg: Segment, ctx: Ctx) -> None:
    # 거부될 명령도 기록한다 — 기록은 '처음 손대기 직전 상태'라 실행 여부와 무관하게 참이다
    if seg.context.kind != "host" or seg.via_xargs:
        return   # shortcut: 컨테이너 안 제자리 수정·mv 는 기록하지 않는다 — 바인드 마운트 대상 오분류가 나오면 호스트 경로로 사상해 기록
    for p in policy.inplace_targets(seg):
        note_touch(p, ctx, None)
    if seg.name == "mv":
        _note_moves(seg, ctx)


# ---- 판정 ----

def _base_mode(environ: Mapping[str, str], cwd: str | None) -> list[str]:
    return [_env_mode(environ), switch_mode(cwd, environ)]


def _cap(reasons: list[str]) -> list[str]:
    reasons = list(dict.fromkeys(reasons))
    if len(reasons) > REASON_CAP:
        return reasons[:REASON_CAP] + [f"… 외 {len(reasons) - REASON_CAP}건"]
    return reasons


def judge(payload: dict, environ: Mapping[str, str], budget: float = BUDGET_SECONDS) -> Decision:
    cwd, ti = payload.get("cwd"), payload.get("tool_input")
    if cwd is not None and not isinstance(cwd, str):
        raise ValueError(f"cwd 가 문자열이 아니다: {type(cwd).__name__}")
    if not isinstance(ti, dict):
        raise ValueError(f"tool_input 이 dict 가 아니다: {type(ti).__name__}")  # noqa: TRY004 — brief 계약이 ValueError
    command = ti.get("command")
    modes = _base_mode(environ, cwd)
    if payload.get("tool_name") != "Bash" or not isinstance(command, str) or not command:
        return Decision(True, [], _strongest(modes))
    ctx = make_ctx(payload, environ, budget)
    res = parse(command, cwd, environ)
    if res.error:   # spec §3.8 (가)
        bad = FAIL_WORDS.search(command) is not None
        return Decision(not bad, [R_PARSE] if bad else [], _strongest(modes))
    reasons: list[str] = []
    errors: list[str] = []
    seen_judged = False
    for seg in res.segments:
        judged = policy.is_judged_op(seg) or seg.context.kind != "host"
        if ctx.remaining() <= 0:   # spec §3.8 시간 예산
            if seen_judged or judged:
                reasons.append(R_TIMEOUT)
            break
        findings, targets = policy.assess(seg, ctx)
        # 저장소 config 의 git alias 처럼 명령 모양만으로는 못 알아보는 판정 대상도 조회 결과로 잡는다
        judged = judged or bool(findings) or bool(targets)
        seen_judged |= judged
        reasons += [f.reason() for f in findings]
        if judged:
            if seg.context.kind == "host":
                modes.append(switch_mode(seg.cwd, environ))
            modes += [switch_mode(t, environ) for t in targets]
        try:
            _record(seg, ctx)
        except Exception as e:  # noqa: BLE001 — 장부 기록은 부가 작업, 실패해도 판정은 유지
            errors.append(f"장부 기록 실패: {type(e).__name__}: {e}")
    return Decision(not reasons, _cap(reasons), _strongest(modes), "; ".join(errors) or None)


def render(d: Decision) -> str:
    out: dict = {"hookEventName": "PreToolUse", "permissionDecision": "allow" if d.allow else "deny"}
    if not d.allow:
        out["permissionDecisionReason"] = "[bash-guard] " + "\n".join([*d.reasons, FOOTER])
    # ensure_ascii: 명령에 든 짝 없는 surrogate 도 \uXXXX 로 표현돼 출력 인코딩이 실패하지 않는다
    return json.dumps({"hookSpecificOutput": out})


# 인코딩까지 실패할 때의 마지막 보루(ASCII 고정 바이트) — on 모드는 이것으로라도 allow/deny 를 낸다
_SAFE = {ok: render(Decision(ok, [R_ERROR], "on")).encode("ascii") for ok in (True, False)}


def final_output(d: Decision, old: str) -> str:
    return render(d) if d.mode == "on" else old


# ---- 기록 (spec §3.9) ----

def log_event(record: dict, environ: Mapping[str, str], max_bytes: int = LOG_MAX_BYTES) -> None:
    d = state_dir(environ)
    if not d.is_absolute():
        return
    d.mkdir(parents=True, exist_ok=True)
    p = d / "bash-guard.jsonl"
    line = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8", "surrogateescape")
    # 순환(.1 교체)과 추가를 같은 잠금 안에서 — 다른 세션의 줄이 교체 사이에 사라지지 않게
    lock = os.open(d / "bash-guard.jsonl.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            if p.stat().st_size > max_bytes:
                os.replace(p, p.with_name(p.name + ".1"))
        except FileNotFoundError:
            pass
        fd = os.open(p, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.fchmod(fd, 0o600)   # 이전 버전이 0644 로 만든 파일도 맞춘다
            os.write(fd, line)
        finally:
            os.close(fd)
    finally:
        os.close(lock)


def _old_decision(old: str) -> str | None:
    try:
        v = json.loads(old)["hookSpecificOutput"]["permissionDecision"]
    except (ValueError, TypeError, KeyError):
        return None
    return v if isinstance(v, str) else None


def _fallback(payload: object, environ: Mapping[str, str], raw: str = "") -> Decision:
    """spec §3.8 (다): 내부 예외 — on 이면 (가) 규칙을 원문에 적용(ask 금지), 그 외 모드는 OLD.

    raw: stdin 원문(깨진 바이트는 대체 문자). 명령을 못 꺼냈어도 원문이 있으면 그 원문에 (가) 규칙을 적용한다."""
    try:
        cwd = payload.get("cwd") if isinstance(payload, dict) else None
        mode = _strongest([_env_mode(environ), switch_mode(cwd if isinstance(cwd, str) else None, environ)])
    except Exception:  # noqa: BLE001 — 폴백 모드 계산 실패는 off(spec §3.8 (다))
        mode = "off"
    ti = payload.get("tool_input") if isinstance(payload, dict) else None
    command = ti.get("command") if isinstance(ti, dict) else None
    text = command if isinstance(command, str) else raw
    bad = FAIL_WORDS.search(text) is not None
    return Decision(not bad, [R_ERROR] if bad else [], mode)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    old = args[args.index("--old") + 1] if "--old" in args[:-1] else ""
    environ = os.environ
    out = old
    try:
        t0 = time.monotonic()
        payload: object = None
        raw = b""
        try:
            raw = sys.stdin.buffer.read()   # 바이트로 — 텍스트 인코딩(ascii 등)에 판정이 좌우되지 않게
            payload = json.loads(raw)
            d = judge(payload, environ)  # type: ignore[arg-type]
        except Exception as e:  # noqa: BLE001 — 판정기 내부 예외는 모두 폴백(spec §3.8 (다))
            d = _fallback(payload, environ, raw.decode("utf-8", "replace"))
            d.error = f"{type(e).__name__}: {e}"
        out = final_output(d, old)
        if not _emit(out, _SAFE[d.allow] if d.mode == "on" else None):
            d.error = "; ".join(filter(None, [d.error, "출력 실패"]))
        out = ""
        old_dec = _old_decision(old)
        old_allow = old_dec not in ("ask", "deny")
        if d.error or (d.mode == "on" and not d.allow) or (d.mode == "shadow" and d.allow != old_allow):
            p = payload if isinstance(payload, dict) else {}
            ti = p.get("tool_input")
            command = ti.get("command") if isinstance(ti, dict) else None
            try:
                log_event({"ts": datetime.now(timezone.utc).isoformat(), "mode": d.mode, "session_id": p.get("session_id"),
                           "agent_id": p.get("agent_id"), "cwd": p.get("cwd"),
                           "command": command[:2000] if isinstance(command, str) else None,
                           "decision": "allow" if d.allow else "deny", "old_decision": old_dec, "reasons": d.reasons,
                           "ms": round((time.monotonic() - t0) * 1000, 1), "error": d.error}, environ)
            except Exception:  # noqa: BLE001, S110 — 기록 실패가 판정 출력을 막으면 안 된다
                pass
    except Exception:  # noqa: BLE001 — 폴백 자체가 실패하면 입구가 OLD 를 내는 것과 같게
        _emit(out)
    return 0


def _emit(out: str, safe: bytes | None = None) -> bool:
    """fd 1 에 바이트로 직접 쓴다 — stdout 인코딩과 무관하고(OLD 의 surrogateescape 바이트도 그대로),
    sys.stdout 버퍼를 거치지 않아 쓰기 실패 뒤 종료 시 다시 flush 하다 rc 120 이 되는 일이 없다."""
    if not out:
        return True
    try:
        data = os.fsencode(out) + b"\n"   # OLD 경로: argv 의 surrogateescape 바이트를 그대로 되돌린다
    except UnicodeError:
        if safe is None:
            return False
        data = safe + b"\n"
    try:
        while data:
            data = data[os.write(1, data):]
    except OSError:
        return False
    return True


if __name__ == "__main__":
    sys.exit(main())
