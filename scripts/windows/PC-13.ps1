$result = 0

$regPath = "HKLM:\Software\Microsoft\Windows\CurrentVersion\Policies\Explorer"
$regName = "NoDriveTypeAutoRun"

if(Test-Path -Path "$regPath\$regName") {
    $autoRunSystem = (Get-ItemProperty -Path $regPath -Name $regName).$regName
    if($autoRunSystem -ne 0xff) {
        Write-Host "NoDriveTypeAutoRun값이 OxFF로 설정되어 있지 않습니다. 현재값: $($autoRunSystem)"
        $result += 1
    }
}
else {
    Write-Host "NoDriveTypeAutoRun값이 없습니다. 생성 후 0xFF로 설정해주세요"
    $result += 1
}

Write-Host "점검 결과: $result"

<#
$result = 0

$defenderSignature = Get-MpComputerStatus | Select-Object -Property AntivirusSignatureLastUpdated, AntivirusSignatureVersion

Write-Host "바이러스 정의 업데이트 날짜: $($defenderSignature.AntivirusSignatureLastUpdated)"
Write-Host "바이러스 정의 버전: $($defenderSignature.AntivirusSignatureVersion)"

Write-Host "점검 결과: $result"
#>