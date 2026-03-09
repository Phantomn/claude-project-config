$result=0

$server = (Get-WindowsFeature -Name "Web-Server").InstallState
if($server -eq "Installed") {
    Import-Module WebAdministration
    $directory = Get-ChildItem "IIS:\Sites\Default Web Site"
    $virtualDirectoires = @("IISSamples" ,"IISHelp")

    foreach($dir in $virtualDirectoires) {
        $exists = Test-Path "IIS:\Sites\Default Web Site\$dir"
        if($exists) {
            Write-Host "불필요한 파일이 존재합니다."
            $result += 1
        }
    }
}

Write-Host "점검 결과: $result"