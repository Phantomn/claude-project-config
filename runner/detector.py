from __future__ import annotations

import platform
import sys

from .models import OSKind


def detect_os_kind() -> str:
    system = platform.system()
    if system == "Linux":
        return OSKind.LINUX
    elif system == "Windows":
        import winreg  # type: ignore[import]
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
        )
        name, _ = winreg.QueryValueEx(key, "ProductName")
        winreg.CloseKey(key)
        return OSKind.WINDOWS_SERVER if "Server" in name else OSKind.WINDOWS
    raise RuntimeError(f"지원하지 않는 OS: {system}")


def _is_admin() -> bool:
    system = platform.system()
    if system == "Linux":
        import os
        return os.geteuid() == 0
    elif system == "Windows":
        import ctypes
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
        except AttributeError:
            return False
    return False


def run_preflight(os_kind: str) -> list[str]:
    """Preflight 점검. 관리자 권한 없으면 즉시 종료. 나머지는 경고 반환."""
    warnings: list[str] = []

    if not _is_admin():
        print("[오류] 관리자(root/Administrator) 권한으로 실행해야 합니다.")
        sys.exit(1)

    if os_kind == OSKind.LINUX:
        import subprocess
        try:
            result = subprocess.run(
                ["getenforce"],
                capture_output=True, text=True, timeout=5
            )
            if result.stdout.strip() == "Enforcing":
                warnings.append(
                    "SELinux가 Enforcing 모드입니다. 일부 점검 항목이 ERROR로 기록될 수 있습니다."
                )
        except FileNotFoundError:
            pass  # SELinux 미설치 환경
        except Exception:
            pass

    elif os_kind in (OSKind.WINDOWS_SERVER, OSKind.WINDOWS):
        import subprocess
        try:
            result = subprocess.run(
                ["powershell.exe", "-NonInteractive", "-Command",
                 "Get-ExecutionPolicy"],
                capture_output=True, text=True, timeout=10
            )
            policy = result.stdout.strip()
            if policy == "Restricted":
                warnings.append(
                    f"PowerShell ExecutionPolicy가 Restricted입니다 (현재: {policy}). "
                    "스크립트 실행 시 -ExecutionPolicy Bypass 플래그로 우회합니다."
                )
        except Exception:
            pass

    return warnings
