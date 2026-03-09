$result=0

$regPath = "HKLM:\System\CurrentControlSet\Control\Lsa"
$regName = "LimitBlankPasswordUse"

if(Test-Path -Path $regPath) {
    $regValue = (Get-ItemProperty -Path $regPath -Name $regName).$regName
    if($regValue -eq "0") {
        Write-Host "'빈 암호 사용 가능 제한 정책'이 '사용 안 함'으로 설정 되어 있습니다."
        $result += 1
    }
}

Write-Host "점검 결과: $result"