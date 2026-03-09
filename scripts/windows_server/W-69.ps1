$result=0

function Get-AuditPolicy {
    param (
        [string]$category
    )
    $cateList = Invoke-Expression "AuditPol /Get /Category:`"$category`""

    $data = $cateList -Split "\s{2,}"
    $data = $data[6..($data.Count)]
    
    $subArr = @()
    $setArr = @()
    
    for($i = 0;$i -lt $data.Count; $i++) {
        if($i %2 -eq 0) {
            $subArr += $data[$i].Trim()
        }
        else {
            $setArr += $data[$i].Trim()
        }
    }

    $dataArr = @()
    for($i = 0;$i -lt $subArr.Count; $i++){
        if($subArr[$i] -ne ""){
            $dataArr += [PSCustomObject]@{
                Subcategory = $subArr[$i]
                Setting     = $setArr[$i]
            }
        }
    }
}

#Object Access

$objectAccess = Get-AuditPolicy -category "Object Access"
foreach($sub in $objectAccess) {
    if($sub.Setting -ne "No Auditing") {
        Write-Host "감사 안함으로 설정이 되어있지 않은 카테고리가 있습니다. 카테고리: $($sub.SubCategroy)"
        $result += 1
    }
}

#Account Management
$accountCategory = Get-AuditPolicy -category "Account Management"
foreach($sub in $accountCategory) {
    if($sub.SubCategory -eq "Computer Account Management" -and $sub.Setting -ne "Success") {
        Write-Host "컴퓨터 계정관리가 Success로 설정되어 있지 않습니다."
        $result += 1
    }
    elseif($sub.SubCategory -eq "Security Group Management" -and $sub.Setting -ne "Success") {
        Write-Host "보안 그룹 관리가 Success로 설정되어 있지 않습니다."
        $result += 1
    }
    elseif($sub.SubCategory -eq "User Account Management") {
        if($sub.Setting -ne "Success") {
            Write-Host "사용자 계정관리가 Success로 설정되어 있지 않습니다."
            $result += 1
        }
    }
}

# Logon Event
$logonCategory = Get-AuditPolicy -category "Account Logon"
foreach($sub in $logonCategory) {
    if($sub.SubCategory -eq "Kerberos Service Ticket Operations" -and $sub.Setting -ne "Success") {
        Write-Host "Kerberos 서비스 티켓 작업이 Success로 설정되어 있지 않습니다."
        $result += 1
    }
    elseif($sub.SubCategory -eq "Kerberos Authentication Service" -and $sub.Setting -ne "Success") {
        Write-Host "Kerberos 인증서비스가 Success로 설정되어 있지 않습니다."
        $result += 1
    }
    elseif($sub.SubCategory -eq "Credential Validation" -and $sub.Setting -ne "Success") {
        Write-Host "자격 증명 유효성 검사가 Success로 설정되어 있지 않습니다."
        $result += 1
    }
}

# Privilege Use
$privUse = Get-AuditPolicy -category "Privilege Use"
foreach($sub in $privUse) {
    if($sub.Setting -ne "No Auditing") {
        Write-Host "감사 안함으로 설정이 되어있지 않은 카테고리가 있습니다. 카테고리: $($sub.SubCategroy)"
        $result += 1
    }
}

# Logon / Logoff
$logonoff = Get-AuditPolicy -category "Logon/Logoff"
foreach($sub in $logonoff) {
    if($sub.SubCategory -eq "Logon" -and $sub.Setting -ne "Success and Failure") {
        Write-Host "로그온이 Success and Failure로 설정되어 있지 않습니다."
        $result += 1
    }
    elseif($sub.SubCategory -eq "Logoff" -and $sub.Setting -ne "Success") {
        Write-Host "로그오프가 Success로 설정되어 있지 않습니다."
        $result += 1
    }
    elseif($sub.SubCategory -eq "Account Lockout" -and $sub.Setting -ne "Success") {
        Write-Host "계정 잠금이 Success로 설정되어 있지 않습니다."
        $result += 1
    }
    elseif($sub.SubCategory -eq "Special Logon" -and $sub.Setting -ne "Success") {
        Write-Host "특수 로그인이 Success로 설정되어 있지 않습니다."
        $result += 1
    }
    elseif($sub.SubCategory -eq "Network Policy Server" -and $sub.Setting -ne "Success and Failure") {
        Write-Host "네트워크 정책 서버가 Success and Failure로 설정되어 있지 않습니다."
        $result += 1
    }
}

# System
$sysEvent = Get-AuditPolicy -category "System"
foreach($sub in $sysEvent) {
    if($sub.SubCategory -eq "Security State Change" -and $sub.Setting -ne "Success") {
        Write-Host "보안 상태 변경이 Success로 설정되어 있지 않습니다."
        $result += 1
    }
    elseif($sub.SubCategory -eq "System Integrity" -and $sub.Setting -ne "Success and Failure") {
        Write-Host "시스템 무결성이 Success and Failure로 설정되어 있지 않습니다."
        $result += 1
    }
    elseif($sub.SubCategory -eq "Other System Events" -and $sub.Setting -ne "Success and Failure") {
        Write-Host "기타 시스템 이벤트가 Success and Failure로 설정되어 있지 않습니다."
        $result += 1
    }
}

# Policy Change
$policyChg = Get-AuditPolicy -category "Policy Change"
foreach($sub in $policyChg) {
    if($sub.SubCategory -eq "Audit Policy Change" -and $sub.Setting -ne "Success") {
        Write-Host "감사 정책 변경이 Success로 설정되어 있지 않습니다."
        $result += 1
    }
    elseif($sub.SubCategory -eq "Authorization Policy Change" -and $sub.Setting -ne "Success") {
        Write-Host "인증 정책 변겅이 Success로 설정되어 있지 않습니다."
        $result += 1
    }
}

# Detailed Tracking
$detailedTracking = Get-AuditPolicy -category "Detailed Tracking"
foreach($sub in $privUse) {
    if($sub.Setting -ne "No Auditing") {
        Write-Host "감사 안함으로 설정이 되어있지 않은 카테고리가 있습니다. 카테고리: $($sub.SubCategroy)"
        $result += 1
    }
}

Write-Host "점검 결과: $result"