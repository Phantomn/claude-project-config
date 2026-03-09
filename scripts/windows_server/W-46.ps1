$result=0

$regPath = "HKLM:\System\CurrentControlSet\Control\Lsa"
$regName = "EveryoneIncludesAnonymous"

$configPath = "C:\Windows\Temp\secpol.cfg"
secedit /export /cfg $configPath /quiet

if(Test-Path -Path "$regPath") {
    $regValue = (Get-ItemProperty -Path $regPath -Name $regName -ErrorAction SilentlyContinue).$regName
    if($regValue -eq "1") {
        Write-Host "'Everyone 사용 권한을 익명 사용자에게 적용' 정책이 '사용'으로 설정되어 있습니다."
        $result += 1
    }
}
else {
    $every = (((Select-String -Path $configPath -Pattern $regName) -Split("="))[1].Trim() -Split(','))[1]
    if($every -eq "1") {
        Write-Host "'Everyone 사용 권한을 익명 사용자에게 적용' 정책이 '사용'으로 설정되어 있습니다."
        $result += 1
    }
}

Write-Host "점검 결과: $result"

Remove-Item $configPath -force