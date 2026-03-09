$result=0

$regPath = "HKLM:\System\CurrentControlSet\Control\Lsa"
$regName = "LmCompatibilityLevel"

if(Test-Path -Path $regPath) {
    $regValue = (Get-ItemProperty -Path $regPath -Name $regName -ErrorAction SilentlyContinue).$regName
    if($regValue -gt 0) {
        Write-Host "네트워크 보안 인증 수준이 NTMLv2 응답만 보내기가 설정되어 있지 않습니다."
        $result += 1
    }
}

Write-Host "점검 결과: $result"