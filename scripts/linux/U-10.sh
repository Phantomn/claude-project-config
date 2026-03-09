#!/bin/bash

result=0

	#/etc/inetd.conf 파일 및 소유자 권한확인
check_file() {
    local file=$1
    file_info=$(ls -l "$file" 2> /dev/null)

    if [ -n "$file_info" ]; then

        permissions=$(echo "$file_info" | awk '{print $1}')
        owner=$(echo "$file_info" | awk '{print $3}')

        if [ "$permission" != "-rw-------" ]; then
            echo "$file 파일의 권한이 $permission 입니다."
            result=$((result+1))
        fi

        if [ "$owner" != "root" ]; then
            echo "$file 파일의 소유자가 $owner 입니다."
            result=$((result+1))
        fi
    fi
}

check_file "/etc/xinetd.conf"
check_file "/etc/inetd.conf"

echo "점검 결과: $result"