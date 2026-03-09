$result=0

$regPath = "HKLM:\System\CurrentControlSet\Services\Http\Parameters"
$regName = "DisableServerHeader"

if(Test-Path -Path $regPath) {
    $regValue = Get-ItemProperty -Path $regPath -Name $regName -ErrorAction SilentlyContinue
    if($regValue -ne $null) {
        if($regValue.$regName -eq 0) {
            Write-Host "Server 헤더가 활성화되어 있습니다."
            $result += 1
        }
    }
    else {
        Write-Host "Server 헤더 설정이 존재하지 않습니다"
        $result += 1
    }
}

Write-Host "점검 결과: $result"