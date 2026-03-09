$result = 0

$regTempPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings\Cache"
$tempName = "Persistent"

if(Test-Path -Path $regTempPath) {
    $persistValue = (Get-ItemProperty -Path $regTempPath -Name $tempName).$tempName
    if($persistValue -eq 1) {
        Write-Host "'브라우저를 닫을 때 임시 인터넷 파일 폴더 비우기'가 설정 되어 있지 않습니다. 설정: $($persistValue)"
        $result += 1
    }

}

$regRemotePath = "HKLM:\System\CurrentControlSet\Control\Remote Assistance"
$remoteName = "fAllowToGetHelp"
if(Test-Path -Path $regRemotePath) {
    $remoteValue = (Get-ItemProperty -Path $regRemotePath -Name $remoteName).$remoteName
    if($remoteValue -eq 1) {
        Write-Host "원격 지원이 활성화 되어 있습니다. 설정: $($remoteValue)"
        $result += 1
    }
}

$desktopPath = "HKLM:\System\CurrentControlSet\Control\Terminal Server"
$desktopName = "fDenyTSConnections"
if(Test-Path -Path $desktopPath) {
    $desktopValue = (Get-ItemProperty -Path $desktopPath -Name $desktopName).$desktopName
    if($desktopValue -eq 0) {
        Write-Host "Remote Desktop이 활성화 되어 있습니다. 설정: $($desktopValue)"
        $result += 1
    }
}

Write-Host "점검 결과: $result"


<#
$result = 0

$registryPath = "HKLM:\Software\Policies\Microsoft\Windows NT\Terminal Services"
$registryName = "fAllowUnsolicited"

if (Test-Path $registryPath) {
    $remoteAssistance = Get-ItemProperty -Path $registryPath -Name $registryName -ErrorAction SilentlyContinue

    if ($remoteAssistance.fAllowUnsolicited -eq 1) {
        Write-Host "요청되지 않은 원격 지원이 활성화되어 있습니다."
        $result += 1
    }
}

Write-Host "점검 결과: $result"
#>