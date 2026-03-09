$result=0

$regPath = "HKLM:\System\CurrentControlSet\Control\Lsa"
$regName = "LmCompatibilityLevel"

$regValue = (Get-ItemProperty -Path $regPath -Name $regName -ErrorAction SilentlyContinue).$regName

if($regValue -ge 3) {
    Write-Host "NTLM 인증이 활성화되어 있습니다."
    $result += 1
}

Write-Host "점검 결과: $result"