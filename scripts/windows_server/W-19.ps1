$result=0

$server = (Get-WindowsFeature -Name "Web-Server").InstallState
if($server -eq "Installed") {
    Import-Module WebAdministration
    
    $VRDirs = @("Admin", "IIS Adminpwd")

    foreach($VRDir in $VRDirs) {
        $exist = Get-WebConfiguration -Filter "system.applicationHost/sites/site[@name='Default Web Site']/application/virtualDirectory[@path='.$VRDir']" -PSPath "IIS:\"
        if($exist) {
            Write-Host "$($VRDir) 가상 디렉토리가 존재합니다."
            $result += 1
        }
    }
}
Write-Host "점검 결과: $result"