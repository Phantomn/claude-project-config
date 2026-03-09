from __future__ import annotations

import json
from pathlib import Path

from .models import CheckResult, ResultCode, RunSession


def _result_to_dict(r: CheckResult) -> dict:
    return {
        "id": r.meta.script_id,
        "code": r.code.name,
        "value": r.parsed_value,
        "elapsed_sec": r.elapsed_sec,
        "output": r.raw_output,
        "error": r.error_message,
    }


def write_json(session: RunSession, out_dir: Path) -> Path:
    counts: dict[str, int] = {"pass": 0, "fail": 0, "error": 0, "timeout": 0}
    for r in session.results:
        if r.code == ResultCode.PASS:
            counts["pass"] += 1
        elif r.code == ResultCode.FAIL:
            counts["fail"] += 1
        elif r.code == ResultCode.TIMEOUT:
            counts["timeout"] += 1
        else:
            counts["error"] += 1

    payload = {
        "session": {
            "started_at": session.started_at.isoformat(timespec="seconds"),
            "os_kind": session.os_kind,
            "hostname": session.hostname,
            "preflight_warnings": session.preflight_warnings,
        },
        "summary": counts,
        "items": [_result_to_dict(r) for r in session.results],
    }

    filename = session.started_at.strftime("%Y%m%d_%H%M%S") + ".json"
    out_path = out_dir / filename
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path
