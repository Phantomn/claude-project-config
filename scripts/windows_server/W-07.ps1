$result=0

$shares = Get-SmbShare | ForEach-Object {
    $shareName = $_.Name
    Get-SmbShareAccess -Name $shareName | Where-Object { $_.Account -eq "Everyone" }}

if($shares.Count -gt 0) {
    Write-Host "Everyone 권한이 존재합니다."
    $result += 1
}

Write-Host "점검 결과: $result"