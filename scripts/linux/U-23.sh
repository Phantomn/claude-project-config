#!/bin/bash

result=0

if [[ "$(uname -s)" =~ "SunOS" ]]; then

    # DoS 공격에 취약한 서비스 확인
    vulnerable_services=("echo" "discard" "daytime" "chargen")

    for service in "${vulnerable_services[@]}"; do
        if svcs -a | grep "$service" | grep "online" > /dev/null 2>&1; then
            echo "$service 서비스가 활성화되어 있습니다."
            result=$((result+1))
        fi
    done

    echo "점검 결과: $result"
    exit 1
fi


services="echo discard daytime chargen"

for service in $services; do
    service_file="/etc/xinetd.d/$service"
    
    if [ -f "$service_file" ]; then
        if grep -q "disable.*= no" "$service_file" 2> /dev/null; then
            echo "$service 서비스가 활성화 상태입니다."
            result=$((result+1))
        fi
    fi
done

echo "점검 결과: $result"