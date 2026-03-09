$result=0

$configPath = "C:\Windows\Temp\secpol.cfg"
secedit /export /cfg $configPath /quiet

$shutdownPrivilege = ((Select-String -Path $configPath -Pattern "SeRemoteShutdownPrivilege") -Split "=")[1].Trim()

if($shutdownPrivilege.Count -gt 1) {
    Write-Host "Administrator 외 권한을 가진 다른 사용자가 존재합니다."
    $result += 1
}

Write-Host "점검 결과: $result"

Remove-Item $configPath -Force