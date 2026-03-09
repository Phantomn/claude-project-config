$result=0

$regPath = "HKLM:\System\CurrentControlSet\Services\Netlogon\Parameters"
$requireSign = "RequireSignOrSeal"
$sealSecure = "SealSecureChannel"
$signSecure = "SignSecureChannel"

if(Test-Path -Path $regPath) {
    $requireSignValue = (Get-ItemProperty -Path $regPath -Name $requireSign -ErrorAction SilentlyContinue).$requireSign
    $sealSecureValue = (Get-ItemProperty -Path $regPath -Name $sealSecure -ErrorAction SilentlyContinue).$sealSecure
    $signSecureValue = (Get-ItemProperty -Path $regPath -Name $signSecure -ErrorAction SilentlyContinue).$signSecure
    if($requireSignValue -eq 0) {
        Write-Host "보안 채널 데이터를 디지털 암호화 또는 서명 정책이 사용 안 함으로 설정되어 있습니다."
        $result += 1
    }
    if($sealSecureValue -eq 0) {
        Write-Host "보안 채널 데이터를 디지털 암호화 정책이 사용 안 함으로 설정되어 있습니다."
        $result += 1
    }
    if($signSecureValue -eq 0) {
        Write-Host "보안 채널 데이터 디지털 서명 정책이 사용 안 함으로 설정되어 있습니다."
        $result += 1
    }
}

Write-Host "점검 결과: $result"