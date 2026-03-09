$result=0

$usersPath = "C:\Users"

foreach($dir in Get-ChildItem -Path $usersPath -Directory) {
    if($dir -ne "Public") {
        $path = $dir.FullName
        $acl = Get-Acl -Path $path
        $auth = $acl.Access | Where-Object {$_.IdentityReference -match "Everyone"}

        if($auth) {
            Write-Host "디렉토리에 Everyone 권한이 있습니다"
            $result += 1
        }
    }
   
}

Write-Host "점검 결과: $result"