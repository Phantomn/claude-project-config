#!/bin/bash

result=0

	#BIND 최신여부 및 패치여부 확인
if ps -ef | grep -q "[n]amed"; then
    echo "DNS 서비스(BIND)가 실행 중입니다." > /dev/null 2>&1
    result=$((result+1))

    bind_version=$(named -v 2> /dev/null)
    if [ -n "$bind_version" ]; then
        echo "BIND 버전: $bind_version" > /dev/null 2>&1
    fi
fi

echo "점검 결과: $result"