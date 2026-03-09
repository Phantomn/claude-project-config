from __future__ import annotations

import getpass
from dataclasses import dataclass

from .models import OSKind


@dataclass(frozen=True)
class LinuxCredentials:
    sudo_password: str


@dataclass(frozen=True)
class WindowsCredentials:
    username: str
    password: str


def collect_credentials(os_kind: str) -> LinuxCredentials | WindowsCredentials:
    """대화형으로 자격증명 수집. 비밀번호는 echo 없이 입력."""
    if os_kind == OSKind.LINUX:
        pw = getpass.getpass("sudo 비밀번호: ")
        return LinuxCredentials(sudo_password=pw)
    else:
        user = input("관리자 계정 (도메인\\사용자 또는 로컬 계정명): ").strip()
        pw = getpass.getpass("비밀번호: ")
        return WindowsCredentials(username=user, password=pw)
