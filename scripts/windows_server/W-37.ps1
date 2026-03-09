$result=0

$acl = (Get-Acl -Path "C:\Windows\System32\config\SAM").Access | Where-Object { $_.IdentityReference -notmatch "SYSTEM|Administrators"}


if($acl) {
    Write-Host "System, Administrator 외 다른 사용자가 권한을 가지고 있습니다."
    $result += 1
}

Write-Host "점검 결과: $result"