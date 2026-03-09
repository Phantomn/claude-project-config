$result=0

$file = Get-Volume -DriveLetter C

if($file.FileSystem -ne "NTFS") {
    Write-Host "FAT파일 시스템을 사용하고 있습니다."
    $result += 1
}


Write-Host "점검 결과: $result"