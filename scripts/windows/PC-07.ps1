$result = 0

$os = Get-WmiObject -Class Win32_OperatingSystem
$osName = $os.Caption
$currentBuild = $os.BuildNumber

switch($osName)
{
    {$_ -like "*Windows 7*"} {
        $latestServiceVersion = 1
        if($servicePack -lt $latestServicePackVersion) {
            Write-Host "Window 7 서비스 팩이 최신이 아닙니다. 설치된 SP: $servicePack"
            $result += 1
        }
    }
    {$_ -like "*Windows 10*"} {
        Write-Host "Windows 10 서비스 팩 현재 버전은 $currentBuild 입니다. 공식 웹 사이트에서 최신 빌드 번호가 맞는지 확인하세요"
    }
    {$_ -like "*Windows 11*"} {
        Write-Host "Windows 11 서비스 팩 현재 버전은 $currentBuild 입니다. 공식 웹 사이트에서 최신 빌드 번호가 맞는지 확인하세요"
    }
}

Write-Host "점검 결과: $result"
        


<#
$volumes = Get-WmiObject -Class Win32_Volume | Where-Object { $_.DriveLetter -ne $null }

$matchedVolumes = @()
foreach ($volume in $volumes) {
    $volumeName = $volume.Name
    $fileSystem = $volume.FileSystem

    if ($fileSystem -ne "NTFS") {
        $matchedVolumes += $volumeName
    }
}

if ($matchedVolumes.Count -gt 0) {
    Write-Host "디스크 볼륨에 대한 파일 시스템으로 NTFS를 사용하고 있지 않습니다: $($matchedVolumes -join ', ')"
    $result += 1
}

Write-Host "점검 결과: $result"
#>