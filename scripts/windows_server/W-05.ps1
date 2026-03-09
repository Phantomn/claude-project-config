$result=0

$configPath = "C:\Windows\Temp\secpol.cfg"
secedit /export /cfg $configPath /quiet

$clearText = ((Select-String -Path $configPath -Pattern "ClearTextPassword") -split "=")[1].Trim()

if($clearText -ne 0) {
    Write-Host "해독 가능한 암호화를 사용하여 암호 저장 정책이 사용으로 되어 있습니다."
    $result += 1
}

Write-Host "점검 결과: $result"

Remove-Item $configPath -Force