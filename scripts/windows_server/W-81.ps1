$result=0

$serviceList = Get-Service | Select-Object DisplayName, Status, StartType

foreach($service in $serviceList) {
    if($service.Status -eq "Running") {
        Write-Host $service.DisplayName
    }
}

Write-Host "현재 실행되고 있는 서비스 목록입니다. 불필요한 항목이 있는지 확인하세요"
$result += 1

Write-Host "점검 결과: $result"