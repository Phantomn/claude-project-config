from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

from .credentials import LinuxCredentials, WindowsCredentials
from .models import CheckResult, OSKind, ResultCode, ScriptMeta

TIMEOUT_MAP: dict[str, int] = {
    # secedit 기반 항목 (60s)
    "W-04": 60, "W-05": 60, "W-15": 60, "W-16": 60,
    "W-40": 60, "W-46": 60, "W-47": 60, "W-48": 60,
    "W-49": 60, "W-50": 60, "W-51": 60, "W-54": 60, "W-55": 60,
    # Win32_Product WMI (120s)
    "PC-08": 120,
    # find / 전체 탐색 (180s)
    "U-06": 180, "U-13": 180, "U-15": 180, "U-58": 180,
}
DEFAULT_TIMEOUT = 30


def build_script_meta(script_path: Path, os_kind: str) -> ScriptMeta:
    script_id = script_path.stem  # "U-01", "W-04", "PC-08"
    timeout = TIMEOUT_MAP.get(script_id, DEFAULT_TIMEOUT)
    return ScriptMeta(
        script_id=script_id,
        path=script_path,
        os_kind=os_kind,
        timeout=timeout,
    )


def _parse_result_line(output: str) -> int | None:
    """마지막 '점검 결과: N' 줄에서 N을 추출."""
    idx = output.rfind("점검 결과:")
    if idx == -1:
        return None
    m = re.search(r"점검\s*결과:\s*(\d+)", output[idx:])
    return int(m.group(1)) if m else None


def _decode_output(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp949", errors="replace")


def run_script(
    meta: ScriptMeta,
    creds: LinuxCredentials | WindowsCredentials,
) -> CheckResult:
    start = time.monotonic()
    raw_output = ""
    error_message = ""

    try:
        if meta.os_kind == OSKind.LINUX:
            assert isinstance(creds, LinuxCredentials)
            proc = subprocess.run(
                ["sudo", "-S", "bash", str(meta.path)],
                input=f"{creds.sudo_password}\n",
                capture_output=True,
                timeout=meta.timeout,
                text=True,
            )
            raw_output = proc.stdout + proc.stderr
            if proc.returncode != 0 and not raw_output.strip():
                error_message = f"exit code {proc.returncode}"
        else:
            # Windows: 현재 프로세스 컨텍스트로 실행 (관리자로 시작 필요)
            proc = subprocess.run(
                [
                    "powershell.exe",
                    "-ExecutionPolicy", "Bypass",
                    "-NonInteractive",
                    "-File", str(meta.path),
                ],
                capture_output=True,
                timeout=meta.timeout,
            )
            raw_output = _decode_output(proc.stdout + proc.stderr)
            if proc.returncode != 0 and not raw_output.strip():
                error_message = f"exit code {proc.returncode}"

    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        return CheckResult(
            meta=meta,
            code=ResultCode.TIMEOUT,
            raw_output="",
            parsed_value=-1,
            error_message=f"타임아웃 ({meta.timeout}s)",
            elapsed_sec=round(elapsed, 2),
        )
    except Exception as exc:
        elapsed = time.monotonic() - start
        return CheckResult(
            meta=meta,
            code=ResultCode.ERROR,
            raw_output="",
            parsed_value=-1,
            error_message=str(exc),
            elapsed_sec=round(elapsed, 2),
        )

    elapsed = time.monotonic() - start
    parsed = _parse_result_line(raw_output)

    if parsed is None:
        return CheckResult(
            meta=meta,
            code=ResultCode.ERROR,
            raw_output=raw_output,
            parsed_value=-1,
            error_message=error_message or "'점검 결과:' 줄을 찾을 수 없음",
            elapsed_sec=round(elapsed, 2),
        )

    code = ResultCode.PASS if parsed == 0 else ResultCode.FAIL
    return CheckResult(
        meta=meta,
        code=code,
        raw_output=raw_output,
        parsed_value=parsed,
        error_message=error_message,
        elapsed_sec=round(elapsed, 2),
    )
