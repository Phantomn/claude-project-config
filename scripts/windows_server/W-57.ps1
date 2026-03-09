$result=0

$groupMember = Get-LocalGroupMember -Group "Remote Desktop Users"

if($groupMember) {
    Write-Host "현재 원격 데스크톱 사용자 그룹 맴버는 $($groupMember -join ', ')"
    $result += 1
}

Write-Host "점검 결과: $result"