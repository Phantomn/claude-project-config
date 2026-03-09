$result=0

$regPath = "HKLM\System\CurrentControlSet\Services\W3SVC\Parameters"
$regName = "DisableWebDAV"

$server = (Get-WindowsFeature -Name "Web-Server").InstallState
if($server -eq "Installed") {
    if(Test-Path -Path "$regPath\$regName") {
        $value = (Get-ItemProperty -Path $regPath -Name $regName).$regName
        if($value -eq 1) {
            Write-Host "IIS WebDAV가 활성화되어 있습니다."
            $result += 1
        }
    }

    $packVersion = (Get-ItemProperty -Path "HKLM:\Software\Microsoft\Windows NT\CurrentVersion" | Select-Object CSDVersion).CSDVersion
    if($packVersion -eq $null -or $packVersion -lt 4) {
        Write-Host "서비스 팩이 4 이하거나 설치되어 있지 않습니다. 현재 버전: $($packVersion)"
        $result += 1
    }
}

Write-Host "점검 결과: $result"