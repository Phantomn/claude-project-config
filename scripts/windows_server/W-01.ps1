$result=0

$users = Get-LocalUser

foreach($user in $users) {
    if($user.Name -eq "Administrator") {
        Write-Host "Administrator Default 계정 이름을 변경하지 않았습니다. Name: $($user)"
        $result += 1
        break
    }
}

Write-Host "점검 결과: $result"