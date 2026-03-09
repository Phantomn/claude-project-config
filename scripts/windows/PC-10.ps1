$result = 0
$defenderStatus = Get-MpComputerStatus

if(!$defenderStatus.RealTimeProtectionEnabled) {
    Write-Host "Windows Defender 실시간 감지가 비활성화 되어 있습니다."
    $result += 1
}

Write-Host "점검 결과: $result"

<#
$result = 0

$hotfixes = Get-HotFix
if ($hotfixes.Count -eq 0) {
    Write-Host "설치된 Hotfix가 없습니다."
    $result += 1
}

$registryPath = "HKLM:\Software\Policies\Microsoft\Windows\WindowsUpdate\AU"
$registryName = "AUOptions"
if (Test-Path $registryPath) {
    $wuSetting = Get-ItemProperty -Path $registryPath -Name $registryName -ErrorAction SilentlyContinue

    if ($wuSetting.AUOptions -eq 1) {
        Write-Host "Windows 자동 업데이트가 비활성화되어 있습니다."
        $result += 1
    }
} 

$pmsAgent = Get-Service -Name "PMSAgent" -ErrorAction SilentlyContinue
if (!($pmsAgent -ne $null -and $pmsAgent.Status -eq "Running")) {
    Write-Host "PMS(Patch Management System) Agent가 설치되어 있지 않거나 실행 중이지 않습니다."
    $result += 1
}

Write-Host "점검 결과: $result"
#>