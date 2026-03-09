$result = 0

$regPaths = @(
    "HKLM:\Software\Microsoft\Windows\CurrentVersion\Ext\Stats",
    "HKLM:\Software\Microsoft\WOW6432Node\Microsoft\Windows\CurrentVersion\Ext\Stats"
)

$thresholdDate = (Get-Date).AddMonths(-3)
$check = $false

foreach($regPath in $regPaths) {
    if(Test-Path -Path $regPath) {
        Get-ChildItem -Path $regPath | ForEach-Object {
            $clsid = $_.PSChildName
            $lastUsedTime = (Get-ItemProperty -Path "$regPath\$clsid").LastUsedTime
            if($lastUsedTime) {
                $lastUsedDate = [DateTime]::FromFileTime([Int64]$lastUsedTime)
                if($lastUsedDate -lt $thresholdDate) {
                    Write-Host "3개월 이상 사용하지 않은 ActiveX 컨트롤이 존재합니다."
                    Write-Host "CLSID: $clsid"
                    Write-Host "마지막 사용 날짜: $lastUsedDate"
                    $check = true
                }
            }
        }
    }
}

if($check) {
    $result += 1
}

Write-Host "점검 결과: $result"


<#
$result = 0

$defenderStatus = Get-MpPreference

if ($defenderStatus.DisableRealtimeMonitoring -eq $true) {
    Write-Host "실시간 보호 기능이 비활성화되어 있습니다."
    $result += 1
}

Write-Host "점검 결과: $result"
#>