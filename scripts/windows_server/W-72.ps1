$result=0

$regPath = "HKLM:\System\CurrentControlSet\Services\Tcpip\Parameters"

if(Test-Path -Path $regPath) {
    $synAttack = (Get-ItemProperty -Path $regPath -Name "SynAttackProtect" -ErrorAction SilentlyContinue).SynAttackProtect
    $enableDeadGW = (Get-ItemProperty -Path $regPath -Name "EnableDeadGWDetect" -ErrorAction SilentlyContinue).EnableDeadGWDetect
    $keepAlive = (Get-ItemProperty -Path $regPath -Name "KeepAliveTime" -ErrorAction SilentlyContinue).KeepAliveTime
    $noNameRelease = (Get-ItemProperty -Path $regPath -Name "NoNameReleaseOnDemand" -ErrorAction SilentlyContinue).NoNameReleaseOnDemand
    
    if($synAttack -lt 1) {
        Write-Host "SYN 공격에 대한 방어 기능이 설정되어 있지 않습니다."
        $result += 1
    }
    if($enableDeadGW -eq 1) {
        Write-Host "작동하지 않는 Gateway가 검색될 수 있습니다."
        $result += 1
    }
    if($keepAlive -gt 300000) {
        Write-Host "Keep-alive 패킷 확인 시간이 5분을 초과합니다."
        $result += 1
    }
    if($noNameRelease -eq 0) {
        Write-Host "NetBIOS 이름 해제 여부를 결정하는 설정이 켜져 있습니다."
        $result += 1
    }
}

Write-Host "점검 결과: $result"