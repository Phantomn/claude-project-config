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


<#
$result = 0

$bootLoaders = (bcdedit | Select-String "Windows Boot Loader").Count

if ($bootLoaders -gt 1) {
    Write-Host "다중 부팅 환경이 감지되었습니다. $bootLoaders 개의 운영 체제가 설치되어 있습니다."
    $result += 1
}

Write-Host "점검 결과: $result"
#>