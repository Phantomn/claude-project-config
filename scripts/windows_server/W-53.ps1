$result=0

$policyPath = "HKLM:\Security\Policy\Secrets"
$policyName = "SeInteractiveLogonRight"

if(Test-Path -Path $policyPath) {
    $policyValue = Get-ItemProperty -Path $policyPath -Name $policyName -ErrorAction SilentlyContinue
    if($policyValue -ne $null) {
        $user = $policyValue | Where-Object {$_ -notmatch "Administrator|IUSR_"}
        if($user) {
            Write-Host "로컬 로그인 허용 정책 권한에 Administrator, IUSR_ 외 권한을 가진 계정이 존재합니다."
            $result += 1
        }
    }
    else {
        Write-Host "로컬 로그인 허용 정책이 설정되지 않았습니다."
        $result += 1
    }
}


Write-Host "점검 결과: $result"