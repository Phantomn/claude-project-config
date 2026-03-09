#!/bin/bash

result=0

	# Secondary Name Server로만 Zone 정보 전송 제한 여부 확인
if ps -ef | grep -q "[n]amed"; then
    if ! grep -q 'allow-transfer' /etc/named.conf 2> /dev/null; then
        echo "/etc/named.conf 파일에서 allow-transfer 설정이 없습니다."
        result=$((result+1))
    fi

    if [ -f "/etc/named.boot" ]; then
        if ! grep -q 'xfrnets' /etc/named.boot 2> /dev/null; then
            echo "/etc/named.boot 파일에서 xfrnets 설정이 없습니다."
            result=$((result+1))
        fi
    fi
fi

echo "점검 결과: $result"