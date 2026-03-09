$result=0

$configPath = "C:\Windows\Temp\secpol.cfg"
secedit /export /cfg $configPath /quiet

$miniAge = ((Select-String -Path $configPath -Pattern "MinimumPasswordAge") -Split("="))[1].Trim()

if([int]$miniAge -eq 0) {
    Write-Host "최소 암호 사용 기간이 설정되어 있지 않습니다."
    $result += 1
}

Write-Host "점검 결과: $result"

Remove-Item $configPath -force