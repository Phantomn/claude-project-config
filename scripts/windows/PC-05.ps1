$result = 0

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