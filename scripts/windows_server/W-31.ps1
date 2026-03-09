$result=0

$verInfo = Get-ComputerInfo | Select-Object WindowsVersion, WindowsBuildLabEx
$currentBuild = $verInfo.WindowsBuildLabEx.Split('.')[0] -as [int]

Write-Host "현재 빌드 번호는 $($currentBuild) 입니다. 공식 사이트를 방문해 최신 번호를 확인하세요. "
$result += 1

Write-Host "점검 결과: $result"