$result=0

$regPath = "HKLM:\Software\Policies\Microsoft\Windows NT\Terminal Services"

if(Test-Path -Path $regPath) {
    $idleTimeout = (Get-ItemProperty -Path $regPath -Name "IdleTimeout" -ErrorAction SilentlyContinue).IdleTimeout
    $maxConnectionTime = (Get-ItemProperty -Path $regPath -Name "MaxConnectionTime" -ErrorAction SilentlyContinue).MaxConnectionTime
    $disconnectTimeout = (Get-ItemProperty -Path $regPath -Name "MaxDisconnectionTime" -ErrorAction SilentlyContinue).MaxDisconnectionTime

    if($idleTimeout -eq $null) {
        Write-Host "활동 없는 세션 제한시간이 설정되어 있지 않습니다."
        $result += 1
    }
    if($maxConnectionTime -eq $null) {
        Write-Host "활성 세션 제한시간이 설정되어 있지 않습니다."
        $result += 1
    }
    if($disconnectTimeout -eq $null) {
        Write-Host "연결 해제 후 제한시간이 설정되어 있지 않습니다."
        $result += 1
    }
}

Write-Host "점검 결과: $result"