$result=0

$regPath = "HKLM:\Software\Microsoft\Windows NT\CurrentVersion\Winlogons"
$regName = "AllocateDASD"

if(Test-Path -Path "$regPath") {
    $regValue = (Get-ItemProperty -Path $regPath -Name $regName -ErrorAction SilentlyContinue).$regName
    if($regValue -gt 1) {
        Write-Host "이동식 미디어 포맷 및 꺼내기 허용 정책 권한이 Administrators 외 다른 권한이 존재합니다."
        $result += 1
    }
}

Write-Host "점검 결과: $result"