#!/bin/bash

result=0
apache_conf="/etc/httpd/conf/httpd.conf" 

	# 디렉터리 검색 기능의 활성화 여부 확인
if grep -q "Options.*Indexes" "$apache_conf" 2> /dev/null; then
    echo "Apache 설정 파일에서 Indexes 옵션이 사용 중입니다."
    result=$((result+1))
fi 

echo "점검 결과: $result"