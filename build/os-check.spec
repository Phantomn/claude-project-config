# -*- mode: python ; coding: utf-8 -*-
# os-check PyInstaller 스펙 파일
# 빌드: pyinstaller build/os-check.spec (프로젝트 루트에서 실행)
# 주의: /usr/local/lib 에 비표준 Python이 설치된 환경에서는 build.sh 가
#       LD_LIBRARY_PATH 로 시스템 Python 라이브러리를 우선 선택하므로
#       이 spec 파일은 별도 패치 없이 사용 가능합니다.

datas = [
    # 한글 폰트 → 번들 내 fonts/ 로 추출 (sys._MEIPASS/fonts/NotoSansKR.ttf)
    ('../runner/fonts', 'fonts'),
]
binaries = []
hiddenimports = [
    'runner.models',
    'runner.detector',
    'runner.credentials',
    'runner.executor',
    'runner.reporter_json',
    'runner.reporter_pdf',
    'fpdf',
    'fpdf.enums',
    'fpdf.fonts',
    'fpdf.table',
]

a = Analysis(
    ['../entrypoint.py'],
    pathex=['..'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='os-check',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
