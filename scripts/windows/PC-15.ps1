$result = 0

$regPath = "HKLM:\Software\Microsoft\Windows NT\CurrentVersion\Winlogon"

if(Test-Path -Path $regPath) {
    $autoAdminLogon = (Get-ItemProperty -Path $regPath | Select-Object AutoAdminLogon).AutoAdminLogon
    if($autoAdminLogon -ne 0) {
        Write-Host "자동 관리 로그온 허용 속성이 '사용'으로 설정되어 있습니다. 설정: $($autoAdminLogon)"
        $result += 1
    }
}

Write-Host "점검 결과: $result"

<#
$result = 0

$firewallProfiles = Get-NetFirewallProfile

foreach ($profile in $firewallProfiles) {
    $profileName = $profile.Name
    $firewallEnabled = $profile.Enabled

    if (!$firewallEnabled) {
        Write-Host "$profileName 네트워크에서 Windows 방화벽이 비활성화되어 있습니다."
        $result += 1 
    }
}

Write-Host "점검 결과: $result"
#>