$result=0

$ftpDir = "C:\inetpub\ftproot"
$acl = Get-Acl -Path $ftpDir

$everyoneAccess = $acl.Access | Where-Object{$_.IdentityReference -eq "Everyone" }
if($everyoneAccess) {
    Write-Host "Everyone 권한이 설정되어 있습니다."
    $result += 1
}

Write-Host "점검 결과: $result"