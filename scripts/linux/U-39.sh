#!/bin/bash

result=0

apache_conf="/etc/httpd/conf/httpd.conf"  

	# 무분별한 심볼릭 링크, aliases 사용제한여부 확인
if grep -q "Options.*FollowSymLinks" "$apache_conf" 2> /dev/null || \
   grep -q "Options FollowSymLinks" "$apache_conf" 2> /dev/null || \
   grep -q "Options Indexes FollowSymLinks" "$apache_conf" 2> /dev/null; then
    echo "FollowSymLinks 옵션이 설정되어 있습니다."
    result=$((result+1))
fi


echo "점검 결과: $result"