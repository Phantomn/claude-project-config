#!/bin/bash

result=0

if [[ "$(uname -s)" =~ "SunOS" ]]; then

    # /etc/default/passwd 파일에서 minlen 값이 8 이하인지 확인
	if grep -v '^#' /etc/default/passwd | egrep 'MINWEEKS=[0-7]$' > /dev/null 2>&1; then
		echo "/etc/default/passwd 파일에서 minlen 값이 8 이하로 설정되어 있습니다."
		result=$((result+1))
	fi

    # retry 값이 3 이상인지 확인
	if grep -v '^#' /etc/default/login | egrep 'RETRIES=[3-9]$' > /dev/null 2>&1; then
		echo "/etc/default/passwd 파일에서 retry 값이 3 이상으로 설정되어 있습니다."
		result=$((result+1))
fi

	# MINALPHA, MINSPECIAL, MINDIGIT 값이 최소 입력기능인지 확인
	if grep -v '^#' /etc/default/passwd | egrep '!MINALPHA=[1-9]$' > /dev/null 2>&1; then
		echo "/etc/default/passwd 파일에서 영문자 최소 입력 기능이 올바르게 설정되지 않았습니다."
		result=$((result+1))
	fi

	if grep -v '^#' /etc/default/passwd | egrep '!MINSPECIAL=[1-9]$' > /dev/null 2>&1; then
		echo "/etc/default/passwd 파일에서 특수문자 최소 입력 기능이 올바르게 설정되지 않았습니다."
		result=$((result+1))
	fi

	if grep -v '^#' /etc/default/passwd | egrep '!MINDIGIT=[1-9]$' > /dev/null 2>&1; then
		echo "/etc/default/passwd 파일에서 숫자 최소 입력 기능이 올바르게 설정되지 않았습니다."
		result=$((result+1))
	fi

    echo "점검 결과: $result"
    exit 1
fi



check_pattern() {
    local file=$1
    local valid=true

    if ! grep -q "pam_cracklib.so" "$file" > /dev/null 2>&1; then
        echo "$file: pam_cracklib.so 설정이 누락되었습니다."
        valid=false
    fi

    retry_value=$(grep -oP "retry=\K[0-9]+" "$file" > /dev/null 2>&1)
    if [ -z "$retry_value" ]; then
        echo "$file: retry 설정이 누락되었습니다."
        valid=false
    elif [ "$retry_value" -gt 3 ]; then
        echo "$file: retry 값이 $retry_value 입니다. (허용되는 최대 값: 3)"
        valid=false
    fi

    minlen_value=$(grep -oP "minlen=\K[0-9]+" "$file" > /dev/null 2>&1)
    if [ -z "$minlen_value" ]; then
        echo "$file: minlen 설정이 누락되었습니다."
        valid=false
    elif [ "$minlen_value" -lt 8 ]; then
        echo "$file: minlen 값이 $minlen_value 입니다. (최소 요구 값: 8)"
        valid=false
    fi

    if ! grep -q "lcredit=-1" "$file" > /dev/null 2>&1 || \
    ! grep -q "ucredit=-1" "$file" > /dev/null 2>&1 || \
    ! grep -q "dcredit=-1" "$file" > /dev/null 2>&1 || \
    ! grep -q "ocredit=-1" "$file" > /dev/null 2>&1; then
        echo "$file: lcredit, ucredit, dcredit, ocredit 설정이 누락되었거나 잘못되었습니다."
        valid=false
    fi

    if [ "$valid" = true ]; then
        echo "true"
    else
        echo "false"
    fi
}


if [ -f /etc/redhat-release ]; then
    pam_file="/etc/pam.d/system-auth"
    pwquality_file="/etc/security/pwquality.conf"

    valid_pam=$(check_pattern "$pam_file")
    valid_pwquality=$(check_pattern "$pwquality_file")
    if !([ "$valid_pam" = "true" ] || [ "$valid_pwquality" = "true" ]); then
        echo "PAM 설정 또는 패스워드 정책이 존재하지 않습니다."
        result=$((result+1))
    fi
fi

login_defs="/etc/login.defs"

if [ -f "$login_defs" ]; then
    min_len=$(grep -E "^PASS_MIN_LEN" "$login_defs" | awk '{print $2}')
    
    if [ -n "$min_len" ]; then
        if ! [ "$min_len" -ge 8 ]; then
            echo "패스워드 최소 길이가 $min_len 자리로 설정되어 있습니다. (최소 요구 값: 8)"
            result=$((result + 1))
        fi
    else
        echo "$login_defs 파일에서 PASS_MIN_LEN 설정을 찾을 수 없습니다."
        result=$((result + 1))
    fi
else
    echo "$login_defs 파일이 존재하지 않습니다."
    result=$((result + 1))
fi

echo "점검 결과: $result"