$result=0

$anti = Get-CimInstance -Namespace "root\SercurityCenter2" -ClassName "AntivirusProduct" -ErrorAction SilentlyContinue

if(-not $anti) {
    Write-Host "백신 프로그램이 설치되어 있지 않습니다."
    $result += 1
}
else {
    $program = $anti | Where-Object {$_.displayName -match "V3|알약|하우리|Norton|Trend Micro" }
    if(-not $program) {
        Write-Host "특정 백신 프로그램이 설치되어 있지 않습니다.(V3, 알약, 하우리, Norton, Trend Micro)"
        $result += 1
    }
}

Write-Host "점검 결과: $result"