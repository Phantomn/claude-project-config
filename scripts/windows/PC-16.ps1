$result = 0

$volumns = Get-Volume
$isNotNTFS = $false

foreach($volumn in $volumns) {
    $filesystem = $volumn.FileSystem
    $disk = $volumn.DriveLetter
    if($filesystem -ne "NTFS") {
        Write-Host "파일 시스템이 NTFS가 아닌 디스크 볼륨이 존재합니다. 디스크: $($disk)"
        $isNotNTFS = $true
    }
}

if($isNotNTFS) {
    $result += 1
}

Write-Host "점검 결과: $result"

<#
$result = 0

$registryPath = 'HKCU:\Control Panel\Desktop\'

$screenSaverActive = Get-ItemProperty -Path $registryPath -Name ScreenSaveActive
if ($screenSaverActive.ScreenSaveActive -eq 1) {
    $screenSaverTimeout = Get-ItemProperty -Path $registryPath -Name ScreenSaveTimeOut -ErrorAction SilentlyContinue
    if ($screenSaverTimeout.ScreenSaveTimeOut -gt 600) {
        Write-Host "화면 보호기 대기 시간이 10분을 초과합니다. 현재 설정: $($screenSaverTimeout.ScreenSaveTimeOut / 60) 분"
        $result += 1
    }
} else {
    Write-Host "화면 보호기가 비활성화되어 있습니다."
    $result += 1
}

$screenSaverSecure = Get-ItemProperty -Path $registryPath -Name ScreenSaverIsSecure -ErrorAction SilentlyContinue
if ($screenSaverSecure.ScreenSaverIsSecure -eq 0) {
    Write-Host "화면 보호기 암호 보호가 설정되어 있지 않습니다."
    $result += 1
}

Write-Host "점검 결과: $result"
#>