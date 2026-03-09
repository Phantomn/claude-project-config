$result=0

$snmp = Get-Service -Name SNMPTRAP

if($snmp.Status -eq "Running") {
    Write-Host "SNMP가 활성화 되어있습니다"
    $result += 1
}

Write-Host "점검 결과: $result"