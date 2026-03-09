$result=0

$regPath = "HKLM:\System\CurrentControlSet\Servicess\LanmanServer\Parameters"
$regName = "enableforcedlogoff"

if(Test-Path -Path $regPath) {
    $regValue = (Get-ItemProperty -Path $regPath -Name $regName).$regName
    if($regValue -lt 15) {
        Write-Host "로그온 시간이 만료되면 클라이언트 연결 끊기 정책이 15분 미만으로 설정되어 있습니다"
        $result += 1
    }
}

Write-Host "점검 결과: $result"
