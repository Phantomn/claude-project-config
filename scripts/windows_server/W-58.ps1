$result=0

$regPath = "HKLM:\Software\Policies\Microsoft\Windows NT\Terminal Services"
$regName = "MinEncryptionLevel"

if(Test-Path -Path $regPath) {
    $regValue = (Get-ItemProperty -Path $regPath -Name $regName -ErrorAction SilentlyContinue).$regName
    if([int]$regValue -lt 2) {
        Write-Host "터미널 서비스 암호화 수준이 '낮음'으로 설정되어 있습니다. 현재: $($regValue)"
        $result += 1
    }
}

Write-Host "점검 결과: $result"