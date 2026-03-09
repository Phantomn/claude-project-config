$result=0

$regPath = "HKLM:\Software\Microsoft\Microsoft SQL Server\MSSQL16.MSSQLSERVER\MSSQLServer"
$regName = "LoginMode"

if(Test-Path -path $regPath) {
    $regValue = (Get-ItemProperty -Path $regPath -Name $regName).$regName
    if($regValue -eq 2) {
        Write-Host "sa 계정에 대해 강력한 암호정책 설정을 하지 않았습니다."
        $result += 1
    }
}

Write-Host "점검 결과: $result"