$result=0

$antivirus = Get-MpComputerStatus | Select-Object AntispywareEnabled, RealTimeProtectionEnabled, NISSignatureVersion, NISSignatureLastUpdated

Write-Host "현재 업데이트 버전: $($antivirus.NISSignatureVersion) 공식 웹사이트를 방문하여 최신 업데이트를 확인하세요."
Write-Host "마지막 업데이트 시간: $($antivirus.NISSignatureLastUpdated)"
$result += 1

Write-Host "점검 결과: $result"