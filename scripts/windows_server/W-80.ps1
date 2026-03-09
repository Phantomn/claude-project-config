$result=0

$regPath = "HKLM:\System\CurrentControlSet\Services\Netlogon\Parameters"
$pwdChgName = "DisablePasswordChange"
$maxAgeName = "MaximumPasswordAge"

if(Test-Path -Path $regPath) {
    $pwdChgValue = (Get-ItemProperty -Path $regPath -Name $pwdChgName -ErrorAction SilentlyContinue).$pwdChgName
    $maxAgeValue = (Get-ItemProperty -Path $regPath -Name $maxAgeName -ErrorAction SilentlyContinue).$maxAgeName
    if($pwdChgValue -eq 0) {
        Write-Host "컴퓨터 계정 암호 변경 사용 안 함 정책이 사용으로 설정되어 있습니다."
        $result += 1
    }
    if([int]$maxAgeValue -lt 90) {
        Write-Host "컴퓨터 계정 암호 최대 사용 기간이 90일 미만으로 설정되어 있습니다. 현재: $($maxAgeValue)"
        $result += 1
    }
}

Write-Host "점검 결과: $result"