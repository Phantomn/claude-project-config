$result=0

$users = Get-LocalUser | Select-Object Name, Enabled

foreach($user in $users) {
    if($user.Enabled -eq "True") {
        Write-Host "활성화 된 계정: $($user.Name)"
    }
}

Write-Host "불필요한 계정이 있는지 확인하세요"
$result += 1

Write-Host "점검 결과: $result"