$result=0

$foundEvery = $false

$server = (Get-WindowsFeature -Name "Web-Server").InstallState
if($server -eq "Installed") {
    $rootPath = "C:\inetpub\wwwroot"
    Get-ChildItem -Path $rootPath -Recurse | ForEach-Object {
        $acl = Get-Acl $_.FullName
        $everyoneAccess = $acl.Access | Where-Object { $_.IdentityReference -eq "Everyone" }

        if($everyoneAccess) {
            Write-Host "Everyone 권한 설정 파일이 존재합니다. $($_.FullName)"
            $foundEvery = $true
        }
    }
}

if($foundEvery) {
    $result += 1
}

Write-Host "점검 결과: $result"