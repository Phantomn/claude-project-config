$result=0

$adminGroup = Get-LocalGroup -Name "Administrators"

if($adminGroup.Count -gt 1) {
    Write-Host "Administrator 그룹 맴버: $($adminGroup -join ', ')"
    Write-Host "불필요한 관리자 계정이 존재하는지 확인하세요."
    $result += 1
}

Write-Host "점검 결과: $result"