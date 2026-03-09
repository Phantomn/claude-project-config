#!/bin/bash

result=0
apache_conf="/etc/httpd/conf/httpd.conf"

	# Apache 데몬 root 권한 구동여부 확인
user=$(grep -i "^User" "$apache_conf" 2> /dev/null | awk '{print $2}')
if [ "$user" = "root" ]; then
    echo "Apache 데몬이 root 사용자로 구동되고 있습니다."
    result=$((result+1))
fi

group=$(grep -i "^Group" "$apache_conf" 2> /dev/null | awk '{print $2}')
if [ "$group" = "root" ]; then
    echo "Apache 데몬이 root 그룹으로 구동되고 있습니다."
    result=$((result+1))
fi

echo "점검 결과: $result"