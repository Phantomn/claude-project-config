#!/bin/bash

result=0  
file_info=$(ls -l /etc/syslog.conf 2> /dev/null)

	# /etc/syslog.conf 파일 및 소유자 권한확인
if [ -n "$file_info" ]; then
    permissions=$(echo "$file_info" | awk '{print $1}')
    owner=$(echo "$file_info" | awk '{print $3}')
    
    octal_permissions=$(stat -c "%a" /etc/syslog.conf 2> /dev/null)
    
    if [ -n "$octal_permissions" ]; then
        if [ "$owner" != "root" ] && [ "$owner" != "bin" ] && [ "$owner" != "sys" ]; then
            echo "/etc/syslog.conf 파일의 소유자가 $owner 입니다."
            result=$((result+1))
        fi

        if [ "$octal_permissions" -gt 644 ]; then
            echo "/etc/syslog.conf 파일의 권한이 $octal_permissions 입니다."
            result=$((result+1))
        fi
    fi
fi 

echo "점검 결과: $result"
