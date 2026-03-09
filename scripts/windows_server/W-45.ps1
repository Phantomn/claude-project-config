$result=0

$regPath = "HKLM:\Software\Policies\Microsoft\Windows NT\CurrentVersion\EFS\CurrentKeys"
$regName = "CertificateHash"

if(Test-Path -Path "$regPath") {
    $regValue = (Get-ItemProperty -Path $regPath -Name $regName -ErrorAction SilentlyContinue).$regName
    if($regValue -ne $null) {
        Write-Host "EFS가 비활성화 되어 있거나 파일이 암호화되지 않은 상태로 저장되도록 허용하고 있습니다."
        $result += 1
    }
}
else {
    Write-Host "EFS가 비활성화 되어 있거나 파일이 암호화되지 않은 상태로 저장되도록 허용하고 있습니다."
    $result += 1
}

Write-Host "점검 결과: $result"