$result=0

$server = (Get-WindowsFeature -Name "Web-Server").InstallState
if($server -eq "Installed") {
    $path = "$env:Temp\secpol.txt"
    secedit /export /cfg $path /areas USER_RIGHTS

    $symlinkAuth = ((Select-String -Path $path -Pattern "SeCreateSymbolicLinkPrivilege") -split "=")[1].Trim()
    if($symlinkAuth -ne "*S-1-5-32-544") {
        Write-Host "심볼릭 링크 권한이 Administrator가 아닙니다."
        $result += 1
    }
    
    $phyPath = Get-ItemProperty "IIS:\Sites\Default Web Site" -Name physicalPath
    $phyPath = $phyPath -replace "%SystemDrive%", "C:"
    $shortcuts = Get-ChildItem -Path $phyPath -Recurse -Filter "*.lnk"
    if($shortcuts) {
        Write-Host "바로가기 파일이 존재합니다. File: $($shortcuts.Count)"
        $result += 1
    }

}
Write-Host "점검 결과: $result"