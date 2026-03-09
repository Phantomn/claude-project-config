$result=0

$service = Get-Service -Name "RemoteRegistry" | Select-Object DisplayName, Status

if($service.Status -eq "Running") {
    Write-Host "Remote Registry Service가 사용 중입니다."
    $result += 1
}

Write-Host "점검 결과: $result"