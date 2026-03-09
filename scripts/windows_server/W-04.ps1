$result=0

$configPath = "C:\Windows\Temp\secpol.cfg"
secedit /export /cfg $configPath /quiet

$lockoutBadCount = ((Select-String -Path $configPath -Pattern "LockoutBadCount") -split "=")[1].Trim()

if($lockoutBadCount -eq 0) {
    Write-Host "계정 잠금 정책이 활성화되어 있지 않습니다."
    $result += 1
}

else {
    $lockDuration = ((Select-String -Path $configPath -Pattern "Account lockout duration") -split "=")[1].Trim()
    if($lockDuration -gt 5) {
        Write-Host "계정 잠금 임계갑이 6이상입니다. 현재: $($lockDuration)"
        $result += 1
    }
}

Write-Host "점검 결과: $result"

Remove-Item $configPath -Force