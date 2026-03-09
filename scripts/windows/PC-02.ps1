$result = 0

$configPath = "C:\Windows\Temp\secpol.cfg"
secedit /export /cfg $configPath /quiet

$minPwdLength = (Select-String -Path $configPath -Pattern "MinimumPasswordLength").Line -split "=" | Select-Object -Last 1
$minPwdLength = $minPwdLength.Trim()

if ($minPwdLength -lt 8) {
    Write-Host "최소 암호 길이가 8자 이상으로 설정되어 있지 않습니다. 현재 설정: $minPwdLength"
    $result += 1
}

$complexityEnabled = (Select-String -Path $configPath -Pattern "PasswordComplexity").Line -split "=" | Select-Object -Last 1
$complexityEnabled = $complexityEnabled.Trim()

if ($complexityEnabled -eq 0) {
    Write-Host "암호 복잡성 요구 사항을 사용하지 않고 있습니다."
    $result += 1
}

Remove-Item $configPath

Write-Host "점검 결과: $result"