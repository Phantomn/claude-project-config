#!/bin/bash

result=0
passwd_file="/etc/passwd"

	# 사용자 홈 디렉터리 내 설정파일이 비인가자에 의한 변조 가능한지 확인
while IFS=: read -r username password uid gid info home shell; do
    if [ -d "$home" ]; then
        owner=$(stat -c "%U" "$home")
        if [ "$owner" != "$username" ]; then
            echo "$username 의 홈 디렉터리($home)의 소유자가 $owner 입니다."
            result=$((result + 1))
        fi
        
        permissions=$(stat -c "%a" "$home")
        if [ "$permissions" -ne 700 ] && [ "$permissions" -ne 755 ]; then
            echo "$username 의 홈 디렉터리($home)의 권한이 부적절합니다."
            result=$((result + 1))
        fi
	fi
done < "$passwd_file"

echo "점검 결과: $result"