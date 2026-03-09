#!/bin/bash

result=0

apache_conf="/etc/httpd/conf/httpd.conf"  

	# 상위 경로로 이동이 가능한지 여부 확인
if grep -q -i "AllowOverride None" "$apache_conf" 2> /dev/null; then
    echo "AllowOverride 지시자가 None으로 설정되어 있습니다."
    result=$((result+1))
fi

echo "점검 결과: $result"