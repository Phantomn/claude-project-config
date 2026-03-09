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

# before
<#
$maxPwdAge = (net accounts | Select-String "Maximum password age").ToString() -split ":\s*" | Select-Object -Last 1
$maxPwdAge = Get-ValidatedNumber $maxPwdAge.Trim()
if ($maxPwdAge -lt 90) {
    Write-Host "최대 암호 사용 기간이 90일로 설정되어 있지 않습니다. 현재 설정: $maxPwdAge"
    $result += 1
}
#>

# after
$maxPwdAge = (net accounts | Select-String "Maximum password age").ToString() -split ":\s*" | Select-Object -Last 1
$maxPwdAge = Get-ValidatedNumber $maxPwdAge.Trim()
if ($maxPwdAge -gt 90) {
    Write-Host "최대 암호 사용 기간이 90일을 초과하여 설정되어 있습니다. 현재 설정: $maxPwdAge"
    $result += 1
}

$minPwdAge = (net accounts | Select-String "Minimum password age").ToString() -split ":\s*" | Select-Object -Last 1
$minPwdAge = Get-ValidatedNumber $minPwdAge.Trim()

if ($minPwdAge -lt 1) {
    Write-Host "최소 암호 사용 기간이 1일로 설정되어 있지 않습니다. 현재 설정: $minPwdAge"
    $result += 1
}

$pwdHistLen = (net accounts | Select-String "Length of password history maintained").ToString() -split ":\s*" | Select-Object -Last 1
$pwdHistLen = Get-ValidatedNumber $pwdHistLen.Trim()
if ($pwdHistLen -lt 24) {
    Write-Host "최근 사용된 24개의 암호를 기억하도록 설정되어 있지 않습니다. 현재 설정: $pwdHistLen"
    $result += 1
}

Write-Host "점검 결과: $result"
