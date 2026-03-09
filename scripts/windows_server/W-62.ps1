$result=0

$regPath = "HKLM:\System\CurrentControlSet\Service\SNMP\Parameters"
$regName = "PermittedManagers"

if(Test-Path -Path $regPath) {
    $regValue = Get-ItemProperty -Path $regPath -Name $regName -ErrorAction SilentlyContinue
    if($regValue -ne $null) {
        $regValue.PSObject.Properties | ForEach-Object {
            if($_.Value -eq "*" -or $_.Value -eq $null) {
                Write-Host "모든 호스트가 접근을 허용 받습니다."
                $result += 1
            }
        }
    }
}

Write-Host "점검 결과: $result"