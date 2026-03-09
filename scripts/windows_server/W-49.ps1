$result=0

$configPath = "C:\Windows\Temp\secpol.cfg"
secedit /export /cfg $configPath /quiet

$miniLength = ((Select-String -Path $configPath -Pattern "MinimumPasswordLength") -Split("="))[1].Trim()

if([int]$miniLength -lt 8) {
    Write-Host "최소 암호 길이가 8문자 미만으로 설정되어 있습니다."
    $result += 1
}

Write-Host "점검 결과: $result"

Remove-Item $configPath -Force