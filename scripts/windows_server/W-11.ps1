$result=0

$server = (Get-WindowsFeature -Name "Web-Server").InstallState
if($server -eq "Installed") {
    Import-Module WebAdministration
    $dirList = (Get-WebConfigurationProperty -Filter "system.webServer/directoryBrowse" -PSPath "IIS:\Sites\Default Web Site" -Name enabled).Value
    if($dirList -eq "True") {
        Write-Host "디렉토리 리스팅이 설정되어 있습니다."
        $result += 1
    }
}

Write-Host "점검 결과: $result"