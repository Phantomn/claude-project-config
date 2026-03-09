$result=0

function Check-DNSDynamicUpdate {
    param (
        [string]$DnsServer = "localhost"
    )

    try {
        $dnsZones = Get-DnsServerZone -ComputerName $DnsServer -ErrorAction Stop
        foreach ($zone in $dnsZones) {
            if($zone.DynamicUpdate -eq "NonsecureAndSecure") {
                Write-Host "DNS 동적 업데이트가 설정되어 있습니다. DNS: $($zone.ZoneName)"
                $result += 1
            }
        }
    } catch {
        Write-Host "DNS Server가 제한되어 있습니다"
    }
}

Check-DNSDynamicUpdate -DnsServer "localhost"
                

Write-Host "점검 결과: $result"