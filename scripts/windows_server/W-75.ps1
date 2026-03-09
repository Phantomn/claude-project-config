$result=0

$regPath = "HKLM:\Software\Microsoft\Windows\CurrentVersion\Policies\System"
$regCaptionName = "LegalNoticeCaption"
$regTextName = "LegalNoticeText"

if(Test-Path -Path $regPath) {
    $regCaptionName = (Get-ItemProperty -Path $regPath -Name $regCaptionName -ErrorAction SilentlyContinue).$regCaptionName
    $regTextName = (Get-ItemProperty -Path $regPath -Name $regTextName -ErrorAction SilentlyContinue).$regTextName
    if($regCaptionName -eq "") {
        Write-Host "로그인 경고 메시지 제목이 설정되어 있지 않습니다."
        $result += 1
    }
    if($regTextName -eq "") {
        Write-Host "로그인 경고 메시지 내용이 설정되어 있지 않습니다."
        $result += 1
    }
}

Write-Host "점검 결과: $result"