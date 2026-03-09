$result=0

$getLog = Get-EventLog -LogName System -Newest 100

if($getLog.Count -ne 100) {
    Write-Host "정기적으로 로그가 작성되고 있지 않습니다."
    $result += 1
}

$evtLog = Get-ChildItem -Path "C:\Windows\System32\winevt\Logs" | Select-Object Name, LastWriteTime
if(-not $evtLog) {
    Write-Host "이벤트 로그가 작성되고 있지 않습니다."
    $result += 1
}

Write-Host "점검 결과: $result"