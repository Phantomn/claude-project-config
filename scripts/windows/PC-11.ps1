$result = 0

$firewalls = Get-NetFirewallProfile | Select-Object Name, Enable
$isAllEnabled = $true

foreach($fw in $firewalls) {
    if(!$fw.Enabled) {
        Write-Host "활성화되지 않은 방화벽이 있습니다. 이름: $($fw.Name)"
        $isAllEnabled = $false
    }
}

if(!$isAllEnabled) {
    $result += 1
}

$FWService = Get-Service -Name "mpssvc" | Select-Object Status, StartType

if($FWService.Status -ne "Running") {
    Write-Host "방화벽 서비스가 실행중이 아닙니다. 상태: $($FWService.status)"
    $result += 1
}

if($FWService.StartType -ne "Automatic") {
    Write-Host "방화벽 서비스가 부팅시 자동으로 시작되지 않습니다. 타입: $($FWService.StartType)"
    $result += 1
}

Write-Host "점검 결과: $result"


<#
$result = 0

$osInfo = Get-WmiObject -Class Win32_OperatingSystem

if ($osInfo.ServicePackMajorVersion -gt 0) {
    Write-Host "현재 시스템에 적용된 서비스 팩: Service Pack $($osInfo.ServicePackMajorVersion)"
} else {
    Write-Host "시스템에 적용된 서비스 팩이 없습니다."
    $result += 1
}
Write-Host "운영 체제: $($osInfo.Caption)"
Write-Host "버전: $($osInfo.Version)"
Write-Host "빌드 번호: $($osInfo.BuildNumber)"

Write-Host "점검 결과: $result"
#>