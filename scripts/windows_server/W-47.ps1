$result=0

$configPath = "C:\Windows\Temp\secpol.cfg"
secedit /export /cfg $configPath /quiet

$lockoutDuration = ((Select-String -Path $configPath -Pattern "LockoutDuration" -ErrorAction SilentlyContinue) -Split("="))[1].Trim()
$resetLockCount = ((Select-String -Path $configPath -Pattern "ResetLockoutCount" -ErrorAction SilentlyContinue) -Split("="))[1].Trim()
$lockoutBadCount = ((Select-String -Path $configPath -Pattern "LockoutBadCount" -ErrorAction SilentlyContinue) -Split("="))[1].Trim()

if(($lockoutDuration -lt 60) -or ($resetLockCount -lt 60)) {
    Write-Host "계정 잠금 기간과 잠금 기간 원래대로 설정 기간 모두 60분 미만으로 설정되어 있습니다."
    $result += 1
}
if(($lockoutBadCount -eq 0) -or ($lockoutBadCount -gt 5)) {
    Write-Host "계정 잠금 임계값이 설정되어 있지 않거나 5회 이상입니다. 현재: $($lockoutBadCount)"
    $result += 1
}

Write-Host "점검 결과: $result"

Remove-Item $configPath -Force