$result=0

$server = (Get-WindowsFeature -Name "Web-Server").InstallState
if($server -eq "Installed") {
    Import-Module WebAdministration

    $asa = Get-WebConfiguration -Filter "system.webServer/handlers/add[@path='*.asa']" -PSPath "MACHINE/WEBROOT/APPHOST"
    if($asa -ne $null) {
        Write-Host ".asa 매핑이 존재합니다. $($asa)"
        $result += 1
    }
}
Write-Host "점검 결과: $result"