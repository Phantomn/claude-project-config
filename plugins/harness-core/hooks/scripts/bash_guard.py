#!/usr/bin/env python3
"""bash-guard 진입점: Bash 명령을 판정하고 모드(off/shadow/on)에 따라 새 판정 또는 기존 판정(OLD)을 낸다 (spec §3.1·§3.2·§3.7·§3.8·§3.9).

사용: bash_guard.py --old <기존 판정 JSON>   (stdin = PreToolUse payload). 종료 코드는 항상 0.
"""
from __future__ import annotations

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
from shell_parse import Segment, Word, expand, parse
from target_class import (
    GIT_TRACKED,
    MODE_RANK,
    PRESERVED,
    PROTECTED_NAME,
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

def _sed_perl_files(seg: Segment) -> list[Word]:
    """`sed -i|--in-place`·`perl -i|-pi` 의 파일 인자. 제자리 수정이 아니면 []."""
    perl = seg.name == "perl"
    a, i, inplace, script, ops = seg.argv[1:], 0, False, False, []
    while i < len(a):
        s = a[i].literal()
        i += 1
        if s == "--":
            ops += a[i:]
            break
        if not s.startswith("-") or s == "-":
            if perl:   # perl 은 첫 비옵션에서 옵션이 끝난다
                ops += a[i - 1:]
                break
            ops.append(a[i - 1])
        elif s.startswith("--"):
            k, eq, _ = s.partition("=")
            inplace |= k == "--in-place"
            if k in ("--expression", "--file"):
                script = True
            if k in ("--expression", "--file", "--line-length") and not eq:
                i += 1
        else:
            for n, c in enumerate(s[1:], 1):
                if c == "i":   # 뒤 글자는 백업 접미사
                    inplace = True
                    break
                if c in ("eE" if perl else "efl"):
                    script = script or c != "l"
                    i += n == len(s) - 1
                    break
                if perl and c in "IMmlx0CdDV":   # 값이 붙어 오는 옵션
                    break
    if not inplace:
        return []
    return ops if script else ops[1:]


def _inplace_targets(seg: Segment) -> list[str]:
    """제자리 수정의 닫힌 목록(리다이렉트·tee·sed -i·perl -i·truncate·cp/mv/install/rsync/dd 목적지·git checkout/restore)."""
    words = [r.target for r in seg.redirects if r.target is not None and r.op in (">", ">|", "&>", ">>", "&>>")]
    out: list[str] = []
    try:
        if seg.name == "tee":
            words += policy._args(seg)[2]
        elif seg.name in ("sed", "perl"):
            words += _sed_perl_files(seg)
        elif seg.name in ("truncate", "cp", "mv", "install", "rsync", "dd"):
            out += [p for j in policy.HANDLERS[seg.name](seg, None) if j.rule == policy.OVERWRITE for p in j.paths or ()]
        elif seg.name == "git":
            out += [os.path.join(j.repo, p) for j in policy._git_handler(seg, None)
                    if j.op in ("git checkout", "git restore") and j.repo for p in j.paths or ()]
    except policy._BadOption:
        pass
    out += [p for w in words for p in expand(w, seg) or ()]
    return [p for p in out if os.path.lexists(p) and not os.path.isdir(p)]


def _mv_moves(seg: Segment) -> list[tuple[str, str]]:
    """mv 의 (원본, 목적지) 쌍. 확정할 수 없으면 생략."""
    try:
        flags, vals, ops = policy._args(seg, policy._COPY_VALUES - {"-m", "-o", "-g"})
    except policy._BadOption:
        return []
    tdir = vals.get("-t") or vals.get("--target-directory")
    force = tdir is not None
    if tdir is None:
        if len(ops) < 2:
            return []
        tdir, ops = ops[-1], ops[:-1]
    dest = expand(tdir, seg)
    if dest is None or len(dest) != 1:
        return []
    srcs = [p for w in ops for p in expand(w, seg) or ()]
    if flags & {"-T", "--no-target-directory"} or not (force or os.path.isdir(dest[0])):
        return [(srcs[0], dest[0])] if len(srcs) == 1 else []
    return [(s, os.path.join(dest[0], os.path.basename(s.rstrip("/")))) for s in srcs]


def _note_moves(seg: Segment, ctx: Ctx) -> None:
    for src, dst in _mv_moves(seg):
        c = classify(src, ctx)
        keep = c.kind in (PRESERVED, PROTECTED_NAME)
        if c.kind == GIT_TRACKED and c.path:
            dirty = git_dirty(c.path if os.path.isdir(c.path) else os.path.dirname(c.path), [c.path], ctx)
            keep = bool(dirty) and not all(is_session_change(d, ctx) for d in dirty)
        if keep:
            ctx.ledger.record(normalize(dst, False), KIND_MOVED_IN, ctx.session_id)


def _record(seg: Segment, ctx: Ctx) -> None:
    if seg.context.kind != "host" or seg.via_xargs:
        return   # shortcut: 컨테이너 안 제자리 수정·mv 는 기록하지 않는다 — 바인드 마운트 대상 오분류가 나오면 호스트 경로로 사상해 기록
    for p in _inplace_targets(seg):
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
    seen_judged = False
    for seg in res.segments:
        judged = policy.is_judged_op(seg) or seg.context.kind != "host"
        if ctx.remaining() <= 0:   # spec §3.8 시간 예산
            if seen_judged or judged:
                reasons.append(R_TIMEOUT)
            break
        seen_judged |= judged
        findings, targets = policy.assess(seg, ctx)
        reasons += [f.reason() for f in findings]
        if judged:
            if seg.context.kind == "host":
                modes.append(switch_mode(seg.cwd, environ))
            modes += [switch_mode(t, environ) for t in targets]
        _record(seg, ctx)
    return Decision(not reasons, _cap(reasons), _strongest(modes))


def render(d: Decision) -> str:
    out: dict = {"hookEventName": "PreToolUse", "permissionDecision": "allow" if d.allow else "deny"}
    if not d.allow:
        out["permissionDecisionReason"] = "\n".join([*(f"[bash-guard] {r}" for r in d.reasons), FOOTER])
    return json.dumps({"hookSpecificOutput": out}, ensure_ascii=False)


def final_output(d: Decision, old: str) -> str:
    return render(d) if d.mode == "on" else old


# ---- 기록 (spec §3.9) ----

def log_event(record: dict, environ: Mapping[str, str], max_bytes: int = LOG_MAX_BYTES) -> None:
    d = state_dir(environ)
    if not d.is_absolute():
        return
    d.mkdir(parents=True, exist_ok=True)
    p = d / "bash-guard.jsonl"
    try:
        if p.stat().st_size > max_bytes:
            os.replace(p, p.with_name(p.name + ".1"))
    except FileNotFoundError:
        pass
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _old_decision(old: str) -> str | None:
    try:
        v = json.loads(old)["hookSpecificOutput"]["permissionDecision"]
    except (ValueError, TypeError, KeyError):
        return None
    return v if isinstance(v, str) else None


def _fallback(payload: object, environ: Mapping[str, str]) -> Decision:
    """spec §3.8 (다): 내부 예외 — on 이면 (가) 규칙을 원문에 적용(ask 금지), 그 외 모드는 OLD."""
    try:
        cwd = payload.get("cwd") if isinstance(payload, dict) else None
        mode = _strongest([_env_mode(environ), switch_mode(cwd if isinstance(cwd, str) else None, environ)])
    except Exception:  # noqa: BLE001 — 폴백 모드 계산 실패는 off(spec §3.8 (다))
        mode = "off"
    ti = payload.get("tool_input") if isinstance(payload, dict) else None
    command = ti.get("command") if isinstance(ti, dict) else None
    bad = isinstance(command, str) and FAIL_WORDS.search(command) is not None
    return Decision(not bad, [R_ERROR] if bad else [], mode)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    old = args[args.index("--old") + 1] if "--old" in args[:-1] else ""
    environ = os.environ
    out = old
    try:
        t0 = time.monotonic()
        payload: object = None
        try:
            payload = json.loads(sys.stdin.read())
            d = judge(payload, environ)  # type: ignore[arg-type]
        except Exception as e:  # noqa: BLE001 — 판정기 내부 예외는 모두 폴백(spec §3.8 (다))
            d = _fallback(payload, environ)
            d.error = f"{type(e).__name__}: {e}"
        out = final_output(d, old)
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
        out = old
    if out:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
