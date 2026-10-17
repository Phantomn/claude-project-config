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

# policy·shell_parse·target_class·ledger(와 dataclasses)는 판정이 필요할 때만 import — 이 훅은 모든 Bash 호출에 돈다
from guard_mode import MODE_RANK, switch_mode

TYPE_CHECKING = False   # typing import(약 3ms)도 피한다 — 타입 검사기는 이 이름을 typing.TYPE_CHECKING 처럼 다룬다
if TYPE_CHECKING:
    from shell_parse import Segment
    from target_class import Ctx

BUDGET_SECONDS = 5.0
LOG_MAX_BYTES = 10 * 1024 * 1024
FOOTER = "이 판정을 우회하지 말 것. 대안이 맞지 않으면 작업을 멈추고 사용자에게 보고하라."
FAIL_WORDS = re.compile(r"(?<![\w.-])(?:rm|unlink|shred|truncate|dd|mkfs[\w.]*|reset|clean|restore|checkout|push|volume|prune|-delete)(?![\w.-])|>")
REASON_CAP = 20
R_PARSE = "거부: 명령을 해석하지 못했다. 단순한 형태로 나눠 실행하라"
R_TIMEOUT = "거부: 판정 시간 초과 — 범위를 좁혀라"
R_MODEL = "거부: 해석 한계 — 모델링할 수 없는 구문(함수 재귀·재정의·갈래 정의·source/eval 정의·break 모양·env -S·상한 초과). 대안: 단순한 형태로 나눠 실행하라"
R_ERROR = "판정기 오류 — 단순한 형태로 나눠 실행하라"
R_DYNAMIC = "거부: 코드를 정적으로 알 수 없다(변수·치환으로 만든 셸 코드) — 리터럴로 쓰거나 스크립트 파일로 실행하라"
# 해석 오류·판정 대상·장부 기록이 생길 수 없는 모양: 판정 처리기·래퍼·제자리 수정이 없는 명령(git 은 표 밖 내장 하위명령)과
# 확장·인용·리다이렉트·그룹이 없는 단어, 단순 연결자만. 판정 결과는 기본 모드의 허용과 같다(tests/test_bash_guard_fast.py 가 대조)
_W = r"[A-Za-z0-9_./,:=+@%~-]+"
# git 은 값이 든 옵션(`--output=F`·`--format=…`)과 `--output` 접두(공백 값 형태)를 빠른 길에서 뺀다 — 파일을 쓰는 옵션이 있다
_GIT_W = rf"(?!-[A-Za-z0-9_./,:+@%~-]*=)(?!--(?:o|ou|out|outp|outpu|output)(?![A-Za-z0-9_./,:=+@%~-])){_W}"
_SAFE_UNIT = rf"(?:(?:ls|pwd|cd|echo|cat|head|tail|wc|grep)(?: +{_W})*|git (?:status|log|diff|show)(?: +{_GIT_W})*)"
_TRIVIAL = re.compile(rf" *{_SAFE_UNIT} *(?:(?:&&|\|\||[|;]) *{_SAFE_UNIT} *)*")


class Decision:
    # dataclass 가 아니다 — dataclasses import(inspect 포함 약 11ms)를 빠른 길에서 피한다
    def __init__(self, allow: bool, reasons: list[str], mode: str, error: str | None = None) -> None:
        self.allow = allow
        self.reasons = reasons
        self.mode = mode             # 이 명령의 모드
        self.error = error


def _env_mode(environ: Mapping[str, str]) -> str:
    v = environ.get("HARNESS_BASH_GUARD", "off")
    return v if v in MODE_RANK else "off"


def _strongest(modes: list[str]) -> str:
    return max(modes, key=MODE_RANK.__getitem__, default="off")


# ---- 장부 기록 (spec §3.7 기록 주체 2) ----

def _note_moves(seg: Segment, ctx: Ctx) -> None:
    import policy
    from ledger import KIND_MOVED_IN
    from target_class import (
        GIT_TRACKED,
        PRESERVED,
        PROTECTED_NAME,
        UNRESOLVED,
        classify,
        git_dirty,
        is_session_change,
        normalize,
    )

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
    import policy
    from ledger import KIND_CREATED
    from target_class import normalize, note_touch

    if seg.context.kind != "host" or seg.via_xargs:
        return   # shortcut: 컨테이너 안 제자리 수정·mv 는 기록하지 않는다 — 바인드 마운트 대상 오분류가 나오면 호스트 경로로 사상해 기록
    for p in policy.inplace_targets(seg):
        note_touch(p, ctx, None)
    # 생성 기록 — birth 를 못 읽는 파일 시스템의 증거. 거부·실패한 명령의 기록은 그 경로를 남이 만들면 세션 것으로 보이게 한다(LIMITS)
    for p in policy.created_targets(seg):
        ctx.ledger.record(normalize(p, False), KIND_CREATED, ctx.session_id)
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
    if _TRIVIAL.fullmatch(command):
        return Decision(True, [], _strongest(modes))
    import policy
    from shell_parse import parse
    from target_class import make_ctx

    ctx = make_ctx(payload, environ, budget)
    res = parse(command, cwd, environ, deadline=ctx.deadline)
    if res.error:   # spec §3.8 (가)
        if ctx.remaining() <= 0:   # 마감이 지나 해석을 멈춘 것 — 위험 단어와 무관하게 fail-closed
            return Decision(False, [R_TIMEOUT], _strongest(modes))
        if res.unmodeled:   # bash 는 돌리는데 해석기가 모델링 못 하는 구문 — 위험 단어와 무관하게 fail-closed(구문 오류와 구분)
            return Decision(False, [R_DYNAMIC if res.dynamic else R_MODEL], _strongest(modes))
        bad = FAIL_WORDS.search(command) is not None
        return Decision(not bad, [R_PARSE] if bad else [], _strongest(modes))
    reasons: list[str] = []
    errors: list[str] = []
    seen_judged = False
    for i, seg in enumerate(res.segments):
        judged = policy.is_judged_op(seg) or seg.context.kind != "host"
        if ctx.remaining() <= 0:   # spec §3.8 시간 예산 — 끊긴 자리 뒤에 남은 판정 대상도 '만난' 것으로 본다
            if seen_judged or any(policy.is_judged_op(s) or s.context.kind != "host" for s in res.segments[i:]):
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
    from ledger import LOCK_WAIT, lock_file, state_dir

    d = state_dir(environ)
    if not d.is_absolute():
        return
    d.mkdir(parents=True, exist_ok=True)
    p = d / "bash-guard.jsonl"
    # 짝 없는 surrogate(명령 JSON 의 \udXXX)는 `\udXXX` 글자로 — JSON 문자열 안이라 읽으면 원문 그대로, 파일은 유효한 UTF-8
    line = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8", "backslashreplace")
    # 순환(.1 교체)과 추가를 같은 잠금 안에서 — 다른 세션의 줄이 교체 사이에 사라지지 않게. 잠금은 장부와 같은 상한 있는
    # 비차단 헬퍼(최종 리뷰 I1 — 무한 대기는 deny 를 낸 뒤 훅을 timeout 으로 취소시켰다)
    lock = lock_file(d / "bash-guard.jsonl.lock", time.monotonic() + LOCK_WAIT)
    # 못 잠그면(None) 순환은 건너뛰고 한 줄만 추가 — O_APPEND 의 write 한 번은 리눅스 로컬 FS 에서 다른 쓰기와 섞이지 않는다
    # (VFS 가 쓰기 동안 inode 잠금을 쥔다; 순환의 rename 과 겹치면 이 줄은 .1 쪽에 남는다)
    try:
        if lock is not None:
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
        if lock is not None:
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
        fallback = False
        old_dec = _old_decision(old)
        try:
            raw = sys.stdin.buffer.read()   # 바이트로 — 텍스트 인코딩(ascii 등)에 판정이 좌우되지 않게
            payload = json.loads(raw)
            d = judge(payload, environ)  # type: ignore[arg-type]
        except Exception as e:  # noqa: BLE001 — 판정기 내부 예외는 모두 폴백(spec §3.8 (다))
            d = _fallback(payload, environ, raw.decode("utf-8", "replace"))
            d.error = f"{type(e).__name__}: {e}"
            fallback = True
            # 폴백 = OLD 결과와 위험 단어의 합집합 거부(둘 다 허용일 때만 허용) — 예외가 OLD 수준 보호를 깎지 않게(최종 리뷰 I3)
            if d.allow and old_dec in ("ask", "deny"):
                d.allow, d.reasons = False, [R_ERROR]
        out = final_output(d, old)
        if not _emit(out, _SAFE[d.allow] if d.mode == "on" else None):
            d.error = "; ".join(filter(None, [d.error, "출력 실패"]))
        out = ""
        old_allow = old_dec not in ("ask", "deny")
        if d.error or (d.mode == "on" and not d.allow) or (d.mode == "shadow" and d.allow != old_allow):
            p = payload if isinstance(payload, dict) else {}
            ti = p.get("tool_input")
            command = ti.get("command") if isinstance(ti, dict) else None
            try:
                from datetime import datetime, timezone

                log_event({"ts": datetime.now(timezone.utc).isoformat(), "mode": d.mode, "session_id": p.get("session_id"),
                           "agent_id": p.get("agent_id"), "cwd": p.get("cwd"),
                           "command": command[:2000] if isinstance(command, str) else None,
                           "decision": "allow" if d.allow else "deny", "old_decision": old_dec, "reasons": d.reasons,
                           "ms": round((time.monotonic() - t0) * 1000, 1), "error": d.error, "fallback": fallback}, environ)
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
