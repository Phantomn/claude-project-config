$result=0

$configPath = "C:\Windows\Temp\secpol.cfg"
secedit /export /cfg $configPath /quiet

$maxiAge = ((Select-String -Path $configPath -Pattern "MaximumPasswordAge") -Split("="))[1].Trim()

if(([int]$maxiAge -gt 90) -or [int]$maxiAge -eq 0) {
    Write-Host "최대 암호 사용 기간이 설정되지 않았거나 90일을 초과합니다."
    $result += 1
}

Write-Host "점검 결과: $result"

Remove-Item $configPath -Force