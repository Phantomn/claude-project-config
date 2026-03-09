$result=0

$dns = (Get-Service -Name "DNS").Status
if($dns -eq "Running") {
    Write-Host "DNS 서비스가 활성화 중입니다."
    $result += 1
}

$serverZone = (Get-DnsServerZone | Select-Object ZoneName, IsZoneTransferAllowed).IsZoneTransferAllowed
if($serverZone -eq "True") {
    Write-Host "영역 전송 설정이 허용으로 설정되어 있습니다."
    $result += 1
}

Write-Host "점검 결과: $result"