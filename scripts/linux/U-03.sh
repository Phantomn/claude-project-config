#!/bin/bash

result=0

if [[ "$(uname -s)" =~ "SunOS" ]]; then

    # /etc/default/login 파일에서 RETRIES 값이 10 이하인지 확인
    if grep -v '^#' /etc/default/login | egrep '!RETRIES=[0-9]$' > /dev/null 2>&1; then
        echo "/etc/default/login 파일에서 계정 잠금 임계값(RETRIES)이 10 이상으로 설정되어 있습니다."
        result=$((result+1))
    fi

    # Solaris 5.9 이상 버전일 경우 /etc/security/policy.conf 확인
    if [[ "$(uname -r)" =~ ^5\.([9-9]|1[0-9]) ]]; then
		if grep -v '^#' /etc/security/policy.conf | egrep '^LOCK_AFTER_RETRIES=NO' > /dev/null 2>&1; then
            echo "/etc/security/policy.conf 파일에서 LOCK_AFTER_RETRIES 설정이 없습니다."
            result=$((result+1))
        fi
    fi

    echo "점검 결과: $result"
    exit 1
fi



pam_file="/etc/pam.d/system-auth"

check_account_lock_threshold() {
    local file=$1
    local valid=true
    local found_module=false

    if [ ! -f "$file" ]; then
        echo "$file 이 존재하지 않습니다."
        return 1
    fi

    while IFS= read -r line; do
        if [[ "$line" =~ pam_tally.so || "$line" =~ pam_tally2.so || "$line" =~ pam_faillock.so ]]; then
            found_module=true

            deny_value=$(echo "$line" | grep -oP "deny=\K[0-9]+" > /dev/null 2>&1)
            if [ -z "$deny_value" ]; then
                echo "계정 잠금을 수행하지 않습니다."
                valid=false
            elif [ "$deny_value" -gt 10 ]; then
                echo "계정 잠금 임계값이 $deny_value 입니다. (허용되는 최대 값: 10)"
                valid=false
            fi
        fi
    done < "$file"

    if [ "$found_module" = false ]; then
        echo "pam_tally.so, pam_tally2.so 또는 pam_faillock.so 설정을 찾을 수 없습니다."
        valid=false
    fi

    if [ "$valid" = true ]; then
        return 0
    else
        return 1
    fi
}

if ! check_account_lock_threshold "$pam_file"; then
    result=$((result+1))
fi

echo "점검 결과: $result"