#!/bin/bash

result=0
passwd_file="/etc/passwd"

	# 사용자 계정과 홈 디렉터리의 일치 여부 확인
while IFS=: read -r username password uid gid info home shell; do
    if [ "$uid" -ge 0 ]; then
        if ! [ -d "$home" ]; then
            echo "$username 의 홈 디렉터리($home)가 존재하지 않습니다."
            result=$((result + 1))
        fi
    fi
done < "$passwd_file"

echo "점검 결과: $result"