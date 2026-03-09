$result = 0

$servicesToCheck = @(
    "Alerter", 
    "Automatic Updates", 
    "Clipbook", 
    "Computer Browser", 
    "Cryptographic Services", 
    "DHCP Client", 
    "Distributed Link Tracking Client", 
    "DNS Client", 
    "Error reporting Service", 
    "Human Interface Device Access", 
    "IMAPI CD-Burning COM Service", 
    "Infrared Monitor", 
    "Messenger", 
    "NetMeeting Remote Desktop Sharing", 
    "Portable Media Serial Number", 
    "Print Spooler", 
    "Remote Registry", 
    "Simple TCP/IP Services", 
    "Universal Plug and Play Device Host", 
    "Wireless Zero Configuration"
)

$matchedServices = @()
foreach ($serviceName in $servicesToCheck) {
    $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
    if ($service) {
        $matchedServices += $serviceName
    }
}

if ($matchedServices.Count -gt 0) {
    Write-Host "불필요한 서비스가 존재합니다: $($matchedServices -join ', ')"
    $result += 1
}

Write-Host "점검 결과: $result"