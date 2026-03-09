#!/bin/bash

result=0

	# 불필요한 TFTP, Talk, NTalk 서비스 확인
if [[ "$(uname -s)" =~ "SunOS" ]]; then
    result=0

    if [[ "$(uname -r)" =~ ^5\.[1-9][0-9]$ || "$(uname -r)" =~ ^5\.10$ ]]; then
        # Solaris 5.10 이상: 불필요한 TFTP, Talk, NTalk 서비스가 활성화되었는지 확인
        if inetadm | egrep "tftp|talk|ntalk" | egrep "enabled" > /dev/null 2>&1; then
            echo "불필요한 서비스(tftp, talk, ntalk)가 활성화되어 있습니다."
            result=$((result+1))
        fi
    fi

    echo "점검 결과: $result"
    exit 1
fi


services="tftp talk ntalk"

if [[ "$(uname -s)" =~ "SunOS" ]]; then
    GREP="/usr/xpg4/bin/grep"
else
    GREP="/usr/bin/grep"
fi

for service in $services; do
    service_file="/etc/xinetd.d/$service"
    
    if [ -f "$service_file" ]; then
        if $GREP -q "disable.*= no" "$service_file" 2> /dev/null; then
            echo "$service 서비스가 활성화되어 있습니다. (disable = yes가 아님)"
            result=$((result+1))
        fi
    fi
done

if [ -f /etc/inetd.conf ]; then
    if $GREP -E "tftp|talk|ntalk" /etc/inetd.conf | $GREP -qv "^#"; then
        echo "inetd.conf에서 tftp, talk 또는 ntalk 서비스가 활성화되어 있습니다."
        result=$((result+1))
    fi
fi



echo "점검 결과: $result"