#!/bin/bash

result=0

	# HOME/.rhosts, hosts.equiv 사용여부 확인
if [ -f /etc/hosts.equiv ]; then
    owner=$(ls -ld /etc/hosts.equiv 2> /dev/null | awk '{print $3}')
    if [ "$owner" != "root" ]; then
        echo "/etc/hosts.equiv 파일의 소유자가 $owner 입니다."
        result=$((result+1))
    fi

    permission=$(stat -c "%a" /etc/hosts.equiv 2> /dev/null)
    if [ "$permission" -ne 600 ]; then
        echo "/etc/hosts.equiv 파일의 권한이 $permission 입니다."
        result=$((result+1))
    fi
fi

for user in $(cut -d: -f1 /etc/passwd); do
    home_dir=$(eval echo ~$user 2> /dev/null)
    rhosts_file="$home_dir/.rhosts"
    
    if [ -f "$rhosts_file" ]; then
        owner=$(ls -ld "$rhosts_file" 2> /dev/null | awk '{print $3}')
        if [ "$owner" != "root" ]; then
            echo "$rhosts_file 파일의 소유자가 $owner 입니다."
            result=$((result+1))
        fi

        permission=$(stat -c "%a" "$rhosts_file" 2> /dev/null)
        if [ "$permission" -ne 600 ]; then
            echo "$rhosts_file 파일의 권한이 $permission 입니다."
            result=$((result+1))
        fi
    fi
done

echo "점검 결과: $result"