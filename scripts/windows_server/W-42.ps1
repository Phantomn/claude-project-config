$result=0

$regPath = "HKLM:\System\CurrentControlSet\Control\Lsa"
$regName = "RestrictAnonymous"

if(Test-Path -Path $regPath) {
    $regValue = (Get-ItemProperty -Path $regPath -Name $regName).$regName
    if($regValue -eq "0") {
        Write-Host "SAM 계정과 공유의 익명 열거 허용 안 함 정책이 설정 되어 있지 않습니다."
        $result += 1
    }
}

Write-Host "점검 결과: $result"