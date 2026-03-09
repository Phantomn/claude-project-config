$result=0

$configPath = "C:\Windows\Temp\secpol.cfg"
secedit /export /cfg $configPath /quiet

$lsaAnonymousName = ((Select-String -Path $configPath -Pattern "LSAAnonymousNameLookup") -Split("="))[1].Trim()

if($lsaAnonymousName -eq "1") {
    Write-Host "익명 SID/이름 변환 혀옹 정책이 사용으로 설정되어 있습니다."
    $result += 1
}

Write-Host "점검 결과: $result"

Remove-Item $configPath -force