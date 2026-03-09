$result=0

$guest = Get-LocalUser -Name "Guest" | Select-Object Name, Enabled

if($guest.Enabled -eq "True") {
    Write-Host "Guest 계정이 활성화 되어 있습니다."
    $result += 1
}

Write-Host "점검 결과: $result"