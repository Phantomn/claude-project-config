$result=0

$hotfix = Get-HotFix | Select-Object Description, HotFixID, InstalledOn

Write-Host "현재 Hot-Fix ID는 $($hotfit.HotFixID) 입니다. 공식 사이트를 통해 최신 ID인지 확인하세요."
$result += 1

$regPath = "HKLM:\Software\Policies\Microsoft\Windows\WindowsUpdate"

if(Test-Path -Path $regPath) {
    $wsusServer = Get-ItemProperty -Path $regPath -ErrorAction SilentlyContinue
    if(-not $wsusServer) {
        Write-Host "현재 WSUS 서버가 활성화되어 있지 않습니다."
        $result += 1
    }

    else {
        if(Test-Path -Path "$regPath\AU") {
            $autoUpdate = Get-ItemProperty -Path "regPath\AU" -ErrorAction SilentlyContinue
            if(-not $autoUpdate) {
                Write-Host "자동 업데이트가 설정되어 있지 않습니다."
                $result += 1
            }
        }
        else {
            Write-Host "자동 업데이트가 설정되어 있지 않습니다."
            $result += 1
        }
    }
}

else {
    Write-Host "WSUS서버가 설정되어 있지 않습니다."
    $result += 1
}

Write-Host "점검 결과: $result"