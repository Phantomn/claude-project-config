$result = 0

$regPath = "HKCU:\Control Panel\Desktop"
$timeOutKey = "ScreenSaveTimeOut"
$secureKey = "ScreenSaverIsSecure"

if(-not (Test-Path -Path "$regPath\$timeOutKey")) {
    Write-Host "화면 보호기 대기시간이 비활성화 되어있습니다."
    $result += 1
}
else {
    $timeOut = (Get-ItemProperty -Path $regPath -Name $tiemoutKey).$timeOutKey
    if(($timeOut -le 300) -and ($timeOut -gt 600)) {
        Write-Host "화면 보호기 대기시간이 5분 미만이거나 10분 초과합니다. 현재 시간: $($timeOut)"
        $result += 1
    }
}

if(-not (Test-Path -Path $"regPath\$secureKey")) {
    Write-Host "화면 보호기가 암호 보호를 비활성화하도록 설정되어 있습니다"
    $result += 1
}

else {
    $isSecure = (Get-ItemProperty -Path $regPath -Name $secureKey).$secureKey
    if($isSecure -ne 1) {
        Write-Host "화면 보호기가 암호 보호를 비활성화하도록 설정되어 있습니다"
        $result += 1
    }
}

Write-Host "점검 결과: $result"

    
<#
$result = 0

$installedUpdates = Get-WmiObject -Class Win32_QuickFixEngineering | Where-Object {
    $_.Description -like "*Office*" -or $_.Description -like "*Microsoft Office*"
}

if ($installedUpdates) {
    Write-Host "MS Office 관련 업데이트가 설치되어 있습니다:"
    $installedUpdates | ForEach-Object {
        Write-Host "$($_.Description) - 설치 날짜: $($_.InstalledOn)"
    }
    $result += 1; 
} 

$installedPrograms = Get-WmiObject -Class Win32_Product | Where-Object {
    $_.Name -like "*한글*" -or $_.Name -like "*Hangul*"
}

if ($installedPrograms) {
    Write-Host "한글(한컴 오피스)이 설치되어 있습니다. 업데이트 여부는 한컴 업데이트 도구에서 확인해야 합니다."
    $installedPrograms | ForEach-Object {
        Write-Host "프로그램 이름: $($_.Name), 버전: $($_.Version)"
    }
    $result += 1; 
} 

Write-Host "점검 결과: $result"
#>