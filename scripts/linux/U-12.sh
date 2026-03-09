#!/bin/bash

result=0

file_info=$(ls -l /etc/services 2> /dev/null)
permissions=$(echo "$file_info" | awk '{print $1}')
owner=$(echo "$file_info" | awk '{print $3}')

octal_permissions=$(stat -c "%a" /etc/services 2> /dev/null)

	# /etc/services 파일 및 소유자 권한확인
if [ "$owner" != "root" ] && [ "$owner" != "bin" ] && [ "$owner" != "sys" ]; then
    echo "/etc/services 파일의 소유자가 $owner 입니다."
    result=$((result+1))
fi

if [ "$octal_permissions" -gt 644 ]; then
    echo "/etc/services 파일의 권한이 $octal_permissions 입니다."
    result=$((result+1))
fi

echo "점검 결과: $result"