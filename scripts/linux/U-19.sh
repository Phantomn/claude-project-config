#!/bin/bash

result=0

    # finger 서비스 활성화 여부 확인
if [[ "$(uname -s)" =~ "SunOS" && "$(uname -r)" =~ ^5\.([1-9][0-9]|10)$ ]]; then
    if inetadm | grep "finger" | grep "online" > /dev/null 2>&1; then
        echo "finger 서비스가 활성화되어 있습니다."
        result=$((result+1))
    fi

    echo "점검 결과: $result"
    exit 1
fi


if systemctl is-active finger.service > /dev/null 2>&1 || systemctl is-active fingerd.service > /dev/null 2>&1; then
    echo "Finger 서비스가 활성화되어 있습니다." > /dev/null 2>&1
    result=$((result+1))
fi

if [ -f /etc/xinetd.d/finger ]; then
    if grep -q "disable.*no" /etc/xinetd.d/finger; then
        echo "Finger 서비스가 xinetd를 통해 활성화되어 있습니다." > /dev/null 2>&1
        result=$((result+1))
    fi
fi

if [ -f /etc/inetd.conf ]; then
    if grep -q "finger" /etc/inetd.conf | grep -qv "^#"; then
        result=$((result+1))
    fi
fi

echo "점검 결과: $result"