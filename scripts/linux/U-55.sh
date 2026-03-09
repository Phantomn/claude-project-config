#!/bin/bash

result=0
files="/etc/profile /etc/bashrc /etc/login.defs"

	# 시스템 UMASK 값이 022 이상인지 확인
for file in $files; do
    if [ -f "$file" ]; then
        umask_value=$(egrep "^UMASK" "$file" | awk '{print $2}')
        
        if [ -z "$umask_value" ]; then
            echo "$file 파일에 UMASK 설정이 없습니다." 
            result=$((result + 1))
        elif [ "$umask_value" -lt 22 ]; then
            echo "$file 파일의 UMASK 값이 022 미만입니다. 현재 값: $umask_value"
            result=$((result + 1))
        fi
    fi
done

echo "점검 결과: $result"
