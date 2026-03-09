$result=0

$foundMapping = $false
$server = (Get-WindowsFeature -Name "Web-Server").InstallState
if($server -eq "Installed") {
    Import-Module WebAdministration

    $targetMap = @('htr', 'idc', 'stm', 'shtm', 'shtml', 'printer', 'htw', 'ida'. 'idq')
    foreach($target in $targetMap) {
        $exist = Get-WebConfiguration -Filter "system.webServer/handlers/add[@path='*.$($target)']" -PSPath "IIS:\Sites\Default Web Site"
        if($exist) {
            Write-Host "$($target) 확장자를 가진 파일이 존재합니다"
            $foundMapping = $true
        }
    }
}

if($foundMapping) {
    $result += 1
}

Write-Host "점검 결과: $result"