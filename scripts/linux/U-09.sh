#!/bin/bash

result=0

file_info=$(ls -l /etc/hosts 2> /dev/null)
permission=$(echo "$file_info" | awk '{print $1}')
owner=$(echo "$file_info" | awk '{print $3}')

	# /etc/hosts 파일의 소유자 및 권한 확인
if [ "$permission" != "-rw-------" ]; then
    echo "/etc/hosts 파일의 권한이 $permission 입니다."
    result=$((result+1))
fi

if [ "$owner" != "root" ]; then
    echo "/etc/hosts 파일의 소유자가 $owner 입니다."
    result=$((result+1))
fi

echo "점검 결과: $result"