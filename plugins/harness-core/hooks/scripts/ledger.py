"""bash-guard 공유 장부: 모든 세션이 함께 쓰는 ledger.tsv (spec §3.7).

행 = `<realpath>\\t<kind>\\t<session_id>\\t<epoch>`.
"""
from __future__ import annotations

import fcntl
import os
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

KIND_PRE_SESSION = "pre-session"
KIND_PRE_DIRTY = "pre-dirty"
KIND_CREATED = "created"
KIND_TOUCHED = "touched"
KIND_MOVED_IN = "moved-in"
PRUNE_SECONDS = 7 * 24 * 3600
COMPACT_BYTES = 5 * 1024 * 1024

_ENC = {"encoding": "utf-8", "errors": "surrogateescape"}


@dataclass(frozen=True)
class Entry:
    kind: str
    session_id: str
    ts: float


def state_dir(environ: Mapping[str, str]) -> Path:
    # XDG 규약: 상대 경로 XDG_STATE_HOME 은 무시. HOME 도 없으면 상대 경로가 되고, Ledger 가 그때 기록을 생략한다
    xdg = environ.get("XDG_STATE_HOME", "")
    base = xdg if os.path.isabs(xdg) else os.path.join(environ.get("HOME", ""), ".local", "state")
    return Path(base) / "harness-core"


def _parse(line: str) -> tuple[str, Entry] | None:
    # rsplit: 경로에 탭이 있어도 뒤 3칸은 고정이라 안전
    parts = line.rsplit("\t", 3)
    if len(parts) != 4:
        return None
    try:
        return parts[0], Entry(parts[1], parts[2], float(parts[3]))
    except ValueError:
        return None


class Ledger:
    def __init__(self, environ: Mapping[str, str], compact_bytes: int = COMPACT_BYTES) -> None:
        d = state_dir(environ)
        # 상대 경로 장부는 훅 cwd 마다 다른 파일이 되어 공유 장부가 아니다 — 만들지 않는다
        self.path: Path | None = d / "ledger.tsv" if d.is_absolute() else None
        self.compact_bytes = compact_bytes

    def _read(self) -> str:
        if self.path is None:
            return ""
        try:
            return self.path.read_text(**_ENC)
        except FileNotFoundError:
            return ""

    def _rows(self, text: str) -> list[tuple[str, Entry]]:
        return [r for r in map(_parse, text.splitlines()) if r]

    def entries(self, path: str) -> list[Entry]:
        return self.entries_for([path]).get(path, [])

    def entries_for(self, paths: Iterable[str] | None = None) -> dict[str, list[Entry]]:
        """장부를 한 번 읽어 경로별 기록을 모은다. paths 가 None 이면 전부."""
        # 압축은 rename 으로 갈아끼우므로 잠금 없이 읽어도 온전한 파일 하나를 본다
        wanted = None if paths is None else set(paths)
        out: dict[str, list[Entry]] = {}
        for p, e in self._rows(self._read()):
            if wanted is None or p in wanted:
                out.setdefault(p, []).append(e)
        return out

    def moved_in_near(self, path: str) -> str | None:
        base = path.rstrip("/") + "/"
        for p, e in self._rows(self._read()):
            if e.kind == KIND_MOVED_IN and (p == path or path.startswith(p.rstrip("/") + "/") or p.startswith(base)):
                return p
        return None

    def _lock(self) -> int:
        # 압축이 파일을 rename 으로 바꾸므로, 잠근 뒤 그 inode 가 아직 현재 파일인지 확인한다
        while True:
            fd = os.open(self.path, os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                if os.fstat(fd).st_ino == os.stat(self.path).st_ino:
                    return fd
            except FileNotFoundError:
                pass
            os.close(fd)

    def record(self, path: str, kind: str, session_id: str | None) -> None:
        if session_id is None or self.path is None:
            return
        # shortcut: 줄바꿈이 든 경로·세션은 한 줄 형식에 담을 수 없어 기록하지 않는다 — 그런 경로를 다룰 일이 생기면 이스케이프 형식으로
        if "\n" in path or "\t" in kind + session_id or "\n" in kind + session_id:
            return
        line = f"{path}\t{kind}\t{session_id}\t{time.time():.6f}\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = self._lock()
        try:
            text = self._read()
            if kind != KIND_TOUCHED and any(p == path and e.kind == kind and e.session_id == session_id
                                            for p, e in self._rows(text)):
                return
            if os.fstat(fd).st_size <= self.compact_bytes:
                os.write(fd, line.encode(**_ENC))
                return
            now = time.time()
            kept = [ln + "\n" for ln in text.splitlines() if _keep(ln, now)]
            tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
            tfd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(tfd, "w", **_ENC) as f:
                f.write("".join(kept) + line)
            os.replace(tmp, self.path)
        finally:
            os.close(fd)


def _keep(line: str, now: float) -> bool:
    r = _parse(line)
    if r is None:
        return False
    p, e = r
    # moved-in 은 보호 근거라 기간으로 빼지 않는다 (spec §3.7, 재감사 rootcause-r1-s1-005)
    if e.kind == KIND_MOVED_IN:
        return os.path.lexists(p)
    return now - e.ts <= PRUNE_SECONDS
