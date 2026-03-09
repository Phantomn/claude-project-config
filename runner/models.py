from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from pathlib import Path


class ResultCode(IntEnum):
    PASS = 0
    FAIL = 1      # result_code >= 1
    ERROR = -1    # 파싱 실패 / 비정상 종료
    TIMEOUT = -2


class OSKind:
    LINUX = "linux"
    WINDOWS_SERVER = "windows_server"
    WINDOWS = "windows"


@dataclass(frozen=True)
class ScriptMeta:
    script_id: str       # "U-01", "W-04", "PC-08"
    path: Path
    os_kind: str
    timeout: int         # 30 / 60 / 120 / 180


@dataclass
class CheckResult:
    meta: ScriptMeta
    code: ResultCode
    raw_output: str
    parsed_value: int    # "점검 결과: N"의 N (-1이면 파싱 불가)
    error_message: str = ""
    elapsed_sec: float = 0.0


@dataclass
class RunSession:
    started_at: datetime
    os_kind: str
    hostname: str
    results: list[CheckResult] = field(default_factory=list)
    preflight_warnings: list[str] = field(default_factory=list)
