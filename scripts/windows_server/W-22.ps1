$result=0

$regPath = "HKLM\System\CurrentControlSet\Services\W3SVC\Parameters"
$regName = "SSIEnableCmdDirective"

if(Test-Path -Path "$regPath\regName") {
    $value = (Get-ItemProperty -Path $regPath -Name $regName).$regName
    if($value -ne 0) {
        Write-Host "Exec 명령어 쉘 호출이 설정되어 있습니다. 설정: $($value)"
        $result += 1
    }
}

Write-Host "점검 결과: $result"