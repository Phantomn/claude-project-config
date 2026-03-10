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

echo "[1.5/3] 한글 폰트 획득"
mkdir -p runner/fonts
if [ ! -f "runner/fonts/NotoSansKR.ttf" ]; then
    FONT_PATH=""
    if command -v fc-list >/dev/null 2>&1; then
        # NotoSansKR Regular 우선 탐색 (grep 실패 시 빈 값 유지)
        FONT_PATH=$(fc-list :lang=ko | grep -i 'NotoSansKR.*Regular' | grep -i '\.ttf' | head -1 | cut -d: -f1 | tr -d ' ' || true)
        if [ -z "$FONT_PATH" ]; then
            # 임의 한글 TTF 폴백
            FONT_PATH=$(fc-list :lang=ko | grep -i '\.ttf' | head -1 | cut -d: -f1 | tr -d ' ' || true)
        fi
    fi

    if [ -n "$FONT_PATH" ] && [ -f "$FONT_PATH" ]; then
        echo "  시스템 폰트 복사: $FONT_PATH"
        cp "$FONT_PATH" runner/fonts/NotoSansKR.ttf
    else
        echo "  시스템 한글 폰트 없음 → NotoSansKR 다운로드 중..."
        python3 -c "
import urllib.request, sys
url = 'https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansKR/NotoSansKR-Regular.ttf'
try:
    urllib.request.urlretrieve(url, 'runner/fonts/NotoSansKR.ttf')
    print('  다운로드 완료')
except Exception as e:
    print(f'  오류: {e}', file=sys.stderr)
    sys.exit(1)"
    fi
fi
echo "  폰트: runner/fonts/NotoSansKR.ttf ($(du -sh runner/fonts/NotoSansKR.ttf | cut -f1))"

echo "[2/3] PyInstaller 빌드"
# LD_LIBRARY_PATH 우선순위로 시스템 Python 공유 라이브러리 선택
# (비표준 위치 /usr/local/lib 에 _struct 없는 라이브러리 존재 시 오동작 방지)
_SYS_LIB_DIR=""
for _d in /lib/x86_64-linux-gnu /lib64 /usr/lib/x86_64-linux-gnu /usr/lib64; do
    if [ -f "${_d}/libpython3.12.so.1.0" ]; then
        _SYS_LIB_DIR="$_d"
        break
    fi
done
if [ -n "$_SYS_LIB_DIR" ]; then
    echo "  시스템 Python 라이브러리 우선: $_SYS_LIB_DIR"
    export LD_LIBRARY_PATH="${_SYS_LIB_DIR}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
fi
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
