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

    # 1) fc-list 탐색 (한글 TTF 우선, fontconfig 없으면 건너뜀)
    if command -v fc-list >/dev/null 2>&1; then
        FONT_PATH=$(fc-list :lang=ko | grep -i '\.ttf' | head -1 | cut -d: -f1 | tr -d ' ' || true)
    fi

    # 2) Ubuntu/Debian 기본 경로 직접 탐색 (네트워크 불필요)
    if [ -z "$FONT_PATH" ]; then
        for _p in \
            /usr/share/fonts/opentype/noto/NotoSansCJKkr-Regular.otf \
            /usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc \
            /usr/share/fonts/truetype/nanum/NanumGothic.ttf \
            /usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf \
            /usr/share/fonts/truetype/unfonts-core/UnDotum.ttf \
            /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf; do
            if [ -f "$_p" ]; then
                FONT_PATH="$_p"
                break
            fi
        done
    fi

    if [ -n "$FONT_PATH" ] && [ -f "$FONT_PATH" ]; then
        echo "  시스템 폰트 복사: $FONT_PATH"
        cp "$FONT_PATH" runner/fonts/NotoSansKR.ttf
    else
        echo "  ⚠ 한글 폰트를 찾지 못함 → PDF는 내장 폰트로 생성됩니다 (한글 깨짐)"
        echo "    한글 PDF 필요 시: sudo apt install fonts-nanum"
        echo "                   또는 runner/fonts/NotoSansKR.ttf 직접 배치"
    fi
fi
if [ -f "runner/fonts/NotoSansKR.ttf" ]; then
    echo "  폰트: runner/fonts/NotoSansKR.ttf ($(du -sh runner/fonts/NotoSansKR.ttf | cut -f1))"
fi

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
