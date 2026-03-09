$result=0

function Get-SystemDSNs {
    $dsnList = New-Object System.Collections.ArrayList

    $regPath = "HKLM:\Software\ODBC\ODBC.INI\ODBC Data Sources"
    
    if(Test-Path $regPath) {
        $dsns = Get-ItemProperty -Path $regPath
        foreach($dsn in $dsns.PSObject.Properties) {
            $dsnList.Add($dsn.Name) | Out-Null
        }
    }
    else {
        Write-Host "시스템에서 DSN을 찾을 수 없습니다."
        $result += 1
    }
    return $dsnList
}

if($systemDSNs.Count -ne 0) {
    Write-Host "현재 DSN 부분의 Data Sources는 $($systemDSNs -join ', ') 입니다."
    $result += 1
}

Write-Host "점검 결과: $result"