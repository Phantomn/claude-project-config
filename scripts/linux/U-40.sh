#!/bin/bash

result=0

apache_conf="/etc/httpd/conf/httpd.conf"

	# 파일 업로드 및 다운로드의 사이즈 제한여부 확인
limit_value=$(grep -i "LimitRequestBody" "$apache_conf" 2> /dev/null | awk '{print $2}')

if [ -z "$limit_value" ]; then
    echo "LimitRequestBody 설정이 없습니다."
    result=$((result+1))
elif [ "$limit_value" -gt 5000000 ]; then
    echo "LimitRequestBody 값이 5MB를 초과합니다. (현재 값: $limit_value)"
    result=$((result+1))
fi

echo "점검 결과: $result"