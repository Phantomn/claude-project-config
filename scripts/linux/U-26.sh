#!/bin/bash

result=0

	# automount 서비스 확인
if [[ "$(uname -s)" =~ "SunOS" ]]; then

    if [[ "$(uname -r)" =~ ^5\.[1-9][0-9]$ || "$(uname -r)" =~ ^5\.10$ ]]; then
        # Solaris 5.10 이상: svcs로 automount 서비스 확인
        if svcs -a | grep "autofs" | grep "online" > /dev/null 2>&1; then
            echo "경고: automountd 서비스(autofs)가 활성화되어 있습니다."
            result=$((result+1))
        fi
    fi
    echo "점검 결과: $result"
    exit 1
fi


if systemctl is-active autofs > /dev/null 2>&1; then
    echo "automount 서비스(autofs)가 활성화되어 있습니다." > /dev/null 2>&1
    result=$((result+1))
fi

if service autofs status > /dev/null 2>&1; then
    if service autofs status | grep -q "running"; then
        echo "automount 서비스가 활성화되어 있습니다." > /dev/null 2>&1
        result=$((result+1))
    fi
fi

echo "점검 결과: $result"