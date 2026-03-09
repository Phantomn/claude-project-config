$result = 0

$updated = (Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object -First 10)

if($updated.Count -ne 0) {
    Write-Host "윈도우를 최신으로 업데이트 하셔야 합니다. 업데이트 개수: $($updated.Count)"
    $result += 1
}

Write-Host "점검 결과: $result"

<#
$registryPath = "HKLM:\Software\Policies\Microsoft\Messenger\Client"
$registryName = "PreventRun"

if (Test-Path $registryPath) {
    $preventRunValue = Get-ItemProperty -Path $registryPath -Name $registryName -ErrorAction SilentlyContinue

    if ($preventRunValue.PreventRun -eq 0) {
        Write-Host "'Windows Messenger를 실행 허용 안 함' 설정이 '사용 안 함'으로 설정되어 있습니다."
        $result += 1
    }
} 

Write-Host "점검 결과: $result"
#>