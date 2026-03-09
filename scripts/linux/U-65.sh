#!/bin/bash

result=0

if [[ "$(uname -s)" =~ "SunOS" ]]; then
    # SNMP 서비스 실행 여부 확인
    if ps -ef | grep snmp | grep -v "grep" > /dev/null || svcs -a | grep snmp > /dev/null 2>&1; then
        echo "SNMP 서비스가 활성화되어 있습니다."
        result=$((result + 1))
    fi

    echo "점검 결과: $result"
    exit 1
fi


if ps -ef | grep -q "[s]nmp"; then
    echo "SNMP 서비스가 동작 중입니다."
    result=$((result + 1))
fi

echo "점검 결과: $result"