#!/usr/bin/env bash
# build.sh - Linux용 os-check 단일 바이너리 빌드
# 실행: bash build/build.sh (프로젝트 루트에서)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="${SCRIPT_DIR}/.venv"
cd "$ROOT_DIR"

echo "=== os-check Linux 빌드 ==="

echo "[1/3] 빌드 의존성 설치"
if [ ! -f "${VENV_DIR}/bin/pip" ]; then
    echo "  venv 생성: $VENV_DIR"
    python3 -m venv "$VENV_DIR"
    # 일부 환경에서 venv에 pip이 포함되지 않는 경우 ensurepip으로 설치
    if [ ! -f "${VENV_DIR}/bin/pip" ]; then
        "${VENV_DIR}/bin/python" -m ensurepip --upgrade
    fi
fi
"${VENV_DIR}/bin/pip" install --quiet --upgrade pip
"${VENV_DIR}/bin/pip" install --quiet pyinstaller
"${VENV_DIR}/bin/pip" install --quiet -r runner/requirements.txt

echo "[2/3] PyInstaller 빌드"
"${VENV_DIR}/bin/pyinstaller" build/os-check.spec \
    --distpath build/dist \
    --workpath build/work \
    --noconfirm

echo "[3/3] 완료"
echo ""
echo "바이너리: build/dist/os-check"
echo ""
echo "배포 방법:"
echo "  타겟 서버에 다음 두 가지를 복사:"
echo "    1) build/dist/os-check  (실행 파일)"
echo "    2) scripts/linux/       (점검 스크립트 디렉토리)"
echo ""
echo "  실행 (타겟 서버에서):"
echo "    mkdir -p scripts/linux"
echo "    sudo ./os-check"
