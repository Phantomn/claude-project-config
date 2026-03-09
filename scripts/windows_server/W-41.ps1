$result=0

$regPath = "HKLM:\System\CurrentControlSet\Control\Lsa"
$regName = "CrashOnAuditFail"

if(Test-Path -Path $regPath) {
    $regValue = (Get-ItemProperty -Path $regPath -Name $regName).$regName
    if($regValue -ne 0) {
        Write-Host "보안 감사를 로그할 수 없는 경우 즉시 시스템 종료 정책이 사용을 되어 있습니다"
        $result += 1
    }
}

Write-Host "점검 결과: $result"