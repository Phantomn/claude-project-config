$result=0

$regPath = "HKLM:\Software\Microsoft\Windows\CurrentVersion\Policies\System"
$regName = "DontDisplayLastUsername"

if(Test-Path -Path $regPath) {
    $lastUserPolicy = (Get-ItemProperty -Path $regPath -Name $regName).$regName
    if($lastUsrPolicy -eq "0") {
        Write-Host "마지막 사용자 이름 표시 안 함 설정이 사용 안 함으로 설정되어 있습니다"
        $result += 1
    }
}

Write-Host "점검 결과: $result"