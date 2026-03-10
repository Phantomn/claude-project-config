$result = 0
$bootEntries = bcdedit /enum all

# bcdedit 출력 레이블은 로케일에 따라 한글화됨 (예: "description" → "설명")
# 레이블 매칭 대신 "bootmgr"/"winload" 등 언어 독립적 로더 식별자로 엔트리 수 계산
$bootLoaderEntries = $bootEntries | Where-Object { $_ -match "winload|winresume|bootmgr" }

if(($bootLoaderEntries | Measure-Object).Count -gt 1) {
    Write-Host "멀티부팅이 설정되어 있습니다"
    $result += 1
}

Write-Host "점검 결과: $result"

<#
$result = 0

$registryPath = "HKLM:\Software\Microsoft\Windows\CurrentVersion\Policies\Explorer"
$registryName = "NoDriveTypeAutoRun"

if (Test-Path $registryPath) {
    $autoRunSetting = Get-ItemProperty -Path $registryPath -Name $registryName -ErrorAction SilentlyContinue

    if ($autoRunSetting.NoDriveTypeAutoRun -ne 255) {
        Write-Host "자동 실행 사용 안 함 정책이 설정되지 않았거나 일부 드라이브에만 적용됩니다. 현재 설정: $($autoRunSetting.NoDriveTypeAutoRun)"
        $result += 1
    }
} else {
    Write-Host "자동 실행 사용 안 함 정책이 설정되지 않았습니다."
    $result += 1
}

Write-Host "점검 결과: $result"
#>