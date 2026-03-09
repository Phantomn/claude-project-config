$result=0

$lists = Get-ScheduledTask | Select-Object TaskName

foreach($list in $lists) {
    Write-Host "Schedule: $($list.TaskName)"
}
Write-Host "불필요한 명령어가 존재하는지 확인하세요."
$result += 1

Write-Host "점검 결과: $result"