$result=0

$regPath = "HKLM:\System\CurrentControlSet\Services\SNMP\Parameters"
$regName = "ValidCommunities"

if(Test-Path -Path $regPath) {
    $regValue = Get-ItemProperty -Path $regPath -Name $regName -ErrorAction SilentlyContinue
    if($regValue -ne $null) {
        $regValue.PSObject.Properties | ForEach-Object {
            $name = $_.name
            if($name -in @("public", "private")) {
                Write-Host " $name : 기본값으로 설정되어 있습니다."
                $result += 1
            }
        }
    }
}

Write-Host "점검 결과: $result"