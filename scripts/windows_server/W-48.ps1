$result=0

$configPath = "C:\Windows\Temp\secpol.cfg"
secedit /export /cfg $configPath /quiet

$pwdComplexity = ((Select-String -Path $configPath -Pattern "PasswordComplexity") -Split("="))[1].Trim()

if($pwdComplexity -ne "1") {
    Write-Host "'암호는 복잡성을 만족해야 함 정책'이 '사용 안 함'으로 설정되어 있습니다."
    $result += 1
}

Write-Host "점검 결과: $result"

Remove-Item $configPath -Force