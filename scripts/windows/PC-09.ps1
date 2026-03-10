$result = 0

$defenderStatus = Get-MpComputerStatus
$currentVersion = $defenderStatus.AntivirusSignatureVersion
$lastUpdated = $defenderStatus.AntivirusSignatureLastUpdated

Write-Host "가장 최근 윈도우 디펜더 업데이트 날짜입니다. 날짜: $($lastUpdated)"
Write-Host "https://www.microsoft.com/en-us/wdsi/defenderupdates를 확인하여 윈도우 디펜더가 최신인지 확인하세요. 현재 버전: $($currentVersion)"

Write-Host "점검 결과: $result"

<#
$result = 0

$edgeRegPath = "HKLM:\SOFTWARE\Policies\Microsoft\Edge"
$policyName = "ClearBrowsingDataOnExit"
if (Test-Path $edgeRegPath) {
    $edgePolicy = Get-ItemProperty -Path $edgeRegPath -Name $policyName -ErrorAction SilentlyContinue

    if (!($edgePolicy.ClearBrowsingDataOnExit -eq 1)) {
        Write-Host "Microsoft Edge는 브라우저 종료 시 캐시를 삭제하지 않습니다."
        $result += 1
    } 
} 

$chromeRegPath = "HKCU:\SOFTWARE\Policies\Google\Chrome\ClearBrowsingDataOnExitList\"
if (!(Test-Path $chromeRegPath)) {
    $regItems = Get-ItemProperty -Path $chromeRegPath -ErrorAction SilentlyContinue

    $properties = $regItems.PSObject.Properties | Where-Object { $_.Name -ne "PSChildName" -and $_.Name -ne "PSDrive" -and $_.Name -ne "PSProvider" -and $_.Name -ne "PSPath" -and $_.Name -ne "PSParentPath" }

    if ($properties.Count -eq 0) {
        Write-Host "Google Chrome은 브라우저 종료 시 캐시를 삭제하지 않습니다."
        $result += 1
    }
}
else
{
    Write-Host "Google Chrome은 브라우저 종료 시 캐시를 삭제하지 않습니다."
    $result += 1
}

Write-Host "점검 결과: $result"
#>