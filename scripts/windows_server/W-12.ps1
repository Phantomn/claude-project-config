$result=0

$server = (Get-WindowsFeature -Name "Web-Server").InstallState
if($server -eq "Installed") {
    $dirPath = "C:\inetpub\scripts"
    if(Test-Path -Path $dirPath){
        $access = (Get-Acl $dirPath | Select-Object -ExpandProperty Access).IdentityReference
        if($access -eq "Everyone") {
            Write-Host "Everyone 권한이 존재합니다."
            $result += 1
        }
    }
}
Write-Host "점검 결과: $result"