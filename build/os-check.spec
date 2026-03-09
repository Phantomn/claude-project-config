# -*- mode: python ; coding: utf-8 -*-
# os-check PyInstaller 스펙 파일
# 빌드: pyinstaller build/os-check.spec (프로젝트 루트에서 실행)

from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = [
    # Jinja2 HTML 템플릿 → 번들 내 templates/ 로 추출
    ('../runner/templates', 'templates'),
]
binaries = []
hiddenimports = [
    'runner.models',
    'runner.detector',
    'runner.credentials',
    'runner.executor',
    'runner.reporter_json',
    'runner.reporter_pdf',
]

# WeasyPrint 전체 수집 (데이터 파일 + 바이너리 + 숨겨진 임포트)
for pkg in ('weasyprint', 'jinja2', 'markupsafe'):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas    += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

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
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
