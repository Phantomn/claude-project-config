#!/bin/bash

result=0

apache_home="/etc/httpd"  

	# Apache 설치 시 기본으로 생성되는 불필요한 파일의 삭제여부 확인
if [ -d "$apache_home/htdocs/manual" ]; then
    echo "불필요한 디렉터리: $apache_home/htdocs/manual이 존재합니다."
    result=$((result+1))
fi

if [ -d "$apache_home/manual" ]; then
    echo "불필요한 디렉터리: $apache_home/manual이 존재합니다."
    result=$((result+1))
fi

echo "점검 결과: $result"