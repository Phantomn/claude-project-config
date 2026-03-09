$result=0

$regPath = "HKLM:\Software\Microsoft\Windows NT\CurrentVersion\Winlogon"
$regName ="AutoAdminLogon"
$default = "DefaultPassword"

if(Test-Path -Path "$regPath") {
    $regValue = (Get-ItemProperty -Path $regPath -Name $regName).$regName
    if($regValue -eq "1") {
        Write-Host "AutoAdminLogon 값이 1로 설정되어 있습니다."
        $result += 1
    }
}

if(Test-Path -Path "$regPath\$default") {
    Write-Host "Deafault Password가 설정되어 있습니다."
    $result += 1
}

Write-Host "점검 결과: $result"