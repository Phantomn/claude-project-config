$result=0

$server = (Get-WindowsFeature -Name "Web-Server").InstallState
if($server -eq "Installed") {
    Import-Module WebAdministration
    
    $rds = Get-WebConfiguration -Filter "system.webServer/handlers/add" -PSPath "IIS:\" | Where-Object { $_.Path -match "rds" } | Select-Object Path, Name, Modules
    Write-Host $rds
}

Write-Host "점검 결과: $result"