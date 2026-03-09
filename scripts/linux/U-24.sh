#!/bin/bash

result=0

	# inetadm을 사용하여 NFS 관련 서비스 점검
if [[ "$(uname -s)" =~ "SunOS" ]]; then

    if [[ "$(uname -r)" =~ ^5\.[1-9][0-9]$ || "$(uname -r)" =~ ^5\.10$ ]]; then
        # Solaris 5.10 이상: inetadm을 사용하여 NFS 관련 서비스 점검
        if inetadm | egrep "nfs|statd|lockd" | grep "online" > /dev/null 2>&1; then
            echo "불필요한 NFS 관련 서비스(nfs, statd, lockd)가 활성화되어 있습니다."
            result=$((result+1))
        fi
    fi

    echo "점검 결과: $result"
    exit 1
fi


if ps -ef | egrep "nfs|statd|lockd" | egrep -v "grep" > /dev/null 2>&1; then
    echo "NFS 관련 서비스가 실행 중입니다."
    result=$((result+1))
fi

echo "점검 결과: $result"