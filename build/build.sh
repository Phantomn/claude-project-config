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

echo "[3/3] 점검 스크립트 배포 디렉토리 구성"
mkdir -p build/dist/scripts
cp -r scripts/linux build/dist/scripts/linux

echo ""
echo "=== 빌드 완료 ==="
echo "배포 패키지: build/dist/"
echo "  os-check          (실행 파일)"
echo "  scripts/linux/    (점검 스크립트 $(find scripts/linux -maxdepth 1 -type f | wc -l)개)"
echo ""
echo "실행 방법:"
echo "  sudo build/dist/os-check"
echo ""
echo "타겟 서버 배포:"
echo "  scp -r build/dist/ user@target:/opt/os-check/"
echo "  ssh user@target 'sudo /opt/os-check/os-check'"
