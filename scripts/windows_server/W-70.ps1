$result=0

$maxLogSize = Get-WinEvent -ListLog "System" | Select-Object LogName, @{Name="MaximumSizeInKB";Expression={($_.MaximumSizeInBytes / 1024)}}, RetentionDays

if($maxLogSize.MaximumSizeInKB -lt 10240) {
    Write-Host "최대 로그 크기가 10,240KB 미만으로 설정되어 있습니다."
    $result += 1
}

if($maxLogSize.RetentionDays -lt 90) {
    Write-Host "이벤트 덮어씀 기간이 90이하로 설정되어 있습니다."
    $result += 1
}

Write-Host "점검 결과: $result"