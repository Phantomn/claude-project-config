# build.ps1 - Windows용 os-check 단일 바이너리 빌드
# 실행: powershell -ExecutionPolicy Bypass -File build\build.ps1 (프로젝트 루트에서)
# Windows Server와 Windows PC 스크립트를 모두 포함하여 런타임 OS 탐지가 정상 동작합니다.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir   = Split-Path -Parent $ScriptDir
$VenvDir   = Join-Path $ScriptDir ".venv"
Set-Location $RootDir

Write-Host "=== os-check Windows 빌드 ==="

Write-Host "[1/3] 빌드 의존성 설치"
if (-not (Test-Path $VenvDir)) {
    Write-Host "  venv 생성: $VenvDir"
    python -m venv $VenvDir
}
& "$VenvDir\Scripts\pip" install --quiet --upgrade pip
& "$VenvDir\Scripts\pip" install --quiet pyinstaller
& "$VenvDir\Scripts\pip" install --quiet fpdf2

Write-Host "[1.5/3] 한글 폰트 획득"
New-Item -ItemType Directory -Path "runner\fonts" -Force | Out-Null
if (-not (Test-Path "runner\fonts\NotoSansKR.ttf")) {
    $candidates = @(
        "$env:WINDIR\Fonts\malgun.ttf",
        "$env:WINDIR\Fonts\malgunbd.ttf",
        "$env:WINDIR\Fonts\batang.ttc",
        "$env:WINDIR\Fonts\gulim.ttc"
    )
    $copied = $false
    foreach ($font in $candidates) {
        if (Test-Path $font) {
            Copy-Item $font "runner\fonts\NotoSansKR.ttf"
            Write-Host "  시스템 폰트 복사: $font"
            $copied = $true
            break
        }
    }
    if (-not $copied) {
        Write-Host "  경고: 한글 폰트를 찾지 못함 → PDF가 한글 깨질 수 있습니다"
        Write-Host "        runner\fonts\NotoSansKR.ttf 에 폰트를 직접 배치하세요"
    }
}
if (Test-Path "runner\fonts\NotoSansKR.ttf") {
    $fontSize = (Get-Item "runner\fonts\NotoSansKR.ttf").Length / 1MB
    Write-Host ("  폰트: runner\fonts\NotoSansKR.ttf ({0:F1}MB)" -f $fontSize)
}

Write-Host "[2/3] PyInstaller 빌드"
& "$VenvDir\Scripts\pyinstaller" build\os-check.spec `
    --distpath build\dist `
    --workpath build\work `
    --noconfirm

Write-Host "[3/3] 점검 스크립트 배포 디렉토리 구성"
# -Recurse 시 대상이 이미 존재하면 하위 중첩 복사되므로 대상 디렉토리를 먼저 생성 후 내용물(*) 복사
New-Item -ItemType Directory -Path "build\dist\scripts\windows_server" -Force | Out-Null
New-Item -ItemType Directory -Path "build\dist\scripts\windows"        -Force | Out-Null
Copy-Item -Recurse -Force "scripts\windows_server\*" "build\dist\scripts\windows_server"
Copy-Item -Recurse -Force "scripts\windows\*"        "build\dist\scripts\windows"

$serverCount = (Get-ChildItem "scripts\windows_server").Count
$pcCount     = (Get-ChildItem "scripts\windows").Count
Write-Host ""
Write-Host "=== 빌드 완료 ==="
Write-Host "배포 패키지: build\dist\"
Write-Host "  os-check.exe                  (실행 파일)"
Write-Host "  scripts\windows_server\       (Windows Server 스크립트 ${serverCount}개)"
Write-Host "  scripts\windows\              (Windows PC 스크립트 ${pcCount}개)"
Write-Host ""
Write-Host "실행 방법 (Administrator PowerShell):"
Write-Host "  .\build\dist\os-check.exe"
