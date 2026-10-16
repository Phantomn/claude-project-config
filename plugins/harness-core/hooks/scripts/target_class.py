"""bash-guard 대상 분류 기반: 세션 시각·생성 시각·정규화·임시 루트·보호 이름·스위치 값 (spec §3.4, §3.9)."""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass

from ledger import Ledger


@dataclass
class Ctx:
    environ: Mapping[str, str]
    session_id: str | None
    session_start: float | None
    ledger: Ledger
    deadline: float  # time.monotonic() 기준

    def remaining(self) -> float:
        return self.deadline - time.monotonic()


FIXED_SCRATCH_ROOTS: tuple[str, ...] = ("/tmp", "/var/tmp")
WIN_TEMP_PATTERN = "/mnt/c/Users/*/AppData/Local/Temp"
# '*' 를 한 경로 구성요소로만 맞춘다(fnmatch 의 '*' 는 '/' 도 넘어 임의 깊이 폴더까지 임시로 본다)
_WIN_TEMP_RE = re.compile(re.escape(WIN_TEMP_PATTERN).replace(r"\*", "[^/]+"))
MODE_RANK = {"off": 0, "shadow": 1, "on": 2}
_ENV_EXAMPLES = {".env.example", ".env.sample", ".env.template"}
_LOCAL_SUFFIXES = (".local.json", ".local.yaml", ".local.yml", ".local.toml")
_KEY_PREFIXES = ("id_rsa", "id_ed25519", "id_ecdsa", "credentials")
_SECRET_DIRS = {".ssh", ".gnupg", ".aws"}
_TEXT = {"encoding": "utf-8", "errors": "surrogateescape"}


def make_ctx(payload: dict, environ: Mapping[str, str], budget: float) -> Ctx:
    deadline = time.monotonic() + budget
    return Ctx(environ, payload.get("session_id") or None,
               session_start(payload.get("transcript_path"), environ), Ledger(environ), deadline)


def session_start(transcript_path: str | None, environ: Mapping[str, str]) -> float | None:
    if not transcript_path:
        return None
    try:
        r = subprocess.run(["stat", "-c", "%.9W", "--", transcript_path], env=dict(environ),
                           capture_output=True, timeout=2.0, check=False, **_TEXT)
        v = float(r.stdout) if r.returncode == 0 else 0.0
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return v or None


def _parse_stat(stdout: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for line in stdout.splitlines():
        num, sep, name = line.partition(" ")
        try:
            v = float(num)
        except ValueError:
            continue
        if sep and v:
            out[name] = v
    return out


def births(paths: list[str], ctx: Ctx) -> dict[str, float]:
    # 줄바꿈 든 경로는 %n 출력 줄이 갈라져 다른 키로 오인될 수 있어 묻지 않는다(키 없음 = 읽을 수 없음, 보호 쪽)
    asked = [p for p in paths if "\n" not in p]
    if not asked:
        return {}
    r = run(["stat", "-c", "%.9W %n", "--", *asked], ctx)
    if r is None:
        return {}
    wanted = set(asked)
    return {k: v for k, v in _parse_stat(r.stdout).items() if k in wanted}


def run(cmd: list[str], ctx: Ctx, cwd: str | None = None) -> subprocess.CompletedProcess | None:
    left = ctx.remaining()
    if left <= 0:
        return None
    try:
        return subprocess.run(cmd, cwd=cwd, env=dict(ctx.environ), capture_output=True,
                              timeout=min(2.0, left), check=False, **_TEXT)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def normalize(path: str, trailing_slash: bool) -> str:
    p = os.path.normpath(path)
    if p == "/" or trailing_slash:
        return os.path.realpath(p)
    # 대상 자체가 링크면 링크를 본다(rm 은 링크만 지움) — 부모만 해소
    return os.path.join(os.path.realpath(os.path.dirname(p)), os.path.basename(p))


def scratch_roots(ctx: Ctx) -> list[str]:
    roots = list(FIXED_SCRATCH_ROOTS)
    if ctx.environ.get("TMPDIR"):
        roots.append(ctx.environ["TMPDIR"])
    if ctx.environ.get("HOME"):
        roots.append(os.path.join(ctx.environ["HOME"], ".cache"))
    roots.append("/mnt/c/Windows/Temp")
    # 대상 경로가 realpath 로 정규화되므로 루트도 같은 형태로
    return list(dict.fromkeys(os.path.realpath(r) for r in roots))


def is_scratch(path: str, ctx: Ctx) -> bool:
    m = _WIN_TEMP_RE.match(path)
    if m and len(path) > m.end() + 1 and path[m.end()] == "/":
        return True
    return any(r != "/" and path.startswith(r + "/") for r in scratch_roots(ctx))


def is_scratch_root(path: str, ctx: Ctx) -> bool:
    return path in scratch_roots(ctx) or _WIN_TEMP_RE.fullmatch(path) is not None


def protected_name(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    if ".git" in parts or _SECRET_DIRS.intersection(parts):
        return True
    if name == ".env" or (name.startswith(".env.") and name not in _ENV_EXAMPLES):
        return True
    return (name.endswith(_LOCAL_SUFFIXES) or name.endswith((".pem", ".key"))
            or name.startswith(_KEY_PREFIXES) or name == ".netrc")


def repo_root(path: str, environ: Mapping[str, str]) -> str | None:
    p = os.path.normpath(path)
    while True:
        if os.path.lexists(os.path.join(p, ".git")):
            break
        if p == "/":
            return None
        p = os.path.dirname(p)
    home = environ.get("HOME")
    if p == "/" or (home and os.path.realpath(home) == os.path.realpath(p)):
        return None
    return p


def switch_mode(path: str | None, environ: Mapping[str, str]) -> str:
    root = repo_root(path, environ) if path else None
    if root is None:
        return "off"
    for name in ("settings.local.json", "settings.json"):
        try:
            with open(os.path.join(root, ".claude", name), encoding="utf-8") as f:
                env = json.load(f).get("env")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(env, dict) and "HARNESS_BASH_GUARD" in env:
            v = env["HARNESS_BASH_GUARD"]
            return v if isinstance(v, str) and v in MODE_RANK else "off"
    return "off"
