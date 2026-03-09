$result = 0

$shares = Get-WmiObject -Class Win32_Share

if ($shares.Count -gt 0) {
    Write-Host "기본 공유 폴더가 존재합니다: $($shares.Name -join ', ')"
    $result += 1
}

$matchedShares = @()
foreach ($share in $shares) {
    try {
        $hasPassword = Get-SmbShareAccess -Name $share.Name | Where-Object { $_.AccessControlType -eq 'Allow' -and $_.AccountName -eq 'Everyone' }
        
        if ($hasPassword -ne $null) {
            $matchedShares += $share.Name  
        }
    }
    catch {}
}

if ($matchedShares.Count -gt 0) {
    Write-Host "공유 폴더 접근 권한이 미흡합니다: $($matchedShares -join ', ')"
    $result += 1
}

$regPath = "HKLM:\System\CurrentControlSet\Services\LanmanServer\Parameters\AutoShareServer"

if ( Test-Path $regPath) {
    $autoShare = Get-ItemProperty -Path $regPath
    if( $autoShare -eq 1) {
        Write-Host "기본 공유 폴더가 자동으로 공유되는 설정이 활성화되어있습니다. 현재 설정: $autoShare"
        $result += 1
    }
} else {}


Write-Host "점검 결과: $result"
