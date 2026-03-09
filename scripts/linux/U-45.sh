#!/bin/bash

result=0

	# 시스템 정책에 패스워드 최소길이정책 적용여부 확인
if [[ "$(uname -s)" =~ "SunOS" ]]; then
    file="/etc/default/passwd"

    if [[ -f "$file" ]]; then
        pass_length=$(egrep "^PASSLENGTH=" /etc/default/passwd | cut -d= -f2)

        if [[ -n "$pass_length" && "$pass_length" -lt 8 ]]; then
            echo "패스워드 최소 길이가 8자 미만으로 설정되어 있습니다. (현재: $pass_length)"
            result=$((result + 1))
        fi
    else
        echo "패스워드 설정 파일이 존재하지 않습니다. ($file)"
    fi

    echo "점검 결과: $result"
    exit 1
fi


min_len=$(grep -E '^PASS_MIN_LEN' /etc/login.defs | awk '{print $2}')

if [ -z "$min_len" ]; then
    echo "'PASS_MIN_LEN' 설정이 /etc/login.defs 파일에서 누락되었습니다." 
    result=$((result + 1))
elif [ "$min_len" -lt 8 ]; then
    echo "'PASS_MIN_LEN' 설정이 $min_len 입니다. 최소 8자 이상이어야 합니다."
    result=$((result + 1))
fi

echo "점검 결과: $result"