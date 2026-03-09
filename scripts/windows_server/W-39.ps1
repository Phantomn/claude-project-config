$result=0

$regPath = "HKLM:\Software\Microsoft\Windows\CurrentVersion\Policies\System"
$regName = "ShutdownWithoutLogon"

if(Test-Path -Path "$regPath") {
    $regValue = (Get-ItemProperty -Path $regPath -Name $regName).$regName
    if($regValue) {
        Write-Host "로그온하지 않고 시스템 종료가 허용되어 있습니다."
        $result += 1
    }
}

Write-Host "점검 결과: $result"