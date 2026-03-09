$result=0

$server = (Get-WindowsFeature -Name "Web-Server").InstallState
if($server -eq "Installed") {
    Import-Module WebAdministration

    $anony = Get-WebConfigurationProperty -Filter "system.ftpServer/security/authentication/anonymousAuthentication" -PSPath "IIS:\" -Name "enabled"
    if($anony -ne "True") {
        Write-Host "익명 접속 허용이 설정되어 있습니다."
        $result += 1
    }
}
Write-Host "점검 결과: $result"