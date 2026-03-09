$result = 0
$bootEntries = bcdedit /enum all

$multiBootEntries = $bootEntires | Select-String "description" -Context 0,1

if($multiBootEntries) {
    Write-Host "멀티부팅이 설정되어 있습니다"
    Write-Host "Boot Entries:" $multiBootEntries | ForEach-Object { $_.Line }
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