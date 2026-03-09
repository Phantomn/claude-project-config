#!/bin/bash

result=0
httpd_conf="/etc/apache2/conf/httpd.conf" 

	# 웹페이지에서 오류 발생 시 출력되는 메시지 내용 확인
if [ -f "$httpd_conf" ]; then
    if ! egrep "^ServerTokens\s+Prod" "$httpd_conf"; then
        echo "ServerTokens 지시자가 'Prod'로 설정되어 있지 않습니다."
        result=$((result + 1))
    fi

    if ! egrep "^ServerSignature\s+off" "$httpd_conf"; then
        echo "ServerSignature 지시자가 'off'로 설정되어 있지 않습니다."
        result=$((result + 1))
    fi
fi

echo "점검 결과: $result"