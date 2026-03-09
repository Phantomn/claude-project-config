$result=0

$settings = Get-ItemProperty -Path "HKCU:\Control Panel\Desktop"

if($settings.ScreenSaveActive -ne "1") {
    Write-Host "화면 보호기가 활성화되어 있지 않습니다."
    $result += 1
}

if(($settings.ScreenSaveTimeout -eq $null) -or ($settings.ScreenSaveTimeout -gt 600)) {
    Write-Host "화면 보호기 대기 시간이 없거나 10분을 초과합니다."
    $result += 1
}

if($settings.ScreenSaverIsSecure -ne "1") {
    Write-Host "화면 보호기 암호가 설정되어 있지 않습니다."
    $result += 1
}

Write-Host "점검 결과: $result"