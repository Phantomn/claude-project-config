$result = 0

function Get-ValidatedNumber {
    param (
        [string]$inputValue
    )

    if ([string]::IsNullOrEmpty($inputValue) -or -not ($inputValue -match '^\d+$')) {
        return 0
    } else {
        return [int]$inputValue
    }
}

# net accounts 출력을 행 인덱스로 파싱 (언어 독립적)
# 순서: [0]=로그오프, [1]=최소암호기간, [2]=최대암호기간, [3]=최소길이, [4]=기록길이
$acctLines = @(net accounts | Where-Object { $_ -match ':' })

$maxPwdAge = Get-ValidatedNumber (($acctLines[2] -split ':\s+' | Select-Object -Last 1).Trim())
if ($maxPwdAge -gt 90) {
    Write-Host "최대 암호 사용 기간이 90일을 초과하여 설정되어 있습니다. 현재 설정: $maxPwdAge"
    $result += 1
}

$minPwdAge = Get-ValidatedNumber (($acctLines[1] -split ':\s+' | Select-Object -Last 1).Trim())
if ($minPwdAge -lt 1) {
    Write-Host "최소 암호 사용 기간이 1일로 설정되어 있지 않습니다. 현재 설정: $minPwdAge"
    $result += 1
}

$pwdHistLen = Get-ValidatedNumber (($acctLines[4] -split ':\s+' | Select-Object -Last 1).Trim())
if ($pwdHistLen -lt 24) {
    Write-Host "최근 사용된 24개의 암호를 기억하도록 설정되어 있지 않습니다. 현재 설정: $pwdHistLen"
    $result += 1
}

Write-Host "점검 결과: $result"
