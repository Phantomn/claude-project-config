$result=0

$server = (Get-WindowsFeature -Name "Web-Server").InstallState
if($server -eq "Installed") {
    Import-Module WebAdministration
    $parentDir = (Get-WebConfigurationProperty -Filter "system.webServer/asp" -PSPath "IIS:\Sites\Default Web Site" -Name "enableParentPaths").Value
    if($parentDir -eq "True") {
        Write-Host "상위 디렉토리 접근이 가능합니다."
        $result += 1
    }
}
Write-Host "점검 결과: $result"