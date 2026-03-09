$result=0

$server = (Get-WindowsFeature -Name "Web-Server").InstallState
if($server -eq "Installed") {
    Import-Module WebAdministration
    $auth = (Get-ItemProperty IIS:\AppPools\DefaultAppPool -Name processModel.identityType).Value
    if($auth -ne $null) {
        if($auth -eq "LocalSystem") {
            Write-Host "시스템 계정으로 웹 어플리케이션이 실행 중입니다."
            $result += 1
        }
    }
    $path = "$env:TEMP\secpol.txt"
    secedit /export /cfg $path /areas USER_RIGHTS

    $logon = Select-String -Path $path -Pattern "SeServiceLogonRight"
    if(-not ($logon -match "nobody")) {
        Write-Host "Nobody 계정이 존재하지 않습니다."
        $result += 1
    }
    
    $account = Get-ChildItem IIS:\AppPools | Select-Object Name, @{Name="Identity";Expression={(Get-ItemProperty $_.PSPath).processModel.identityType}}
    if($account.Identity -ne "ApplicationPoolIdentity") {
        WriteHost "ApplicationPoolIdentity 권한이 설정되어 있지 않습니다."
        $result += 1
    }    
}

Write-Host "점검 결과: $result"