$result=0

$regPath = "HKLM\System\CurrentControlSet\Services\Lanmanserver\Parameters"
$regValue = "AutoSharedServer"

if(Test-Path -Path "$regPath\$regValue") {
    $autoShared = (Get-ItemProperty -Path $regPath -Name $regValue).$regValue
    if($autoShared -ne 0) {
        Write-Host "하드디스크 기본 공유가 설정되어 있습니다."
        $result += 1
    }
}

Write-Host "점검 결과: $result"