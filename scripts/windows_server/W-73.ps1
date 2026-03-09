$result=0

$regPath = "HKLM:\System\CurrentControlSet\Control\Print\Providers\LanMan Print Services\Servers"
$regName = "AddPrinterDrivers"

if(Test-Path -Path $regPath) {
    $regValue = (Get-ItemProperty -Path $regPath -Name $regName).$regName
    if($regValue -eq 0) {
        Write-Host "사용자가 프린터 드라이버를 설치할 수 없게 함 정책이 사용 안함으로 설정되어 있습니다."
        $result += 1
    }
}

Write-Host "점검 결과: $result"
