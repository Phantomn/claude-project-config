$result=0

$configPath = "C:\Windows\Temp\secpol.cfg"
secedit /export /cfg $configPath /quiet

$pwdHistory = ((Select-String -Path $configPath -Pattern "PasswordHistorySize") -Split("="))[1].Trim()

if([int]$pwdHistory -lt 4) {
    Write-Host "최근 암호 기억 갯수가 4개 미만으로 설정되어 있습니다. 현재: $([int]$pwdHistory)"
    $result += 1
}

Write-Host "점검 결과: $result"
Remove-Item $configPath -force