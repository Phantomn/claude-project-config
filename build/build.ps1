# build.ps1 - Windows용 os-check 단일 바이너리 빌드
# 실행: powershell -ExecutionPolicy Bypass -File build\build.ps1 (프로젝트 루트에서)
param(
    [ValidateSet("windows_server", "windows")]
    [string]$Target = "windows_server"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir   = Split-Path -Parent $ScriptDir
$VenvDir   = Join-Path $ScriptDir ".venv"
Set-Location $RootDir

Write-Host "=== os-check Windows 빌드 (대상: $Target) ==="

Write-Host "[1/3] 빌드 의존성 설치"
if (-not (Test-Path $VenvDir)) {
    Write-Host "  venv 생성: $VenvDir"
    python -m venv $VenvDir
}
& "$VenvDir\Scripts\pip" install --quiet --upgrade pip
& "$VenvDir\Scripts\pip" install --quiet pyinstaller
& "$VenvDir\Scripts\pip" install --quiet -r runner\requirements.txt

Write-Host "[2/3] PyInstaller 빌드"
& "$VenvDir\Scripts\pyinstaller" build\os-check.spec `
    --distpath build\dist `
    --workpath build\work `
    --noconfirm

Write-Host "[3/3] 점검 스크립트 배포 디렉토리 구성"
New-Item -ItemType Directory -Path "build\dist\scripts" -Force | Out-Null
Copy-Item -Recurse -Force "scripts\$Target" "build\dist\scripts\$Target"

$scriptCount = (Get-ChildItem "scripts\$Target").Count
Write-Host ""
Write-Host "=== 빌드 완료 ==="
Write-Host "배포 패키지: build\dist\"
Write-Host "  os-check.exe            (실행 파일)"
Write-Host "  scripts\$Target\   (점검 스크립트 ${scriptCount}개)"
Write-Host ""
Write-Host "실행 방법 (Administrator PowerShell):"
Write-Host "  .\build\dist\os-check.exe"
