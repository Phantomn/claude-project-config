$result=0

$server = (Get-WindowsFeature -Name "Web-Server").InstallState
if($server -eq "Installed") {
    Import-Module WebAdministration
    $maxEntity = Get-WebConfigurationProperty -pspath "MACHINE/WEBROOT/APPHOST" -filter "system.webServer/asp" -name "AspMaxRequestEntityAllowed"
    $bufLimit = Get-WebConfigurationProperty -pspath "MACHINE/WEBROOT/APPHOST" -filter "system.webServer/asp" -name "AspBufferingLimit"
    if($maxEntity -ne $null) {
        if($maxEntity -gt 204800) {
            Write-Host "파일 업로드 용량이 200MB를 초과합니다."
            $result += 1
        }
    }

    if($bufLimit -ne $null) {
        if($bufLimit -gt 4194304) {
            Write-Host "파일 다운로드 용량이 4MB를 초과합니다."
            $result += 1
        }
    }
    
}
Write-Host "점검 결과: $result"