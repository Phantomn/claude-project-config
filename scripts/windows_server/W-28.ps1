$result=0

$server = (Get-WindowsFeature -Name "Web-Server").InstallState
if($server -eq "Installed") {
    Import-Module WebAdministration

    $ipSecurity = Get-WebConfiguration -Filter "system.ftpServer/security/ipSecurity" -PSPath "IIS:\" | Select-Object *
    $allowUnlisted = $ipSecurity.allowUnlisted
    if($awllowUnlisted -eq "True") {
        Write-Host "목록에 없는 IP 접근 허용이 활성화 되어 있습니다."
        $result += 1
    }
}
Write-Host "점검 결과: $result"