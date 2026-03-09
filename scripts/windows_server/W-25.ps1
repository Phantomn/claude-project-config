$result=0

$ftp = (Get-Service -Name "FTPSVC").Status
if($ftp -eq "Running") {
    Write-Host "FTP가 사용중입니다."
    $result += 1
}

Write-Host "점검 결과: $result"