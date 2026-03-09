#!/bin/bash

result=0

	# 취약한 버전의 Sendmail 서비스 확인
if ps -ef | grep -q "[s]endmail"; then
    echo "Sendmail 서비스가 실행 중입니다." 
    result=$((result+1))
fi

sendmail_version=$( (echo "QUIT"; sleep 1) | telnet localhost 25 2> /dev/null | grep -i "sendmail" )
if [ -n "$sendmail_version" ]; then
    echo "Sendmail 버전: $sendmail_version" 
fi

echo "점검 결과: $result"