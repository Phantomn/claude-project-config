$result=0

$systemLogPath = "C:\Windows\System32\config"
$IISLogPath = "C:\inetpub\logs\LogFiles"

$sysAccess = Get-Acl -Path $systemLogPath | Select-Object -ExpandProperty Access | Where-Object {$_.IdentityReference -eq "Everyone"}
$IISAccess = Get-Acl -Path $IISLogPath | Select-Object -ExpandProperty Access | Where-Object {$_.IdentityReference -eq "Everyone"}

if($sysAccess -ne $null) {
    Write-Host "시스템 로그 디렉토리에 Everyone 권한이 존재합니다."
    $result += 1
}
if($IISAccess -ne $null) {
    Write-Host "IIS 로그 디렉토리에 Everyone 권한이 존재합니다."
    $result += 1
}

Write-Host "점검 결과: $result"